#!/usr/bin/env python3
"""ehall 网上办事服务大厅工具(Playwright)。保守确认模式。

用法:
  py scripts/ehall.py login-assist [--timeout 秒]   # 协作登录:自动填表,滑块由用户拖(推荐)
  py scripts/ehall.py login-manual [--timeout 秒]   # 纯人工登录(全自己操作)
  py scripts/ehall.py login                         # 全自动登录(风控下大概率弹滑块,慎用)
  py scripts/ehall.py explore <url>                 # 打开页面截图+列出可点元素(排查用)

会话持久化:用 Chromium 持久化配置目录(data/state/ehall/profile/),Cookie、
localStorage、浏览器指纹全部落盘,跨进程复用;登录态过期后重新协作登录即可。

安全铁律(与 CLAUDE.md 规则一致):
  1. 任何"提交"动作前,先把关键字段+后果展示给用户,等确认后才真正点提交;
  2. 退课、撤销申请等危险操作本工具一律不提供自动提交能力。

已探明的 CAS 机制(别再踩):
  - 无头浏览器 + navigator.webdriver 未抹除 → 必弹滑块验证码,机器过不了;
  - 连续登录失败会进风控名单,之后每次都弹滑块(人拖可通过);
  - 登录成功标志 = 出现 TGC Cookie;仅靠 URL 跳到 ehall 域名不算成功;
  - TGC 与浏览器指纹绑定(MULTIFACTOR_BROWSER_FINGERPRINT Cookie):无头/有头
    的指纹不同,混用会直接吊销 TGC!同一 profile 永远只用一种模式。
    本工具全部命令默认有头(窗口丢屏幕外),绝不要对 profile 用 headless=True;
  - context.storage_state(path=...) 是"保存"不是"加载",加载要 new_context(storage_state=)。
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail import load_env

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "data" / "state" / "ehall"
PROFILE_DIR = STATE_DIR / "profile"
HOME = "https://ehall.nju.edu.cn"
CAS_LOGIN = ("https://authserver.nju.edu.cn/authserver/login"
             "?service=https%3A%2F%2Fehall.nju.edu.cn%3A443%2Flogin"
             "%3Fservice%3Dhttps%3A%2F%2Fehall.nju.edu.cn%2Fywtb-portal%2Fofficial%2Findex.html")
CDP_PORT = 9224  # 常驻 ehall 会话浏览器的调试端口(login-keepalive 启动)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


def launch_ctx(pw, headless=False, offscreen=True):
    """持久化上下文:所有登录态落在 profile 目录,跨进程复用。

    默认有头+屏幕外窗口:CAS 的 TGC 与浏览器指纹绑定,无头与有头指纹不同,
    一旦对同一 profile 混用无头,会触发 TGC 吊销。屏幕外窗口不打扰用户。
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # --disable-gpu:Windows 上后台进程启动的 Chromium 若不关 GPU 合成,
    # 窗口内容会渲染成透明(框架在、页面看不见)。指纹一致性:所有启动都带此参数。
    args = ["--disable-gpu"]
    if offscreen:
        args.append("--window-position=-32000,-32000")
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
        user_agent=UA,
        headless=headless,
        args=args,
    )
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return ctx


def wait_logged_in(ctx, page, timeout):
    """轮询等待 TGC Cookie 出现(登录成功的唯一可靠标志)。

    返回 "ok" / "closed" / "timeout";窗口被用户关掉或浏览器崩溃时
    立即返回 "closed",不傻等。
    """
    for i in range(timeout):
        try:
            if page.is_closed():
                return "closed"
            page.wait_for_timeout(1000)
            if any("TGC" in (c.get("name") or "").upper() for c in ctx.cookies()):
                return "ok"
            if i % 30 == 29:
                print(f"  仍在等待登录…(已等 {i + 1} 秒)")
        except Exception:
            return "closed"
    return "timeout"


def goto_hall(ctx, page, timeout=60000, report_dir=None):
    """进入已登录大厅:先走 CAS 入口(TGC 在则自动换票放行)。

    返回 True = 已进入大厅;False = 仍卡在认证页(会截图+存文字供诊断)。
    """
    page.goto(CAS_LOGIN, wait_until="domcontentloaded", timeout=timeout)
    ok = False
    for _ in range(30):
        page.wait_for_timeout(1000)
        try:
            if "authserver" not in page.url:
                ok = True
                break
        except Exception:
            pass
    if not ok and report_dir:
        try:
            page.screenshot(path=str(report_dir / "stuck-authserver.png"))
            (report_dir / "stuck-authserver.txt").write_text(
                page.inner_text("body"), encoding="utf-8")
        except Exception:
            pass
    if ok:
        page.wait_for_timeout(6000)  # 等大厅 SPA 登录态落定
    return ok


# ---------- 子命令 ----------

def cmd_login_assist(args):
    """协作登录:自动填账号密码并提交,滑块/验证码由用户在窗口里亲手完成。"""
    env = load_env()
    user, pas = env.get("EHALL_USER", "").strip(), env.get("EHALL_PASS", "").strip()
    if not user or not pas:
        print("[错误] .env 缺 EHALL_USER/EHALL_PASS", file=sys.stderr)
        sys.exit(1)
    with sync_playwright() as p:
        ctx = launch_ctx(p, headless=False)  # 正常位置可见窗口
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(CAS_LOGIN, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            page.locator("#userNameLogin_a").click()
            page.wait_for_timeout(1500)
            page.locator("#pwdFromId #username:visible").fill(user)
            page.locator("#pwdFromId #password:visible").fill(pas)
            page.locator("#pwdFromId #login_submit:visible").click()
            print("已填好账号密码并提交。若弹出滑块/验证码,请在浏览器窗口里亲手完成。")
            print(f"最多等待 {args.timeout} 秒……(注意:窗口要一直开着,别关)")
            r = wait_logged_in(ctx, page, args.timeout)
            if r == "ok":
                page.wait_for_timeout(5000)
                print(f"登录成功!会话已持久化到:{PROFILE_DIR.relative_to(ROOT)}")
                print(f"Cookie 数:{len(ctx.cookies())}")
            elif r == "closed":
                print("[错误] 浏览器窗口被关闭或崩溃,登录中断。请重跑一次并保持窗口开启。", file=sys.stderr)
                sys.exit(1)
            else:
                print("[错误] 等待超时,未完成登录(可能密码错或验证没通过)", file=sys.stderr)
                sys.exit(1)
        finally:
            ctx.close()


def cmd_login_manual(args):
    """纯人工登录:窗口里全自己操作(输密码/拖滑块/扫码均可)。"""
    with sync_playwright() as p:
        ctx = launch_ctx(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(CAS_LOGIN, wait_until="domcontentloaded", timeout=60000)
            print("浏览器窗口已打开,请在窗口中完成登录(输密码/拖滑块/扫码均可)。")
            print(f"最多等待 {args.timeout} 秒……(窗口要一直开着,别关)")
            r = wait_logged_in(ctx, page, args.timeout)
            if r == "ok":
                page.wait_for_timeout(5000)
                print(f"登录成功!会话已持久化到:{PROFILE_DIR.relative_to(ROOT)}")
            elif r == "closed":
                print("[错误] 浏览器窗口被关闭或崩溃,登录中断。", file=sys.stderr)
                sys.exit(1)
            else:
                print("[错误] 等待超时,未完成登录", file=sys.stderr)
                sys.exit(1)
        finally:
            ctx.close()


def cmd_login(args):
    """全自动登录:窗口丢屏幕外。风控下大概率弹滑块,一般用 login-assist。"""
    env = load_env()
    user, pas = env.get("EHALL_USER", "").strip(), env.get("EHALL_PASS", "").strip()
    if not user or not pas:
        print("[错误] .env 缺 EHALL_USER/EHALL_PASS", file=sys.stderr)
        sys.exit(1)
    with sync_playwright() as p:
        ctx = launch_ctx(p, headless=False, offscreen=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(CAS_LOGIN, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            page.locator("#userNameLogin_a").click()
            page.wait_for_timeout(1500)
            page.locator("#pwdFromId #username:visible").fill(user)
            page.locator("#pwdFromId #password:visible").fill(pas)
            page.locator("#pwdFromId #login_submit:visible").click()
            if wait_logged_in(ctx, page, 60) == "ok":
                print(f"登录成功!会话已持久化到:{PROFILE_DIR.relative_to(ROOT)}")
            else:
                print("[错误] 自动登录失败(弹了滑块或密码错),改用 login-assist", file=sys.stderr)
                sys.exit(1)
        finally:
            ctx.close()


def connect_live(pw):
    """连接常驻 ehall 会话浏览器(login-keepalive 启动的那个)。

    返回 (browser, ctx, page) 或 (None, None, None)。
    所有 ehall 操作都走它,不要另开浏览器——CAS 会话(CASTGC)活在它的内存里。
    """
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return browser, ctx, page
    except Exception:
        return None, None, None


def cmd_search(args):
    """在大厅搜索服务,列出结果及链接(需常驻浏览器已登录)。"""
    with sync_playwright() as p:
        browser, ctx, page = connect_live(p)
        if not browser:
            print("[错误] 常驻 ehall 浏览器不在(CDP 端口无响应),先跑 login-keepalive", file=sys.stderr)
            sys.exit(1)
        try:
            page.goto(HOME + "/ywtb-portal/official/index.html#/hall", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            box = page.locator("input[placeholder*='搜索'], input[placeholder*='查询']").first
            if not box.is_visible(timeout=3000):
                box = page.locator("input:visible").first
            box.click()
            box.fill(args.keyword)
            page.keyboard.press("Enter")
            page.wait_for_timeout(6000)
            txt = page.inner_text("body")
            out = STATE_DIR / "search-result.txt"
            out.write_text(txt, encoding="utf-8")
            print(f"搜索结果已存:{out.relative_to(ROOT)}")
            items = page.eval_on_selector_all(
                "a", "els => els.map(e => ({t: (e.innerText||'').trim().slice(0,40), h: e.href||''})).filter(x => x.h.length>0 && x.t.length>1)")
            seen = set()
            for it in items:
                key = (it["t"], it["h"])
                if key in seen or "javascript" in it["h"]:
                    continue
                seen.add(key)
                print(f"  {it['t']} -> {it['h'][:120]}")
        finally:
            pass  # connect_over_cdp 的浏览器不归我们关闭,常驻保持


def cmd_app_status(args):
    """查节假日离返校应用状态:有没有可登记的假期。

    依赖常驻浏览器(CDP)。返回:
      open   = 有可登记的假期(列表在输出里)
      closed = 暂无可登记的假期
    这是"保守确认模式"的入口:只有 open 时才谈得上填表提交。

    已知表单字段(来自登记历史,2026-09 探明,供将来填表用):
      节假日名称、个人手机号、假期是否全程留校、预计离校日期、
      预计返校日期(留校填任意日期)、紧急联系人、紧急联系人电话
    """
    with sync_playwright() as p:
        browser, ctx, page = connect_live(p)
        if not browser:
            print("[错误] 常驻 ehall 浏览器不在,先启动 keepalive(见 CLAUDE.md)", file=sys.stderr)
            sys.exit(1)
        try:
            # 打开大厅 → 点热门服务卡片(或搜索)进应用
            page.goto(HOME + "/ywtb-portal/official/index.html#/hall", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            card = page.locator("li.online-service-content-item:has-text('节假日离返校')")
            if not card.is_visible(timeout=5000):
                box = page.locator("input[placeholder*='搜索']").first
                box.click(); box.fill("节假日离返校"); page.keyboard.press("Enter")
                page.wait_for_timeout(6000)
                btns = page.locator("a.text.has-app:visible")
                if btns.count() == 0:
                    print("[错误] 找不到节假日离返校入口", file=sys.stderr)
                    sys.exit(1)
                btns.first.click()
            else:
                card.click()
            # 等应用页出现
            app = None
            for _ in range(20):
                page.wait_for_timeout(1000)
                app = next((pg for pg in ctx.pages if "jjrlfxapp" in pg.url), None)
                if app:
                    break
            if not app:
                print("[错误] 应用页未打开", file=sys.stderr)
                sys.exit(1)
            app.bring_to_front()
            app.reload()  # 回到主视图(历史视图会误判)
            app.wait_for_timeout(8000)
            txt = app.inner_text("body")
            open(STATE_DIR / "app-status.txt", "w", encoding="utf-8").write(txt)
            if "暂无可登记的假期" in txt:
                print("closed:暂无可登记的假期")
                return "closed"
            # 主视图没有"暂无可登记"且出现登记表单区,才算 open
            if "登记" in txt and "暂无可登记" not in txt and "登记历史" not in txt[:200]:
                print("open:有可登记的假期,详情见 data/state/ehall/app-status.txt")
                return "open"
            print("unknown:应用状态见 data/state/ehall/app-status.txt")
            return "unknown"
        finally:
            pass  # 常驻浏览器不关


def cmd_explore(args):
    with sync_playwright() as p:
        ctx = launch_ctx(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            out_dir = STATE_DIR / "shots"
            out_dir.mkdir(parents=True, exist_ok=True)
            shot = out_dir / "explore.png"
            page.screenshot(path=str(shot), full_page=False)
            print(f"标题: {page.title()}")
            print(f"URL: {page.url}")
            print(f"截图: {shot}")
            links = page.eval_on_selector_all(
                "a, button", "els => els.slice(0, 60).map(e => "
                "(e.innerText||'').trim().slice(0, 30) + ' -> ' + (e.href||e.getAttribute('onclick')||''))")
            for ln in links:
                if ln.split(" -> ")[0].strip():
                    print("  ", ln)
        finally:
            ctx.close()


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="ehall 工具")
    sub = p.add_subparsers(dest="cmd", required=True)
    la = sub.add_parser("login-assist", help="协作登录(自动填表,滑块由用户拖)")
    la.add_argument("--timeout", type=int, default=180, help="等待秒数")
    lm = sub.add_parser("login-manual", help="人工登录(弹出窗口自己操作)")
    lm.add_argument("--timeout", type=int, default=300, help="等待秒数")
    sub.add_parser("login", help="自动登录(可能被风控弹滑块)")
    s = sub.add_parser("search", help="在大厅搜索服务(需常驻浏览器已登录)")
    s.add_argument("keyword")
    sub.add_parser("app-status", help="查节假日离返校应用:有无可登记的假期")
    e = sub.add_parser("explore", help="打开页面截图+列出可点元素")
    e.add_argument("url")
    args = p.parse_args()
    {"login": cmd_login, "login-manual": cmd_login_manual,
     "login-assist": cmd_login_assist, "search": cmd_search,
     "app-status": cmd_app_status, "explore": cmd_explore}[args.cmd](args)


if __name__ == "__main__":
    main()
