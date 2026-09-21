@echo off
chcp 65001 >nul
cd /d D:\生成式软件工程\myassistant
"%USERPROFILE%\AppData\Local\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe\claude.exe" -p "执行 CLAUDE.md '用户交给的例行事务' 中的每日自律推送:找一条简短自律名言或小故事(80字以内,不与 data/state/quotes-used.md 中已用过的重复),用 py scripts/push.py 自律打卡 <内容> 推送到用户 iPhone,并把内容追加一行到 data/state/quotes-used.md。自动完成,不要提问。" --permission-mode bypassPermissions >> logs\daily-quote.log 2>&1
