@echo off
cd /d E:\localai\blogbotbob
call .venv\Scripts\activate.bat
blogbot run >> data\scheduler.log 2>&1
