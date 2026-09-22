@echo off
rem ASCII-only bat (GBK cmd chokes on UTF-8 Chinese paths, see DELIVERY.md)
cd /d "%~dp0.."
"%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe" scripts\run_daily_quote.py >> logs\daily-quote.log 2>&1
