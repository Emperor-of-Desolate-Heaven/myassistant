---
name: ehall-holiday-register
description: ehall 节假日离返校登记代办:会话恢复、查登记窗口、填表、加去向明细、保守确认提交。涉及 ehall/jjrlfxapp 操作时使用。
---

# ehall 节假日离返校登记代办

用户要求代办 ehall「节假日离返校」登记时按此流程。所有操作走常驻浏览器
(CDP 127.0.0.1:9224,profile=data/state/ehall/profile),**绝不对该 profile 用 headless**。

## 0. 会话状态

- `py scripts/ehall.py app-status` → open/closed/unknown。
- 会话过期(无 CASTGC cookie / 停留 authserver 登录页):
  按 CDP 端口杀常驻浏览器进程 → `py scripts/ehall.py login-assist`
  (窗口现在可见,用户亲手拖滑块)→ 用启动项 bat 重启常驻浏览器。

## 1. 填表(保守确认模式)

先探表单再填;填完**截图 + 字段清单给用户过目,确认后才点提交**(CLAUDE.md 铁律)。

- 基础表单:手机号 `input[name=SJH]`(通常系统已带出)、紧急联系人
  `input[name=JJLXR]`、电话 `input[name=JJLXRDH]`;
- 单选:`input[name=YL5]`(是否住校)、`input[name=YL2]`(全程留校),value 1=是 0=否;
- 全程留校=否时,点「新增一条」创建行程行(一行 = 一段行程,多地点逐一新增)。

## 2. 日期控件(最大的坑)

行内日期框是 `input[bh-form-role="dateTimeInput"]`。**键盘输入 / JS 赋值只改显示,
不入表单模型**,提交必报「离校后的行程记录为必填」。正确方式:

1. click 输入框 → 弹出双月日历(第一块=当前月,第二块=下月);
2. 目标月不是当前月时:click `th.bhtc-picker-switch`(月份头)→ click
   `span.month`(如「10月」)→ 自动回到日视图;
3. click 目标日 `td.day`,**排除 class 含 bhtc-old / bhtc-new 的格子**(上月/下月的尾头);
4. 回读 `input_value` 校验(期望 yyyy-MM-dd)。

## 3. 去向明细(校验必需)

提交校验(saveStuApply)要求子表 xsdjqxmxbd 按行的 DJBH 存在记录,否则同样报
「离校后的行程记录为必填!」。添加方式:

1. click `[data-action="新添加去向"]` —— 页面上可见文字就是「离校后的行程记录」
   那一行,是 DIV 不是按钮;
2. 弹纸堆对话框:去向类型是 jqx 下拉,**DOM 点击选项不生效**,必须
   `jQuery(combo).jqxDropDownList('selectItem','1')`(1=回家,2=其他);
   开始/结束日期会自动带出行里的值,核对即可;
3. click `[data-action="保存去向信息"]`(报「去向类型不能为空」= 选择没生效);
4. 验证:`mineQuery('xsdjqxmxbd',{DJBH:<行DJBH>},false).data.length > 0`。

## 4. 提交与验证

- click 提交按钮;警告弹窗用 `get_by_text('确定', exact=True).last.click(force=True)`
  (「确定」不是 button 元素,按文本定位);
- 成功标志:页面变只读「登记于 <日期>」+ 弹出「× 登记成功」+ 出现「修改」按钮;
- 失败排查:警告文案对应校验项——「离校信息请输入完整」= jqxValidator(DOM 值)
  「离校后的行程记录为必填」= 子表无记录或日期没入模型。

## 5. 收尾

- Bark 推送结果;事务摘要记入 data/archive/(不入 git,可含家庭地址等个人数据);
- 表单字段定义:行内 `data-name=YL1`(离校)/`YJFXRQ`(返校)/`YL6`(交通工具,隐藏)/
  `YL10`(附件);基础表单隐藏项 `YL7`(住校=否时用)/`YL4`(留校=是时用)/
  `JTDZ`(家庭地址,自动带出)。
