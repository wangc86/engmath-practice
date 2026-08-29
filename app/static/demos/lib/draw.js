// 繪製層（PLAN.md §8.2.3 第三段）。
//
// 吃 canvas + 資料 + 選項；**不算任何東西、不讀任何控制項**。
//
// 這個檔案分成兩半，分界是刻意的：
//
//   * 上半是**座標換算與路徑生成**，純函式、沒有副作用，因此可以在 node 裡
//     被測試（§8.4：「繪製層斷言資料，不斷言像素」——被斷言的就是這半邊
//     吐出來的那組座標）。
//   * 下半是真正對 CanvasRenderingContext2D 下指令的部分，測不到，
//     所以它必須**薄到用眼睛就能檢查**：每個函式只做 stroke/fill，不做計算。
//
// ⛔ 模組載入時不得碰 `document` 或 `window`（否則 node 會直接爆），
//    要用到的地方一律由呼叫端把 canvas 傳進來。

// ---------------------------------------------------------------- 純函式半邊

/**
 * 建立一個線性座標轉換：資料座標 (t, v) → 畫布像素 (x, y)。
 *
 * y 軸是**翻轉**的（資料值越大 → 像素 y 越小），這是 canvas 的慣例，
 * 也是這一層最容易寫反、而且寫反了圖還是「看起來像個波形」的地方——
 * 所以測試裡有一項專門盯著它。
 */
export function makeScale({ t0, t1, vMin, vMax, width, height, pad }) {
  const spanT = t1 - t0 || 1;
  const spanV = vMax - vMin || 1;
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  return {
    width, height, pad, t0, t1, vMin, vMax,
    x(t) { return pad.left + ((t - t0) / spanT) * innerW; },
    y(v) { return pad.top + (1 - (v - vMin) / spanV) * innerH; },
    /** 反向：像素 x → 時間，供日後的游標讀值用。 */
    timeAt(x) { return t0 + ((x - pad.left) / innerW) * spanT; },
  };
}

/** 把 (times, values) 轉成一串 {x, y} 像素座標。 */
export function curvePoints(scale, times, values) {
  const n = Math.min(times.length, values.length);
  const points = new Array(n);
  for (let i = 0; i < n; i += 1) {
    points[i] = { x: scale.x(times[i]), y: scale.y(values[i]) };
  }
  return points;
}

/**
 * 零階保持的階梯路徑：每個取樣點先水平走到下一個取樣時刻，再垂直跳。
 * 回傳的一樣是 {x, y} 陣列，可以直接餵給 strokePolyline。
 */
export function staircasePoints(scale, times, values, tEnd) {
  const points = [];
  const n = Math.min(times.length, values.length);
  for (let i = 0; i < n; i += 1) {
    const y = scale.y(values[i]);
    const nextT = i + 1 < n ? times[i + 1] : tEnd;
    points.push({ x: scale.x(times[i]), y });
    points.push({ x: scale.x(nextT), y });
  }
  return points;
}

/**
 * Canvas 的 devicePixelRatio 縮放。
 *
 * D30 之後展示限定桌機，但這一支**仍然必要**——DPR 不是行動裝置專屬的東西，
 * 任何 HiDPI 螢幕（MacBook、4K 外接、Windows 的 125% 縮放）不做這件事
 * 都會得到一張糊掉的圖，而投影出來的糊圖比小螢幕上的糊圖更明顯。
 *
 * 回傳 {width, height}，單位是 CSS 像素——上面那些純函式全部用 CSS 像素，
 * 因為 ctx 已經被 setTransform 縮放過了。
 */
export function fitCanvas(canvas, dpr) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const ratio = dpr || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { width, height, ctx };
}

/**
 * 把一個 dB 值映到 [0, 1]，供色階與縱軸使用。
 *
 * 夾制是**繪圖的需要**（畫面沒有無限高），所以它住在 draw.js 而不是
 * transform.js——§8.2.3 那張表寫著「dB 下限、色階都是 draw 的事」。
 */
export function dbToUnit(db, floor, ceiling) {
  const span = ceiling - floor || 1;
  const t = (db - floor) / span;
  return t < 0 ? 0 : (t > 1 ? 1 : t);
}

// viridis 的八個錨點（取自原始色表的等距取樣）。
// **選它而不是 jet 的理由是 §8.6 第 4 點**：viridis 的亮度隨 t 單調上升，
// 因此色盲學生、黑白列印、以及投影機色偏之下都還讀得出強弱；
// jet 在綠色區有一段假的邊界，看起來像資料裡有一條線，其實沒有。
const VIRIDIS = [
  [68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142],
  [38, 130, 142], [53, 183, 121], [144, 215, 67], [253, 231, 37],
];

/**
 * viridis 色階。t ∈ [0, 1] → [r, g, b]，每個分量 0–255 的整數。
 *
 * 錨點之間線性內插。**亮度單調**這件事因此是可以證明的而不是希望的：
 * 亮度是 RGB 的線性組合，線性內插的線性組合仍是線性內插，
 * 而八個錨點的亮度本身遞增——`tests/test_dsp_js.py` 有一項斷言它。
 */
export function viridisColor(t) {
  const x = t < 0 ? 0 : (t > 1 ? 1 : t);
  const scaled = x * (VIRIDIS.length - 1);
  const i = Math.min(VIRIDIS.length - 2, Math.floor(scaled));
  const frac = scaled - i;
  const a = VIRIDIS[i];
  const b = VIRIDIS[i + 1];
  return [
    Math.round(a[0] + (b[0] - a[0]) * frac),
    Math.round(a[1] + (b[1] - a[1]) * frac),
    Math.round(a[2] + (b[2] - a[2]) * frac),
  ];
}

/** 相對亮度（sRGB 的加權和）。色階單調性的測試用它。 */
export function relativeLuminance([r, g, b]) {
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * 頻率軸的刻度位置：1、2、5 × 10^n 這一組。
 *
 * 回傳落在 [0, fMax] 內的刻度值。刻度不是裝飾——沒有刻度的頻譜圖，
 * 學生讀不出「那根峰在哪裡」，而讀出峰的位置正是這一頁的目的。
 */
export function niceTicks(fMax, target = 6) {
  if (!(fMax > 0)) return [0];
  const rough = fMax / target;
  const power = 10 ** Math.floor(Math.log10(rough));
  const candidates = [1, 2, 5, 10].map((m) => m * power);
  let step = candidates[candidates.length - 1];
  for (const c of candidates) {
    if (c >= rough) { step = c; break; }
  }
  const ticks = [];
  for (let v = 0; v <= fMax + step * 1e-9; v += step) ticks.push(v);
  return ticks;
}

/**
 * 把一條長度 n 的資料壓成長度 count，**每一段取最大值**。
 *
 * 頻譜圖的高度只有一百多像素，而一次 FFT 可能吐出四千多格——不壓縮的話
 * 每推一欄就要下四千次繪圖指令，而且畫面上根本分辨不出來。
 *
 * **取最大值而不是取平均**是有理由的：平均會把一根又細又高的譜線
 * （純音、口哨）稀釋成一片淡色，而那根線正是要看的東西。
 * 最大值保證「有峰就看得見」，代價是雜訊看起來比實際亮一點——
 * 這個方向的誤差在教學上是無害的。
 */
export function resampleMax(values, count) {
  const out = new Float64Array(count);
  const n = values.length;
  if (n === 0 || count === 0) return out;
  for (let i = 0; i < count; i += 1) {
    const start = Math.floor((i * n) / count);
    const end = Math.max(start + 1, Math.floor(((i + 1) * n) / count));
    let best = -Infinity;
    for (let k = start; k < end && k < n; k += 1) {
      if (values[k] > best) best = values[k];
    }
    out[i] = best;
  }
  return out;
}

/**
 * 長條圖的矩形（2S5：Fourier 係數的頻域檢視）。
 *
 * 為什麼是長條而不是折線：Fourier 級數的頻譜是**離散**的，只有 n = 1, 2, 3…
 * 上有值，中間什麼都沒有。用折線畫會在諧波之間補出一條斜線，
 * 讀起來像「1.5 次諧波有一點點」——而方波沒有第 2 次諧波這件事
 * 正是這一頁要學生看見的。長條圖說的是實話，折線不是。
 *
 * 回傳的矩形以**資料座標**算出、以像素表示，因此測試可以斷言幾何不變量
 * （在畫布內、不重疊、高度與值成正比、值為 0 的高度就是 0）而不必碰像素。
 *
 * @param {object} scale        `makeScale` 的結果，t 軸是諧波次數
 * @param {ArrayLike<number>} values  第 firstIndex 次起的各次振幅
 * @param {{firstIndex?: number, fill?: number}} [options]
 *        `fill` 是長條佔一格的比例；留白是刻意的，否則相鄰兩根會黏成一片。
 */
export function barRects(scale, values, { firstIndex = 1, fill = 0.62 } = {}) {
  const baseY = scale.y(scale.vMin);
  const step = Math.abs(scale.x(firstIndex + 1) - scale.x(firstIndex));
  const width = Math.max(1, step * fill);
  const rects = [];
  for (let i = 0; i < values.length; i += 1) {
    const index = firstIndex + i;
    const top = scale.y(values[i]);
    rects.push({
      index,
      value: values[i],
      x: scale.x(index) - width / 2,
      y: Math.min(top, baseY),
      width,
      height: Math.abs(baseY - top),
    });
  }
  return rects;
}

/**
 * 一段沿著 t 軸的直立區塊（2S10：摺積的「重疊區間」那片陰影）。
 *
 * 摺積求和的上下限 k ∈ [max(0, n−M+1), min(n, N−1)] 是課本上最勸退的一行，
 * 而它其實只是「兩個支撐區間的交集」。畫成一片陰影之後那件事是看得見的，
 * 而且**陰影的寬度隨著滑桿變化的方式本身就是那條公式**。
 *
 * ⚠️ 沒有重疊時（`tTo < tFrom`）回傳 `width: 0` 而不是負寬度或 null。
 * 動畫會掃過兩端，那裡本來就沒有重疊——回傳 0 讓繪製端不必寫特例，
 * 而測試可以直接斷言「n 在範圍外時寬度是 0」。
 */
export function regionRect(scale, tFrom, tTo) {
  const top = scale.pad.top;
  const bottom = scale.height - scale.pad.bottom;
  if (!(tTo >= tFrom)) {
    return { x: scale.x(tFrom), y: top, width: 0, height: bottom - top };
  }
  const x0 = scale.x(tFrom);
  const x1 = scale.x(tTo);
  return { x: Math.min(x0, x1), y: top, width: Math.abs(x1 - x0), height: bottom - top };
}

/**
 * 把一串點在「跳得太遠」的地方切開，回傳一組線段（2S11：相位圖）。
 *
 * 相位畫在 (−π, π] 上，所以一條連續的相位斜坡在圖上是一排鋸齒——
 * 每次繞過 ±π 就跳一次。**用一條 polyline 畫的話，那些跳會變成一條
 * 幾乎垂直的線**，看起來像相位在那裡瞬間掃過整個範圍，
 * 而學生要看的斜率就被那些假的直線蓋掉了。
 *
 * ⚠️ 切開的判準是**像素上的落差**而不是資料上的落差，因為呼叫端要的是
 * 「畫出來不好看的那些」。門檻由呼叫端給（通常是 π 對應的像素高度），
 * 所以這一層仍然不知道自己畫的是相位還是別的東西。
 *
 * ⚠️ **長度 1 的段也要回傳，不得順手丟掉。** 第一版丟掉了它們，理由是
 * 「一個點畫不出線」——那句話是對的（`strokePolyline` 對單點只會 moveTo
 * 然後 stroke，什麼都不畫），但丟掉會讓這支函式失去一個很有用的性質：
 * **回傳的那些段是輸入的一個分割**。有了那個性質，測試可以斷言
 * 「點一個都沒有少」；沒有它，就只能斷言「段數看起來合理」，
 * 而一個把資料吃掉一半的實作照樣會通過。
 */
export function splitOnJumps(points, maxRise) {
  const segments = [];
  let current = [];
  for (let i = 0; i < points.length; i += 1) {
    if (i > 0 && Math.abs(points[i].y - points[i - 1].y) > maxRise) {
      if (current.length > 0) segments.push(current);
      current = [];
    }
    current.push(points[i]);
  }
  if (current.length > 0) segments.push(current);
  return segments;
}

// ------------------------------------------------------------ canvas 指令半邊

export function clear(ctx, width, height) {
  ctx.clearRect(0, 0, width, height);
}

/** 水平的零線 + 左右框線。刻意極簡：這張圖要看的是波形，不是格線。 */
export function strokeAxes(ctx, scale, style) {
  const zeroY = scale.y(0);
  ctx.save();
  ctx.strokeStyle = style.axis;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(scale.pad.left, zeroY);
  ctx.lineTo(scale.width - scale.pad.right, zeroY);
  ctx.stroke();
  ctx.restore();
}

export function strokePolyline(ctx, points, { color, width = 2, dash = [] }) {
  if (points.length === 0) return;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  ctx.lineJoin = 'round';
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i += 1) ctx.lineTo(points[i].x, points[i].y);
  ctx.stroke();
  ctx.restore();
}

/**
 * 底部座標軸 + 刻度 + 標籤。
 *
 * 標籤的文字由呼叫端給（`format`），因為 draw.js 不該知道單位是 Hz 還是秒。
 */
export function strokeAxisWithTicks(ctx, scale, ticks, format, style) {
  const baseY = scale.height - scale.pad.bottom;
  ctx.save();
  ctx.strokeStyle = style.axis;
  ctx.fillStyle = style.axisText;
  ctx.lineWidth = 1;
  ctx.font = '11px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.beginPath();
  ctx.moveTo(scale.pad.left, baseY);
  ctx.lineTo(scale.width - scale.pad.right, baseY);
  ctx.stroke();
  for (const value of ticks) {
    const x = scale.x(value);
    if (x < scale.pad.left - 1 || x > scale.width - scale.pad.right + 1) continue;
    ctx.beginPath();
    ctx.moveTo(x, baseY);
    ctx.lineTo(x, baseY + 4);
    ctx.stroke();
    ctx.fillText(format(value), x, baseY + 6);
  }
  ctx.restore();
}

/** 一條水平參考線（例如奈奎斯特位置、或 dB 的某一格）。 */
export function strokeVerticalMarker(ctx, scale, value, { color, dash = [4, 4] }) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.setLineDash(dash);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(scale.x(value), scale.pad.top);
  ctx.lineTo(scale.x(value), scale.height - scale.pad.bottom);
  ctx.stroke();
  ctx.restore();
}

/** 曲線下方填色。頻譜用它比純線條好讀（峰的「面積感」就是能量感）。 */
export function fillUnderCurve(ctx, points, baseY, { color }) {
  if (points.length === 0) return;
  ctx.save();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(points[0].x, baseY);
  for (const p of points) ctx.lineTo(p.x, p.y);
  ctx.lineTo(points[points.length - 1].x, baseY);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/**
 * 捲動頻譜圖。
 *
 * 作法是 §8.5 指定的那一種：**把畫布往左平移一欄，只畫新的那一欄**，
 * 不要每格重畫整段歷史（那是 O(欄數) 的重畫，幾秒之後就開始掉格）。
 * 平移用 `drawImage(canvas, -1, 0)`——canvas 可以畫自己，這是合法且快的。
 *
 * `prefers-reduced-motion` 的處理不在這裡，在展示層：它決定要不要呼叫
 * `push()`（§8.6 第 5 點）。這一層只負責畫。
 */
export function createSpectrogram(canvas, { columnWidth = 2 } = {}) {
  const ctx = canvas.getContext('2d');
  return {
    resize(width, height) {
      if (canvas.width === width && canvas.height === height) return;
      canvas.width = width;
      canvas.height = height;
      ctx.fillStyle = 'rgb(68, 1, 84)';        // viridis 的最低端＝靜音
      ctx.fillRect(0, 0, width, height);
    },
    /** 推進一欄。`units` 是由低頻到高頻、已經映到 [0,1] 的強度。 */
    push(units) {
      const { width, height } = canvas;
      ctx.drawImage(canvas, -columnWidth, 0);
      const n = units.length;
      for (let i = 0; i < n; i += 1) {
        const [r, g, b] = viridisColor(units[i]);
        ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
        // 低頻畫在下面（與頻譜圖的慣例一致），所以 y 由下往上。
        const y0 = height - Math.round(((i + 1) * height) / n);
        const y1 = height - Math.round((i * height) / n);
        ctx.fillRect(width - columnWidth, y0, columnWidth, Math.max(1, y1 - y0));
      }
    },
    clear() {
      ctx.fillStyle = 'rgb(68, 1, 84)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    },
  };
}

/**
 * 畫長條。`barRects()` 已經把所有計算做完，這裡只剩 fillRect。
 *
 * `outline` 是給無障礙用的（§8.6 第 4 點）：填色以外再描一圈邊，
 * 高對比模式與黑白列印之下長條的邊界仍然看得出來。
 */
export function fillBars(ctx, rects, { color, outline = null }) {
  ctx.save();
  ctx.fillStyle = color;
  for (const rect of rects) {
    if (rect.height <= 0) continue;
    ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
  }
  if (outline) {
    ctx.strokeStyle = outline;
    ctx.lineWidth = 1;
    for (const rect of rects) {
      if (rect.height <= 0) continue;
      ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
    }
  }
  ctx.restore();
}

/**
 * 一個標在圖上的小圓點 + 一段引線，用來指出「峰值在這裡」。
 *
 * 吉布斯的過衝需要它：翹起來的那一格只有幾個像素寬，
 * 沒有標記的話學生會看著整條曲線找不到我們在說哪裡。
 */
export function markPoint(ctx, point, { color, radius = 4 }) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(point.x, point.y, radius, 0, 2 * Math.PI);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(point.x, point.y - radius);
  ctx.lineTo(point.x, point.y - radius - 10);
  ctx.stroke();
  ctx.restore();
}

/**
 * 填一片區塊（`regionRect()` 已經把幾何算完，這裡只剩 fillRect）。
 *
 * `outline` 不是裝飾：§8.6 第 4 點要求顏色不得是唯一的訊息載體，
 * 而一片很淡的底色在投影機上常常整片消失，邊界線不會。
 */
export function fillRegion(ctx, rect, { color, outline = null }) {
  if (rect.width <= 0) return;
  ctx.save();
  ctx.fillStyle = color;
  ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
  if (outline) {
    ctx.strokeStyle = outline;
    ctx.lineWidth = 1;
    ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
  }
  ctx.restore();
}

/**
 * 取樣點：一根從零線拉起來的細棒 + 一個實心圓。
 *
 * 用棒棒糖圖而不是只畫圓點，是因為「取樣是在某個時刻抓一個值」這件事
 * 靠垂直的那一筆才表達得出來。
 */
export function strokeStems(ctx, points, zeroY, { color, radius = 3.5 }) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 1.5;
  for (const p of points) {
    ctx.beginPath();
    ctx.moveTo(p.x, zeroY);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius, 0, 2 * Math.PI);
    ctx.fill();
  }
  ctx.restore();
}
