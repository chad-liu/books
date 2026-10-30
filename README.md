# Liu 的知識圖譜與電子書庫

個人知識庫，由兩套**彼此獨立**的內容組成，各自有建置腳本與輸出，請不要混用：

| | 知識圖譜（知識地圖） | 電子書庫 |
|---|---|---|
| 內容 | 手工整理與轉換的主題頁面：歷史、哲學、宗教、音樂、科普…… | 把 EPUB 電子書轉成可在瀏覽器閱讀的互動式 HTML 閱讀器 |
| 來源 | `html\`（進版控） | `epub\`（不進版控） |
| 入口 | 根目錄 `index.html`、`treeview.html` | `reader\index.html`（不進版控） |
| 建置腳本 | `tools\build_html_index.py`、`tools\build_treeview.py` | `tools\build_library.py` |

線上網站（GitHub Pages）：

- 知識圖譜首頁：<https://chad-liu.github.io/books/>
- 檔案樹瀏覽器：<https://chad-liu.github.io/books/treeview.html>
- 原始碼庫：<https://github.com/chad-liu/books>

> 電子書庫的本體（約 3 GB，單檔可達數百 MB，超過 GitHub 單檔 100 MB 的限制）不放上網，只在本機使用。

---

## 一、目錄結構

```
Books\
├─ index.html            知識圖譜首頁（由 build_html_index.py 產生）
├─ treeview.html         檔案樹瀏覽器（由 build_treeview.py 產生）
├─ start_treeview.bat    在本機開啟 treeview.html（localhost:8899）
├─ html\                 知識圖譜的頁面，一個分類一個資料夾，各有 order.md
├─ tools\                建置腳本與設定檔
├─ app\                  小工具（Markdown 編輯器）
├─ epub\                 來源電子書（不進版控）
├─ reader\               電子書庫的產出（不進版控）
├─ md\                   轉換用的 Markdown 原稿（目前沒有納入版控）
├─ png\                  圖檔
└─ CLAUDE.md、Plan*.md、plan*.md、prompt.md、booklist.md   需求筆記與工作流程
```

---

## 二、知識圖譜（`html\`）

### 資料夾命名：編號決定順序與階層

資料夾名稱是 `編號.名稱`，編號用連字號分段，**首頁卡片與檔案樹都依編號的數字大小排序**（`1-6` 排在 `1-6-1` 前面，再來才是 `1-7`）。

| 寫法 | 意義 | 例子 |
|---|---|---|
| `N.名稱` | 第一層分類（群組），可以只當標題、不放檔案 | `2.哲學與宗教` |
| `N-M.名稱` | 分類底下的資料夾，**在首頁是一張卡片** | `2-2.哲學家` |
| `N-M-K.名稱` | 再下一層，與 `N-M` 同為 `N` 的子資料夾 | `1-6-1.大航海時代` |

目前的第一層分類：

| 編號 | 分類 |
|---|---|
| 0 | 參考速查 |
| 1 | 歷史 |
| 2 | 哲學與宗教 |
| 3 | 人文社會 |
| 4 | 政治經濟商業 |
| 5 | 音樂與電影 |
| 6 | 文學 |
| 7 | 教育學習 |
| 8 | 科普 |
| 9 | 休閒娛樂 |

規則的細節：

- **在檔案樹裡**，同一個第一段編號的資料夾會收合在 `N.名稱` 底下（例如 `2-1`、`2-2`…`2-7` 都在 `2.哲學與宗教` 裡）。找不到唯一的 `N.名稱` 時，就攤平成頂層。
- **在首頁**，只有「有 `order.md` 的資料夾」才會變成卡片；`N.名稱` 群組資料夾通常不放 `order.md`，所以不會出現在首頁。
- 空的群組資料夾請放一個空的 `.gitkeep`，不然 Git 不會保存它。
- 改資料夾名稱或編號時，請用 `git mv`，歷史才不會斷；改完重新建置（見下方）。

### `order.md`：決定卡片裡的條目與順序

每個資料夾的 `order.md` 決定首頁卡片要列哪些條目，**依行的順序**顯示並編流水號。每一行是下列其中一種：

| 寫法 | 意思 |
|---|---|
| `檔名` | 同資料夾的 `檔名.html`（不含副檔名） |
| `名字(附註)` | 顯示為「名字(附註)」，實際連到 `名字.html`（例如 `蒙田(1533~1592)`） |
| `標籤(https://…)` | 外部連結，另開分頁 |
| `---`（或 `===`、`___`） | 排版用分隔線，不當條目 |
| 空行 | 略過 |

如果資料夾底下還有子資料夾，條目寫成 `子資料夾/檔名`，卡片會依子資料夾分組。

`order.md` 沒列到的檔案不會出現在首頁，但**檔案樹會列出全部檔案**，並在未列入的檔案上加淡色標記，方便發現漏列。

### 新增頁面的流程

1. 把頁面（`.html`）放進對應的 `html\<編號.名稱>\` 資料夾。
   - 製作新的知識圖譜頁面時，套用 `infograph-style` skill 的風格。
   - 可以是電子書庫已有的書，也可以只是外部連結。
2. 把檔名加進該資料夾的 `order.md`（新資料夾要先建立 `order.md` 才會出現在首頁）。
3. 重新建置首頁與檔案樹：

   ```bash
   python tools/build_html_index.py
   python tools/build_treeview.py
   ```

4. 到瀏覽器確認，然後 commit / push。

> `build_html_index.py` 若看到 `order.md` 列了找不到的檔案，會印出 `[警告]` 並略過該條目；沒有 `order.md` 的資料夾則顯示 `[略過]`。這兩種訊息是提醒，不是錯誤。

---

## 三、檔案樹瀏覽器（`treeview.html`）

左邊是 `html\` 的完整檔案樹，右邊可用分頁同時開啟多個頁面，也可以直接編輯原始碼。

**啟動**：雙擊 `start_treeview.bat`，它會在 `localhost:8899` 起一個本機伺服器並開啟瀏覽器。

> 編輯功能一定要用 `localhost` 開啟。直接用 `file://` 開檔時，瀏覽器會擋住讀取本機檔案，編輯功能會自動關閉，只剩瀏覽與分頁。

| 環境 | 瀏覽與分頁 | 編輯 | 直接存回原檔 | 下載修改後的檔案 |
|---|---|---|---|---|
| localhost（Chrome、Edge） | ✓ | ✓ | ✓ | ✓ |
| localhost（Firefox、Safari） | ✓ | ✓ | ✗ | ✓ |
| GitHub Pages | ✓ | ✓ | ✗ | ✓ |
| `file://` 直接開檔 | ✓ | ✗ | ✗ | ✗ |

使用上的重點：

- **搜尋框**：比對檔名或資料夾名稱（`Ctrl+F` 聚焦）。
- **分頁**：中鍵點分頁或 `Ctrl+W` 關閉；有未存檔的修改時標題會顯示 `●`。
- **A− / A+**：縮放右邊預覽（50%–250%），整份頁面等比縮放，包含 SVG 圖表。
- **深連結**：`treeview.html#f=html/2-2.哲學家/康德.html` 會直接開啟該檔並展開所在資料夾，網址可以分享。
- **草稿**：編輯中的內容會自動存在瀏覽器的 `localStorage`，關掉瀏覽器不會遺失。
- **為什麼沒有深色模式**：頁面裡的 SVG 顏色全部是寫死的（SVG 不吃 CSS 變數），從外部切換只會讓圖表浮在深色背景上，反而更難看，所以不提供。

新增或改名檔案後要重跑 `python tools/build_treeview.py`，因為檔案樹是在建置時烘進 `treeview.html` 的。

---

## 四、電子書庫（`epub\` → `reader\`）

### 放書的規則

`epub\` 底下第一層是類別資料夾（`1.社會人文類`、`2.哲學類`…`15.美洲小說`），第二層通常是作者或主題書櫃。`reader\` 的結構與 `epub\` 完全鏡射。

1. 把 EPUB 放進 `epub\` 的類別資料夾。
2. **簡體書預設會被略過**，要轉成台灣用語的繁體再收進書庫時加 `--to-tw`。
3. 執行建置，產出會放進 `reader\`，並重建 `reader\index.html`。

### 常用指令

```bash
python tools/build_library.py
```

增量建置：依來源檔的修改時間與大小略過沒變的書，最後自動重建首頁。**新增或抽換 EPUB 後跑這個就好**。

```bash
python tools/build_library.py --plan
```

只列出建置計畫（哪些做成書架、哪些是單書），不實際轉檔。調整分冊或簡繁邏輯後先用這個確認。

| 參數 | 用途 |
|---|---|
| `--only "2.哲學類"` | 只處理某個資料夾（可含多層，如 `"7.學習休閒類\音樂"`） |
| `--force` | 忽略指紋全部重轉；改過 `text_fixes.json` 後必須用它才會生效 |
| `--to-tw` | 把簡體書轉成繁體後收進書庫（不加時簡體書一律略過） |
| `--index-only` | 只重建 `reader\index.html`，不碰任何書 |
| `--refresh` | 不重轉，只補既有產出的書目資訊與加工 |
| `--patch-only` | 只重貼所有產出的後加工區塊，不動 manifest |
| `--orphans` | 列出來源已消失的孤兒檔，**只列出不刪** |
| `--delete-orphans` | 真的刪除孤兒檔（先用 `--orphans` 確認清單） |

> ⚠️ **不加 `--to-tw` 的完整建置**會把「由簡體轉成繁體收進來」的書從首頁移除（它們不在建置計畫內）。若書庫裡有這類書，完整建置時請一併加上 `--to-tw`。`--delete-orphans` 前也請務必先用 `--orphans` 看過清單。

### 三個手動設定檔（個案用，不要為了單一本書放寬全域規則）

| 檔案 | 用途 |
|---|---|
| `tools\series.json` | 手動指定要合併成書架的分冊（自動偵測只認「上/中/下」、「卷一」、「第N冊」等明確標記） |
| `tools\titles.json` | 書名修正表，首頁與閱讀器頁首都會套用；值可以是字串（只改書名），也可以是 `{"title": …, "author": …}` |
| `tools\text_fixes.json` | 指定書籍的內文字串替換；**改完要用 `--force` 重跑該資料夾才會生效** |

### 運作原理（遇到問題時用得到）

- **轉檔不是腳本本身做的**：`build_library.py` 以子行程呼叫兩個 skill，缺少任何一個整個腳本就無法運作。
  - `~\.claude\skills\html-reader-maker\scripts\run.py`：單本書閱讀器
  - `~\.claude\skills\multi-book-shelf\scripts\run.py`：多本書書架
- **`reader\.manifest.json` 是書庫的權威清單**，首頁完全由它產生。檔案還在硬碟上但不在 manifest 裡，就不會出現在首頁。
- **簡繁轉換**需要系統 Python 的 `opencc`（`s2twp`，台灣用語）。
- **後加工**：每個產出的 HTML 尾端會插入「← 書庫」返回連結（會捲回首頁上該書的位置）、預設夜間模式，以及書架的 `#bN` 深連結。重跑可重複套用，不會疊加。
- 建置紀錄寫在 `tools\library_changes.md`。

---

## 五、與 Liu's Timeline 的互連

[Liu's Timeline](https://chad-liu.github.io/Timeline/)（另一個 repo）有人物的生平時間軸。兩邊不整合，只互相連結：

- **對應關係只維護在 Timeline 那一側**：各人物 md 的 `related:` 欄位列出連到本站的頁面。
- 本站執行：

  ```bash
  python tools/add_timeline_links.py          # 在被連到的頁面 footer 前加入「生平時間軸」區塊
  python tools/add_timeline_links.py --check  # 只列出會變動的頁面，不寫檔
  ```

  預設讀取線上的 `https://chad-liu.github.io/Timeline/people.json`；Timeline 還沒部署時，可先在 Timeline 那邊 `npm run build`，再用 `--source <本機路徑>\dist\people.json` 讀本機檔案。

- 要新增或拿掉某頁的連結，改 Timeline 那邊的 `related:`，push 並等部署完成後，再回來重跑腳本。
- 某頁不再被任何人 `related` 到時，重跑會清掉它殘留的舊區塊。

> ⚠️ **改 `html\` 的資料夾名稱前先確認**：Timeline 的 `related:` 連結寫的是 `https://chad-liu.github.io/books/html/<資料夾>/…`。目前只有 `1-1`、`2-1`、`2-2`、`6-2` 這幾個資料夾被連到，改名會讓那邊的連結失效。

---

## 六、Git 與版控

遠端：`https://github.com/chad-liu/books`

| 進版控 | 不進版控 |
|---|---|
| `html\`（含各資料夾 `order.md`） | `epub\`（來源電子書） |
| `index.html`、`treeview.html` | `reader\`（產出，可隨時重新產生） |
| `tools\` 的腳本與設定、`library_changes.md` | `tools\*.log`、`__pycache__\`、`*.twtmp`、`*.fixtmp` |
| `app\`、`png\`、各種 `*.md` 筆記 | `bookwant.md`（個人書單草稿） |

`md\` 目前**既沒有納入版控、也沒有被 `.gitignore` 排除**（Git 會把它顯示成未追蹤）；提交時請指定路徑，避免用 `git add -A` 把它整包加進去。

注意事項：

- **動 git 之前先 `git status -sb`**。你也會直接在 GitHub 網頁上編輯 `index.html`（提交訊息是「Add files via upload」），所以本機 `main` 可能落後遠端。若本機的 `index.html` 修改其實跟 `origin/main` 相同，還原後 `git pull --rebase` 即可，不必手動解衝突。
- 每次改了 `html\`（新增、改名、改 `order.md`），**都要重跑 `build_html_index.py` 與 `build_treeview.py`**，並把重新產生的 `index.html`、`treeview.html` 一起提交。
- 刪除與移動檔案前，一律先列出實際要動的檔案再動手。
- 在 Windows 上，`git add` 時看到 `LF will be replaced by CRLF` 的警告是換行格式提示，不影響內容。
- GitHub Pages 推送後約一兩分鐘建置完成，CDN 快取最多約 10 分鐘，網站才會更新。

---

## 七、環境需求

- Windows、Python 3
- 簡繁轉換：系統 Python 安裝 `opencc`
- 電子書庫：`~\.claude\skills\` 底下需有 `html-reader-maker` 與 `multi-book-shelf` 兩個 skill（各自有獨立的虛擬環境，由其 `run.py` 管理）
- 檔案樹與首頁：只需 Python 標準函式庫，不需額外安裝套件

## 八、常見問題

**新增了頁面，首頁卻沒有出現？**
檢查三件事：該資料夾有沒有 `order.md`、檔名有沒有列在 `order.md` 裡（不含 `.html`）、有沒有重跑 `build_html_index.py`。

**treeview 看得到檔案，首頁看不到？**
這是設計如此：首頁只顯示 `order.md` 列出的條目；treeview 顯示全部檔案，未列入的會有淡色標記。

**treeview 無法編輯？**
你可能是用 `file://` 開啟的，請改用 `start_treeview.bat`（`localhost`）。

**電子書首頁沒有某本書，但檔案還在 `reader\` 裡？**
書庫首頁完全由 `reader\.manifest.json` 產生，不在 manifest 裡就不會出現。通常是來源改名，或簡體書在沒加 `--to-tw` 的完整建置時被略過。

**改了 `text_fixes.json` 卻沒有生效？**
指紋沒變不會重轉，要用 `--force`，並用 `--only` 限定資料夾。

**資料夾改名後，treeview 的分組不對？**
檔案樹只看「第一段編號」分組，且該編號必須對應到**唯一**一個 `N.名稱` 資料夾；同一個編號有多個資料夾時視為有歧義，不會分組。
