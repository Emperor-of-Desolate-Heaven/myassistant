@echo off
chcp 65001 >nul
cd /d D:\生成式软件工程\myassistant
"%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe" scripts\check_tasks.py >> logs\task-watcher.log 2>&1
