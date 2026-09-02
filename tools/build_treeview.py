#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依 plan_treeview.md 規劃，掃描 D:\\Books\\html\\ 產生根目錄的 treeview.html。

跟 build_html_index.py 的差別：
  * index.html 是給讀者看的策展入口，只列 order.md 挑選過的條目
  * treeview.html 是給自己用的維護工具，列出資料夾裡的「全部」html 檔

規則：
  * 資料夾依名稱升冪排序（資料夾名已用數字前綴人工排好順序）
  * 檔案先依該資料夾 order.md 的順序，order.md 未列到的接在後面依檔名排序
  * 未列入 order.md 的檔案標記 o=false，前端會加淡色標記（順便當漏列偵測）
  * 檔案樹在建置時烘進 treeview.html，因為 GitHub Pages 沒有目錄列表 API、
    file:// 又會被 CORS 擋掉，執行時抓不到目錄內容
  * 沒有 dark/light 切換：被瀏覽的頁面在 SVG 內寫死了上萬處顏色（不吃 CSS 變數），
    從外部無法正確改成深色，詳見 plan_treeview.md 第五節

用法：
    python tools/build_treeview.py
"""

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOOKS_ROOT = Path(__file__).resolve().parent.parent
HTML_ROOT = BOOKS_ROOT / 'html'
OUT = BOOKS_ROOT / 'treeview.html'

URL_RE = re.compile(r'^(?P<label>.*?)\((?P<url>https?://[^\s()]+)\)\s*$')
SEP_RE = re.compile(r'^[-=_]{3,}$')


def order_names(folder):
    """讀 order.md，回傳「本機檔名（不含 .html）」的順序清單。外部連結與分隔線略過。"""
    f = folder / 'order.md'
    if not f.exists():
        return []
    names = []
    for line in f.read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if not s or SEP_RE.match(s) or URL_RE.match(s):
            continue
        names.append(s)
    return names


def collect():
    tree = []
    orphans = 0
    for folder in sorted(p for p in HTML_ROOT.iterdir() if p.is_dir()):
        files = sorted(p for p in folder.iterdir()
                       if p.is_file() and p.suffix.lower() == '.html')
        if not files:
            continue

        listed = order_names(folder)
        rank = {n: i for i, n in enumerate(listed)}
        # order.md 有列的排前面並照其順序，沒列的接在後面依檔名排
        files.sort(key=lambda p: (rank.get(p.stem, len(rank)), p.name))

        items = []
        for p in files:
            in_order = p.stem in rank
            if not in_order:
                orphans += 1
            items.append({
                'n': p.name,
                'p': 'html/%s/%s' % (folder.name, p.name),
                's': p.stat().st_size,
                'o': in_order,
            })
        tree.append({'name': folder.name, 'files': items})
    return tree, orphans


CSS = """
:root{
  --bg:#f2f5f7;--panel:#ffffff;--ink:#22303a;--muted:#5d7784;--line:#d5dfe5;
  --accent:#285b78;--accent2:#17324d;--hot:#b8442a;--ok:#3d7a55;
  --side:#f7f9fb;--hover:#e8eef2;--sel:#dce8f0;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;
  display:flex;flex-direction:column;overflow:hidden}

/* ---- 頂部列 ---- */
#top{display:flex;align-items:center;gap:12px;padding:8px 14px;background:var(--panel);
  border-bottom:1px solid var(--line);flex:0 0 auto;flex-wrap:wrap}
#top h1{font-size:15px;margin:0;letter-spacing:.06em;color:var(--accent2);white-space:nowrap}
#q{flex:1;min-width:150px;max-width:340px;padding:6px 10px;border:1px solid var(--line);
  border-radius:6px;background:var(--bg);color:var(--ink);font:inherit;font-size:13px}
#q:focus{outline:none;border-color:var(--accent)}
.btn{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:6px;
  padding:5px 10px;font:inherit;font-size:12.5px;cursor:pointer;white-space:nowrap}
.btn:hover{background:var(--hover)}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn.pri{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn.pri:hover{filter:brightness(1.1)}
#zl{font-size:11.5px;color:var(--muted);min-width:38px;text-align:center}
#env{font-size:11.5px;color:var(--muted);margin-left:auto;white-space:nowrap}
#env b{color:var(--hot)}

/* ---- 主體 ---- */
#main{flex:1;display:flex;min-height:0}
#side{width:280px;flex:0 0 auto;background:var(--side);border-right:1px solid var(--line);
  overflow:auto;padding:6px 0 20px}
#side.hide{display:none}
#gutter{width:5px;flex:0 0 auto;cursor:col-resize;background:transparent}
#gutter:hover{background:var(--accent)}
#work{flex:1;display:flex;flex-direction:column;min-width:0}

/* ---- 樹狀選單 ---- */
.fold{user-select:none}
.fold>.hd{display:flex;align-items:center;gap:6px;padding:5px 10px;cursor:pointer;
  font-weight:600;color:var(--accent2);font-size:13px}
.fold>.hd:hover{background:var(--hover)}
.fold>.hd .cnt{margin-left:auto;font-weight:400;font-size:11px;color:var(--muted)}
.fold>.hd .ar{width:10px;text-align:center;font-size:10px;color:var(--muted)}
.fold.closed>ul{display:none}
.fold ul{list-style:none;margin:0;padding:0}
.fold li{padding:4px 10px 4px 28px;cursor:pointer;font-size:13px;
  color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fold li:hover{background:var(--hover)}
.fold li.on{background:var(--sel);font-weight:600}
.fold li .no{color:var(--muted);font-size:10px;margin-left:5px}
.fold li.hid,.fold.hid{display:none}
#noHit{display:none;padding:14px;color:var(--muted);font-size:12.5px}

/* ---- 分頁 ---- */
#tabs{display:flex;gap:2px;padding:6px 8px 0;background:var(--panel);
  border-bottom:1px solid var(--line);overflow-x:auto;flex:0 0 auto}
.tab{display:flex;align-items:center;gap:7px;padding:6px 9px;border:1px solid var(--line);
  border-bottom:0;border-radius:6px 6px 0 0;background:var(--bg);cursor:pointer;
  font-size:12.5px;white-space:nowrap;max-width:230px}
.tab.on{background:var(--panel);border-color:var(--accent);color:var(--accent2);font-weight:600}
.tab .nm{overflow:hidden;text-overflow:ellipsis}
.tab .x{color:var(--muted);font-size:14px;line-height:1}
.tab .x:hover{color:var(--hot)}
.tab .dot{color:var(--hot);font-size:15px;line-height:1}
.tab.add{color:var(--muted);font-weight:700;padding:6px 12px;background:transparent;border-style:dashed}
.tab.add:hover{background:var(--hover);color:var(--accent2);border-color:var(--accent)}

/* ---- 工具列 ---- */
#bar{display:flex;align-items:center;gap:8px;padding:7px 12px;background:var(--panel);
  border-bottom:1px solid var(--line);flex:0 0 auto;flex-wrap:wrap}
#bar .path{font-size:11.5px;color:var(--muted);margin-right:auto;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:46%}
#msg{font-size:12px}
#msg.ok{color:var(--ok)} #msg.err{color:var(--hot)}

/* ---- 內容區 ---- */
#panes{flex:1;min-height:0;display:flex}
#viewWrap{flex:1;min-width:0;display:flex}
#editWrap{flex:1;min-width:0;display:none}
body.edit #viewWrap{display:none}
body.edit #editWrap{display:flex}
iframe{border:0;width:100%;height:100%;background:#fff}
#src{width:50%;height:100%;border:0;border-right:1px solid var(--line);resize:none;
  padding:12px;font-family:ui-monospace,Consolas,"Noto Sans Mono",monospace;
  font-size:13px;line-height:1.6;background:var(--panel);color:var(--ink);
  tab-size:2;white-space:pre;overflow:auto}
#src:focus{outline:none}
#prevWrap{width:50%;height:100%}
#empty{flex:1;display:flex;align-items:center;justify-content:center;
  color:var(--muted);font-size:13.5px;text-align:center;line-height:2;padding:20px}
"""

JS = r"""
var TREE = __TREE__;
var BIG = 2*1024*1024;              // 超過 2MB 的檔預設不載入編輯器
var isFile = location.protocol === 'file:';
var canEdit = !isFile;              // file:// 會被 CORS 擋住 fetch，讀不到原始碼
var canFS = !!window.showDirectoryPicker && window.isSecureContext;

var tabs = [], active = -1, rootHandle = null;
var $ = function(s){ return document.querySelector(s); };

/* ---------- localStorage 小工具 ---------- */
function LS(k, v){
  try{
    if (v === undefined) { var r = localStorage.getItem('tv.'+k); return r===null?null:JSON.parse(r); }
    localStorage.setItem('tv.'+k, JSON.stringify(v));
  }catch(e){}
}

/* ---------- 預覽欄縮放 ---------- */
/* 縮放的是右邊預覽欄的內容，不是左邊檔案樹。
   不能只改 font-size：這些頁面的字級多是絕對 px，且 SVG 內的 font-size 屬於 SVG 使用者單位，
   不會跟著 CSS 字級走——只改字級會變成內文放大但圖表不動。用 zoom 才能整頁等比縮放。 */
var zoom = LS('zoom') || 1, zoomOK = true;
function applyZoom(){
  [$('#view'), $('#prev')].forEach(function(f){
    try{
      var d = f.contentDocument;
      if (d && d.documentElement) d.documentElement.style.zoom = zoom;
    }catch(e){ zoomOK = false; }      // file:// 之下取不到 iframe 內容
  });
  $('#zl').textContent = Math.round(zoom*100) + '%';
  $('#fsUp').disabled = $('#fsDn').disabled = !zoomOK;
  if (!zoomOK) $('#zl').title = 'file:// 之下無法存取預覽內容，縮放已停用';
}
function setZoom(z){
  zoom = Math.max(0.5, Math.min(2.5, Math.round(z*10)/10));
  LS('zoom', zoom); applyZoom();
}

/* ---------- 樹狀選單 ---------- */
function buildTree(){
  var side = $('#side'), open = LS('open') || {};   // 預設全部收合，只有存過 true 的才展開
  TREE.forEach(function(f, i){
    var d = document.createElement('div');
    d.className = 'fold' + (open[f.name] === true ? '' : ' closed');
    d.dataset.name = f.name;
    var hd = document.createElement('div');
    hd.className = 'hd';
    hd.innerHTML = '<span class="ar">▼</span><span>'+esc(f.name)+
                   '</span><span class="cnt">'+f.files.length+'</span>';
    hd.onclick = function(){
      d.classList.toggle('closed');
      var o = LS('open')||{}; o[f.name] = !d.classList.contains('closed'); LS('open',o);
      syncArrow(d);
    };
    d.appendChild(hd);
    syncArrow(d);            // 要等 hd 掛進 d 之後才找得到 .ar
    var ul = document.createElement('ul');
    f.files.forEach(function(it){
      var li = document.createElement('li');
      li.dataset.path = it.p;
      li.title = it.p + '　(' + fmt(it.s) + ')';
      li.innerHTML = esc(it.n.replace(/\.html$/,'')) +
        (it.o ? '' : '<span class="no" title="未列入 order.md">未列</span>');
      li.onclick = function(){ openTab(it); };
      ul.appendChild(li);
    });
    d.appendChild(ul);
    side.appendChild(d);
  });
}
function syncArrow(d){
  d.querySelector('.ar').textContent = d.classList.contains('closed') ? '▶' : '▼';
}
function esc(s){ return s.replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function fmt(n){ return n>=1048576 ? (n/1048576).toFixed(1)+' MB'
                : n>=1024 ? Math.round(n/1024)+' KB' : n+' B'; }

/* ---------- 搜尋 ---------- */
function search(){
  var t = $('#q').value.trim().toLowerCase(), hit = 0;
  var open = LS('open') || {};
  document.querySelectorAll('.fold').forEach(function(d){
    var fname = d.dataset.name.toLowerCase();
    var folderHit = t && fname.indexOf(t) >= 0, any = folderHit;
    d.querySelectorAll('li').forEach(function(li){
      var ok = !t || folderHit || li.textContent.toLowerCase().indexOf(t) >= 0;
      li.classList.toggle('hid', !ok);
      if (ok) any = true;
    });
    d.classList.toggle('hid', !!t && !any);
    if (!t || any) hit++;
    if (t && any) d.classList.remove('closed');                        // 命中就自動展開
    else if (!t) d.classList.toggle('closed', open[d.dataset.name] !== true);  // 清空搜尋後還原
    syncArrow(d);
  });
  $('#noHit').style.display = (t && !hit) ? 'block' : 'none';
}

/* ---------- 分頁 ---------- */
function blankTab(){
  return { p:null, n:'新分頁', s:0, mode:'view', dirty:false, draft:null, loaded:false };
}
function newTab(){
  tabs.push(blankTab());
  activate(tabs.length - 1);
  renderTabs(); saveTabs();
}
/* 單擊左欄＝取代目前分頁（類似 VS Code 的預覽分頁），要另開請按「＋」。
   已開啟的檔案直接切過去；有未存檔變更的分頁不覆蓋，改開新分頁保住草稿。 */
function openTab(it){
  var i = tabs.findIndex(function(t){ return t.p === it.p; });
  if (i >= 0) { activate(i); return; }
  var cur = tabs[active];
  if (cur && !cur.dirty){
    cur.p=it.p; cur.n=it.n; cur.s=it.s;
    cur.mode='view'; cur.draft=null; cur.dirty=false; cur.loaded=false;
    activate(active);
  } else {
    tabs.push({ p:it.p, n:it.n, s:it.s, mode:'view', dirty:false, draft:null, loaded:false });
    activate(tabs.length - 1);
    if (cur && cur.dirty) msg('原分頁有未存檔變更，已改為開新分頁', 'ok');
  }
  renderTabs(); saveTabs();
}
function closeTab(i, ev){
  if (ev) ev.stopPropagation();
  if (tabs[i].dirty && !confirm('「'+tabs[i].n+'」有未存檔的變更，確定關閉？')) return;
  tabs.splice(i,1);
  if (!tabs.length) tabs.push(blankTab());
  if (active >= tabs.length) active = tabs.length - 1;
  activate(active);
  renderTabs(); saveTabs();
}
function renderTabs(){
  var el = $('#tabs'); el.innerHTML = '';
  tabs.forEach(function(t,i){
    var d = document.createElement('div');
    d.className = 'tab' + (i===active ? ' on' : '');
    d.innerHTML = (t.dirty ? '<span class="dot">●</span>' : '') +
                  '<span class="nm">'+esc(t.n.replace(/\.html$/,''))+'</span><span class="x">×</span>';
    d.onclick = function(){ activate(i); };
    d.onauxclick = function(e){ if (e.button===1) closeTab(i,e); };
    d.querySelector('.x').onclick = function(e){ closeTab(i,e); };
    el.appendChild(d);
  });
  var add = document.createElement('div');
  add.className = 'tab add'; add.title = '新增分頁（Ctrl+T）';
  add.textContent = '＋';
  add.onclick = newTab;
  el.appendChild(add);
  // 分頁列會橫向捲動，新分頁常落在視野外，看起來像「沒有新增」
  var on = el.querySelector('.tab.on');
  if (on && on.scrollIntoView) on.scrollIntoView({block:'nearest', inline:'nearest'});
}
function activate(i){
  active = i; var t = tabs[i]; if (!t) return showEmpty();
  if (!t.p){                       // 空白分頁：等使用者從左欄挑檔案
    $('#empty').style.display='flex'; $('#panes').style.display='none';
    $('#bar').style.display='none'; document.body.classList.remove('edit');
    document.querySelectorAll('#side li').forEach(function(li){ li.classList.remove('on'); });
    renderTabs(); saveTabs(); return;
  }
  $('#empty').style.display='none'; $('#panes').style.display='flex';
  $('#bar').style.display='flex';
  $('#bar .path').textContent = t.p + '　·　' + fmt(t.s);
  document.body.classList.toggle('edit', t.mode==='edit');
  $('#mView').classList.toggle('pri', t.mode==='view');
  $('#mEdit').classList.toggle('pri', t.mode==='edit');
  $('#mEdit').disabled = !canEdit;
  document.querySelectorAll('#side li').forEach(function(li){
    li.classList.toggle('on', li.dataset.path === t.p); });
  renderTabs(); msg('');

  if (t.mode === 'view'){
    var want = url(t.p);
    if ($('#view').getAttribute('src') !== want) $('#view').setAttribute('src', want);
  } else {
    $('#src').value = t.draft !== null ? t.draft : '';
    preview();
  }
  saveTabs();
}
function showEmpty(){
  active=-1; $('#empty').style.display='flex'; $('#panes').style.display='none';
  $('#bar').style.display='none'; document.body.classList.remove('edit');
  document.querySelectorAll('#side li').forEach(function(li){ li.classList.remove('on'); });
}
function url(p){ return p.split('/').map(encodeURIComponent).join('/'); }
function saveTabs(){ LS('tabs', tabs.map(function(t){ return {p:t.p,n:t.n,s:t.s,mode:t.mode}; }));
  LS('active', active); }

/* ---------- 編輯 ---------- */
async function toEdit(){
  var t = tabs[active]; if (!t || !canEdit) return;
  if (t.s > BIG && !confirm('這個檔約 '+fmt(t.s)+'，載入編輯器可能會很卡。仍要編輯？')) return;
  if (t.draft === null){
    var d = LS('draft.'+t.p);
    if (d !== null && confirm('偵測到「'+t.n+'」的未存草稿，要載入嗎？（取消則讀取原檔）')){
      t.draft = d; t.dirty = true;
    } else {
      msg('載入中…');
      try{
        var r = await fetch(url(t.p));
        if (!r.ok) throw new Error('HTTP '+r.status);
        t.draft = await r.text(); t.dirty = false; msg('');
      }catch(e){ msg('讀取失敗：'+e.message, 'err'); return; }
    }
  }
  t.mode = 'edit'; activate(active);
}
function toView(){ var t=tabs[active]; if(!t) return; t.mode='view'; activate(active); }

var tmr = null;
function onInput(){
  var t = tabs[active]; if (!t) return;
  t.draft = $('#src').value;
  if (!t.dirty){ t.dirty = true; renderTabs(); }
  clearTimeout(tmr);
  tmr = setTimeout(function(){
    LS('draft.'+t.p, t.draft);
    preview();
  }, 400);
}
function preview(){
  var t = tabs[active]; if (!t || t.draft === null) return;
  // srcdoc 的相對路徑基準跟父頁不同，注入 <base> 才能讓頁內相對連結正常
  var base = new URL(url(t.p.replace(/[^/]+$/,'')), location.href).href;
  var html = t.draft.replace(/<head([^>]*)>/i, '<head$1><base href="'+base+'">');
  if (html === t.draft) html = '<base href="'+base+'">' + html;
  $('#prev').srcdoc = html;
}

/* ---------- 存檔 ---------- */
async function connectDir(){
  try{
    rootHandle = await window.showDirectoryPicker({ mode:'readwrite' });
    msg('已連結資料夾：'+rootHandle.name, 'ok'); updEnv();
  }catch(e){ if (e.name!=='AbortError') msg('連結失敗：'+e.message,'err'); }
}
async function handleFor(path){
  var parts = path.split('/'), file = parts.pop(), dir = rootHandle;
  for (var i=0;i<parts.length;i++) dir = await dir.getDirectoryHandle(parts[i]);
  return dir.getFileHandle(file);
}
async function save(){
  var t = tabs[active]; if (!t || t.mode!=='edit') return;
  if (!rootHandle){
    if (!canFS){ return download(); }
    msg('尚未連結本機資料夾，請先點「連結資料夾」', 'err'); return;
  }
  try{
    msg('存檔中…');
    var h = await handleFor(t.p);
    var w = await h.createWritable();
    await w.write(t.draft); await w.close();
    t.dirty = false; renderTabs();
    try{ localStorage.removeItem('tv.draft.'+t.p); }catch(e){}
    msg('已存回 '+t.p, 'ok');
  }catch(e){ msg('存檔失敗：'+e.message+'（可改用下載）', 'err'); }
}
function download(){
  var t = tabs[active]; if (!t || t.draft === null) return;
  var b = new Blob([t.draft], {type:'text/html;charset=utf-8'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(b); a.download = t.n;
  a.click(); URL.revokeObjectURL(a.href);
  msg('已下載 '+t.n+'，請自行覆蓋原檔', 'ok');
}
function msg(s, cls){ var m=$('#msg'); m.textContent=s||''; m.className = cls||''; }

/* ---------- 環境提示 ---------- */
function updEnv(){
  var e = $('#env');
  if (isFile){
    e.innerHTML = '<b>file:// 模式</b>：瀏覽器擋住讀取本機檔案，編輯已停用。要編輯請改用 localhost 開啟';
  } else if (rootHandle){
    e.innerHTML = '已連結 <b>'+esc(rootHandle.name)+'</b>　·　可直接存回原檔';
  } else if (canFS){
    e.textContent = '可編輯　·　點「連結資料夾」後才能直接存回原檔，否則只能下載';
  } else {
    e.textContent = '可編輯　·　此瀏覽器不支援直接存回原檔，只能下載';
  }
  $('#conn').style.display = (canFS && !rootHandle) ? '' : 'none';
}

/* ---------- 啟動 ---------- */
function init(){
  applyZoom();
  buildTree();
  updEnv();

  $('#q').oninput = search;
  $('#fsUp').onclick = function(){ setZoom(zoom + 0.1); };
  $('#fsDn').onclick = function(){ setZoom(zoom - 0.1); };
  $('#view').onload = applyZoom;      // 換檔／換分頁後要重新套用
  $('#prev').onload = applyZoom;
  $('#tog').onclick = function(){ $('#side').classList.toggle('hide'); };
  $('#mView').onclick = toView;
  $('#mEdit').onclick = toEdit;
  $('#save').onclick = save;
  $('#dl').onclick = download;
  $('#conn').onclick = connectDir;
  $('#src').oninput = onInput;

  // 左欄寬度可拖曳
  var drag=false;
  $('#gutter').onmousedown = function(){ drag=true; document.body.style.userSelect='none'; };
  document.onmousemove = function(e){ if(!drag) return;
    var w=Math.max(160,Math.min(560,e.clientX)); $('#side').style.width=w+'px'; LS('sw',w); };
  document.onmouseup = function(){ if(drag){ drag=false; document.body.style.userSelect=''; } };
  var sw = LS('sw'); if (sw) $('#side').style.width = sw+'px';

  document.addEventListener('keydown', function(e){
    if ((e.ctrlKey||e.metaKey) && e.key==='t'){ e.preventDefault(); newTab(); }
    else if ((e.ctrlKey||e.metaKey) && e.key==='s'){ e.preventDefault(); save(); }
    else if ((e.ctrlKey||e.metaKey) && e.key==='w'){ if(active>=0){ e.preventDefault(); closeTab(active); } }
    else if ((e.ctrlKey||e.metaKey) && e.key==='f'){ e.preventDefault(); $('#q').focus(); $('#q').select(); }
    else if (e.key==='Escape' && document.activeElement===$('#q')){ $('#q').value=''; search(); $('#q').blur(); }
  });
  window.addEventListener('beforeunload', function(e){
    if (tabs.some(function(t){ return t.dirty; })){ e.preventDefault(); e.returnValue=''; }
  });

  // 還原上次開啟的分頁
  var saved = LS('tabs') || [];
  saved.forEach(function(s){
    tabs.push({p:s.p,n:s.n,s:s.s,mode:'view',dirty:false,draft:null,loaded:false}); });
  if (tabs.length){ renderTabs(); activate(Math.min(LS('active')||0, tabs.length-1)); }
  else showEmpty();
}
document.addEventListener('DOMContentLoaded', init);
"""

BODY = """<div id="top">
  <h1>Liu的檔案樹</h1>
  <button class="btn" id="tog" title="收合／展開左欄">☰</button>
  <input id="q" type="search" placeholder="搜尋檔名或資料夾…（Ctrl+F）" autocomplete="off">
  <button class="btn" id="fsDn" title="縮小右邊預覽欄">A−</button>
  <span id="zl">100%</span>
  <button class="btn" id="fsUp" title="放大右邊預覽欄">A+</button>
  <button class="btn" id="conn" title="授權後可直接存回原檔">連結資料夾</button>
  <span id="env"></span>
</div>

<div id="main">
  <aside id="side"><div id="noHit">找不到符合的檔案</div></aside>
  <div id="gutter"></div>
  <section id="work">
    <div id="tabs"></div>
    <div id="bar" style="display:none">
      <button class="btn" id="mView">檢視</button>
      <button class="btn" id="mEdit">編輯</button>
      <span class="path"></span>
      <span id="msg"></span>
      <button class="btn pri" id="save" title="Ctrl+S">存檔</button>
      <button class="btn" id="dl">下載</button>
    </div>
    <div id="empty">從左欄挑一個檔案開始<br>單擊會取代目前分頁，要另開請按分頁列的「＋」（Ctrl+T）</div>
    <div id="panes" style="display:none">
      <div id="viewWrap"><iframe id="view"></iframe></div>
      <div id="editWrap">
        <textarea id="src" spellcheck="false"></textarea>
        <div id="prevWrap"><iframe id="prev"></iframe></div>
      </div>
    </div>
  </section>
</div>"""


def build():
    tree, orphans = collect()
    total = sum(len(f['files']) for f in tree)

    js = JS.replace('__TREE__', json.dumps(tree, ensure_ascii=False))

    out = ['<!DOCTYPE html>', '<html lang="zh-TW">', '<head>',
           '<meta charset="UTF-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1.0">',
           '<title>Liu的檔案樹</title>',
           '<style>%s</style>' % CSS, '</head>', '<body>', BODY,
           '<script>%s</script>' % js, '</body>', '</html>']

    OUT.write_text('\n'.join(out), encoding='utf-8')

    for f in tree:
        miss = [i['n'] for i in f['files'] if not i['o']]
        if miss:
            print('[未列入 order.md] %s：%s' % (f['name'], '、'.join(miss)))

    print('\n已產生 %s（%d 個資料夾、%d 個檔案，其中 %d 個未列入 order.md）'
          % (OUT, len(tree), total, orphans))


if __name__ == '__main__':
    build()
