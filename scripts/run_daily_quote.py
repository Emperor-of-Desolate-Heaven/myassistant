#!/usr/bin/env python3
"""每日自律推送:headless claude 执行 CLAUDE.md 的例行事务。

由计划任务经 run_daily_quote.bat 调用。中文提示词放在这里而不是 .bat 里:
Windows 的 cmd 用 GBK 解析 UTF-8 无 BOM 的 .bat 会乱码,.bat 一律保持纯 ASCII
(踩坑记录见 DELIVERY.md)。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# claude CLI:优先 PATH,否则用 WinGet 默认安装位置(基于 USERPROFILE,不写死用户名)
CLAUDE = shutil.which("claude") or str(
    Path(os.environ.get("USERPROFILE", "~")) / "AppData" / "Local" / "Microsoft"
    / "WinGet" / "Packages"
    / "Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe" / "claude.exe")

PROMPT = (
    "你是用户的个人助手(项目在 D:\\生成式软件工程\\myassistant,先读 CLAUDE.md)。"
    "现在执行 CLAUDE.md '用户交给的例行事务' 中的每日自律推送:"
    "从网上找一条简短的自律名言或小故事(80 字以内,不与 "
    "data/state/quotes-used.md 里已用过的重复),用 py scripts/push.py "
    "自律打卡 <内容> 推送到用户 iPhone,并把内容追加一行到 "
    "data/state/quotes-used.md。自动完成,不要提问。")


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    r = subprocess.run(
        [CLAUDE, "-p", PROMPT, "--permission-mode", "bypassPermissions"],
        timeout=900, cwd=str(ROOT))
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
