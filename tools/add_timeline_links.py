"""在知識圖譜頁面加上「生平時間軸」連結，指向 Liu's Timeline（https://chad-liu.github.io/Timeline/）。

對應關係不另外維護，直接讀 Timeline 公開的人物索引 people.json：每位人物的 related 連結裡，
凡是指向本站 html\\ 頁面的，該頁就連回這位人物的時間軸。一頁可以連到多位人物（例如學派頁），
順序照 people.json（類別、再依出生）；連結文字是「名字（生卒年）」。
所以要讓某頁出現或拿掉某人的連結，是去改 Timeline 那條時間軸的 related:，部署後再重跑這支腳本。

連結區塊以 <!--timeline-links--> … <!--/timeline-links--> 標記，重跑時會先整段移除再插入，
可重複執行；不再被任何人物 related 到的頁面，舊區塊也會一併移除。
插入位置：頁面的 <footer> 之前；沒有 <footer> 的頁面放在 </body> 之前，兩者都沒有就接在檔尾。
沿用原檔的換行（CRLF 或 LF），不會改動區塊以外的任何內容。

    python tools/add_timeline_links.py                  # 讀線上的 people.json 更新所有頁面
    python tools/add_timeline_links.py --check          # 只列出會變動的頁面，不寫檔
    python tools/add_timeline_links.py --source D:/Notes-Timeline/dist/people.json   # 改讀本機檔案（Timeline 尚未部署時）
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
PEOPLE_URL = 'https://chad-liu.github.io/Timeline/people.json'
BOOKS_HTML_URL = 'https://chad-liu.github.io/books/html/'
MARK_START, MARK_END = '<!--timeline-links-->', '<!--/timeline-links-->'

# 區塊本身加上它結尾的換行：插入時是「區塊＋換行」，移除時整段拿掉，原檔就完全還原
BLOCK_RE = re.compile(re.escape(MARK_START) + r'.*?' + re.escape(MARK_END) + r'\r?\n', re.S)
NAV_STYLE = 'max-width:960px;margin:28px auto 0;padding:0 16px;text-align:center;font-size:14px;color:#475569'
LINK_STYLE = 'color:#1d4ed8;text-decoration:none;margin:0 6px;white-space:nowrap'


def quote_attr(url):
    # 只擋住會跳出屬性的引號；& 照原樣保留，輸出才會和改版前逐位元組相同
    return url.replace('"', '%22')


def block(people, nl):
    links = ''.join(
        f'<a href="{quote_attr(p["url"])}" target="_blank" rel="noopener" style="{LINK_STYLE}">{html.escape(p["label"])} ↗</a>'
        for p in people
    )
    return f'{MARK_START}<nav class="timeline-links" style="{NAV_STYLE}">生平時間軸：{links}</nav>{MARK_END}{nl}'


def updated(text, people):
    nl = '\r\n' if '\r\n' in text else '\n'
    text = BLOCK_RE.sub('', text)
    if not people:
        return text
    for marker in ('<footer', '</body>'):
        i = text.find(marker)
        if i >= 0:
            return text[:i] + block(people, nl) + text[i:]
    if not text.endswith('\n'):
        text += nl
    return text + block(people, nl)


def load_people(source):
    if source.startswith(('http://', 'https://')):
        with urllib.request.urlopen(source) as res:
            return json.load(res)['people']
    return json.loads(Path(source).read_text(encoding='utf-8'))['people']


def pages_from(people):
    """html\\ 相對路徑 → 連到該頁的人物（{url, label}），依 people.json 的順序。"""
    pages = {}
    for person in people:
        link = {'url': person['url'], 'label': f"{person['name']}（{person['years']}）"}
        for related in person.get('related', []):
            url = related['url']
            if url.startswith(BOOKS_HTML_URL):
                rel = urllib.parse.unquote(url[len(BOOKS_HTML_URL):].split('#')[0])
                if link not in pages.setdefault(rel, []):
                    pages[rel].append(link)
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只列出會變動的頁面')
    ap.add_argument('--source', default=PEOPLE_URL, help='people.json 的網址或本機路徑')
    args = ap.parse_args()

    people = load_people(args.source)
    # 舊版 people.json 沒有 related，照跑會把所有頁面的連結區塊清光
    if not any('related' in p for p in people):
        raise SystemExit(f'{args.source} 沒有 related 欄位，不更新任何頁面')
    pages = pages_from(people)
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
        new = updated(text, pages.get(rel, []))
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
