# 交付说明:会成长的个人助手

《生成式软件工程》2026 秋 Lab 1 · 作者信息已脱敏
运行环境:Windows 11 笔记本(个人电脑当服务器)+ iPhone;Agent 大脑为 Claude Code(DeepSeek v4-pro 模型,Anthropic 兼容端点)。

---

## 一、架构

```
Claude Code(大脑,交互或 headless 两种形态)
 ├─ scripts/*.py      手脚:邮件、数据库、ehall、推送、监视器(纯 Python,少依赖)
 ├─ server/app.py     神经:FastAPI 任务队列 + 手机确认页/草稿编辑页
 ├─ data/             个人数据库(Markdown)与机器状态(UID/索引/处理记录,幂等)
 ├─ CLAUDE.md         行为规则 + 用户纠正沉淀(助手的"宪法")
 └─ .claude/skills/   成功流程沉淀的技能
iPhone(Bark 推送 + Tailscale 内网)  ←→  上述服务
Windows 计划任务 ×4 + 启动文件夹 ×2   ←→  无对话窗口时的自治运行
```

## 二、五项能力与演示

### ① 个人数据库(索引/检索/引用原文)
- `data/` 分目录组织:profile(敏感,不入 git)/ contacts / events / archive,Markdown 可读可改
- `scripts/db.py index|search|show|stats`,检索输出 `文件:行号` 可引用原文
- 演示:`py scripts/db.py search <关键词>` → 输出 `文件:行号` 引用原文

### ② smail 邮箱(草稿+确认+幂等发送)
- `scripts/mail.py` 多账号(smail 腾讯企业邮 / 163 / QQ,纯标准库 IMAP/SMTP)
- 流程:check 新邮件 → new 生成回复草稿 → 用户编辑确认 → send(发送的必须是用户确认过的版本)→ 归档
- 幂等:已处理 UID 存 `data/state/email/`,重复检查绝不重复处理/发送(实测 QQ 收件箱验证)
- 反向通道:收件箱中发件人=自己账号的邮件,自动识别为手机发来的指令 → 转成任务由 headless Agent 执行(实测)
- 演示:给任一账号发邮件 → `py scripts/mail.py check` → 回复流程走一遍;再 check,不再出现

### ③ ehall 事务(保守确认模式)
- `scripts/ehall.py`(Playwright):登录 → 服务搜索 → 应用操作;会话持久化在浏览器 profile,常驻浏览器复用
- 保守确认:任何提交前先展示关键字段+后果,等用户确认;退课/撤销类危险操作一律不做自动提交(双确认)
- 已落地能力:登录(人机协作拖滑块)、`search`、`app-status`(查"节假日离返校"登记窗口,每天 09:07 自动检查,开放即推手机)
- 表单字段已从登记历史全部探明(7 个字段);填表提交链路待学校开放登记窗口后实测(现在"暂无可登记的假期")

### ④ 手机端联动(推送+确认链接,iOS,不依赖桌面聊天窗口)
- Bark 推送 + Tailscale 内网;FastAPI 任务页(确认/拒绝)+ 草稿编辑页
- 实测闭环:电脑建任务 → Bark 推确认链接 → 手机点开确认 → 服务端状态翻转;
  手机填写模板(课表)保存 → 助手自动落库(课程/老师/时间均已脱敏处理)
- **不依赖桌面窗口**:`myassistant-task-watcher` 每 5 分钟检测新确认任务,
  唤醒 headless claude 自动处理(读 CLAUDE.md → 干活 → Bark 反馈),无需用户口头提示
- **手机反向布置任务(两条通道)**:
  - 留言板:手机收藏 `http://<电脑100.x地址>:<端口>/new`,随时打字布置 → 5 分钟内处理 → Bark 反馈(实测)
  - 邮件指令:手机邮箱发给自己任一账号的信,自动转成任务,headless 读全文执行后标记 done;
    不需要连 Tailscale 也能布置(实测)

### ⑤ 能力组合(可复用端到端流程)
- 已沉淀技能 `.claude/skills/db-summary-push/`:ehall 信息落库 → 整理速览 → 163 邮件 + Bark 推送(实测:邮件 18:23 达 163 收件箱,手机收到推送)
- 例行事务:每日 20:27 headless claude 自动找自律名言推送到手机(不重复),用过的记入 `data/state/quotes-used.md`
- 完整链路实例:ehall 数据(P4)→ 数据库(P1)→ 163 邮件(P2)+ 手机推送(P3),再经任务监视器闭环

## 三、成长机制(实验核心)

- **成功流程 → 技能**:`.claude/skills/`(personal-db、db-summary-push)
- **每次纠正 → 规则 + git commit**:`CLAUDE.md` "规则"一节,例如:
  - 事件记录必须区分"活动时间/报名截止/材料截止"(用户纠正)
  - 手机端确认后助手要自己轮询检测,不等用户口头提示(用户纠正)
- **git 提交即成长过程记录**(按 P0→P6 顺序,每条 commit 说明当时学到/修了什么):
  完整历史含脱敏前的个人信息,仅备份于本地 `backup-full-history` 分支(绝不上传);
  GitHub 以脱敏后的单提交发布,仓库设为私有

## 四、安全与保守设计

- 所有对外动作(发邮件、提交表单)先经用户明确确认;执行的一定是确认过的版本
- 危险操作(退课/撤销)禁止自主决定,双重确认
- 幂等三层:邮件 UID / 任务 handled / 推送 notified,绝不重复处理
- 密码只在 .env(gitignored);身份证号/银行卡号只存本地,不随邮件外发
- 手机确认页只对内网(Tailscale)开放

## 五、关键技术点(踩坑记录,详见 commit 与 CLAUDE.md)

- 网易 Coremail 需 IMAP ID 命令否则 SELECT 报 Unsafe Login;腾讯企业邮开"安全登录"后 IMAP/SMTP 只认客户端专用密码
- CAS 风控:无头浏览器必弹滑块;TGC 与浏览器指纹绑定,无头/有头混用会直接吊销登录票 → 常驻浏览器固定有头
- Windows 控制台 GBK 乱码(curl 传中文)→ 专用 UTF-8 工具;后台启动的 Chromium 需 --disable-gpu 否则窗口透明
- Playwright `context.storage_state(path=…)` 是"保存"不是"加载"

## 六、已知限制(如实)

- 请假表单填表提交待假期窗口期实测;ehall 登录票过期需人工拖一次滑块(1 分钟)
- 定时任务在用户登录 Windows 时运行;电池模式下电脑会睡眠(AC 已禁眠)
- headless 运行消耗 DeepSeek API:每日自律推送约 1 次短调用,监视器无任务时零成本

## 七、复现要点

- 依赖:`py` + pip(fastapi uvicorn python-multipart playwright)+ `playwright install chromium`
- 配置:`.env`(邮箱三账号、BARK_KEY、EHALL_*、SERVER_PORT)
- 手机:Bark + Tailscale App;计划任务 4 个(schtasks 或见 CLAUDE.md),启动文件夹 2 个 .bat
