#!/usr/bin/env python3
"""发作业一条龙:找 PDF → smail 发 fla_26 → 监听自动回复 → Bark 推送结果。

用法:
  py scripts/send_homework.py <n> [--listen 秒] [--body 正文]

固定规则(2026-10-11 用户确认):
  - 附件:D:/fla_26/形式语言与自动机_作业{n}_241220161_李璟睿.pdf
  - 主题:形式语言与自动机_作业{n}_241220161_李璟睿
  - 发件:smail;收件:fla_26@163.com;正文默认空
  - 发送后监听 fla_26 自动回复(默认 90 秒),收到即标记已处理并 Bark 推送结果

幂等:drafts/sent/smail-homework{n}.md 已存在 = 该作业已发过,直接拒绝。
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from push import bark_push
from mail import load_env

ROOT = Path(__file__).resolve().parent.parent
HOMEWORK_DIR = Path("D:/fla_26")
TO_ADDR = "fla_26@163.com"
ACC = "smail"
NAME = "241220161_李璟睿"


def bark(key, title, body):
    try:
        bark_push(key, title, body)
        print("Bark 推送成功")
    except Exception as e:
        print(f"[错误] Bark 推送失败: {e}", file=sys.stderr)


def main():
    for s in (sys.stdout, sys.stderr):
        if s and hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="发作业一条龙")
    p.add_argument("n", help="作业编号")
    p.add_argument("--listen", type=int, default=90, help="监听自动回复秒数(默认 90)")
    p.add_argument("--body", default="", help="邮件正文(默认空)")
    a = p.parse_args()
    key = load_env().get("BARK_KEY", "").strip()
    subject = f"形式语言与自动机_作业{a.n}_{NAME}"
    pdf = HOMEWORK_DIR / f"{subject}.pdf"
    if not pdf.is_file():
        print(f"[错误] 附件不存在:{pdf}", file=sys.stderr)
        if key:
            bark(key, "作业发送失败", f"找不到附件:{pdf.name}")
        sys.exit(1)
    sent = ROOT / "drafts" / "sent" / f"{ACC}-homework{a.n}.md"
    if sent.is_file():
        print(f"[跳过] {sent.relative_to(ROOT)} 已存在,作业{a.n} 已发过(幂等保护)")
        if key:
            bark(key, f"作业{a.n}已发过", "草稿归档已存在,未重复发送。")
        sys.exit(0)
    draft = ROOT / "drafts" / f"{ACC}-homework{a.n}.md"
    draft.write_text(
        f"---\nto: {TO_ADDR}\nsubject: {subject}\n"
        f"attach: {pdf.as_posix()}\n---\n{a.body}\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mail.py"), "send",
         f"drafts/{draft.name}"],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120, cwd=str(ROOT))
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip())
    if r.returncode != 0:
        if key:
            bark(key, f"作业{a.n}发送失败", out.strip()[:200])
        sys.exit(1)
    print(f"已发送 {subject} → {TO_ADDR},开始监听自动回复({a.listen} 秒)…")
    reply_uid = None
    deadline = time.time() + a.listen
    while time.time() < deadline:
        time.sleep(10)
        try:
            c = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "mail.py"), "check", ACC],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=90, cwd=str(ROOT))
            lines = (c.stdout or "").splitlines()
        except subprocess.TimeoutExpired:
            continue
        hits = [ln for ln in lines if "fla_26" in ln and "自动回复" in ln]
        if hits:
            m = re.search(r"\[(\d+)\]", hits[0])
            reply_uid = m.group(1) if m else None
            print("发现自动回复:", hits[0].strip())
            break
    if reply_uid:
        d = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "mail.py"), "done",
             ACC, reply_uid],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=str(ROOT))
        print((d.stdout or "").strip() or (d.stderr or "").strip())
        if key:
            bark(key, f"作业{a.n}发送成功",
                 f"{subject} 已发往 {TO_ADDR}(附件 PDF),自动回复已收到,对方已收到作业。")
    else:
        if key:
            bark(key, f"作业{a.n}已发送(未见自动回复)",
                 f"{subject} 已发往 {TO_ADDR},{a.listen} 秒内未收到自动回复,请留意。")
    sys.exit(0 if reply_uid else 1)


if __name__ == "__main__":
    main()
