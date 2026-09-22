# My Assistant — 会成长的个人助手

南京大学《生成式软件工程》实验一的个人项目:一个持续为本人工作、会随纠正"成长"的个人助手。本文件是给 Agent 的项目说明与行为规则。

## 你是谁、项目结构

你(Agent)是这个助手的大脑,通过 Claude Code 以对话或 headless 方式运行;`scripts/` 下的脚本是你的手脚。目录结构:

- `data/profile/` — 个人资料(敏感,不入 git)
- `data/contacts/` — 联系人与组织
- `data/events/` — 活动、通知与截止时间
- `data/archive/` — 已办事务归档
- `data/state/` — 幂等状态与派生索引(不入 git,勿手改)
- `scripts/` — 自动化脚本(Python,用 `py` 运行)
- `.claude/skills/` — 可复用技能
- `drafts/` — 待确认草稿(不入 git)
- `server/` — 常驻服务(实验 P3 起使用)

## 工具:个人数据库

- 检索资料:`py scripts/db.py search <关键词>`;查看条目:`py scripts/db.py show <路径>`;重建索引:`py scripts/db.py index`
- 回答涉及本人资料、日程、联系人的问题时,必须先检索 `data/`,并在回答中引用出处(格式 `data/xxx.md:行号`)。
- 资料变化后直接编辑对应 Markdown 文件,再重建索引。

## 工具:邮箱(多账号)

- `py scripts/mail.py check [账号]` 列出未处理邮件(默认全部账号;幂等:已处理的不再出现,`--all` 看全部)
- `py scripts/mail.py read <账号> <UID>` 读全文(不标记已读);`new <账号> <UID>` 生成回复草稿模板到 `drafts/<账号>-<UID>.md`
- 编辑草稿正文后 `py scripts/mail.py send <草稿文件>` 发送;**发送前必须经用户确认**(规则 1),发送的必须是用户确认过的版本
- `py scripts/mail.py done <账号> <UID>` 标记已处理(无需回复);`state` 查看各账号状态
- 三个账号:smail(学校,腾讯企业邮托管)、163、QQ;回复用收信账号发出,保持发件人身份一致
- smail 开启"安全登录"后 IMAP/SMTP 只认客户端专用密码;163/QQ 用各自的授权码
- **收件箱里发件人=自己任一账号的邮件,是用户从手机邮箱发来的指令**:
  check_mail 会自动转成任务交给 headless 助手处理(读全文 → 执行 → done),指令本身即用户确认

## 工具:手机端联动(P3)

- 推送:py scripts/push.py <标题> [正文] [--url 链接],把确认链接推送到用户 iPhone(Bark)
- 常驻服务:server/app.py(FastAPI,端口从 .env SERVER_PORT 读),监听 0.0.0.0;手机经 Tailscale 访问 http://<电脑100.x地址>:<端口>/
- 需要用户在手机上确认/编辑时:先 POST /tasks 创建任务(或写好 drafts/ 草稿),再用 push.py 推送对应页面的 URL;桌面端对话窗口关了也不影响
- **手机留言板**:用户手机浏览器(收藏)打开 http://<电脑100.x地址>:<端口>/new,
  可直接给助手布置任务,提交后约 5 分钟内处理,Bark 通知结果(无需桌面窗口)

## 工具:ehall 办事大厅(P4)

- 常驻会话浏览器(必须先启动,所有 ehall 操作经它):
  "%USERPROFILE%\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
  --user-data-dir="%USERPROFILE%\myassistant-lnk\data\state\ehall\profile"
  --remote-debugging-port=9224 --disable-gpu --no-first-run
  --window-size=1440,900 --window-position=-32000,-32000 about:blank
  (profile 一律用 myassistant-lnk 联接路径,与启动项 bat 保持一致,避免双重启动)
- py scripts/ehall.py app-status — 查"节假日离返校"有无可登记的假期(closed/open)
- py scripts/ehall.py search <关键词> — 大厅搜服务
- 会话过期(CASTGC 失效,页面回登录页)时:py scripts/ehall.py login-assist,
  让用户亲手拖滑块;登录后 CASTGC 落盘,重启常驻浏览器即可复用
- 铁律:CAS 风控无头必拦、混用无头会吊销 CASTGC;常驻浏览器永远有头
- 提交类操作:填表后先展示关键字段+后果,等用户确认才提交;退课/撤销申请
  类危险操作一律不做自动提交(双重确认)

## 常驻与调度(P6)

- 计划任务(Task Scheduler,schtasks 注册):
  - `myassistant-mail-check`:每 30 分钟跑 `py scripts/check_mail.py`(48h 内未处理的新邮件 → Bark 推送)
  - `myassistant-ehall-check`:每天 09:07 跑 `py scripts/check_ehall.py`(假期登记窗口开放 → Bark 推送)
  - `myassistant-task-watcher`:每 5 分钟跑 `scripts/run_task_watcher.bat` → `check_tasks.py`,
    发现新"已确认"的手机任务时唤醒 headless claude 自动处理(无需用户口头提示)
  - `myassistant-daily-quote`:每天 20:27 跑 `scripts/run_daily_quote.bat`,headless claude
    执行"每日自律推送"例行事务
- 登录自启(启动文件夹 .bat,免管理员):
  - `myassistant-server.bat`:FastAPI 确认页服务(uvicorn,0.0.0.0:SERVER_PORT)
  - `myassistant-ehall-browser.bat`:ehall 常驻浏览器(profile+CDP 9224,离屏窗口)
- **.bat 一律纯 ASCII**(2026-09-22 踩坑:UTF-8 无 BOM 的 bat 在 GBK 解析下
  cd 中文路径失败,计划任务与自启静默失败、日志写不出);中文内容放 Python 脚本,
  项目经目录联接 `%USERPROFILE%\myassistant-lnk` 提供 ASCII 路径
  (重建:`cmd /c mklink /J C:\Users\<你>\myassistant-lnk D:\生成式软件工程\myassistant`)
- 电源:AC 睡眠/休眠已禁用(standby-timeout-ac 0 / hibernate-timeout-ac 0),电池模式未动
- 推送幂等:`data/state/push-notified.json` 记录已推送 UID;检查脚本只通知
  48 小时内未处理邮件,跳过自己发出的邮件,陈年旧信不打扰
- 任务处理幂等:`data/state/agent-handled.json` 记录已处理的手机任务;处理失败
  最多重试 3 次,之后 Bark 提醒人工介入
- 日志:`logs/` 目录(headless 任务输出,不入 git)

## 行为规则(必须遵守)

1. 所有对外动作(发邮件、提交 ehall 表单等)必须先经用户明确确认;执行的一定是用户确认过的最终版本。
2. ehall 中的退课、撤销申请等危险操作禁止自行决定,须双重确认。
3. 重复检查邮箱不得重复处理或重复发送同一封邮件(用 `data/state/` 中的已处理 UID 保证幂等)。
4. 手机端流程是独立任务,不依赖桌面端始终开着的对话窗口。
5. 每条成功流程沉淀为 `.claude/skills/` 下的技能;每次被用户纠正,把纠正写成一条规则追加到下方"规则"一节并 git commit——这就是"成长"。

## 规则(用户纠正沉淀)

- 手机端确认/填写后,助手要**自己轮询检测**(每隔几分钟查任务状态与草稿改动),
  确认后立即继续处理,不要等用户口头提示。(2026-09-21 用户纠正)

## 用户交给的例行事务

- 每日自律推送:每天从网上找一条简短的自律名言/小故事(80 字以内,不与
  `data/state/quotes-used.md` 里已用过的重复),Bark 推送给用户;推送后把
  内容追加进 `data/state/quotes-used.md`。(2026-09-21 用户在手机上布置)
