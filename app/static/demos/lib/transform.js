// 變換層（PLAN.md §8.2.3 第二段）。
//
// 與 signal.js 一樣是**純函式**，不知道 DOM 與 AudioContext 存在。
//
// ⚠️ **這個檔案目前沒有 FFT。** §8.8 把 FFT 層排在 2S1，而 2S1 被 §7 #32
// （vendored 函式庫的授權與單檔可用性）擋著。混疊展示（2S3）刻意不需要 FFT
// （§8.2.2：「它的核心根本不需要 FFT」），所以這一輪**沒有為了湊齊四段而放
// 一支空的 FFT 進來**——一個沒有人呼叫、沒有測試看守的 FFT 是這份規劃裡
// 最不該存在的東西（§8.3 已經寫過：FFT 的錯法都很安靜）。
//
// 現在住在這裡的是「頻率軸上的換算」，也就是 §8.2.3 那一列寫的
// 「頻率軸標定」的一部分：把一個頻率經取樣之後摺到哪裡去。

/** 奈奎斯特頻率。取樣率 fs 之下，能無歧義表示的最高頻率。 */
export function nyquist(fs) {
  return fs / 2;
}

/**
 * **有號**的混疊頻率：f - round(f/fs) * fs，落在 [-fs/2, fs/2]。
 *
 * 有號是重點，不是多餘的細節。取樣之後，
 *
 *     sin(2π f n/fs) = sin(2π (f - k fs) n/fs)
 *
 * 對任何整數 k 都成立；當 f - k·fs 是負的，那條穿過同一組取樣點的低頻正弦
 * 是**倒相**的（sin(-x) = -sin x）。畫重建波形時如果只用絕對值，
 * 波形會與取樣點對不上——而那是一個看得見、卻很容易被當成「畫錯了」的錯誤。
 */
export function signedAliasFrequency(f, fs) {
  if (fs <= 0) return f;
  return f - Math.round(f / fs) * fs;
}

/**
 * 混疊後的**表觀頻率**（人耳聽到、也是畫面上要顯示的那個數字），恆為非負。
 *
 * f <= fs/2 時它就等於 f 自己（沒有混疊，公式自動退化）。
 */
export function aliasFrequency(f, fs) {
  return Math.abs(signedAliasFrequency(f, fs));
}

/** 有沒有發生混疊：訊號頻率是否超過奈奎斯特頻率。 */
export function isAliased(f, fs) {
  return f > nyquist(fs);
}

/**
 * 摺疊的方向：混疊後的正弦相對原訊號是同相還是反相。
 * 回傳 +1 或 -1，供繪圖層決定重建波形的正負號。
 */
export function aliasSign(f, fs) {
  const signed = signedAliasFrequency(f, fs);
  return signed < 0 ? -1 : 1;
}
