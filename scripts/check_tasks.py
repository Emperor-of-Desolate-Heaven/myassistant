#!/usr/bin/env python3
"""手机任务监视器:检测新确认的任务,唤醒 headless Agent 处理。

配合 Task Scheduler 每 5 分钟跑一次(见 scripts/run_task_watcher.bat)。
平时只读状态文件,零成本;只有发现"新确认且未处理"的任务才唤醒 Agent。

幂等:处理状态记 data/state/agent-handled.json;Agent 处理失败最多重试 3 次,
之后放弃并 Bark 提醒用户人工介入。
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail import load_env
from push import bark_push

ROOT = Path(__file__).resolve().parent.parent
TASKS_FILE = ROOT / "data" / "state" / "server" / "tasks.json"
HANDLED_FILE = ROOT / "data" / "state" / "agent-handled.json"
MAX_ATTEMPTS = 3

# claude CLI:优先 PATH,否则用 WinGet 默认安装位置(基于 USERPROFILE,不写死用户名)
CLAUDE = shutil.which("claude") or str(
    Path(os.environ.get("USERPROFILE", "~")) / "AppData" / "Local" / "Microsoft"
    / "WinGet" / "Packages"
    / "Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe" / "claude.exe")

AGENT_PROMPT = (
    "你是用户的个人助手(项目在 D:\\生成式软件工程\\myassistant,先读 CLAUDE.md)。"
    "用户刚在手机上确认了任务,现在要完成后续处理:"
    "1) 读 data/state/server/tasks.json,找出 status=confirmed 的任务;"
    "2) 查看 drafts/ 目录中用户填写过的草稿(如 phone-input-*.md);"
    "3) 按任务要求完成后续:把内容落进 data/ 数据库、重建索引、"
    "用 py scripts/push.py 给用户推送处理结果;"
    "4) 全程自动完成,不要提问,不要修改任务文件本身。")


def load_json(f, default):
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def save_json(f, data):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    tasks = [t for t in load_json(TASKS_FILE, {}).get("tasks", [])
             if t.get("status") == "confirmed"]
    handled = load_json(HANDLED_FILE, {})
    todo = [t for t in tasks if t["id"] not in handled
            or handled[t["id"]].get("status") == "failed" and handled[t["id"]].get("attempts", 0) < MAX_ATTEMPTS]
    if not todo:
        print("无新确认任务")
        return
    for t in todo:
        tid = t["id"]
        rec = handled.get(tid, {"attempts": 0})
        print(f"处理任务 {tid}: {t.get('title', '')[:40]}")
        try:
            r = subprocess.run(
                [CLAUDE, "-p", AGENT_PROMPT, "--permission-mode", "bypassPermissions"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=900, cwd=str(ROOT))
            out = (r.stdout or "")[-500:] + (r.stderr or "")[-200:]
            if r.returncode == 0:
                handled[tid] = {"status": "done", "attempts": rec.get("attempts", 0) + 1,
                                "at": datetime.now(timezone.utc).isoformat(), "log": out}
                print(f"  {tid} 完成")
            else:
                raise RuntimeError(f"claude 退出码 {r.returncode}")
        except Exception as e:
            rec["attempts"] = rec.get("attempts", 0) + 1
            rec["status"] = "failed"
            rec["last_error"] = str(e)[:200]
            rec["at"] = datetime.now(timezone.utc).isoformat()
            handled[tid] = rec
            print(f"  {tid} 失败(第 {rec['attempts']} 次): {e}", file=sys.stderr)
            if rec["attempts"] >= MAX_ATTEMPTS:
                key = load_env().get("BARK_KEY", "").strip()
                if key:
                    try:
                        bark_push(key, "助手处理任务失败", f"任务 {tid} 尝试 {MAX_ATTEMPTS} 次未完成,需要人工介入。")
                    except Exception:
                        pass
    save_json(HANDLED_FILE, handled)


if __name__ == "__main__":
    main()
