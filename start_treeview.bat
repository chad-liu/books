@echo off
REM 起一個本機 server 並開啟 treeview.html。
REM 一定要用 localhost 開啟，編輯功能才能運作（file:// 會被瀏覽器擋住讀取本機檔案）。
cd /d "%~dp0"
start "" http://localhost:8899/treeview.html
python -m http.server 8899
