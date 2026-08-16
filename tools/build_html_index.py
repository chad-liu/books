#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依 Plan2.md 規劃，用 D:\\Books\\html\\ 底下的資料夾重建根目錄 index.html。

規則：
  * html\\ 的每個子資料夾是一張卡片，依資料夾名稱升冪排序
  * 卡片內的條目順序依同資料夾內 order.md 的順序，用 <ol> 顯示流水序號
  * order.md 每行若為「標籤(https://...)」格式視為外部連結；
    否則視為本機檔名（不含 .html），連到同資料夾的 <檔名>.html
  * 沒有 order.md 的資料夾略過，不產生卡片（沒有依據可以排序內容）

用法：
    python tools/build_html_index.py
"""

import re
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOOKS_ROOT = Path(__file__).resolve().parent.parent
HTML_ROOT = BOOKS_ROOT / 'html'
OUT = BOOKS_ROOT / 'index.html'

URL_RE = re.compile(r'^(?P<label>.*?)\((?P<url>https?://[^\s()]+)\)\s*$')

CSS = """*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1a2e;color:#e8d5b7;font-family:"Noto Serif TC","Microsoft JhengHei",serif;
line-height:1.7;padding-bottom:60px}
header{background:linear-gradient(135deg,#0f3460,#16213e);padding:28px 32px 22px;
border-bottom:2px solid #c9a94f;position:sticky;top:0;z-index:50}
h1{color:#c9a94f;font-size:1.7rem;letter-spacing:.08em}
.sub{color:#9ba4b4;font-size:.9rem;margin-top:6px}
.tools{margin-top:16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
#cat{background:#16213e;border:1px solid #2d4a7a;border-radius:6px;color:#c9a94f;
padding:9px 13px;font-size:.95rem;font-family:inherit;cursor:pointer;min-width:190px}
#cat:focus{outline:none;border-color:#c9a94f}
#cat option{background:#16213e;color:#e8d5b7}
#q{flex:1;min-width:220px;max-width:420px;background:#16213e;border:1px solid #2d4a7a;
border-radius:6px;color:#e8d5b7;padding:9px 13px;font-size:.95rem;font-family:inherit}
#q:focus{outline:none;border-color:#c9a94f}
#q::placeholder{color:#6b7688}
.hint{color:#9ba4b4;font-size:.82rem}
.empty{color:#6b7688;text-align:center;padding:50px;display:none}
main{padding:8px 32px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:16px;margin-top:24px}
.card{background:#16213e;border:1px solid #24365c;border-radius:9px;padding:15px 17px;
display:flex;flex-direction:column;transition:border-color .15s,transform .15s}
.card:hover{border-color:#c9a94f;transform:translateY(-2px)}
.card h3{font-size:1.1rem;margin-bottom:9px;color:#c9a94f}
.card h3 .cnt{color:#9ba4b4;font-size:.78rem;font-weight:400;margin-left:7px}
ol{list-style-position:inside;font-size:.9rem;padding-left:.2rem}
li{padding:3px 0;border-bottom:1px dashed #21304f}
li:last-child{border-bottom:none}
li::marker{color:#6b7688}
li a{color:#b8c5d6;text-decoration:none;display:inline;padding:2px 4px;border-radius:4px}
li a:hover{background:#1e3a5f;color:#c9a94f}
li a.ext::after{content:" ↗";color:#6b7688;font-size:.75rem}
footer{color:#6b7688;font-size:.8rem;padding:34px 32px 0;text-align:center}
@media(max-width:600px){header{padding:20px}main{padding:8px 16px}}
"""


def local_href(folder_name, filename):
    return 'html/' + quote(folder_name) + '/' + quote(filename) + '.html'


def parse_order(folder):
    order_file = folder / 'order.md'
    if not order_file.exists():
        return None

    html_files = {p.stem for p in folder.glob('*.html')}
    items = []
    for raw in order_file.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r'[-=—_]{3,}', line):
            continue  # 純分隔線，用來把 order.md 排版成幾個小節，不是條目
        m = URL_RE.match(line)
        if m:
            label = m.group('label').strip() or m.group('url')
            items.append({'label': label, 'href': m.group('url'), 'external': True})
            continue
        if line not in html_files:
            print('[警告] %s/order.md 列了「%s」但資料夾內找不到對應的 .html 檔，已略過'
                  % (folder.name, line))
            continue
        items.append({'label': line, 'href': local_href(folder.name, line), 'external': False})
    return items


def build():
    cards = []
    for folder in sorted(p for p in HTML_ROOT.iterdir() if p.is_dir()):
        items = parse_order(folder)
        if items is None:
            print('[略過] %s 沒有 order.md' % folder.name)
            continue
        cards.append((folder.name, items))

    total_items = sum(len(items) for _, items in cards)

    out = ['<!DOCTYPE html>', '<html lang="zh-TW">', '<head>', '<meta charset="UTF-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1.0">',
           '<title>Liu的雲端閱讀</title>', '<style>', CSS, '</style>',
           '</head>', '<body>', '<header>', '<h1>Liu的雲端閱讀</h1>',
           '<div class="sub">%d 個分類 · %d 個項目</div>' % (len(cards), total_items),
           '<div class="tools">']

    out.append('<select id="cat"><option value="">📂 跳到分類…</option>')
    for i, (name, items) in enumerate(cards):
        out.append('<option value="cat-%d">%s（%d 項）</option>' % (i, escape(name), len(items)))
    out.append('</select>')

    out += ['<input id="q" type="search" placeholder="搜尋條目或分類…（按 / 快速聚焦）" autocomplete="off">',
            '<span class="hint">Esc 清除</span>', '</div>', '</header>',
            '<main>', '<div class="grid">']

    for i, (name, items) in enumerate(cards):
        out.append('<article class="card" id="cat-%d" data-name="%s">' % (i, escape(name)))
        out.append('<h3>%s<span class="cnt">%d 項</span></h3>' % (escape(name), len(items)))
        out.append('<ol>')
        for it in items:
            cls = ' ext' if it['external'] else ''
            out.append('<li data-t="%s"><a class="%s" href="%s" target="_blank" rel="noopener">%s</a></li>'
                       % (escape(it['label']), cls.strip(), escape(it['href']), escape(it['label'])))
        out.append('</ol></article>')

    out += ['</div>', '<div class="empty">找不到符合的項目</div>', '</main>',
            '<footer>檔案位置：%s\\　·　依 html\\ 各資料夾的 order.md 排序</footer>'
            % escape(str(BOOKS_ROOT)),
            """<script>
var cat = document.getElementById('cat');
var q = document.getElementById('q');

function run() {
  var t = q.value.trim().toLowerCase();
  var shown = 0;
  document.querySelectorAll('.card').forEach(function (c) {
    var hitCard = c.dataset.name.toLowerCase().indexOf(t) >= 0;
    var any = hitCard;
    c.querySelectorAll('li').forEach(function (li) {
      var hit = !t || hitCard || li.dataset.t.toLowerCase().indexOf(t) >= 0;
      li.style.display = hit ? '' : 'none';
      if (hit) any = true;
    });
    c.style.display = (!t || any) ? '' : 'none';
    if (!t || any) shown++;
  });
  document.querySelector('.empty').style.display = shown ? 'none' : 'block';
}
q.addEventListener('input', run);
document.addEventListener('keydown', function (e) {
  if (e.key === '/' && document.activeElement !== q) { e.preventDefault(); q.focus(); }
  if (e.key === 'Escape') { q.value = ''; run(); q.blur(); }
});

cat.addEventListener('change', function () {
  var card = document.getElementById(cat.value);
  if (!card) return;
  // 搜尋條件可能正把該分類整張卡片藏起來，先清掉才跳得過去
  if (q.value.trim()) { q.value = ''; run(); }
  var top = card.getBoundingClientRect().top + window.pageYOffset
            - document.querySelector('header').offsetHeight - 8;
  window.scrollTo(0, Math.max(0, top));
  cat.selectedIndex = 0;
});
</script>""",
            '</body>', '</html>']

    OUT.write_text('\n'.join(out), encoding='utf-8')
    print('\n已產生 %s（%d 個分類、%d 個項目）' % (OUT, len(cards), total_items))


if __name__ == '__main__':
    build()
