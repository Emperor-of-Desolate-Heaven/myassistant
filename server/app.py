#!/usr/bin/env python3
"""手机端联动服务(FastAPI):任务队列 + 手机确认页 + 草稿编辑。

设计目标:手机不需要桌面端开着的对话窗口,只靠浏览器即可:
  - 查看任务进度:GET  /           (任务列表,手机友好页面)
  - 创建任务:      POST /tasks     (Agent 用;创建后配合 scripts/push.py 推送确认链接)
  - 确认/拒绝:     POST /tasks/<id>/confirm|reject  (手机浏览器点按钮即触发)
  - 手机留言板:    GET/POST /new   (用户从手机直接布置任务,无需桌面窗口)
  - 查看/编辑草稿: GET/POST /drafts/<name>  (Agent 生成的待确认邮件草稿)

状态存 data/state/server/tasks.json(不入 git)。监听 0.0.0.0,
手机经 Tailscale 访问 http://<电脑100.x地址>:<端口>/。
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "state" / "server" / "tasks.json"
DRAFTS_DIR = ROOT / "drafts"
SERVER_PORT = 8765

sys.path.insert(0, str(ROOT / "scripts"))
try:
    from mail import load_env  # 端口从 .env 读
    SERVER_PORT = int(load_env().get("SERVER_PORT", SERVER_PORT))
except Exception:
    pass

app = FastAPI(title="myassistant 手机端")


# ---------- 状态读写 ----------

def load_tasks():
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8")).get("tasks", [])
        except json.JSONDecodeError:
            pass
    return []


def save_tasks(tasks):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(
        {"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_tid(tasks):
    """生成任务 ID(时间戳格式),避免与旧 ID 或并发创建冲突。"""
    base = "t" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    tid, n = base, 1
    while any(t["id"] == tid for t in tasks):
        n += 1
        tid = f"{base}-{n}"
    return tid


STATUS_CN = {"pending": "待确认", "confirmed": "已确认", "rejected": "已拒绝", "done": "已完成"}


# ---------- 页面 ----------

PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, "PingFang SC", sans-serif; max-width: 640px;
  margin: 0 auto; padding: 16px; background: #f5f5f7; color: #1d1d1f; }}
h1 {{ font-size: 22px; }}
.card {{ background: #fff; border-radius: 12px; padding: 14px 16px;
  margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 8px;
  font-size: 12px; background: #e8e8ed; }}
.badge.pending {{ background: #ffe8a3; }}
.badge.confirmed {{ background: #c8f0c0; }}
.badge.rejected {{ background: #ffd4d4; }}
.btn {{ display: inline-block; padding: 10px 22px; border-radius: 10px;
  text-decoration: none; font-size: 16px; border: none; margin-right: 8px; }}
.btn.ok {{ background: #007aff; color: #fff; }}
.btn.no {{ background: #e0e0e5; color: #1d1d1f; }}
.detail {{ white-space: pre-wrap; }}
.meta {{ color: #86868b; font-size: 13px; }}
a {{ color: #007aff; }}
textarea {{ width: 100%; min-height: 40vh; font-size: 15px; padding: 10px;
  border: 1px solid #d2d2d7; border-radius: 10px; box-sizing: border-box; }}
input[type=text] {{ width: 100%; font-size: 16px; padding: 10px;
  border: 1px solid #d2d2d7; border-radius: 10px; box-sizing: border-box; }}
</style></head><body>
{body}
</body></html>"""


def task_card(t):
    badge = STATUS_CN.get(t.get("status"), "?")
    href = f"/tasks/{t['id']}"
    return (f"<div class='card'><a href='{href}'><b>{t['title']}</b></a>"
            f"<div class='meta'>{t['created_at'][:16]} · <span class='badge {t['status']}'>{badge}</span></div>"
            f"<div class='detail'>{t.get('detail', '')[:80]}</div></div>")


@app.get("/", response_class=HTMLResponse)
def index():
    tasks = sorted(load_tasks(), key=lambda t: t.get("created_at", ""), reverse=True)
    body = ("<h1>我的助手 · 任务</h1>"
            "<div class='card'><a class='btn ok' href='/new'>＋ 布置新任务</a>"
            "<span class='meta'>提交后约 5 分钟内处理,Bark 通知结果</span></div>")
    body += "".join(task_card(t) for t in tasks) or "<div class='card'>暂无任务</div>"
    return PAGE.format(title="我的助手 · 任务", body=body)


def linkify(s):
    """把 [文字](url) 渲染成可点链接;其余 HTML 字符转义。"""
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)


@app.get("/tasks/{tid}", response_class=HTMLResponse)
def task_page(tid: str):
    tasks = load_tasks()
    t = next((x for x in tasks if x["id"] == tid), None)
    if not t:
        raise HTTPException(404, "任务不存在")
    badge = STATUS_CN.get(t["status"], "?")
    body = (f"<h1>{t['title']}</h1>"
            f"<div class='card'><span class='badge {t['status']}'>{badge}</span>"
            f"<div class='meta'>创建于 {t['created_at'][:16]}</div>"
            f"<div class='detail'>{linkify(t.get('detail', ''))}</div></div>")
    if t["status"] == "pending":
        body += (f"<form method='post' action='/tasks/{tid}/confirm'>"
                 f"<button class='btn ok' type='submit'>确认执行</button></form><br>"
                 f"<form method='post' action='/tasks/{tid}/reject'>"
                 f"<button class='btn no' type='submit'>拒绝</button></form>")
    else:
        if t["status"] == "confirmed" and not t.get("result"):
            r = "已收到,处理中(最长约 5 分钟,结果经 Bark 通知)"
        else:
            r = t.get("result") or "已处理"
        body += f"<div class='card meta'>处理结果:{r}</div>"
    body += "<br><a href='/'>← 返回任务列表</a>"
    return PAGE.format(title=t["title"], body=body)


def _set_status(tid, status, result=""):
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == tid:
            t["status"] = status
            t["result"] = result
            t["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks(tasks)
            return t
    raise HTTPException(404, "任务不存在")


@app.post("/tasks/{tid}/confirm")
def confirm(tid: str):
    _set_status(tid, "confirmed", "已确认")
    return RedirectResponse(f"/tasks/{tid}", 303)


@app.post("/tasks/{tid}/reject")
def reject(tid: str):
    _set_status(tid, "rejected", "已拒绝")
    return RedirectResponse(f"/tasks/{tid}", 303)


@app.post("/tasks")
def create_task(title: str = Form(...), detail: str = Form("")):
    tasks = load_tasks()
    tid = _new_tid(tasks)
    tasks.append({
        "id": tid, "title": title, "detail": detail, "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    save_tasks(tasks)
    return RedirectResponse(f"/tasks/{tid}", 303)


# ---------- 手机留言板(用户直接布置任务) ----------

@app.get("/new", response_class=HTMLResponse)
def new_task_page():
    body = ("<h1>给助手布置任务</h1>"
            "<div class='card'><form method='post' action='/new'>"
            "<input type='text' name='title' placeholder='一句话标题(必填)' required>"
            "<br><br>"
            "<textarea name='content' placeholder='具体要求……(选填)' "
            "style='min-height:30vh'></textarea><br><br>"
            "<button class='btn ok' type='submit'>发送给助手</button></form></div>"
            "<div class='card meta'>提交后约 5 分钟内处理,结果经 Bark 通知手机。</div>"
            "<a href='/'>← 返回任务列表</a>")
    return PAGE.format(title="布置任务", body=body)


@app.post("/new")
def new_task(title: str = Form(...), content: str = Form("")):
    tasks = load_tasks()
    tid = _new_tid(tasks)
    tasks.append({
        "id": tid, "title": title, "detail": content, "status": "confirmed",
        "source": "phone-form", "result": "已收到,处理中",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    save_tasks(tasks)
    return RedirectResponse(f"/tasks/{tid}", 303)


# ---------- 草稿 ----------

def _draft_path(name: str):
    name = Path(name).name  # 拒绝路径穿越
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.md", name):
        raise HTTPException(400, "草稿名不合法")
    return DRAFTS_DIR / name


@app.get("/drafts", response_class=HTMLResponse)
def draft_list():
    files = sorted(DRAFTS_DIR.glob("*.md")) if DRAFTS_DIR.is_dir() else []
    body = "<h1>待确认草稿</h1>"
    body += "".join(f"<div class='card'><a href='/drafts/{f.name}'>{f.name}</a></div>" for f in files) \
        or "<div class='card'>暂无草稿</div>"
    body += "<br><a href='/'>← 返回任务列表</a>"
    return PAGE.format(title="草稿", body=body)


@app.get("/drafts/{name}", response_class=HTMLResponse)
def draft_page(name: str):
    f = _draft_path(name)
    if not f.is_file():
        raise HTTPException(404, "草稿不存在")
    content = f.read_text(encoding="utf-8")
    body = (f"<h1>草稿:{name}</h1>"
            f"<form method='post' action='/drafts/{name}'>"
            f"<textarea name='content'>{content}</textarea><br><br>"
            f"<button class='btn ok' type='submit'>保存修改</button>"
            f"<a class='btn no' href='/drafts'>取消</a></form>")
    return PAGE.format(title=name, body=body)


@app.post("/drafts/{name}")
def draft_save(name: str, content: str = Form(...)):
    f = _draft_path(name)
    if not f.is_file():
        raise HTTPException(404, "草稿不存在")
    f.write_text(content, encoding="utf-8")
    return RedirectResponse(f"/drafts/{name}", 303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
