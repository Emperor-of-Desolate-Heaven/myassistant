#!/usr/bin/env python3
"""多账号邮箱工具:IMAP 收信、草稿、SMTP 发信。纯标准库,无第三方依赖。

用法:
  py scripts/mail.pycheck [账号...]     # 列出未处理的新邮件(默认全部启用账号)
  py scripts/mail.pycheck --all         # 含已处理过的
  py scripts/mail.pyread <账号> <UID>   # 读全文(不标记已读)
  py scripts/mail.pynew <账号> <UID>    # 生成回复草稿模板 drafts/<账号>-<UID>.md
  py scripts/mail.pysend <草稿文件>     # 发送草稿(发送前必须经用户确认)
  py scripts/mail.pydone <账号> <UID>   # 标记已处理(无需回复)
  py scripts/mail.pystate               # 各账号处理状态

幂等:已处理 UID 存在 data/state/email/<账号>.json;check 默认跳过它们,
重复检查邮箱不会重复处理或重复发送。
"""
import argparse
import json
import re
import ssl
import sys
import imaplib
import smtplib
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.parser import BytesParser
from email import policy
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "data" / "state" / "email"
DRAFTS_DIR = ROOT / "drafts"
FETCH_BATCH = 50


def load_env():
    env = {}
    f = ROOT / ".env"
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def get_accounts():
    env = load_env()
    names = [n.strip() for n in env.get("MAIL_ACCOUNTS", "").split(",") if n.strip()]
    accs = {}
    for name in names:
        key = name.upper()
        user = env.get(f"MAIL_{key}_USER", "").strip()
        pas = env.get(f"MAIL_{key}_PASS", "").strip()
        accs[name] = {
            "name": name,
            "user": user,
            "pass": pas,
            "complete": bool(user and pas),
            "imap": env.get(f"MAIL_{key}_IMAP", "").strip() or "imap.exmail.qq.com",
            "smtp": env.get(f"MAIL_{key}_SMTP", "").strip() or "smtp.exmail.qq.com",
        }
    return accs


def pick_accounts(args_names):
    accs = get_accounts()
    if not accs:
        print("[错误] 没有配置好的邮箱账号,请先填 .env", file=sys.stderr)
        sys.exit(1)
    if args_names:
        unknown = [n for n in args_names if n not in accs]
        if unknown:
            print(f"[错误] 未知账号: {', '.join(unknown)};可用: {', '.join(accs)}", file=sys.stderr)
            sys.exit(1)
        return {n: accs[n] for n in args_names}
    return accs


def load_state(acc):
    f = STATE_DIR / f"{acc['name']}.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("processed", {})
        except json.JSONDecodeError:
            pass
    return {}


def save_state(acc, processed):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{acc['name']}.json").write_text(
        json.dumps({"processed": processed}, ensure_ascii=False, indent=2), encoding="utf-8")


def dec(s):
    """解码邮件头(处理 =?utf-8?...?= 编码字)。"""
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def send_id(M):
    """发送 IMAP ID 命令(网易 Coremail 服务器要求,否则 SELECT 报 Unsafe Login)。"""
    imaplib.Commands["ID"] = ("NONAUTH", "AUTH", "SELECTED")
    try:
        M._simple_command("ID", '("name" "myassistant" "version" "1.0")')
    except imaplib.IMAP4.error:
        pass  # 服务器不支持 ID 也不影响(如部分企业邮)


def imap_conn(acc):
    M = imaplib.IMAP4_SSL(acc["imap"], 993, ssl_context=ssl.create_default_context())
    send_id(M)
    M.login(acc["user"], acc["pass"])
    return M


def fetch_meta(M, uids):
    """取一批邮件的 From/Subject/Date,返回 {uid: (from, subject, date_str)}。"""
    result = {}
    if not uids:
        return result
    uidset = b",".join(str(u).encode() for u in uids)
    typ, data = M.uid("fetch", uidset, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
    if typ != "OK":
        return result
    for item in data:
        if not isinstance(item, tuple):
            continue
        meta = item[0].decode("utf-8", "replace")
        # 响应形如 "seq (UID n BODY[...] {...}";UID 才是稳定标识,seq 只是当前位置
        m = re.search(r"\(UID (\d+)", meta) or re.match(r"(\d+) ", meta)
        if not m:
            continue
        uid = m.group(1)
        try:
            msg = BytesParser(policy=policy.default).parsebytes(item[1])
            dt = None
            try:
                dt = parsedate_to_datetime(msg.get("Date"))
            except Exception:
                dt = None
            result[uid] = (
                dec(msg.get("From")),
                dec(msg.get("Subject")).replace("\n", " "),
                dt.strftime("%Y-%m-%d %H:%M" if dt.year != datetime.now().year else "%m-%d %H:%M") if dt else "?",
            )
        except Exception:
            result[uid] = ("?", "?", "?")
    return result


def extract_body(msg):
    """取文本正文与附件名列表。"""
    plain, has_html, atts = [], False, []
    if not msg.is_multipart():
        if msg.get_content_type() == "text/plain":
            return msg.get_content(), atts
        return "(无文本正文)", atts
    for part in msg.walk():
        if part.is_multipart():
            continue
        fname = part.get_filename()
        if fname:
            atts.append(dec(fname))
        elif part.get_content_type() == "text/plain":
            try:
                plain.append(part.get_content())
            except Exception:
                plain.append(str(part.get_payload(decode=True), "utf-8", "replace"))
        elif part.get_content_type() == "text/html":
            has_html = True
    if plain:
        return "\n\n".join(plain), atts
    return ("(只有 HTML 版本,未展示)" if has_html else "(无文本正文)"), atts


# ---------- 子命令 ----------

def cmd_check(args):
    total = 0
    for name, acc in pick_accounts(args.accounts).items():
        if not acc["complete"]:
            print(f"== {name} 未配置(缺用户名或密码,请填 .env)== ")
            continue
        processed = load_state(acc)
        try:
            M = imap_conn(acc)
            M.select("INBOX")
            typ, data = M.uid("search", None, "ALL")
            raw = b" ".join(x for x in data if isinstance(x, bytes))
            uids = [int(u) for u in raw.split()]
            recent = uids[-FETCH_BATCH:]
            metas = fetch_meta(M, recent)
            M.logout()
        except imaplib.IMAP4.error as e:
            print(f"[错误] {name} 登录或读取失败: {e}", file=sys.stderr)
            continue
        shown = 0
        print(f"== {name} <{acc['user']}> ==")
        for u in reversed(recent):
            if str(u) in processed and not args.all:
                continue
            frm, subj, when = metas.get(str(u), ("?", "?", "?"))
            tag = " [已处理]" if str(u) in processed else ""
            print(f"  [{u}] {when}  {frm}  {subj}{tag}")
            shown += 1
        total += shown
        print(f"  -- 最近 {len(recent)} 封,未处理 {shown} 封 --")
    print(f"合计未处理 {total} 封" if not args.all else "")


def cmd_read(args):
    acc = pick_accounts([args.account])[args.account]
    M = imap_conn(acc)
    M.select("INBOX")
    typ, data = M.uid("fetch", str(args.uid).encode(), "(BODY.PEEK[])")
    M.logout()
    if typ != "OK" or not data or not isinstance(data[0], tuple):
        print(f"[错误] 找不到 {args.account} UID {args.uid}", file=sys.stderr)
        sys.exit(1)
    msg = BytesParser(policy=policy.default).parsebytes(data[0][1])
    print(f"From: {dec(msg.get('From'))}")
    print(f"To: {dec(msg.get('To'))}")
    print(f"Date: {msg.get('Date')}")
    print(f"Subject: {dec(msg.get('Subject'))}")
    print(f"Message-ID: {msg.get('Message-ID')}")
    print("---")
    body, atts = extract_body(msg)
    print(body)
    if atts:
        print("---")
        print("附件:", ", ".join(atts))


def cmd_new(args):
    acc = pick_accounts([args.account])[args.account]
    M = imap_conn(acc)
    M.select("INBOX")
    typ, data = M.uid("fetch", str(args.uid).encode(), "(BODY.PEEK[])")
    M.logout()
    if typ != "OK" or not data or not isinstance(data[0], tuple):
        print(f"[错误] 找不到 {args.account} UID {args.uid}", file=sys.stderr)
        sys.exit(1)
    msg = BytesParser(policy=policy.default).parsebytes(data[0][1])
    reply_hdr = msg.get("Reply-To") or msg.get("From") or ""
    to_addr = parseaddr(dec(reply_hdr))[1]
    subject = dec(msg.get("Subject"))
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    body, _ = extract_body(msg)
    quoted = "\n".join("> " + ln for ln in body.splitlines()) if body else "> (无文本)"
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    f = DRAFTS_DIR / f"{args.account}-{args.uid}.md"
    f.write_text(
        f"---\nto: {to_addr}\nsubject: {subject}\n---\n\n"
        f"(待写正文)\n\n# 原邮件(参考)\n\nFrom: {dec(msg.get('From'))}\n"
        f"Date: {msg.get('Date')}\nTo: {dec(msg.get('To'))}\n\n{quoted}\n",
        encoding="utf-8")
    rel = f.relative_to(ROOT)
    print(f"草稿已生成:{rel}")
    print(f"编辑正文后发送: py scripts/mail.pysend {rel}")


def cmd_send(args):
    f = (ROOT / args.draft).resolve()
    if not f.is_file():
        print(f"[错误] 草稿不存在:{args.draft}", file=sys.stderr)
        sys.exit(1)
    m = re.match(r"([a-z0-9]+)-(\d+)\.md$", f.name)
    acc_name = m.group(1) if m else f.name.split("-", 1)[0]
    uid = m.group(2) if m else None
    accs = get_accounts()
    if acc_name not in accs:
        print(f"[错误] 账号未配置:{acc_name}", file=sys.stderr)
        sys.exit(1)
    acc = accs[acc_name]
    lines = f.read_text(encoding="utf-8").splitlines()
    header = {}
    i = 1
    while i < len(lines) and lines[i] != "---":
        if ":" in lines[i]:
            k, v = lines[i].split(":", 1)
            header[k.strip().lower()] = v.strip()
        i += 1
    body = "\n".join(lines[i + 1:]).strip()
    to, subject = header.get("to", ""), header.get("subject", "")
    if not to or not subject:
        print("[错误] 草稿缺少 to/subject", file=sys.stderr)
        sys.exit(1)
    if "(待写正文)" in body:
        print("[错误] 草稿正文未填写(仍含 '(待写正文)')", file=sys.stderr)
        sys.exit(1)
    msg = EmailMessage()
    msg["From"] = acc["user"]
    msg["To"] = to
    msg["Subject"] = subject
    if header.get("cc"):
        msg["Cc"] = header["cc"]
    msg.set_content(body)
    with smtplib.SMTP_SSL(acc["smtp"], 465, context=ssl.create_default_context(), timeout=30) as S:
        S.login(acc["user"], acc["pass"])
        S.send_message(msg)
    processed = load_state(acc)
    if uid:  # 回复型草稿(文件名 账号-UID.md)才更新幂等状态
        processed[uid] = {"status": "replied", "at": datetime.now(timezone.utc).isoformat(),
                          "subject": subject, "to": to}
        save_state(acc, processed)
    sent_dir = DRAFTS_DIR / "sent"
    sent_dir.mkdir(parents=True, exist_ok=True)
    f.rename(sent_dir / f.name)
    print(f"已发送并归档:drafts/sent/{f.name} (账号 {acc_name})")


def cmd_done(args):
    acc = pick_accounts([args.account])[args.account]
    processed = load_state(acc)
    processed[args.uid] = {"status": "no-reply", "at": datetime.now(timezone.utc).isoformat()}
    save_state(acc, processed)
    print(f"已标记 {args.account} UID {args.uid} 为已处理(无需回复)")


def cmd_state(args):
    for name, acc in get_accounts().items():
        if not acc["complete"]:
            print(f"== {name} 未配置(缺用户名或密码,请填 .env)== ")
            continue
        processed = load_state(acc)
        print(f"== {name} <{acc['user']}> 已处理 {len(processed)} 封 ==")
        rows = sorted(processed.items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:5]
        for uid, info in rows:
            print(f"  [{uid}] {info.get('at', '?')[:16]} {info.get('status', '?')} {info.get('subject', '')[:40]}")
        if not rows:
            print("  (无)")


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="多账号邮箱工具")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="列出未处理邮件")
    c.add_argument("accounts", nargs="*")
    c.add_argument("--all", action="store_true", help="含已处理的")
    r = sub.add_parser("read", help="读邮件全文")
    r.add_argument("account"); r.add_argument("uid")
    n = sub.add_parser("new", help="生成回复草稿模板")
    n.add_argument("account"); n.add_argument("uid")
    s = sub.add_parser("send", help="发送草稿")
    s.add_argument("draft")
    d = sub.add_parser("done", help="标记已处理")
    d.add_argument("account"); d.add_argument("uid")
    sub.add_parser("state", help="查看处理状态")
    args = p.parse_args()
    {"check": cmd_check, "read": cmd_read, "new": cmd_new,
     "send": cmd_send, "done": cmd_done, "state": cmd_state}[args.cmd](args)


if __name__ == "__main__":
    main()
