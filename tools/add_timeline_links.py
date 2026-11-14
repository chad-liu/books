"""在知識圖譜頁面加上「生平時間軸」與「相關時間軸」連結，指向 Liu's Timeline（https://liu-timeline.pages.dev/）。

對應關係不另外維護，直接讀 Timeline 公開的兩份索引：
- people.json（人物）：每位人物的 related 連結裡，凡是指向本站 html\\ 頁面的，該頁就連回這位人物的時間軸，
  列在「生平時間軸：」之後，連結文字是「名字（生卒年）」，順序照 people.json（類別、再依出生）。
- timelines.json（戰爭、時代、學派等非人物時間軸）：規則相同，列在「相關時間軸：」之後，連結文字是時間軸標題，
  順序照 timelines.json（類別、再依最早日期）。兩種都有時分兩行。
一頁可以連到多條時間軸（例如學派頁）。所以要讓某頁出現或拿掉某條時間軸的連結，是去改 Timeline 那條時間軸的
related:，部署後再重跑這支腳本。

連結區塊以 <!--timeline-links--> … <!--/timeline-links--> 標記，重跑時會先整段移除再插入，
可重複執行；不再被任何時間軸 related 到的頁面，舊區塊也會一併移除。
插入位置：頁面最後面，也就是最後一個 </body> 之前（在 <footer> 之後）；沒有 </body> 就接在檔尾。
左側目錄是 nav{position:fixed…} 的頁面例外，放在最後一個 </main> 之前，否則會被目錄蓋住。
沿用原檔的換行（CRLF 或 LF），不會改動區塊以外的任何內容。

    python tools/add_timeline_links.py                  # 讀線上的 people.json 與 timelines.json 更新所有頁面
    python tools/add_timeline_links.py --check          # 只列出會變動的頁面，不寫檔
    python tools/add_timeline_links.py --source D:/Notes-Timeline/dist   # 改讀本機的 dist（Timeline 尚未部署時）
"""

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

BOOKS_ROOT = Path(__file__).resolve().parent.parent
HTML_ROOT = BOOKS_ROOT / 'html'
TIMELINE_SITE = 'https://liu-timeline.pages.dev'
BOOKS_HTML_URL = 'https://chad-liu.github.io/books/html/'
MARK_START, MARK_END = '<!--timeline-links-->', '<!--/timeline-links-->'

# 區塊本身加上它結尾的換行：插入時是「區塊＋換行」，移除時整段拿掉，原檔就完全還原
BLOCK_RE = re.compile(re.escape(MARK_START) + r'.*?' + re.escape(MARK_END) + r'\r?\n', re.S)
FIXED_NAV_RE = re.compile(r'(?<![\w.#-])nav\s*\{[^}]*position\s*:\s*fixed')
NAV_STYLE ='max-width:960px;margin:28px auto 0;padding:0 16px;text-align:center;font-size:14px;color:#475569'
LINK_STYLE = 'color:#1d4ed8;text-decoration:none;margin:0 6px;white-space:nowrap'


def quote_attr(url):
    # 只擋住會跳出屬性的引號；& 照原樣保留，輸出才會和改版前逐位元組相同
    return url.replace('"', '%22')


SECTIONS = (('people', '生平時間軸'), ('timelines', '相關時間軸'))


def block(links, nl):
    parts = []
    for kind, heading in SECTIONS:
        anchors = ''.join(
            f'<a href="{quote_attr(link["url"])}" target="_blank" rel="noopener" style="{LINK_STYLE}">{html.escape(link["label"])} ↗</a>'
            for link in links.get(kind, [])
        )
        if anchors:
            parts.append(f'{heading}：{anchors}')
    # 用 <div> 而不是 <nav>：不少頁面的 CSS 以 nav{position:fixed;left:0…} 排左側目錄、腳本以 querySelector('nav') 找目錄，
    # 用 <nav> 會被套上同樣的樣式而蓋住目錄
    return f'{MARK_START}<div class="timeline-links" style="{NAV_STYLE}">{"<br>".join(parts)}</div>{MARK_END}{nl}'


def updated(text, links):
    nl = '\r\n' if '\r\n' in text else '\n'
    text = BLOCK_RE.sub('', text)
    if not links:
        return text
    # 左側目錄是 position:fixed 的頁面，<main> 之外的內容會被目錄蓋住，所以放在 </main> 之前（主欄的最後面）
    i = text.rfind('</main>') if FIXED_NAV_RE.search(text) else -1
    if i < 0:
        i = text.rfind('</body>')
    if i >= 0:
        return text[:i] + block(links, nl) + text[i:]
    if not text.endswith('\n'):
        text += nl
    return text + block(links, nl)


def load_index(source, kind):
    """讀 <source>/<kind>.json 裡的 <kind> 陣列；source 是 Timeline 網站網址或本機資料夾。"""
    if source.startswith(('http://', 'https://')):
        # Cloudflare Pages 會擋 Python 預設的 "Python-urllib/x.y" User-Agent（回 403）
        req = urllib.request.Request(f'{source.rstrip("/")}/{kind}.json', headers={'User-Agent': 'books-timeline-links'})
        with urllib.request.urlopen(req) as res:
            return json.load(res)[kind]
    return json.loads((Path(source) / f'{kind}.json').read_text(encoding='utf-8'))[kind]


def pages_from(people, timelines):
    """html\\ 相對路徑 → {'people': [...], 'timelines': [...]}，每項是 {url, label}，依兩份索引各自的順序。"""
    pages = {}
    entries = [('people', p, f"{p['name']}（{p['years']}）") for p in people]
    entries += [('timelines', t, t['title']) for t in timelines]
    for kind, entry, label in entries:
        link = {'url': entry['url'], 'label': label}
        for related in entry.get('related', []):
            url = related['url']
            if url.startswith(BOOKS_HTML_URL):
                rel = urllib.parse.unquote(url[len(BOOKS_HTML_URL):].split('#')[0])
                bucket = pages.setdefault(rel, {}).setdefault(kind, [])
                if link not in bucket:
                    bucket.append(link)
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只列出會變動的頁面')
    ap.add_argument('--source', default=TIMELINE_SITE, help='Timeline 網站網址，或含 people.json 與 timelines.json 的本機資料夾')
    args = ap.parse_args()

    people = load_index(args.source, 'people')
    timelines = load_index(args.source, 'timelines')
    # 舊版 people.json 沒有 related，照跑會把所有頁面的連結區塊清光
    if not any('related' in p for p in people):
        raise SystemExit(f'{args.source} 的 people.json 沒有 related 欄位，不更新任何頁面')
    pages = pages_from(people, timelines)
    # 已經沒有人物 related 到、但頁面上還留著舊區塊的，也要清掉
    targets = set(pages) | {
        p.relative_to(HTML_ROOT).as_posix()
        for p in HTML_ROOT.rglob('*.html')
        if MARK_START in p.read_bytes().decode('utf-8', errors='ignore')
    }
    changed, missing = [], []
    for rel in sorted(targets):
        path = HTML_ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
        text = path.read_bytes().decode('utf-8')   # 不做換行轉換
        new = updated(text, pages.get(rel, {}))
        if new != text:
            changed.append(rel)
            if not args.check:
                path.write_bytes(new.encode('utf-8'))
    print(f'{"會更新" if args.check else "已更新"} {len(changed)} 個頁面')
    for rel in changed:
        print('  ' + rel)
    for rel in missing:
        print('  [找不到] ' + rel)


if __name__ == '__main__':
    main()
