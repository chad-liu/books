# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 這是什麼

個人知識庫，兩套獨立的內容各自有自己的建置腳本與輸出，**不要混用**：

1. **電子書庫**：來源 EPUB 放在 `epub\`，經 `tools\build_library.py` 轉成單檔互動式 HTML 閱讀器，輸出到 `reader\`，產生 `reader\index.html`。
2. **知識地圖首頁**：手工整理的哲學／歷史／宗教等主題 HTML 頁面放在 `html\`，經 `tools\build_html_index.py` 重建**根目錄** `index.html`（標題「Liu的雲端閱讀」）。

不是一般程式專案，沒有測試套件與建置系統，「跑一次腳本」就是建置動作。`Plan.md`／`plan1.md`／`plan2.md`／`booklist.md` 是對應兩套系統的需求筆記（plan1 對應書庫、plan2 對應知識地圖首頁）。

`epub\` 底下的第一層是類別資料夾（`1.社會人文類`、`2.哲學類`…`15.美洲小說`），第二層通常是作者或主題書櫃，`reader\` 的資料夾結構與 `epub\` 完全鏡射。

## 常用指令

```bash
python tools/build_library.py
```

增量建置：依來源檔的 mtime/size 指紋略過沒異動的書，最後自動重建首頁。新增或抽換 EPUB 後跑這個就好。

```bash
python tools/build_library.py --plan
```

只列出建置計畫（哪些會做成書架、哪些是單書），不實際轉檔。**動到分冊或簡繁邏輯後先用這個確認**。

其他參數：

| 參數 | 用途 |
|---|---|
| `--only "2.哲學類"` | 只處理某個資料夾（可含多層，如 `"7.學習休閒類\音樂"`） |
| `--force` | 忽略指紋全部重轉；改過 `text_fixes.json` 後必須用它才會生效 |
| `--index-only` | 只重建 `reader\index.html`，不碰任何書 |
| `--refresh` | 不重轉，只補既有產出的書目資訊與加工 |
| `--patch-only` | 只重貼所有產出的 patch，不動 manifest（可與建置並行） |
| `--orphans` | 列出來源已消失的孤兒檔，**只列出不刪** |
| `--delete-orphans` | 真的刪除孤兒檔（先用 `--orphans` 確認清單） |
| `--to-tw` | 把簡體書轉繁後收進書庫；不加時簡體書一律略過 |

## 架構

### 建置流程

`plan_jobs()` 走訪 `epub\`，為每個輸出產生一個 job（`reader` 單書／`shelf` 多冊書架／`copy` 直接複製現成 HTML），`build()` 逐項執行：

1. 呼叫 skill 轉檔 → 2. 簡繁轉換（僅 `--to-tw`）→ 3. `text_fixes.json` 內文替換 → 4. `patch_output()` 加工 → 5. 寫入 manifest

**轉檔本身不是這個腳本做的**，而是以子行程呼叫兩個外部 skill：

- `~\.claude\skills\html-reader-maker\scripts\run.py` — 單書閱讀器
- `~\.claude\skills\multi-book-shelf\scripts\run.py` — 多書書架

這兩個 skill 不存在時整個腳本無法運作。子行程一律帶 `PYTHONIOENCODING=utf-8`（`CHILD_ENV`）—— skill 會把輸出檔名 print 出來，Windows 預設 cp950 遇到簡體字或日文中點會在最後一行 `UnicodeEncodeError`，導致整本書被誤判成失敗。

### 狀態檔

- `reader\.manifest.json` — 每個輸出對應的來源指紋、書目、大小。**它是書庫的權威清單，首頁完全由它產生**。檔案還在硬碟上但不在 manifest 裡的，就不會出現在首頁。
- `reader\.zh.json` — 簡繁偵測結果快取（鍵含 mtime/size，來源換檔會自動重測）。

完整建置（未指定 `--only`）時會把「不在建置計畫內」的 manifest 紀錄移除，所以來源改名或簡體書被略過後，首頁會自動不再列出，但**檔案仍留在硬碟上**，要用 `--orphans` / `--delete-orphans` 處理。

### 三個手動設定檔

自動規則刻意保守，個案用設定檔處理，不要為了單一書去放寬全域規則：

- `tools\series.json` — 手動指定要合併成書架的分冊。自動偵測（`volume_number()`）只認明確標記（上/中/下、卷一、第N冊、羅馬數字＋冒號），像「好音樂的科學 I」「《曾國藩一》」這種認不出來的列在這裡。鍵是相對 `epub\` 的資料夾路徑，`members` 順序即書架順序。
- `tools\titles.json` — 書名修正表（首頁與閱讀器頁首都會套用）。首頁書名取自 EPUB metadata，常有館藏編號、`【全新修訂版】` 之類雜訊，`clean_title()` 已處理通例，個案寫這裡。值可以是字串（只改書名）或 `{"title": ..., "author": ...}`（連 metadata 寫 `Unknown` 的作者一併修正）。
- `tools\text_fixes.json` — 指定書籍的內文字串替換，鍵是 `reader\` 底下的相對路徑。**改完要 `--force` 重跑該資料夾才生效**（指紋沒變不會重轉）。章節目錄名來自 EPUB 的 toc.ncx，`titles.json` 管不到，要改目錄名得用這個。

### 產出後加工（`patch_output()`）

每個產出的 HTML 尾端會插入一段 `<!--library-patch v3-->` 區塊：右下角「← 書庫」返回連結（依資料夾深度算相對路徑，並帶 `#bk-<路徑md5前10碼>` 錨點）、預設夜間模式、書架的 `#bN` 深連結支援。

patch 有版本標記，重貼前會把舊區塊整段移除，所以可重複套用不會疊加。**夜間模式是呼叫樣板既有的 `toggleNight()` 而不是硬加 class**，這樣工具列按鈕文字才會同步。返回書庫的錨點對應 `reader\index.html` 每本書 `<li>` 上同一個 `book_anchor()` 算出的 id，所以從閱讀器點「← 書庫」會捲回首頁上那本書的位置並短暫高亮，而不是回到頁面最上面。

### 大檔處理

圖多的書 base64 內嵌後單一行就可能到 388 MB。`convert_output_to_tw()` 與 `apply_text_fixes()` 都是固定 4 MB 分段處理，分段邊界會保留尾巴避免切斷待替換字串；簡繁轉換另外只對漢字串呼叫 OpenCC，跳過 base64。**不要改回整份讀進記憶體**——之前那樣做在該檔上被系統砍掉過。

## 知識地圖首頁（`tools\build_html_index.py`）

依 `plan2.md` 規劃，跟電子書庫完全獨立的第二套建置腳本：

```bash
python tools/build_html_index.py
```

規則：

- `html\` 每個子資料夾是一張卡片，**依資料夾名稱單純升冪排序**（字串排序，不像書庫那樣解析數字前綴；資料夾名稱本身已用 `1.`、`2.`、`3-1.`、`3.`…前綴人工排好順序）
- 卡片內容依同資料夾 `order.md` 的**行順序**，用 `<ol>` 顯示流水號
- `order.md` 每行若是 `標籤(https://...)` 格式視為外部連結（外部連結一律 `target="_blank"`）；純一串 `---`/`===`/`___` 視為排版用分隔線略過；其餘視為本機檔名（不含 `.html`），連到同資料夾的 `<檔名>.html`
- **沒有 `order.md` 的資料夾直接略過**，不產生空卡片——新增分類資料夾後要記得放一個 `order.md` 才會出現在首頁
- 頂部固定列有分類下拉選單（跳到卡片，自動扣掉固定列高度）與搜尋框（比對條目與分類名稱）；下拉跳轉前若搜尋框有內容會先清空，避免跳到被搜尋隱藏的分類

新增或修改 `html\` 底下內容後，重跑上面那行指令即可，`order.md` 要手動同步更新（沒有自動掃描資料夾生成順序）。

## 慣例

- 首頁每本書只列一次。同一本書若既有單書檔又收在書架裡，只保留單書那筆；整櫃都被取代的書架另外以 📚 一行列出，才不會連不到。
- 類別依開頭數字排序（1~8 → 11~15），書櫃卡片一律依藏書數降冪，數量相同時以路徑為次要排序確保順序固定。
- 來源已是 `.html` 的檔案直接複製不轉換；同資料夾有同名 `.epub` 時該 epub 不再轉一次，否則兩個工作會產出同一個檔名互相覆蓋。
- 刪除與移動一律先列出實際檔案再動手，孤兒檔預設只列不刪。
- 使用者自製的整櫃書架 HTML（`XX書架.html`）是原樣複製進來的，無法從中單獨移除某一本書。

## 環境

Windows + PowerShell。簡繁轉換需要系統 Python 的 `opencc`（`s2twp`，台灣用語）；轉檔 skill 各自有獨立 venv，由其 `run.py` 自行管理。

## 版控

遠端是 `https://github.com/chad-liu/books`。**只有腳本與設定進版控，書籍本體不進**：

| 進版控 | 不進版控（`.gitignore`） |
|---|---|
| `tools\build_library.py`、`build_html_index.py` | `epub\`（來源電子書） |
| `tools\series.json`、`titles.json`、`text_fixes.json` | `reader\`（產出，約 3 GB，隨時可重新產生） |
| `tools\library_changes.md`（書庫異動紀錄） | `tools\*.log`、`__pycache__\`、`*.twtmp`、`*.fixtmp` |
| `html\`（知識地圖來源，含各資料夾 `order.md`） | |
| `index.html`、`Plan.md`、`booklist.md`、`plan1.md`、`plan2.md`、`CLAUDE.md` | |

`reader\` 單檔可達數百 MB，超過 GitHub 單檔 100 MB 硬限制，**不要把它加進版控**。

使用者也會直接在 GitHub 網頁上編輯 `index.html`（提交訊息為「Add files via upload」），所以**本機 main 常落後遠端數十筆**。動 git 之前先 `git status -sb` 看有沒有分岔；若本機的 `index.html` 修改其實與 `origin/main` 相同（用 `git diff origin/main -- index.html` 確認），還原後 `git pull --rebase` 即可，不必手動解衝突。
