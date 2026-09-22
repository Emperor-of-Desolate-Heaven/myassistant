#!/usr/bin/env python3
"""定时邮件检查:发现新邮件 → Bark 推送到 iPhone;自己发来的邮件 → 转成任务。

设计(与 Task Scheduler 配合,每 30 分钟跑一次):
  - 只通知"最近 48 小时内的未处理邮件",陈年旧信不打扰;
  - 发件人=自己任一账号的收件箱邮件,是用户从手机邮箱发来的指令:
    自动转成 tasks.json 里 status=confirmed 的任务(交给 task-watcher 唤醒
    headless Agent 执行),并 Bark 通知用户已收到;
  - 已推送过的 UID 记在 data/state/push-notified.json,绝不重复推送/转任务;
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
TASKS_FILE = ROOT / "data" / "state" / "server" / "tasks.json"
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


def load_tasks():
    if TASKS_FILE.is_file():
        try:
            return json.loads(TASKS_FILE.read_text(encoding="utf-8")).get("tasks", [])
        except json.JSONDecodeError:
            pass
    return []


def save_tasks(tasks):
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(
        {"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")


def new_tid(tasks):
    base = "t" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    tid, n = base, 1
    while any(t["id"] == tid for t in tasks):
        n += 1
        tid = f"{base}-{n}"
    return tid


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
    fresh, instructions, errors = [], [], []
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
                dt = None
                try:
                    dt = parsedate_to_datetime(msg.get("Date"))
                except Exception:
                    pass
                if dt and dt < cutoff:
                    continue  # 超过 48 小时,陈年旧信不打扰
                notified.setdefault(name, []).append(str(uid))
                if frm in self_addrs:
                    # 自己发来的 = 用户从手机邮箱布置的指令
                    instructions.append((name, uid, dec(msg.get("Subject")), dt))
                    continue
                fresh.append((name, uid, dec(msg.get("From")), dec(msg.get("Subject")), dt))
            M.logout()
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue

    save_notified(notified)
    if instructions:
        tasks = load_tasks()
        for name, uid, subj, dt in instructions:
            tid = new_tid(tasks)
            when = dt.strftime("%m-%d %H:%M") if dt else "?"
            tasks.append({
                "id": tid,
                "title": f"邮件指令:{subj[:30]}",
                "detail": ("来源:邮件指令(用户从手机邮箱发给自己账号的邮件)\n"
                           f"账号:{name}\nUID:{uid}\n主题:{subj}\n时间:{when}\n"
                           f"请用 py scripts/mail.py read {name} {uid} 读邮件全文,"
                           "按邮件内容完成用户要求;处理完后用 "
                           f"py scripts/mail.py done {name} {uid} 标记已处理。"),
                "status": "confirmed",
                "source": "email",
                "result": "已收到,处理中",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        save_tasks(tasks)
        lines = [f"· {subj[:40]}" for _, _, subj, _ in instructions[:5]]
        bark_push(key, f"收到你的邮件指令 {len(instructions)} 条", "\n".join(lines))
        print(f"已转成任务 {len(instructions)} 条邮件指令")
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
