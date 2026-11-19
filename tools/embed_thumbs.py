"""把作品列表頁的縮圖下載並以 base64 內嵌，讓頁面可離線瀏覽。

用法（可一次給多個檔案）：
    python tools/embed_thumbs.py html/9-2-1.作品列表/莫內作品列表.html
    python tools/embed_thumbs.py a.html b.html --width 320

頁面要依 tools/templates/works_list_template.html 的格式寫，每件作品的圖片格是
    <div class="thumb" data-wiki="英文維基百科的條目標題">作品短名</div>
data-wiki 可以是任何英文維基百科條目（含重新導向）；想換掉某件作品的圖，改這個
標題即可。查無縮圖的作品保留作品短名當退路，不會留下破圖。

做了三件事，之後頁面就不再需要網路：
  1. 向維基百科 API 查縮圖網址，逐張下載並轉成 data: URI 嵌回 <div class="thumb">。
  2. 刪掉樣板裡負責「開啟頁面時即時載入」的 <script id="thumb-loader">。
  3. 把頁尾那句「縮圖於開啟頁面時…即時載入」改成「已內嵌，可離線瀏覽」。
     頁尾若找不到那句會警告——代表頁面還寫著即時載入，但實際已經內嵌了。

處理過的頁面已沒有 data-wiki 標記，再跑一次會直接略過、不動檔案，所以重複執行是
安全的。有動到檔案時，原檔會先備份成 .bak（請自行刪除，不要提交）。
讀寫都保留原檔的換行（CRLF 或 LF），不會把整個檔案的換行改掉。

只用 Python 標準函式庫。

重要：這支腳本只認上面那種 <div class="thumb" data-wiki=…> 標記。9-2-1.作品列表
裡拉斐爾、達文西、米開朗基羅、提香四頁是用 <img class="thumb"> 直接匯入的，不是這支
腳本的產物，餵給它會被略過。

授權：腳本不會判斷圖片能不能用。只有作者作品已進入公有領域時才適合內嵌（例如畢卡索
仍在保護期內，9-2-1.作品列表的畢卡索頁就刻意不放圖）。
"""
import argparse
import base64
import html
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = "WorksListThumbEmbedder/1.0 (https://chad-liu.github.io/books/)"
API = "https://en.wikipedia.org/w/api.php"
BATCH = 50  # MediaWiki 一次最多接受 50 個標題，超過會整批被拒

THUMB_CELL = re.compile(r'<div class="thumb" data-wiki="([^"]+)">([^<]*)</div>')
LOADER = re.compile(r'(?:\r?\n)?<script id="thumb-loader">.*?</script>(?:\r?\n)?', re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
NOTE_BEFORE = ("縮圖於開啟頁面時從維基百科（Wikimedia Commons）即時載入，"
               "離線或查無對應條目時以作品名稱代替。")
NOTE_AFTER = "圖片取自 Wikimedia Commons，已縮成縮圖內嵌於本頁，可離線瀏覽。"


def get(url, tries=6):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read(), r.headers.get_content_type()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or i == tries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 10) + 2
            print(f"  （限速，{wait} 秒後重試）")
            time.sleep(wait)


def outside_comments(text, fn):
    """只對 HTML 註解以外的部分套用 fn，註解原樣保留。

    樣板開頭的說明註解裡會舉圖片格的範例，那些不是真的作品，不該被查圖或改寫。
    """
    out, pos = [], 0
    for m in COMMENT.finditer(text):
        out.append(fn(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(fn(text[pos:]))
    return "".join(out)


def thumb_cells(text):
    """註解以外的所有圖片格，回傳 [(條目標題, 作品短名)]。"""
    cells = []
    outside_comments(text, lambda t: cells.extend(THUMB_CELL.findall(t)) or t)
    return cells


def lookup_thumbs(titles, width):
    """回傳 {條目標題: 縮圖網址}，沒有縮圖的條目不在結果裡。"""
    result = {}
    for i in range(0, len(titles), BATCH):
        batch = titles[i:i + BATCH]
        params = {
            "action": "query", "format": "json", "prop": "pageimages",
            "piprop": "thumbnail", "pithumbsize": str(width),
            "redirects": "1", "titles": "|".join(batch),
        }
        data = json.loads(get(API + "?" + urllib.parse.urlencode(params))[0])
        q = data.get("query", {})
        alias = {n["from"]: n["to"]
                 for n in q.get("normalized", []) + q.get("redirects", [])}
        thumbs = {p["title"]: p["thumbnail"]["source"]
                  for p in q.get("pages", {}).values() if "thumbnail" in p}
        for t in batch:
            cur, seen = t, set()
            while cur in alias and cur not in seen:
                seen.add(cur)
                cur = alias[cur]
            if cur in thumbs:
                result[t] = thumbs[cur]
    return result


def embed(path, width, note_after):
    src = open(path, encoding="utf-8", newline="").read()
    eol = "\r\n" if "\r\n" in src else "\n"  # 原檔用哪種換行就寫回哪種
    cells = thumb_cells(src)
    if not cells:
        print(f"{path}：沒有 data-wiki 縮圖格，略過（可能已處理過）")
        return
    titles = [html.unescape(t) for t, _ in cells]
    print(f"{path}：{len(titles)} 件作品")
    found = lookup_thumbs(titles, width)

    data_uris = {}
    for t in titles:
        if t not in found:
            continue
        try:
            time.sleep(1)
            body, ctype = get(found[t])
            data_uris[t] = f"data:{ctype};base64,{base64.b64encode(body).decode()}"
            print(f"  OK  {t}")
        except Exception as e:  # noqa: BLE001
            print(f"  失敗 {t}: {e}")

    def repl(m):
        title, label = html.unescape(m.group(1)), m.group(2)
        if title in data_uris:
            return f'<div class="thumb"><img src="{data_uris[title]}" alt="{label}"></div>'
        return f'<div class="thumb">{label}</div>'

    out = outside_comments(src, lambda t: THUMB_CELL.sub(repl, t))
    out = LOADER.sub(eol, out)
    if NOTE_BEFORE in out:
        out = out.replace(NOTE_BEFORE, note_after)
    else:
        print("  警告：頁尾找不到「即時載入」那句，頁尾說明可能與實際不符，請自行檢查")

    shutil.copyfile(path, path + ".bak")
    open(path, "w", encoding="utf-8", newline="").write(out)
    missing = [t for t in titles if t not in data_uris]
    print(f"  內嵌 {len(data_uris)}/{len(titles)} 張，已寫回（原檔備份為 .bak）")
    if missing:
        print("  查無縮圖（保留作品短名）：")
        for t in missing:
            print("    -", t)


def main():
    ap = argparse.ArgumentParser(description="把作品列表頁的縮圖內嵌成 base64。")
    ap.add_argument("files", nargs="+", help="要處理的 .html（可多個）")
    ap.add_argument("--width", type=int, default=240, help="縮圖寬度 px（預設 240）")
    ap.add_argument("--note-after", default=NOTE_AFTER,
                    help="取代頁尾「即時載入」那句的文字")
    args = ap.parse_args()
    for f in args.files:
        embed(f, args.width, args.note_after)


if __name__ == "__main__":
    main()
