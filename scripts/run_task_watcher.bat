@echo off
rem ASCII-only bat (GBK cmd chokes on UTF-8 Chinese paths, see DELIVERY.md)
cd /d "%~dp0.."
"%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe" scripts\check_tasks.py >> logs\task-watcher.log 2>&1
