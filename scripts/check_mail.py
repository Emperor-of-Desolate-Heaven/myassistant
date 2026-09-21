#!/usr/bin/env python3
"""定时邮件检查:发现新邮件 → Bark 推送到 iPhone。

设计(与 Task Scheduler 配合,每 30 分钟跑一次):
  - 只通知"最近 48 小时内的未处理邮件",陈年旧信不打扰;
  - 跳过自己发出的邮件(发件人=自己任一账号);
  - 已推送过的 UID 记在 data/state/push-notified.json,绝不重复推送;
  - 幂等:未处理 UID 仍以 data/state/email/ 为准(与 mail.py 共享)。
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email import policy
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail import load_env, get_accounts, load_state, imap_conn, dec
from push import bark_push

ROOT = Path(__file__).resolve().parent.parent
NOTIFIED_FILE = ROOT / "data" / "state" / "push-notified.json"
WINDOW_H = 48
FETCH_BATCH = 30


def load_notified():
    if NOTIFIED_FILE.is_file():
        try:
            return json.loads(NOTIFIED_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_notified(d):
    NOTIFIED_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTIFIED_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    key = load_env().get("BARK_KEY", "").strip()
    if not key:
        print("[错误] .env 无 BARK_KEY,无法推送", file=sys.stderr)
        sys.exit(1)
    accs = get_accounts()
    self_addrs = {a["user"].lower() for a in accs.values() if a.get("user")}
    notified = load_notified()
    fresh, errors = [], []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_H)

    for name, acc in accs.items():
        if not acc["complete"]:
            continue
        processed = load_state(acc)
        try:
            M = imap_conn(acc)
            M.select("INBOX")
            typ, data = M.uid("search", None, "ALL")
            raw = b" ".join(x for x in data if isinstance(x, bytes))
            uids = [int(u) for u in raw.split()][-FETCH_BATCH:]
            for uid in uids:
                if str(uid) in processed or str(uid) in notified.get(name, []):
                    continue
                typ2, d2 = M.uid("fetch", str(uid).encode(),
                                "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if typ2 != "OK" or not d2 or not isinstance(d2[0], tuple):
                    continue
                msg = BytesParser(policy=policy.default).parsebytes(d2[0][1])
                frm = parseaddr(dec(msg.get("From")))[1].lower()
                if frm in self_addrs:
                    continue  # 自己发出的,不通知
                dt = None
                try:
                    dt = parsedate_to_datetime(msg.get("Date"))
                except Exception:
                    pass
                if dt and dt < cutoff:
                    continue  # 超过 48 小时
                fresh.append((name, uid, dec(msg.get("From")), dec(msg.get("Subject")), dt))
                notified.setdefault(name, []).append(str(uid))
            M.logout()
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue

    save_notified(notified)
    if fresh:
        lines = [f"· {acc} | {subj[:40]}" for acc, _, _, subj, _ in fresh[:5]]
        more = f" 等 {len(fresh)} 封" if len(fresh) > 5 else ""
        bark_push(key, f"新邮件 {len(fresh)} 封", "\n".join(lines) + more)
        print(f"已推送 {len(fresh)} 封新邮件")
    else:
        print("无新邮件")
    for e in errors:
        print(f"[错误] {e}", file=sys.stderr)
    sys.exit(1 if errors and not fresh else 0)


if __name__ == "__main__":
    main()
