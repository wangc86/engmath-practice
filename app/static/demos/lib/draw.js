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
 * Canvas 的 devicePixelRatio 縮放（§8.5：不做的話手機上全部是模糊的）。
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
