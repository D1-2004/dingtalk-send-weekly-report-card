---
name: dingtalk-send-weekly-report-card
description: Use when 用户提供周报链接或周报内容，并要求生成可托管的 HTML 客户回访页，或直接发送钉钉满意度互动卡片。
---

# 钉钉周报回访卡片

## 功能

读取用户给出的周报链接和补充描述，提取客户、周期、摘要与动态项目列表，然后只调用一个命令：

```text
scripts/weekly_report_tool.py gen-card
```

- `--type html`：校验数据、注入提交地址并生成单 HTML 文件。
- `--type card`：校验钉钉卡片业务 JSON，补齐固定正式回调路由后由命令内部调用 DWS 发送卡片并返回投递结果。

Agent 不自行检查环境变量、不拼接额外 Shell 校验，也不直接调用 DWS。命令成功才能向用户报告产物已生成或卡片已发送。

## 参数规格与来源

### 命令参数

| 参数 | HTML | Card | 说明 |
| --- | --- | --- | --- |
| `--type` | 必填 | 必填 | 只接受 `html` 或 `card` |
| `--data` | 必填 | 必填 | 严格 JSON 对象，不接受 Python 字面量 |
| `--output` | 必填 | 禁止 | HTML 输出文件；支持相对路径、绝对路径和 `~` |
| `--template` | 可选 | 禁止 | 自定义 HTML 模板；默认使用内置模板 |

运行环境由部署方注入：

- HTML：`WEEKLY_FEEDBACK_SUBMIT_URL`。
- Card：`DDWS_CLIENT_ID`、`DDWS_CLIENT_SECRET`。

环境变量缺失或格式错误时由命令报错并停止；Agent 不读取其值。

### 周报字段来源

| 信息 | 来源与规则 |
| --- | --- |
| 周报链接 | 用户消息中的原始链接 |
| 客户 | 用户明确说明优先，否则从周报标题和正文提取 |
| 标题 | 通常为“{客户或项目}周报回访” |
| 时间周期、周次 | 周报正文；没有周次时由日期范围计算 ISO 周次 |
| 简报 | 从周报提取 3–5 条可对外展示的事实，不编造数据 |
| 项目列表 | 从周报提取、去重并保留顺序；数量动态，不写死 |
| `collector` | 发起本次生成或发送任务的用户，不是 Agent 或机器人 |
| 接收人 | 默认是任务发起人的钉钉 `userId`；无法确定时询问用户 |
| `iconUrl` | 用户或业务配置提供的公网 HTTPS 图片地址 |
| `reportTime` | 当前生成时间，格式 `YYYY-MM-DD HH:mm:ss` |

使用当前 Agent 已有的文档读取能力获取周报正文；读取失败时请求授权或让用户粘贴正文，不根据标题猜测周报内容。

### HTML 数据

按照 `assets/weekly-report-card-data.schema.json` 构造，样例见 `assets/weekly-feedback-html-data.example.json`。主要字段：

- `schemaVersion` 固定为 `1`。
- `iconUrl`、`title`、`reportUrl`、`reportPeriod`、`customer`、`week`、`collector`、`reportTime`、`submissionId`。
- `summaryMarkdown` 是字符串数组。
- `projects` 是对象数组，每项包含唯一 `id`、项目 `name`、初始满意度、原因数组和反馈文本。
- `dissatisfactionOptions` 是快捷不满意原因数组。

不要在 `--data` 中生成 `callbackUrl` 或按钮文案。命令从环境变量注入提交地址，按钮固定为“提交 / 已提交”。

### Card 数据

`--type card` 接收最终卡片请求 JSON，不接收“客户、项目数组”等中间业务对象。严格按照：

- `assets/create-and-deliver.schema.json`
- `assets/project-rows.schema.json`
- `assets/card-request.example.json`

构造。关键规则：

- `cardTemplateId` 使用已发布的模板 ID。
- `outTrackId` 每次发送生成新值；`submissionId` 必须与其一致。
- 不要生成 `callbackType` 或 `callbackRouteKey`。命令固定注入已注册的正式 HTTP 回调路由 `customer_feedback_aitable_prod_v1`，Agent 不能传入或覆盖。
- `openSpaceId` 为 `dtv1.card//IM_ROBOT.<接收人userId>`。
- `cardData.cardParamMap` 的所有值必须是字符串。
- `title`、`iconUrl`、`reportUrl`、摘要、周期、客户、周次、收集人和时间来自上表。
- `weeklySummary` 与 `summaryMarkdown` 一致。
- `projectRows` 是符合 `project-rows.schema.json` 的动态项目数组序列化后的 JSON String；项目 `id` 从 `p1` 连续递增，项目名唯一。
- 每个项目行独立包含满意度选项、快捷原因、已选原因序号和反馈文本；不要复用其他项目的状态。
- `submitButtonText` 为 `提交`，`formState` 为 `normal`，`formDisabled` 为字符串 `false`。
- `imRobotOpenSpaceModel.supportForward` 为 `true`，`imRobotOpenDeliverModel.spaceType` 为 `IM_ROBOT`，`userIdType` 为 `1`。
- 请求 JSON 中禁止出现凭证、令牌或其他敏感字段。

## 命令使用

### 生成 HTML

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --type html \
  --data "$CARD_DATA_JSON" \
  --output "$OUTPUT_PATH"
```

成功结果包含 `success: true`、`type: html`、绝对 `output` 路径和实际 `submitUrl`。

### 校验并发送钉钉卡片

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --type card \
  --data "$CARD_DATA_JSON"
```

命令依次执行外层 Schema、反序列化 `projectRows` Schema、跨字段关系和敏感字段校验；随后使用显式 `--client-id` 和 `--client-secret` 参数发送卡片。只有顶层投递成功、`outTrackId` 一致、投递结果非空且每项成功时，命令才返回 `success: true`。

成功后回复用户：

> 卡片已发送，请在钉钉中查收。

任一步失败时直接报告命令的安全错误摘要，不声称已生成或已发送，也不要绕过校验后重试。

## 协议变更记录

- 2026-08-28：将卡片回调切换为已注册到 AI 表格 Webhook 的正式路由 `customer_feedback_aitable_prod_v1`；发卡命令只注入该路由，不再重复注册回调。
- 2026-08-27：从 Agent 输入中移除 `callbackType`、`callbackRouteKey`，改由命令固定注入已注册路由，避免调用方覆盖卡片回调目标。
