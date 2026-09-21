# My Assistant — 会成长的个人助手

南京大学《生成式软件工程》2026 秋 实验一:持续为本人工作的个人助手,能随纠正"成长"。

## 五项能力与进度

| # | 能力 | 状态 |
|---|---|---|
| 1 | 个人数据库(索引/检索/引用原文) | ✅ P1 |
| 2 | smail 邮箱(草稿+确认+幂等发送) | ✅ P2(smail/163/QQ 三账号) |
| 3 | ehall 事务(保守确认模式) | ✅ P4(登录/会话/服务访问/状态查询;填表提交待假期窗口期实测) |
| 4 | 手机端联动(推送+确认链接,iOS) | ✅ P3(Bark+Tailscale 实测通) |
| 5 | 能力组合(一条完整可复用流程) | ✅ P5(ehall 落库→整理→163 邮件+Bark 推送,沉淀为 skill) |
| 6 | 持续运行(定时调度+开机常驻) | ✅ P6(邮件 30min/ehall 每日定时检查,服务与浏览器登录自启,AC 不睡眠) |

## 架构

Claude Code(headless,DeepSeek v4-pro)当大脑;`scripts/` Python 脚本当手脚;`server/` 常驻服务(FastAPI)当神经,手机经 Tailscale 访问确认页、Bark 推送通知。

## 使用

- 检索资料:`py scripts/db.py search <词>`
- 行为规则与纠正沉淀:见 `CLAUDE.md`
