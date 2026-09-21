#!/usr/bin/env python3
"""任务工具:创建手机确认任务并(可选)推送到 iPhone。

用法:
  py scripts/task.py new <标题> <详情...> [--push]   # 创建任务,打印任务页 URL
  py scripts/task.py list                            # 列出所有任务及状态
  py scripts/task.py get <任务id>                    # 查单个任务状态

为什么不用 curl:Windows shell 会把中文按 GBK 发出,服务端按 UTF-8 存成乱码。
本工具用 urllib 显式 UTF-8 编码,与运行环境无关(未来 headless 定时任务同样安全)。
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail import load_env
from push import bark_push

PORT = 8765
try:
    PORT = int(load_env().get("SERVER_PORT", PORT))
except Exception:
    pass
BASE = f"http://127.0.0.1:{PORT}"  # 本机调用用


def tailscale_ip():
    """查本机 Tailscale IP(推送给手机用的可达地址;127.0.0.1 在手机上指向手机自己)。"""
    import subprocess
    env = load_env()
    url = env.get("SERVER_URL", "").strip()  # 手工指定优先
    if url:
        return url.rstrip("/")
    candidates = [
        r"C:\Program Files\Tailscale\tailscale.exe",
        r"C:\Program Files (x86)\Tailscale\tailscale.exe",
    ]
    for exe in candidates:
        if Path(exe).is_file():
            try:
                out = subprocess.run([exe, "ip", "-4"], capture_output=True, timeout=10)
                ip = out.stdout.decode("utf-8", "replace").strip().splitlines()
                if ip and ip[0]:
                    return f"http://{ip[0]}:{PORT}"
            except Exception:
                pass
    return BASE  # 拿不到就用本机地址(仅本机调试场景)


def post_form(path, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, resp.geturl()


def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cmd_new(args):
    detail = " ".join(args.detail) if args.detail else ""
    code, url = post_form("/tasks", {"title": args.title, "detail": detail})
    tid = url.rstrip("/").rsplit("/", 1)[-1]
    print(f"任务已创建:{tid}")
    phone_url = f"{tailscale_ip()}/tasks/{tid}"  # 推送用手机可达地址
    print(f"确认页(本机): {url}")
    print(f"确认页(手机): {phone_url}")
    if args.push:
        key = load_env().get("BARK_KEY", "").strip()
        if not key:
            print("[错误] .env 中没有 BARK_KEY,无法推送", file=sys.stderr)
            sys.exit(1)
        bark_push(key, args.title, "点开确认:" + (detail[:50] or args.title), phone_url)
        print("已推送到 iPhone(Bark)")
    return tid


def cmd_list(_args):
    with urllib.request.urlopen(BASE + "/", timeout=15) as resp:
        html = resp.read().decode("utf-8")
    # 任务列表没有 JSON 接口,从页面里抽标题与状态徽章
    import re
    for m in re.finditer(r"href='/tasks/(t\d+)'><b>(.*?)</b></a>", html):
        print(f"{m.group(1)}  {m.group(2)}")
    for m in re.finditer(r"<span class='badge (\w+)'>([^<]+)</span>", html):
        print(f"  {m.group(1)}: {m.group(2)}")


def cmd_get(args):
    with urllib.request.urlopen(f"{BASE}/tasks/{args.tid}", timeout=15) as resp:
        html = resp.read().decode("utf-8")
    import re
    status = re.search(r"<span class='badge (\w+)'>([^<]+)</span>", html)
    detail = re.search(r"<div class='detail'>(.*?)</div>", html, re.S)
    print(f"{args.tid} 状态: {status.group(2) if status else '?'}")
    if detail:
        print("详情:", detail.group(1).strip())


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="手机确认任务工具")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new", help="创建任务")
    n.add_argument("title")
    n.add_argument("detail", nargs="*")
    n.add_argument("--push", action="store_true", help="创建后推送到 iPhone")
    sub.add_parser("list", help="列出任务")
    g = sub.add_parser("get", help="查任务状态")
    g.add_argument("tid")
    args = p.parse_args()
    {"new": cmd_new, "list": cmd_list, "get": cmd_get}[args.cmd](args)


if __name__ == "__main__":
    main()
