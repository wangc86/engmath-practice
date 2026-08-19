// pytest 用來驅動 node 的執行器（PLAN.md §8.4「沒有 npm，JS 測試怎麼跑」方案 B）。
//
// 用法：
//     node scripts/run_dsp_case.mjs '{"case": "aliasFrequency", "args": {...}}'
//
// 它把結果以 JSON 印到 stdout，由 `tests/test_dsp_js.py` 讀進去、與**同一支
// 測試裡用 SymPy／閉合式現算的參考值**比對。選這個做法而不是 `node --test`
// 的理由寫在 §8.4：**pytest 仍是唯一的測試入口**——單人維護的專案裡，
// 一個沒有人記得跑的第二套測試會慢慢變紅然後被跳過。
//
// ⚠️ 這個檔案本身**不做任何斷言、也不放任何參考值**。它只負責「把被測的
// 那三層純函式跑起來，把數字吐出來」。參考值一律留在 Python 那一側，
// 否則兩條路徑會在這裡合流，交叉驗證就不成立了。

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import {
  traceSine, sampleTimes, sineAt, zeroOrderHold, viewWindowSeconds, clamp,
} from '../app/static/demos/lib/signal.js';
import {
  nyquist, aliasFrequency, signedAliasFrequency, isAliased, aliasSign,
} from '../app/static/demos/lib/transform.js';
import {
  makeScale, curvePoints, staircasePoints,
} from '../app/static/demos/lib/draw.js';

const here = dirname(fileURLToPath(import.meta.url));

const toArray = (typed) => Array.from(typed);

/**
 * 把 worklet 檔案載進來。
 *
 * worklet 不是 ES module（Safari 對 worklet 裡的 import 支援不一致，
 * 所以那個檔案刻意寫成不 import 任何東西的普通腳本），因此這裡用
 * `new Function` 注入 AudioWorkletGlobalScope 的那三個全域，
 * 把 registerProcessor 攔下來拿到 class 本身。
 *
 * 這樣做的目的只有一個：讓「worklet 裡那份 ZOH 迴圈」與
 * 「signal.js 裡那份」可以被逐格比對。那兩份的重複是刻意的，
 * 而重複該付的代價就是一項盯著它們的測試。
 */
function loadWorkletProcessor(deviceRate) {
  const source = readFileSync(
    join(here, '..', 'app', 'static', 'demos', 'worklets', 'sampler-processor.js'),
    'utf8',
  );
  let registered = null;
  const register = (name, ctor) => { registered = { name, ctor }; };
  class AudioWorkletProcessorStub {}
  const run = new Function(
    'AudioWorkletProcessor', 'registerProcessor', 'sampleRate', source,
  );
  run(AudioWorkletProcessorStub, register, deviceRate);
  if (!registered) throw new Error('the worklet did not call registerProcessor');
  return registered;
}

const CASES = {
  /** 有號與無號的混疊頻率、奈奎斯特、是否混疊。 */
  aliasFrequency({ pairs }) {
    return pairs.map(([f, fs]) => ({
      f, fs,
      nyquist: nyquist(fs),
      signed: signedAliasFrequency(f, fs),
      apparent: aliasFrequency(f, fs),
      aliased: isAliased(f, fs),
      sign: aliasSign(f, fs),
    }));
  },

  /**
   * 這個展示的數學核心：以 fs 取樣頻率 f 的正弦，與取樣「有號混疊頻率」的
   * 正弦，取樣點必須**完全相同**。畫面上那條重建曲線的正當性就是這一條。
   */
  aliasSamplesMatch({ f, fs, count }) {
    const original = [];
    const reconstructed = [];
    const signed = signedAliasFrequency(f, fs);
    for (let n = 0; n < count; n += 1) {
      const t = n / fs;
      original.push(sineAt(f, t));
      reconstructed.push(sineAt(signed, t));
    }
    return { signed, original, reconstructed };
  },

  /** signal.js 的取樣時刻：落在取樣網格上、在視窗內、等距。 */
  sampleTimes({ fs, t0, duration }) {
    return toArray(sampleTimes(fs, t0, duration));
  },

  /** 零階保持（純函式版）。 */
  zeroOrderHold({ input, ctxRate, fs }) {
    const { output, acc, held } = zeroOrderHold(
      Float64Array.from(input), ctxRate, fs,
    );
    return { output: toArray(output), acc, held };
  },

  /** worklet 裡那份 ZOH，與上面那份比對用。 */
  workletZeroOrderHold({ input, ctxRate, fs }) {
    const { name, ctor } = loadWorkletProcessor(ctxRate);
    const processor = new ctor();
    const output = new Float32Array(input.length);
    const params = { samplingRate: [fs] };
    processor.process([[Float32Array.from(input)]], [[output]], params);
    return { name, output: toArray(output) };
  },

  /** worklet 在沒有輸入時必須輸出靜音，而不是上一個保持值。 */
  workletSilenceWithoutInput({ blockSize, ctxRate, fs }) {
    const { ctor } = loadWorkletProcessor(ctxRate);
    const processor = new ctor();
    const primed = new Float32Array(blockSize).fill(0.5);
    const first = new Float32Array(blockSize);
    processor.process([[primed]], [[first]], { samplingRate: [fs] });
    const second = new Float32Array(blockSize);
    processor.process([[]], [[second]], { samplingRate: [fs] });
    return { first: toArray(first), second: toArray(second) };
  },

  /** 畫面時間窗。 */
  viewWindow({ pairs }) {
    return pairs.map(([f, fs]) => ({
      f, fs, seconds: viewWindowSeconds(f, fs), alias: aliasFrequency(f, fs),
    }));
  },

  /** 繪製層的幾何：座標轉換與路徑（§8.4「斷言資料，不斷言像素」）。 */
  geometry({ t0, t1, vMin, vMax, width, height, pad, times, values }) {
    const scale = makeScale({ t0, t1, vMin, vMax, width, height, pad });
    const curve = curvePoints(scale, times, values);
    const stairs = staircasePoints(scale, times, values, t1);
    return {
      curve,
      stairs,
      zeroY: scale.y(0),
      topY: scale.y(vMax),
      bottomY: scale.y(vMin),
      leftX: scale.x(t0),
      rightX: scale.x(t1),
      roundTrip: scale.timeAt(scale.x((t0 + t1) / 2)),
    };
  },

  /** clamp 與 traceSine 的基本性質。 */
  trace({ f, t0, duration, count }) {
    const { times, values } = traceSine(f, t0, duration, count);
    return { times: toArray(times), values: toArray(values), clampCheck: clamp(5, 1, 3) };
  },
};

function main() {
  const raw = process.argv[2];
  if (!raw) throw new Error('missing case JSON argument');
  const request = JSON.parse(raw);
  const runner = CASES[request.case];
  if (!runner) throw new Error(`unknown case: ${request.case}`);
  process.stdout.write(JSON.stringify(runner(request.args || {})));
}

main();
