#!/usr/bin/env python3
"""定时查 ehall 假期登记窗口:开放 → Bark 推送到 iPhone。

每天一次(Task Scheduler)。依赖常驻浏览器(见 CLAUDE.md ehall 一节)。
窗口开放时通知用户"可以请假登记了",由用户决定是否让助手代办。
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from push import bark_push
from mail import load_env

ROOT = Path(__file__).resolve().parent.parent


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    key = load_env().get("BARK_KEY", "").strip()
    if not key:
        print("[错误] .env 无 BARK_KEY", file=sys.stderr)
        sys.exit(1)
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ehall.py"), "app-status"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        bark_push(key, "ehall 检查超时", "假期登记窗口检查卡住,需要人工看看。")
        sys.exit(1)
    out = (r.stdout or "") + (r.stderr or "")
    if "open:" in out:
        bark_push(key, "假期登记窗口开放", "ehall 节假日离返校已开放登记,回复助手即可帮你填表提交。")
        print("窗口开放,已推送")
    elif "closed:" in out:
        print("窗口未开放,无推送")
    else:
        bark_push(key, "ehall 检查异常", "常驻浏览器或登录会话不可用,需要处理(重新登录)。")
        print("检查异常,已推送提醒")
        sys.exit(1)


if __name__ == "__main__":
    main()
