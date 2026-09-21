#!/usr/bin/env python3
"""Bark 推送工具(iOS)。纯标准库,无第三方依赖。

用法:
  py scripts/push.py <标题> <正文>
  可选 --url <链接>   点击推送后跳转的地址(如确认页)

Bark Key 从 .env 的 BARK_KEY 读取;Bark 官方服务器 api.day.app 转发到
用户手机上的 Bark App(同一 Key)。
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from mail import load_env  # 复用 .env 读取


def bark_push(key, title, body, url=None):
    api = f"https://api.day.app/{key}/" + urllib.parse.quote(title)
    if body:
        api += "/" + urllib.parse.quote(body)
    params = {}
    if url:
        params["url"] = url
    if params:
        api += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(api, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data  # {"code": 200, "message": "success", ...}


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Bark 推送")
    p.add_argument("title")
    p.add_argument("body", nargs="?")
    p.add_argument("--url", default="")
    args = p.parse_args()
    key = load_env().get("BARK_KEY", "").strip()
    if not key:
        print("[错误] .env 中没有 BARK_KEY,请先在手机 Bark App 中查看并填入", file=sys.stderr)
        sys.exit(1)
    try:
        data = bark_push(key, args.title, args.body or "", args.url)
        if data.get("code") == 200:
            print("推送成功")
        else:
            print(f"[错误] Bark 返回异常: {data}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[错误] 推送失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
