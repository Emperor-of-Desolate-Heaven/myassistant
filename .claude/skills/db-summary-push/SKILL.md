# 技能:数据库速览推送(DB Summary Push)

把 ehall 等外部系统里读到的个人信息落进个人数据库,整理后同时发到
用户手机(Bark)和 163 邮箱。2026-09-21 首次验证通过(P5 测试)。

## 何时用

- 从 ehall 等系统获取了用户新信息(联系人、事务记录),需要入个人数据库时
- 用户要求"把数据库内容发到手机/邮箱"时

## 步骤

1. **落库**:按目录约定写入 `data/`(联系人 → `contacts/<名>.md`,办完的事务 →
   `archive/<事务>.md`,一个文件一个主题;格式参照已有文件)
2. **重建索引**:`py scripts/db.py index`,并用 `py scripts/db.py stats` 拿统计
3. **写邮件草稿**:`drafts/163-db-summary.md`,头部
   `to: <用户 163 邮箱地址>` + `subject:`;正文用整理好的速览
   - **敏感信息(身份证号、银行卡号)不随邮件发送,只留本地库**
4. **发邮件**:`py scripts/mail.py send drafts/163-db-summary.md`
   (规则 1:发送前把草稿内容给用户看过/经用户确认)
5. **手机推送**:`py scripts/push.py "数据库速览已发" "<一句总结>"`
6. **验证**:`py scripts/mail.py check 163` 确认邮件到达;git commit 落库变更

## 注意

- 用户个人资料(`data/profile/`)不入 git;contacts/archive 入库
- ehall 数据读取依赖常驻浏览器与登录会话(见 CLAUDE.md ehall 一节)
