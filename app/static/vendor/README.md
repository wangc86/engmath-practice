# 自架的前端資產

這個目錄的檔案是第三方函式庫的副本，**刻意納入版本控制**：
clone 完就能離線啟動，校內網路連不到外部 CDN 時數學也能正常渲染。

| 函式庫 | 版本 | 授權 | 檔案 |
|---|---|---|---|
| [KaTeX](https://katex.org/) | 0.16.11 | MIT（見 `katex/LICENSE`） | `katex/` |
| [HTMX](https://htmx.org/) | 2.0.4 | 0BSD（見 `htmx.LICENSE`） | `htmx.min.js` |
| [fft.js](https://github.com/indutny/fft.js) | 4.0.4 | MIT（見 `fftjs/LICENSE`） | `fftjs/fft.js` |

總計約 670 KB。

## `fftjs/` 這一個與其他兩個不同：它被改過一行

上游是 CommonJS（`module.exports = FFT;`），而瀏覽器裡沒有 `module` 這個
識別字，所以**原封不動地 vendor 進來是行不通的**——那一行無論以 ES module
或傳統 script 載入都會丟 ReferenceError。因此改了、而且只改了那一行：

```
module.exports = FFT;      →      export default FFT;
```

其餘 500 行逐字保留。改動與上游 sha256 記在 `fftjs/fft.js` 的標頭裡，
並由 `tests/test_demos.py::test_the_vendored_fft_is_the_upstream_file_with_exactly_one_line_changed`
盯著——**任何人日後「順手改一下」vendored 的程式碼都會讓那一項變紅**。

選型的完整比較（ooura／fft-js／kissfft-js 為什麼沒選）見 PLAN.md §8.3 與 D31。
升級的步驟與其他兩個一樣（`npm pack fft.js@X.Y.Z`），但**多兩步**：
重新套用那一行改動，並更新測試裡的 sha256。

## 只保留了必要的檔案

從 npm 套件的 `dist/` 中挑出實際會用到的部分：

- `katex/katex.min.css`、`katex/katex.min.js`
- `katex/contrib/auto-render.min.js`（`base.html` 用它掃描整頁的 `$…$` 與 `$$…$$`）
- `katex/fonts/*.woff2`（20 個）
- `htmx.min.js`

**字型只保留 woff2**。`katex.min.css` 的每個 `@font-face` 都把 woff2 排在第一順位，
瀏覽器取到 woff2 後就不會再去要 woff／ttf，所以省下的 876 KB 不影響顯示。
woff2 自 2016 年起已是全瀏覽器支援。若真的遇到極舊的瀏覽器（字型會退回系統預設，
數學結構仍正確、只是字形不對），把 `fonts/*.woff` 一併補進來即可。

## 更新版本

以 KaTeX 升到 `X.Y.Z` 為例（HTMX 同理）：

```bash
cd /tmp && npm pack katex@X.Y.Z && tar xzf katex-X.Y.Z.tgz

V=/path/to/engmath-practice/app/static/vendor
cp package/dist/katex.min.css              "$V/katex/"
cp package/dist/katex.min.js               "$V/katex/"
cp package/dist/contrib/auto-render.min.js "$V/katex/contrib/"
cp package/dist/fonts/*.woff2              "$V/katex/fonts/"
cp package/LICENSE                         "$V/katex/LICENSE"
```

升級後請確認：

1. 更新本檔案的版本表。
2. 開一題含矩陣的線性系統（難度 3），確認 `\begin{matrix}` 與初始條件都正常渲染。
3. `pytest tests/test_web.py -q` 全過（其中有一項會檢查 `base.html` 引用的資產確實存在）。

> 若舊版的字型檔名有變動，`fonts/` 裡會留下用不到的舊檔——這不會造成錯誤，
> 但記得手動刪掉，避免目錄越長越大。
