"""在知識圖譜頁面加上「生平時間軸」連結，指向 Liu's Timeline（https://chad-liu.github.io/Timeline/）。

對應表在 tools/timeline_links.json：鍵是 html\\ 底下的相對路徑，值是該頁要連到的時間軸
（id 對應 Timeline 的 Data\\<id>.md，label 是顯示文字）。一頁可以連到多位人物，例如學派頁。

連結區塊以 <!--timeline-links--> … <!--/timeline-links--> 標記，重跑時會先整段移除再插入，
可重複執行；對應表裡拿掉某頁後重跑，該頁的區塊也會一併移除。
插入位置：頁面的 <footer> 之前；沒有 <footer> 的頁面放在 </body> 之前，兩者都沒有就接在檔尾。
沿用原檔的換行（CRLF 或 LF），不會改動區塊以外的任何內容。

    python tools/add_timeline_links.py          # 依對應表更新所有頁面
    python tools/add_timeline_links.py --check  # 只列出會變動的頁面，不寫檔
"""

import argparse
import html
import json
import re
from pathlib import Path

BOOKS_ROOT = Path(__file__).resolve().parent.parent
HTML_ROOT = BOOKS_ROOT / 'html'
MAP_FILE = Path(__file__).resolve().parent / 'timeline_links.json'
TIMELINE_URL = 'https://chad-liu.github.io/Timeline/#v=vertical&t='
MARK_START, MARK_END = '<!--timeline-links-->', '<!--/timeline-links-->'

# 區塊本身加上它結尾的換行：插入時是「區塊＋換行」，移除時整段拿掉，原檔就完全還原
BLOCK_RE = re.compile(re.escape(MARK_START) + r'.*?' + re.escape(MARK_END) + r'\r?\n', re.S)
NAV_STYLE = 'max-width:960px;margin:28px auto 0;padding:0 16px;text-align:center;font-size:14px;color:#475569'
LINK_STYLE = 'color:#1d4ed8;text-decoration:none;margin:0 6px;white-space:nowrap'


def block(people, nl):
    links = ''.join(
        f'<a href="{TIMELINE_URL}{html.escape(p["id"])}" target="_blank" rel="noopener" style="{LINK_STYLE}">{html.escape(p["label"])} ↗</a>'
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只列出會變動的頁面')
    args = ap.parse_args()

    pages = json.loads(MAP_FILE.read_text(encoding='utf-8'))['pages']
    # 對應表裡已經拿掉、但頁面上還留著舊區塊的，也要清掉
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
