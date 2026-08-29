---
name: dingtalk-send-weekly-report-card
description: Use when 用户提供周报链接或周报内容，并要求生成可填写的周报反馈网页，或发送带反馈入口的钉钉 Markdown 周报回访消息。
---

# 钉钉周报回访

## 功能

读取用户提供的周报链接和补充描述，提取标题、周期、简报、客户与进行中的项目。默认产物是钉钉 Markdown 消息；消息中的反馈入口指向先生成并托管到 Multica 的 HTML 表单。

Agent 只负责理解周报、构造 JSON，并调用统一命令：

```text
scripts/weekly_report_tool.py gen-card
```

命令支持两种类型：

- `markdown`：默认类型。渲染并发送带周报链接和反馈入口的 Markdown 消息。
- `html`：生成响应式网页表单及运行时文件，供 Multica 静态网站托管。

网页使用一份整体反馈：客户和项目只读，用户只填写一次满意度、不满意原因和具体反馈。一次提交在 AI 表格中新增一行；多个项目合并写入同一个“项目”单元格。

## 默认工作流

1. 读取周报，按照 `assets/weekly-report-card-data.schema.json` 构造 HTML 数据。
2. 调用 `gen-card --type html`，输出到独立网站目录的 `index.html`。
3. 将命令返回的 `siteRoot` 整体打成 ZIP。ZIP 根目录直接包含：
   - `index.html`
   - `multica-fetch-proxy-config.js`
   - `dingtalk-identity.js`
   - `weekly-feedback-runtime.js`
4. 使用 Multica MCP：
   - 调用 `prepare_static_site_deploy`，传 ZIP 的 SHA-256 和字节长度。
   - 按返回的上传地址和一次性凭证流式上传原始 ZIP，不使用 multipart 或 base64。
   - 调用 `get_static_site_deploy`，确认状态为 `active` 并取得 `site_url`。
5. 将 `site_url` 写入 Markdown 数据的 `feedbackUrl`。
6. 调用 `gen-card`，省略 `--type` 即使用默认 `markdown` 完成发送。
7. 只有 HTML 发布成功且 Markdown 命令返回 `success: true`，才回复用户“已发送，请查收”。

HTML 发布失败时，不发送缺少反馈入口或使用本地文件地址的消息。

## 参数规格与来源

### 命令参数

| 参数 | Markdown | HTML | 说明 |
| --- | --- | --- | --- |
| `--type` | 可省略 | 必填 `html` | 可选值 `markdown`、`html`；默认 `markdown` |
| `--data` | 必填 | 必填 | 严格 JSON 对象，不接受 Python 字面量 |
| `--output` | 禁止 | 必填 | HTML 输出文件；支持相对路径、绝对路径和 `~` |
| `--template` | 禁止 | 可选 | 自定义 HTML 模板；默认使用内置模板 |

运行环境由部署方注入：

- HTML：`WEEKLY_FEEDBACK_SUBMIT_URL`，值为 `https://connector.dingtalk.com/webhook/flow/{flowId}`。
- Markdown：不需要环境变量，使用当前 DWS 登录态。

环境变量缺失或格式错误由命令直接报错；Agent 不在命令外重复校验。

### 周报数据来源

| 信息 | 来源与规则 |
| --- | --- |
| 周报链接 | 用户消息中的原始链接 |
| 客户 | 用户明确说明优先，否则从周报标题和正文提取 |
| 标题 | 通常为“{客户或项目}周报回访” |
| 时间周期、周次 | 周报正文；缺少周次时根据日期范围计算 ISO 周次 |
| 简报 | 提取 3–5 条可对外展示的事实，不编造数字或状态 |
| 项目列表 | 从周报提取、去重并保留顺序；数量动态，不写死 |
| `collector` | 发起本次生成或发送任务的用户，不是 Agent 或机器人 |
| 接收人 | 用户明确指定的姓名或花名；未指定时询问，不猜测 |
| `iconUrl` | 用户或业务配置提供的公网 HTTP/HTTPS 图片地址 |
| `reportTime` | 当前生成时间，格式 `YYYY-MM-DD HH:mm:ss` |

使用当前 Agent 已有的文档读取能力获取周报正文；读取失败时请求授权或让用户粘贴正文，不根据标题猜测正文。

## 命令使用

### HTML 反馈表单

数据按照 `assets/weekly-report-card-data.schema.json` 构造，样例见 `assets/weekly-feedback-html-data.example.json`。

关键规则：

- `schemaVersion` 固定为 `2`。
- `iconUrl`、`title`、`reportUrl`、`reportPeriod`、`customer`、`week`、`collector`、`reportTime`、`submissionId` 必填。
- `summaryMarkdown` 是简报字符串数组。
- `projects` 是只读项目数组，每项只包含唯一 `id` 和 `name`。
- `satisfaction`、`dissatisfactionReasons`、`feedback` 是整张表单的初始值，通常分别传 `""`、`[]`、`""`。
- `dissatisfactionOptions` 是快捷不满意原因数组。

不要在 JSON 中构造 `callbackUrl`。命令会读取 `WEEKLY_FEEDBACK_SUBMIT_URL`，注入 HTML，并生成：

```javascript
window.__MULTICA_FETCH_PROXY_ALLOWLIST__ = ["https://connector.dingtalk.com/webhook/flow/{flowId}"];
```

页面在钉钉容器内调用 `internal.user.getCurrentUserInfo({})` 获取提交人，不使用 `requestAuthCode`，也不需要应用 Client ID 或 Secret。身份读取失败时禁止提交。

页面提交给 AI 表格 Webhook 的固定协议为：

```json
{
  "schemaVersion": 2,
  "action": "submit_weekly_feedback",
  "submissionId": "唯一提交编号",
  "reportUrl": "周报链接",
  "reportPeriod": "时间周期",
  "customer": "客户名",
  "week": "周次",
  "projects": ["项目A", "项目B"],
  "satisfaction": "满意或不满意",
  "dissatisfactionReasons": ["原因1", "原因2"],
  "feedback": "具体反馈",
  "collector": "收集人",
  "reportTime": "YYYY-MM-DD HH:mm:ss",
  "feedbackUserId": "提交人 userId",
  "feedbackUserName": "提交人姓名"
}
```

生成命令：

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --type html \
  --data "$HTML_DATA_JSON" \
  --output "$SITE_DIR/index.html"
```

成功结果包含绝对 `output`、`assets`、`siteRoot` 和实际 `submitUrl`。

### Markdown 消息

数据严格按照 `assets/weekly-report-markdown-data.schema.json` 构造，样例见 `assets/weekly-report-markdown-data.example.json`。

命令会将原始 HTTPS `feedbackUrl` 转换为钉钉工作台深链，Agent 不自行拼接 Markdown 或深链：

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --data "$MARKDOWN_DATA_JSON"
```

命令内部使用当前登录态执行：

```bash
dws chat +dm --to "$RECIPIENT_NAME" --content "$RENDERED_MARKDOWN" --yes --format json
```

任何校验、托管或投递失败都直接报告安全错误摘要，不绕过校验，不声称已生成、已发布或已发送。

## 协议审计

- 2026-08-30：HTML 数据升级为 v2，移除按项目分别反馈和互动卡片兼容协议，改为一次提交一行的网页表单协议。原因：互动卡片链路已停止使用，保留其嵌套结构会增加页面与 AI 表格自动化的复杂度。
