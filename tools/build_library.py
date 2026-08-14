#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 D:\\Books\\epub 底下的電子書批次轉成 D:\\Books\\reader 底下的 HTML 閱讀器。

規則（依 plan1.md 與使用者確認）：
  * 每一本 .epub 各自產生一個單書閱讀器 HTML（html-reader-maker skill）
  * 只有「同一本書的分冊」（上/中/下、卷一~卷四、第N冊…）才合併成一個書架 HTML
    （multi-book-shelf skill）
  * 來源已經是 .html 的檔案不轉換，直接複製過去
  * reader\\ 的資料夾結構與 epub\\ 完全一致
  * 以 .manifest.json 記錄每個輸出對應的來源檔與 mtime/size，之後新增書籍時
    重跑本腳本只會處理新增或異動的部分

用法：
    python tools/build_library.py --plan                 # 只列出計畫，不轉檔
    python tools/build_library.py --only "2.哲學類"      # 只處理某個類別
    python tools/build_library.py                        # 全量（增量）轉換
    python tools/build_library.py --force                # 忽略 manifest 重轉
    python tools/build_library.py --index-only           # 只重建 reader/index.html
"""

import argparse
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import time
from html import escape
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BOOKS_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = BOOKS_ROOT / 'epub'
DST_ROOT = BOOKS_ROOT / 'reader'
MANIFEST = DST_ROOT / '.manifest.json'
LOG_PATH = BOOKS_ROOT / 'tools' / 'build_library.log'
CHANGELOG = BOOKS_ROOT / 'tools' / 'library_changes.md'

SKILLS = Path(os.path.expanduser('~')) / '.claude' / 'skills'
READER_RUN = SKILLS / 'html-reader-maker' / 'scripts' / 'run.py'
SHELF_RUN = SKILLS / 'multi-book-shelf' / 'scripts' / 'run.py'


# ---------------------------------------------------------------- 分冊偵測

CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7,
          '八': 8, '九': 9, '十': 10}

# 只有檔名裡出現「明確的分冊標記」才會被視為同一本書的分冊候選，
# 避免把「中國小說」「下流社會」這種標題誤判成卷冊。
VOL_PATTERNS = [
    re.compile(r'[（(【\[]\s*([上中下])\s*[）)】\]：:，,]'),   # （上）、（上：古代）
    re.compile(r'([上中下])[冊卷篇部]'),                       # 上卷、下冊
    re.compile(r'卷([一二三四五六七八九十]+|\d+)'),            # 卷一、卷2
    re.compile(r'第([一二三四五六七八九十]+|\d+)[冊卷部集]'),  # 第三冊
    # 《三體》I：地球往事 — 羅馬數字後面必須緊接冒號，避免誤判一般書名
    re.compile(r'(?:^|[》\]）)\s])\s*(I{1,3}|IV|VI{0,3}|IX|X)\s*[：:]'),
]

ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
         'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10}


def cn_to_int(text):
    if text.isdigit():
        return int(text)
    if text == '十':
        return 10
    if len(text) == 1:
        return CN_NUM.get(text, 99)
    if text.startswith('十'):
        return 10 + CN_NUM.get(text[1], 0)
    if '十' in text:
        head, tail = text.split('十', 1)
        return CN_NUM.get(head, 0) * 10 + (CN_NUM.get(tail, 0) if tail else 0)
    return 99


def volume_number(stem):
    """回傳這個檔名的分冊序號；沒有分冊標記則回傳 None。"""
    for pat in VOL_PATTERNS:
        m = pat.search(stem)
        if not m:
            continue
        token = m.group(1)
        if token in ('上', '中', '下'):
            return {'上': 1, '中': 2, '下': 3}[token]
        if token in ROMAN:
            return ROMAN[token]
        return cn_to_int(token)
    return None


def longest_common_substring(a, b):
    if not a or not b:
        return ''
    prev = [0] * (len(b) + 1)
    best, best_end = 0, 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, best_end = cur[j], i
        prev = cur
    return a[best_end - best:best_end]


def clean_series_name(name):
    """把共同子字串整理成適合當檔名的系列名。"""
    name = re.sub(r'^\s*\d+\s*[.、．]\s*', '', name).strip()
    name = name.strip(' 　:：-—～~、,，（(【[')
    name = name.rstrip(' 　:：-—～~、,，）)】]')
    name = re.sub(r'\s*(?:I{1,3}|IV|VI{0,3}|IX|X)$', '', name)
    name = re.sub(r'[卷冊部集篇]$', '', name).rstrip(' 　:：-—～~、,，')
    # 主標題通常在第一個冒號之前，太長時只留主標題
    if len(name) > 24:
        head = re.split(r'[：:]', name, maxsplit=1)[0].strip()
        if len(head) >= 4:
            name = head
    return name.strip()


def group_volumes(epubs):
    """把同一資料夾內的 epub 分成 [(系列名, [路徑,...]), ...] 與單本清單。

    只有同時具備分冊標記、且書名主體有 >=4 字共同子字串的檔案才會成組。
    """
    candidates = [p for p in epubs if volume_number(p.stem) is not None]
    singles = [p for p in epubs if volume_number(p.stem) is None]

    groups = []
    used = set()
    for i, a in enumerate(candidates):
        if a in used:
            continue
        members = [a]
        common = a.stem
        for b in candidates[i + 1:]:
            if b in used:
                continue
            lcs = longest_common_substring(common, b.stem)
            lcs_clean = clean_series_name(lcs)
            if len(lcs_clean) >= 4:
                members.append(b)
                common = lcs
        if len(members) >= 2:
            members.sort(key=lambda p: (volume_number(p.stem), p.name))
            used.update(members)
            groups.append((clean_series_name(common), members))
        else:
            singles.append(a)

    singles.sort(key=lambda p: p.name)
    return groups, singles


# ---------------------------------------------------------------- 工作規劃

def sig(paths):
    """來源檔案的指紋：路徑 + mtime + size。

    來源在批次執行途中被搬走／刪掉時回傳 None（代表指紋不可信），
    讓那一項自己失敗就好，不要讓整批中斷。
    """
    items = []
    for p in sorted(paths):
        try:
            st = p.stat()
        except OSError:
            return None
        items.append([str(p.relative_to(SRC_ROOT)), int(st.st_mtime), st.st_size])
    return items


TW_ENABLED = False          # 由 --to-tw 開啟；預設不做簡繁轉換
skipped_simplified = []     # 這次略過的簡體書，跑完列出來讓使用者知道
SERIES_FILE = BOOKS_ROOT / 'tools' / 'series.json'


def manual_series(rel):
    """讀 series.json 取得這個資料夾要手動合併的分冊。

    自動偵測刻意保守（兩本都要有明確卷冊標記），像「好音樂的科學 I」這種
    標記不明確的系列就在設定檔裡指定，不必為了個案放寬規則、
    連帶讓「AI：…」之類的書名被誤判成第一冊。
    """
    if not SERIES_FILE.exists():
        return []
    try:
        conf = json.loads(SERIES_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        print('[警告] series.json 讀取失敗，這次略過手動分冊設定：%s' % e)
        return []
    return [g for g in conf.get(str(rel), []) if isinstance(g, dict)]


def plan_jobs(only=None):
    jobs = []
    skipped_simplified.clear()
    for dirpath, dirnames, filenames in os.walk(SRC_ROOT):
        dirnames.sort()
        cur = Path(dirpath)
        rel = cur.relative_to(SRC_ROOT)
        if only and not (str(rel) == only or str(rel).startswith(only + os.sep)):
            continue

        epubs = sorted([cur / f for f in filenames if f.lower().endswith('.epub')])
        htmls = sorted([cur / f for f in filenames if f.lower().endswith('.html')])
        out_dir = DST_ROOT / rel

        for h in htmls:
            jobs.append({'kind': 'copy', 'rel': str(rel), 'name': h.stem,
                         'sources': [h], 'output': out_dir / h.name})

        # plan1.md：「若已 html 不必轉換」。同資料夾已經有同名的 .html 時，
        # 那本 epub 就不再轉一次 —— 否則兩個工作會產出同一個檔名，
        # 後跑的 reader 會把現成的 html 蓋掉。
        done_stems = {h.stem for h in htmls}
        epubs = [p for p in epubs if p.stem not in done_stems]

        # 簡體書預設整本略過，不進書庫也不上首頁；
        # 只有明確加 --to-tw 時才會轉成繁體收進來
        if not TW_ENABLED:
            kept = []
            for p in epubs:
                (skipped_simplified if is_simplified(p) else kept).append(p)
            epubs = kept

        # 手動指定的分冊優先，剩下的才交給自動偵測
        groups = []
        by_name = {p.name: p for p in epubs}
        for g in manual_series(rel):
            picked = [by_name[n] for n in g.get('members', []) if n in by_name]
            missing = [n for n in g.get('members', []) if n not in by_name]
            if missing:
                print('[警告] series.json「%s」找不到：%s' % (g.get('name'), '、'.join(missing)))
            if len(picked) >= 2:
                groups.append((g.get('name') or picked[0].stem, picked))
                epubs = [p for p in epubs if p not in picked]

        auto_groups, singles = group_volumes(epubs)
        groups += auto_groups
        for series, members in groups:
            tw = TW_ENABLED and any(is_simplified(m) for m in members)
            name = to_tw(series) if tw else series
            fname = '%s（全%d冊）.html' % (name, len(members))
            jobs.append({'kind': 'shelf', 'rel': str(rel), 'name': name, 'tw': tw,
                         'sources': members, 'output': out_dir / fname})
        for p in singles:
            tw = TW_ENABLED and is_simplified(p)
            name = to_tw(p.stem) if tw else p.stem
            jobs.append({'kind': 'reader', 'rel': str(rel), 'name': name, 'tw': tw,
                         'sources': [p], 'output': out_dir / (name + '.html')})
    return jobs


# ---------------------------------------------------------------- 簡繁轉換

ZH_CACHE = DST_ROOT / '.zh.json'
_zh_cache = None
_cc = {}
TAG_RE = re.compile(r'<[^>]+>')


def _opencc(config):
    if config not in _cc:
        try:
            from opencc import OpenCC
        except ImportError:
            raise SystemExit('需要 opencc：pip install opencc-python-reimplemented')
        _cc[config] = OpenCC(config)
    return _cc[config]


def to_tw(text):
    """簡體 → 繁體（台灣用語，s2twp 會一併處理詞彙差異，例如 软件→軟體）。"""
    return _opencc('s2twp').convert(text)


def _epub_sample(epub, limit=20000):
    import zipfile
    parts = []
    try:
        with zipfile.ZipFile(epub) as z:
            names = [n for n in z.namelist()
                     if n.lower().endswith(('.xhtml', '.html', '.htm'))]
            for n in names[:12]:
                try:
                    parts.append(TAG_RE.sub(' ', z.read(n).decode('utf-8', 'replace')))
                except Exception:
                    continue
                if sum(len(x) for x in parts) > limit:
                    break
    except Exception:
        return ''
    return ' '.join(parts)


def is_simplified(epub):
    """內文有多少比例的字經 s2t 會變動；實測簡體書都在 23% 以上，
    繁體書在 2% 以下（少數異體字），中間有很大的空隙，門檻取 10%。"""
    global _zh_cache
    if _zh_cache is None:
        _zh_cache = json.loads(ZH_CACHE.read_text(encoding='utf-8')) if ZH_CACHE.exists() else {}

    st = epub.stat()
    key = '%s|%d|%d' % (epub.relative_to(SRC_ROOT), int(st.st_mtime), st.st_size)
    if key in _zh_cache:
        return _zh_cache[key]

    cjk = [c for c in _epub_sample(epub) if '一' <= c <= '鿿']
    if len(cjk) < 300:
        ratio = 0.0
    else:
        s = ''.join(cjk)
        t = _opencc('s2t').convert(s)
        ratio = sum(1 for a, b in zip(s, t) if a != b) / len(s)

    _zh_cache[key] = ratio > 0.10
    return _zh_cache[key]


def save_zh_cache():
    if _zh_cache is not None:
        DST_ROOT.mkdir(parents=True, exist_ok=True)
        ZH_CACHE.write_text(json.dumps(_zh_cache, ensure_ascii=False, indent=1),
                            encoding='utf-8')


HAN_RUN = re.compile(r'[㐀-鿿豈-﫿]+')
HAN_TAIL = re.compile(r'[㐀-鿿豈-﫿]+$')


TEXT_FIXES_FILE = BOOKS_ROOT / 'tools' / 'text_fixes.json'
_text_fixes = None


def text_fixes(key):
    """讀 text_fixes.json 取得這個輸出檔要套用的字串替換。"""
    global _text_fixes
    if _text_fixes is None:
        _text_fixes = {}
        if TEXT_FIXES_FILE.exists():
            try:
                conf = json.loads(TEXT_FIXES_FILE.read_text(encoding='utf-8'))
                _text_fixes = {k: v for k, v in conf.items() if not k.startswith('_')}
            except Exception as e:
                print('[警告] text_fixes.json 讀取失敗，這次不套用內文修正：%s' % e)
    return [(a, b) for a, b in _text_fixes.get(key, []) if a]


def apply_text_fixes(out, fixes, chunk=4 * 1024 * 1024):
    """分段替換內文字串。跟簡繁轉換一樣不整份讀進記憶體，
    圖多的書單一行就可能好幾百 MB。"""
    keep = max(len(a) for a, _ in fixes) - 1   # 分段邊界可能切斷待替換字串
    tmp = out.with_name(out.name + '.fixtmp')
    carry = ''
    with open(out, 'r', encoding='utf-8', errors='replace') as fin, \
            open(tmp, 'w', encoding='utf-8') as fout:
        while True:
            buf = fin.read(chunk)
            if not buf:
                break
            buf = carry + buf
            if keep and len(buf) > keep:
                carry, buf = buf[-keep:], buf[:-keep]
            else:
                carry = ''
            for a, b in fixes:
                buf = buf.replace(a, b)
            fout.write(buf)
        for a, b in fixes:
            carry = carry.replace(a, b)
        fout.write(carry)
    tmp.replace(out)


def convert_output_to_tw(out, chunk=4 * 1024 * 1024):
    """把產出的 HTML 轉繁，分段處理、只轉漢字串。

    不能整份讀進來丟給 OpenCC：圖多的書單一行就可能到 388 MB
    （章節資料和 base64 圖片全擠在同一行），整份轉換會把記憶體吃爆。
    改成固定大小分段，而且只對漢字串呼叫 OpenCC —— base64 與標籤都是
    ASCII，正規表示式直接略過，不會白白掃過幾百 MB。
    """
    cc = _opencc('s2twp')
    sub = lambda s: HAN_RUN.sub(lambda m: cc.convert(m.group()), s)
    tmp = out.with_name(out.name + '.twtmp')
    carry = ''
    with open(out, 'r', encoding='utf-8', errors='replace') as fin, \
            open(tmp, 'w', encoding='utf-8') as fout:
        while True:
            buf = fin.read(chunk)
            if not buf:
                break
            buf = carry + buf
            # 分段邊界剛好落在漢字串中間時，留到下一段再一起轉，
            # 否則「軟體」這類詞彙轉換會被切斷而失效
            m = HAN_TAIL.search(buf)
            if m:
                carry, buf = m.group(), buf[:m.start()]
            else:
                carry = ''
            fout.write(sub(buf))
        if carry:
            fout.write(sub(carry))
    tmp.replace(out)


# ---------------------------------------------------------------- 書目資訊

def epub_meta(path):
    """直接從 EPUB 的 OPF 讀出書名與作者（不必解析整本書，很快）。"""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            container = z.read('META-INF/container.xml').decode('utf-8', 'replace')
            m = re.search(r'full-path="([^"]+)"', container)
            if not m:
                return path.stem, ''
            opf = z.read(m.group(1)).decode('utf-8', 'replace')
    except Exception:
        return path.stem, ''

    def pick(tag):
        mm = re.search(r'<dc:%s[^>]*>(.*?)</dc:%s>' % (tag, tag), opf, re.S)
        if not mm:
            mm = re.search(r'<%s[^>]*>(.*?)</%s>' % (tag, tag), opf, re.S)
        return re.sub(r'\s+', ' ', mm.group(1)).strip() if mm else ''

    return clean_title(pick('title'), path.stem), pick('creator')


TITLES_FILE = BOOKS_ROOT / 'tools' / 'titles.json'
_title_overrides = None


def title_overrides():
    global _title_overrides
    if _title_overrides is None:
        _title_overrides = {}
        if TITLES_FILE.exists():
            try:
                conf = json.loads(TITLES_FILE.read_text(encoding='utf-8'))
                _title_overrides = {k: v for k, v in conf.items()
                                    if not k.startswith('_') and isinstance(v, str)}
            except Exception as e:
                print('[警告] titles.json 讀取失敗，這次不套用書名修正：%s' % e)
    return _title_overrides


def clean_title(title, stem):
    """EPUB metadata 的書名常帶館藏編號或行銷用的版本括號，整理成適合列表顯示的樣子。"""
    if not title:
        return stem
    t = re.sub(r'^[A-Za-z]{1,2}\d{3,}[\s_-]+', '', title).strip()   # Y0035 初期大乘…
    t = re.sub(r'[_-]\d{5,}$', '', t).strip()                       # 手衝一杯好咖啡_13804904
    t = re.sub(r'【[^】]*】', '', t).strip()                          # 【全新修訂版】
    t = re.sub(r'[（(][^）)]*(?:版|套書|增訂|修訂|不分)[^）)]*[）)]\s*$', '', t).strip()
    if not t:
        return stem
    # metadata 只給了主標題、檔名其實更完整時（「一本就通」← 「一本就通 西方哲學史」）改用檔名；
    # 但檔名長很多通常是夾雜來源雜訊（「… by 傅佩荣 (z-lib.org)」），那就維持 metadata
    if t in stem and 0 < len(stem) - len(t) <= 6:
        t = stem
    return title_overrides().get(t, t)


SHELF_ITEM_RE = re.compile(
    r'<div class="shelf-item" data-book="(b\d+)"[^>]*>'
    r'<div class="shelf-item-title">(.*?)</div>'
    r'(?:<div class="shelf-item-author">(.*?)</div>)?', re.S)


def html_books(path):
    """從既有的 HTML（複製過來的書架或單書閱讀器）反查裡面有哪些書。"""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return [{'title': path.stem, 'author': '', 'anchor': ''}]

    ov = title_overrides()
    items = [{'title': ov.get(re.sub(r'<[^>]+>', '', t).strip(),
                              re.sub(r'<[^>]+>', '', t).strip()),
              'author': re.sub(r'<[^>]+>', '', a or '').strip(),
              'anchor': '#' + bid}
             for bid, t, a in SHELF_ITEM_RE.findall(text)]
    if items:
        return items

    m = re.search(r'<div class="header-title">(.*?)</div>', text, re.S)
    a = re.search(r'<div class="header-author">(.*?)</div>', text, re.S)
    title = (m.group(1).strip() if m else path.stem)
    return [{'title': ov.get(title, title),
             'author': (a.group(1).strip() if a else ''),
             'anchor': ''}]


def job_books(job):
    """這個輸出檔裡收了哪些書（給首頁列清單用）。"""
    if job['kind'] == 'copy':
        return html_books(job['sources'][0])
    books = []
    for i, src in enumerate(job['sources']):
        title, author = epub_meta(src)
        books.append({'title': title, 'author': author,
                      'anchor': '#b%d' % i if job['kind'] == 'shelf' else ''})
    return books


# ---------------------------------------------------------------- 產出後加工

BACK_LINK_CSS = """<style>
.lib-back{position:fixed;left:12px;bottom:12px;z-index:200;background:#0f3460;color:#c9a94f;
border:1px solid #2d4a7a;border-radius:6px;padding:6px 12px;font-size:.85rem;text-decoration:none;
font-family:"Noto Sans TC","Microsoft JhengHei",sans-serif;opacity:.85}
.lib-back:hover{opacity:1;background:#1e3a5f}
</style>"""

HASH_SCRIPT = """<script>
(function () {
  function pick() {
    var m = /^#(b\\d+)$/.exec(window.location.hash || '');
    if (m && typeof books !== 'undefined' && books[m[1]]) { selectBook(m[1]); return true; }
    return false;
  }
  // 註冊在樣板自己的 load listener 之後，用來覆蓋「預設開第一本」
  window.addEventListener('load', pick);
  window.addEventListener('hashchange', pick);
})();
</script>"""

DARK_SCRIPT = """<script>
// 註冊在樣板自己的 load listener 之後，所以開書時預設就是夜間模式
// （toggleNight 會一併把工具列按鈕文字換成「☀️ 日間」，狀態不會不同步）
window.addEventListener('load', function () {
  if (typeof toggleNight === 'function' && !document.body.classList.contains('night-mode')) {
    toggleNight();
  }
});
</script>"""

PATCH_PREFIX = '<!--library-patch'
PATCH_MARK = PATCH_PREFIX + ' v2-->'


def patch_output(out, is_shelf=None):
    """加上「← 書庫」返回連結、預設夜間模式；書架另外支援 #bN 深連結。

    is_shelf 給 None 時直接看檔案內容判斷，這樣單獨重貼 patch 時
    不需要 job 資訊也能正確處理。
    """
    text = out.read_text(encoding='utf-8', errors='replace')
    if is_shelf is None:
        is_shelf = 'function selectBook' in text

    # 舊版 patch 整塊拿掉再重貼，避免改版後新舊兩份並存
    i = text.find(PATCH_PREFIX)
    if i != -1:
        j = text.find('</body>', i)
        text = text[:i] + (text[j:] if j != -1 else '')

    depth = len(out.relative_to(DST_ROOT).parts) - 1
    back = '../' * depth + 'index.html'
    patch = '\n'.join([PATCH_MARK, BACK_LINK_CSS,
                       '<a class="lib-back" href="%s">← 書庫</a>' % back, DARK_SCRIPT]
                      + ([HASH_SCRIPT] if is_shelf else []))
    if '</body>' in text:
        text = text.replace('</body>', patch + '\n</body>', 1)
    else:
        text += patch
    out.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------- 執行

# skill 會把輸出檔名 print 出來；子行程的 stdout 預設是系統 ANSI（Windows 上是 cp950），
# 遇到簡體字或日文中點的檔名會在最後一行 UnicodeEncodeError，讓整本書被誤判成失敗。
CHILD_ENV = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')


def run_reader(src, out):
    cmd = [sys.executable, str(READER_RUN), 'main.py',
           '--input', str(src), '--output', str(out)]
    # titles.json 有指定修正時，連閱讀器頁首的書名一起換掉，
    # 才不會首頁寫「手沖」、打開書卻是「手衝」
    raw, _ = epub_meta(src)
    if raw in title_overrides().values():
        cmd += ['--title', raw]
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=CHILD_ENV)


def run_shelf(srcs, out):
    return subprocess.run(
        [sys.executable, str(SHELF_RUN), 'main.py',
         '--inputs'] + [str(s) for s in srcs] + ['--output', str(out)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        env=CHILD_ENV)


def build(jobs, manifest, force=False, log=None):
    done = skipped = failed = 0
    total = len(jobs)
    for i, job in enumerate(jobs, 1):
        out = job['output']
        key = str(out.relative_to(DST_ROOT))
        cur_sig = sig(job['sources'])

        if cur_sig is None:
            failed += 1
            msg = '      SKIP %s（來源檔已不存在）' % key
            print(msg, flush=True)
            if log:
                log.write(msg + '\n')
            continue

        prev = manifest.get(key, {})
        # 也要比對 tw：書名本來就是繁體、只有內文是簡體的書，輸出檔名不會變，
        # 光比對來源指紋的話會被當成沒異動而永遠跳過、轉不到繁體
        # tw 要用 bool() 正規化再比：加這個欄位之前建立的紀錄沒有 tw 鍵，
        # 直接比 None != False 會讓整個書庫每一本都被判定成有異動而重跑
        if (not force and out.exists() and prev.get('sources') == cur_sig
                and bool(prev.get('tw')) == bool(job.get('tw'))):
            skipped += 1
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        started = time.time()
        print('[%d/%d] %s  %s' % (i, total, job['kind'], key), flush=True)

        if job['kind'] == 'copy':
            shutil.copy2(job['sources'][0], out)
            rc, err = 0, ''
        elif job['kind'] == 'shelf':
            r = run_shelf(job['sources'], out)
            rc, err = r.returncode, (r.stderr or '')[-800:]
        else:
            r = run_reader(job['sources'][0], out)
            rc, err = r.returncode, (r.stderr or '')[-800:]

        if rc == 0 and out.exists():
            books = job_books(job)
            if job.get('tw'):
                convert_output_to_tw(out)
                books = [{'title': to_tw(b['title']), 'author': to_tw(b['author']),
                          'anchor': b['anchor']} for b in books]
                print('      簡→繁 已轉換', flush=True)
            fixes = text_fixes(key)
            if fixes:
                apply_text_fixes(out, fixes)
                books = [dict(b, title=functools.reduce(
                    lambda s, ab: s.replace(*ab), fixes, b['title'])) for b in books]
                print('      內文修正 %d 條已套用' % len(fixes), flush=True)
            patch_output(out, is_shelf=(job['kind'] != 'reader'))
            manifest[key] = {
                'kind': job['kind'],
                'name': job['name'],
                'sources': cur_sig,
                'tw': bool(job.get('tw')),
                'size': out.stat().st_size,
                'books': books,
                'built': int(time.time()),
            }
            done += 1
            print('      OK  %.1fs  %.1f MB' % (time.time() - started,
                                                out.stat().st_size / 1048576), flush=True)
        else:
            failed += 1
            msg = '      FAIL %s\n%s' % (key, err)
            print(msg, flush=True)
            if log:
                log.write(msg + '\n')
            manifest.pop(key, None)

        if i % 10 == 0:
            save_manifest(manifest)

    return done, skipped, failed


def save_manifest(manifest):
    DST_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                        encoding='utf-8')


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding='utf-8'))
    return {}


def snapshot(manifest):
    """跑之前先記下每個輸出的書名與來源指紋，跑完拿來比對出增／減／更新。"""
    return {k: {'name': v.get('name', ''),
                'books': [b.get('title', '') for b in (v.get('books') or [])],
                'sources': v.get('sources')}
            for k, v in manifest.items()}


def write_changelog(before, manifest, note=''):
    """把這一次執行造成的書籍增減寫進 tools/library_changes.md。"""
    added = sorted(k for k in manifest if k not in before)
    removed = sorted(k for k in before if k not in manifest)
    updated = sorted(k for k in manifest
                     if k in before and before[k]['sources'] != manifest[k].get('sources'))
    if not (added or removed or updated):
        return 0

    def names(key, src):
        info = src[key]
        titles = info.get('books') or []
        if isinstance(titles, list) and titles and isinstance(titles[0], dict):
            titles = [b.get('title', '') for b in titles]
        return titles or [info.get('name') or Path(key).stem]

    lines = ['', '## %s%s' % (time.strftime('%Y-%m-%d %H:%M'),
                              ('　—　' + note) if note else '')]
    for label, keys, src in (('新增', added, manifest),
                             ('移除', removed, before),
                             ('更新', updated, manifest)):
        if not keys:
            continue
        total = sum(len(names(k, src)) for k in keys)
        lines.append('')
        lines.append('### %s %d 本（%d 個檔）' % (label, total, len(keys)))
        for k in keys:
            for t in names(k, src):
                lines.append('- %s' % t)
            lines.append('  　`%s`' % k)
    lines.append('')
    lines.append('_執行後共 %d 個檔_' % len(manifest))

    if not CHANGELOG.exists():
        CHANGELOG.write_text('# 書庫異動紀錄\n\n每次執行 `build_library.py` 後自動附加。\n',
                             encoding='utf-8')
    with open(CHANGELOG, 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('異動紀錄：新增 %d／移除 %d／更新 %d 個檔 → %s'
          % (len(added), len(removed), len(updated), CHANGELOG))
    return len(added) + len(removed) + len(updated)


def prune_manifest(manifest):
    """書籍搬過資料夾或刪掉之後，清掉指向不存在檔案的紀錄。"""
    gone = [k for k in manifest if not (DST_ROOT / k).exists()]
    for k in gone:
        del manifest[k]
    if gone:
        print('清掉 %d 筆已不存在的紀錄' % len(gone))
    return gone


# ---------------------------------------------------------------- 首頁

INDEX_CSS = """*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1a2e;color:#e8d5b7;font-family:"Noto Serif TC","Microsoft JhengHei",serif;
line-height:1.7;padding-bottom:60px}
header{background:linear-gradient(135deg,#0f3460,#16213e);padding:28px 32px 22px;
border-bottom:2px solid #c9a94f;position:sticky;top:0;z-index:50}
h1{color:#c9a94f;font-size:1.7rem;letter-spacing:.08em}
.sub{color:#9ba4b4;font-size:.9rem;margin-top:6px}
.tools{margin-top:16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
#q{flex:1;min-width:220px;max-width:420px;background:#16213e;border:1px solid #2d4a7a;
border-radius:6px;color:#e8d5b7;padding:9px 13px;font-size:.95rem;font-family:inherit}
#q:focus{outline:none;border-color:#c9a94f}
#q::placeholder{color:#6b7688}
#cat{background:#16213e;border:1px solid #2d4a7a;border-radius:6px;color:#c9a94f;
padding:9px 13px;font-size:.95rem;font-family:inherit;cursor:pointer;min-width:190px}
#cat:focus{outline:none;border-color:#c9a94f}
#cat option{background:#16213e;color:#e8d5b7}
.hint{color:#9ba4b4;font-size:.82rem}
main{padding:8px 32px}
h2{color:#c9a94f;font-size:1.25rem;margin:34px 0 4px;padding-bottom:8px;
border-bottom:1px solid #2d4a7a;letter-spacing:.05em}
h2 .n{color:#6b7688;font-size:.8rem;font-weight:400;margin-left:10px;letter-spacing:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:16px;margin-top:18px}
.card{background:#16213e;border:1px solid #24365c;border-radius:9px;padding:15px 17px;
display:flex;flex-direction:column;transition:border-color .15s,transform .15s}
.card:hover{border-color:#c9a94f;transform:translateY(-2px)}
.crumb{color:#6b7688;font-size:.75rem;letter-spacing:.03em;margin-bottom:3px}
.card h3{font-size:1.05rem;margin-bottom:9px;color:#e8d5b7}
.card h3 a{color:#e8d5b7;text-decoration:none}
.card h3 a:hover{color:#c9a94f}
.card h3 .cnt{color:#9ba4b4;font-size:.78rem;font-weight:400;margin-left:7px}
ul{list-style:none;font-size:.88rem}
li{padding:2px 0;border-bottom:1px dashed #21304f}
li:last-child{border-bottom:none}
li a{color:#b8c5d6;text-decoration:none;display:block;padding:2px 4px;border-radius:4px}
li a:hover{background:#1e3a5f;color:#c9a94f}
li.set a{color:#d8c187}
.shelves{margin:-4px 0 8px}
.shelves a{color:#c9a94f;font-size:.82rem;text-decoration:none;opacity:.9}
.shelves a:hover{opacity:1;text-decoration:underline}
.au{color:#6b7688;font-size:.78rem;margin-left:8px}
.empty{color:#6b7688;text-align:center;padding:50px;display:none}
footer{color:#6b7688;font-size:.8rem;padding:34px 32px 0;text-align:center}
@media(max-width:600px){header{padding:20px}main{padding:8px 16px}}
"""

INDEX_JS = """<script>
var q = document.getElementById('q');
var cat = document.getElementById('cat');

cat.addEventListener('change', function () {
  var sec = document.getElementById(cat.value);
  if (!sec) return;
  // 搜尋條件可能正把該類別整段藏起來，先清掉才跳得過去
  if (q.value.trim()) { q.value = ''; run(); }
  // 直接跳，不用 smooth：整頁近三萬 px，捲動動畫又慢又暈
  var top = sec.getBoundingClientRect().top + window.pageYOffset
            - document.querySelector('header').offsetHeight - 8;
  window.scrollTo(0, top);
  cat.selectedIndex = 0;
});

function run() {
  var t = q.value.trim().toLowerCase();
  var shown = 0;
  document.querySelectorAll('.card').forEach(function (c) {
    var hitShelf = c.dataset.name.toLowerCase().indexOf(t) >= 0;
    var any = hitShelf;
    c.querySelectorAll('li').forEach(function (li) {
      var hit = !t || hitShelf || li.dataset.t.toLowerCase().indexOf(t) >= 0;
      li.style.display = hit ? '' : 'none';
      if (hit) any = true;
    });
    c.style.display = (!t || any) ? '' : 'none';
    if (!t || any) shown++;
  });
  document.querySelectorAll('section').forEach(function (s) {
    var vis = Array.prototype.filter.call(s.querySelectorAll('.card'), function (c) {
      return c.style.display !== 'none';
    }).length;
    s.style.display = vis ? '' : 'none';
  });
  document.querySelector('.empty').style.display = shown ? 'none' : 'block';
}
q.addEventListener('input', run);
document.addEventListener('keydown', function (e) {
  if (e.key === '/' && document.activeElement !== q) { e.preventDefault(); q.focus(); }
  if (e.key === 'Escape') { q.value = ''; run(); q.blur(); }
});
</script>"""


def url(rel_key, anchor=''):
    from urllib.parse import quote
    return quote(rel_key.replace('\\', '/')) + anchor


def cat_key(name):
    """類別依開頭數字排序，讓 11~15 類排在 8.科普類 後面而不是 1.社會人文類 後面。"""
    m = re.match(r'^\s*(\d+)', name)
    return (int(m.group(1)) if m else 9999, name)


def norm_title(t):
    """比對書名用：去掉書名號、括號、標點與空白。"""
    return re.sub(r'[\s《》〈〉「」『』【】（）()\[\]：:，,、。．·・\-—~～!！?？"\'’”]', '', t).lower()


def same_book(a, b):
    if a == b:
        return True
    # 「真確」vs「真確：扭轉十大直覺偏誤…」這種副標題長短不一的情況
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 6 and long_.startswith(short)


def build_index(manifest):
    """每個資料夾一張卡片，卡片內列出該資料夾的每一本書。"""
    cards = {}   # 類別 -> 資料夾相對路徑 -> {'entries': [...], 'size': int, 'shelves': [...]}
    for key, info in manifest.items():
        rel = Path(key)
        cat = rel.parts[0] if len(rel.parts) > 1 else '（未分類）'
        folder = str(rel.parent)
        card = cards.setdefault(cat, {}).setdefault(
            folder, {'entries': [], 'size': 0, 'shelves': []})
        card['size'] += info.get('size', 0)

        books = info.get('books') or [{'title': info['name'], 'author': '', 'anchor': ''}]
        multi = len(books) > 1
        if multi:
            card['shelves'].append({'name': info['name'], 'key': key, 'used': False})
        for b in books:
            card['entries'].append({
                'title': b['title'], 'author': b.get('author', ''),
                'href': url(key, b.get('anchor', '')),
                'norm': norm_title(b['title']),
                'shelf_key': key if multi else None,
            })

    # 同一本書若既有自己的單書檔、又收在書架裡，首頁只留單書那一筆
    for folders in cards.values():
        for card in folders.values():
            solo = [e['norm'] for e in card['entries'] if not e['shelf_key']]
            kept = []
            for e in card['entries']:
                if e['shelf_key'] and any(same_book(e['norm'], s) for s in solo):
                    continue
                kept.append(e)
            card['entries'] = kept
            used = {e['shelf_key'] for e in kept if e['shelf_key']}
            # 整櫃的書都已經被單書取代時，書架本身另外列一行，才不會變成連不到
            card['shelves'] = [s for s in card['shelves'] if s['key'] not in used]

    total_books = sum(len(c['entries']) for cat in cards.values() for c in cat.values())
    total_files = len(manifest)

    out = ['<!DOCTYPE html>', '<html lang="zh-TW">', '<head>', '<meta charset="UTF-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1.0">',
           '<title>Liu的雲端書庫</title>', '<style>', INDEX_CSS, '</style>',
           '</head>', '<body>', '<header>', '<h1>Liu的雲端書庫</h1>',
           '<div class="sub">%d 個類別 · %d 本書 · %d 個閱讀器檔 · 點書名直接開始讀</div>'
           % (len(cards), total_books, total_files),
           '<div class="tools">']

    ordered = sorted(cards, key=cat_key)
    out.append('<select id="cat"><option value="">📚 跳到類別…</option>')
    for i, c in enumerate(ordered):
        n = sum(len(x['entries']) for x in cards[c].values())
        out.append('<option value="sec-%d">%s（%d 本）</option>' % (i, escape(c), n))
    out.append('</select>')

    out += ['<input id="q" type="search" placeholder="搜尋書名、作者或資料夾…（按 / 快速聚焦）" autocomplete="off">',
            '<span class="hint">Esc 清除</span>', '</div>', '</header>', '<main>']

    for i, cat in enumerate(ordered):
        folders = cards[cat]
        n_books = sum(len(c['entries']) for c in folders.values())
        out.append('<section id="sec-%d">' % i)
        out.append('<h2>%s<span class="n">%d 個書櫃 · %d 本</span></h2>'
                   % (escape(cat), len(folders), n_books))
        out.append('<div class="grid">')
        # 書櫃卡片一律依藏書數由多到少排；數量相同時再依路徑排，
        # 這樣每次重建的順序都固定，不會無故跳動
        order = sorted(folders, key=lambda f: (-len(folders[f]['entries']), f))
        for folder in order:
            card = folders[folder]
            parts = Path(folder).parts
            name = parts[-1]
            crumb = '\\'.join(parts[1:-1])
            out.append('<article class="card" data-name="%s">'
                       % escape('%s %s' % (name, folder)))
            if crumb:
                out.append('<div class="crumb">%s</div>' % escape(crumb))
            out.append('<h3>%s<span class="cnt">%d 本 · %.2f MB</span></h3>'
                       % (escape(name), len(card['entries']), card['size'] / 1048576))
            for s in sorted(card['shelves'], key=lambda x: x['name']):
                out.append('<div class="shelves"><a href="%s">📚 %s</a></div>'
                           % (url(s['key']), escape(s['name'])))
            out.append('<ul>')
            for e in sorted(card['entries'], key=lambda x: x['title']):
                au = '<span class="au">%s</span>' % escape(e['author']) if e['author'] else ''
                out.append('<li%s data-t="%s"><a href="%s">%s%s</a></li>'
                           % (' class="set"' if e['shelf_key'] else '',
                              escape('%s %s' % (e['title'], e['author'])),
                              e['href'], escape(e['title']), au))
            out.append('</ul></article>')
        out.append('</div></section>')

    out += ['<div class="empty">找不到符合的書</div>', '</main>',
            '<footer>檔案位置：%s　·　原始 EPUB 未更動　·　更新於 %s</footer>'
            % (escape(str(DST_ROOT) + '\\'), time.strftime('%Y-%m-%d')),
            INDEX_JS, '</body>', '</html>']
    (DST_ROOT / 'index.html').write_text('\n'.join(out), encoding='utf-8')
    print('已產生 %s（%d 本書）' % (DST_ROOT / 'index.html', total_books))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', action='store_true', help='只列出計畫，不實際轉檔')
    ap.add_argument('--only', default=None, help='只處理某個類別資料夾，例如 "2.哲學類"')
    ap.add_argument('--force', action='store_true', help='忽略 manifest 全部重轉')
    ap.add_argument('--index-only', action='store_true', help='只重建 reader/index.html')
    ap.add_argument('--refresh', action='store_true',
                    help='不重新轉檔，只補上既有產出的書目資訊與「← 書庫」連結')
    ap.add_argument('--patch-only', action='store_true',
                    help='只重貼所有產出的 patch（返回連結／夜間模式／深連結），不碰 manifest')
    ap.add_argument('--orphans', action='store_true',
                    help='列出 reader\\ 裡來源已不存在的孤兒檔（只列出，不刪）')
    ap.add_argument('--delete-orphans', action='store_true',
                    help='真的把孤兒檔刪掉（請先用 --orphans 確認清單）')
    ap.add_argument('--to-tw', action='store_true',
                    help='把簡體書轉成繁體收進書庫；不加這個參數時簡體書一律略過')
    args = ap.parse_args()

    global TW_ENABLED
    TW_ENABLED = args.to_tw

    if args.orphans or args.delete_orphans:
        planned = {j['output'] for j in plan_jobs()}
        orphans = [p for p in sorted(DST_ROOT.rglob('*.html'))
                   if p.name != 'index.html' and p not in planned]
        if not orphans:
            print('沒有孤兒檔')
            return
        print('來源已不存在的孤兒檔共 %d 個：' % len(orphans))
        for p in orphans:
            print('  %8.1f MB  %s' % (p.stat().st_size / 1048576, p.relative_to(DST_ROOT)))
        if args.delete_orphans:
            manifest = load_manifest()
            before = snapshot(manifest)
            for p in orphans:
                p.unlink()
            prune_manifest(manifest)
            save_manifest(manifest)
            write_changelog(before, manifest, '刪除孤兒檔')
            build_index(manifest)
            print('已刪除 %d 個孤兒檔並重建首頁' % len(orphans))
        else:
            print('\n（只是列出。確認無誤後加 --delete-orphans 才會真的刪除）')
        return

    if args.patch_only:
        now = time.time()
        done = busy = 0
        for out in sorted(DST_ROOT.rglob('*.html')):
            if out.name == 'index.html':
                continue
            # 剛寫入的檔案可能正在被轉檔程序寫到一半，這輪先跳過
            if now - out.stat().st_mtime < 60:
                busy += 1
                continue
            patch_output(out)
            done += 1
        print('已重貼 %d 個檔案的 patch（%d 個剛寫入、這輪跳過）' % (done, busy))
        return

    manifest = load_manifest()

    if args.index_only:
        build_index(manifest)
        return

    jobs = plan_jobs(args.only)

    if args.refresh:
        n = 0
        for job in jobs:
            out = job['output']
            if not out.exists():
                continue
            patch_output(out, is_shelf=(job['kind'] != 'reader'))
            key = str(out.relative_to(DST_ROOT))
            entry = manifest.setdefault(key, {'kind': job['kind'], 'name': job['name'],
                                              'sources': sig(job['sources'])})
            entry['books'] = job_books(job)
            entry['size'] = out.stat().st_size
            n += 1
        prune_manifest(manifest)
        save_manifest(manifest)
        build_index(manifest)
        print('已補齊 %d 個既有產出' % n)
        return

    if args.plan:
        by_kind = {}
        for j in jobs:
            by_kind[j['kind']] = by_kind.get(j['kind'], 0) + 1
        print('共 %d 項工作：%s\n' % (len(jobs), by_kind))
        for j in jobs:
            if j['kind'] == 'shelf':
                print('[書架] %s' % j['output'].relative_to(DST_ROOT))
                for s in j['sources']:
                    print('        - %s' % s.name)
        print('\n--- 全部工作 ---')
        for j in jobs:
            print('%-7s %s' % (j['kind'], j['output'].relative_to(DST_ROOT)))
        return

    DST_ROOT.mkdir(parents=True, exist_ok=True)
    before = snapshot(manifest)
    with open(LOG_PATH, 'a', encoding='utf-8') as log:
        log.write('\n===== %s  only=%s force=%s =====\n'
                  % (time.strftime('%Y-%m-%d %H:%M:%S'), args.only, args.force))
        done, skipped, failed = build(jobs, manifest, force=args.force, log=log)

    prune_manifest(manifest)
    # 檔案還在、但已經不在建置計畫裡的（例如來源改名，或是簡體書被略過），
    # 也要移出 manifest，否則首頁還是會列出來。--only 時計畫只涵蓋部分書庫，
    # 不能拿來當全域依據，所以只在完整建置時做。
    if not args.only:
        planned = {str(j['output'].relative_to(DST_ROOT)) for j in jobs}
        stale = [k for k in manifest if k not in planned]
        for k in stale:
            del manifest[k]
        if stale:
            print('從書庫移除 %d 筆（檔案仍在硬碟上，可用 --orphans 檢視）' % len(stale))

    save_manifest(manifest)
    save_zh_cache()
    write_changelog(before, manifest,
                    ('只跑 ' + args.only) if args.only else '完整建置')

    if skipped_simplified:
        print('\n略過 %d 本簡體書（未收進書庫、首頁也不會出現）：' % len(skipped_simplified))
        for p in skipped_simplified:
            print('  %s' % p.relative_to(SRC_ROOT))
        print('若要把它們轉成繁體收進來，加 --to-tw 重跑')
    build_index(manifest)
    print('\n完成：新建/更新 %d，略過 %d，失敗 %d' % (done, skipped, failed))


if __name__ == '__main__':
    main()
