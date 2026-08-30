---
name: dingtalk-send-weekly-report-card
description: Use when 用户提供周报链接或周报内容，并要求生成可填写的周报反馈网页，或发送带反馈入口的钉钉 Markdown 周报回访消息。
---

# 钉钉周报回访

## 功能

读取用户提供的周报链接和补充描述，提取标题、周期、简报、客户与进行中的项目。默认产物是钉钉 Markdown 消息；消息中的反馈入口指向先生成并托管到 Multica Site 的 HTML 表单。

Agent 只负责理解周报、构造 JSON，并调用统一命令：

```text
scripts/weekly_report_tool.py gen-card
```

命令支持：

- `markdown`：默认类型，渲染并发送带周报链接和反馈入口的 Markdown 消息。
- `html`：生成自包含的响应式网页表单，供 Multica Site 托管。

网页只收集一份整体反馈。客户和项目只读，用户填写一次满意度、不满意原因和具体反馈。提交给 Webhook 的数据协议见 `assets/weekly-feedback-webhook.schema.json`。

## 工作流

1. 读取周报，根据下方参数规格构造 HTML 数据。
2. 调用 `gen-card --type html`，默认将网站入口输出为构建目录下的 `index.html`。
3. 按 Multica Site 当前托管协议打包并上传完整构建产物 ZIP。ZIP 应保持构建产物的目录结构，并以根目录的 `index.html` 作为默认入口；不要假设或写死其他文件名。
4. 使用 Multica MCP 的 `prepare_static_site_deploy` 准备上传，完成上传后调用 `get_static_site_deploy`，确认部署状态为 `active` 并取得 `site_url`。
5. 将 `site_url` 写入 Markdown 数据的 `feedbackUrl`。
6. 调用 `gen-card`，省略 `--type` 即使用默认 `markdown` 完成发送。
7. 只有 HTML 发布成功且 Markdown 命令返回 `success: true`，才回复用户“已发送，请查收”。

HTML 发布失败时，不发送缺少反馈入口或使用本地文件地址的消息。

## 参数规格与来源

### 命令参数

| 参数 | Markdown | HTML | 说明 |
| --- | --- | --- | --- |
| `--type` | 可省略 | 必填 `html` | 可选值为 `markdown`、`html`；默认 `markdown` |
| `--data` | 必填 | 必填 | 严格 JSON 对象，不接受 Python 字面量 |
| `--output` | 禁止 | 必填 | HTML 输出文件；支持相对路径、绝对路径和 `~`，托管时建议使用 `{siteRoot}/index.html` |
| `--template` | 禁止 | 可选 | 自定义 HTML 模板；默认使用内置模板 |

HTML 模式需要部署方注入 `WEEKLY_FEEDBACK_SUBMIT_URL`，值为 `https://connector.dingtalk.com/webhook/flow/{flowId}`。环境变量缺失或格式错误由命令直接报错，Agent 不在命令外重复校验。

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

HTML 输入样例见 `assets/weekly-feedback-html-data.example.json`。必填字段为：

- `schemaVersion`：固定为 `2`。
- `iconUrl`、`title`、`reportUrl`、`reportPeriod`、`customer`、`week`、`collector`、`reportTime`、`submissionId`：非空字符串。
- `summaryMarkdown`：简报字符串数组。
- `projects`：只读项目数组，每项包含唯一 `id` 和 `name`。
- `dissatisfactionOptions`：不满意原因快捷选项数组。

`satisfaction`、`dissatisfactionReasons`、`feedback` 是表单初始值，通常分别传 `""`、`[]`、`""`。不要在 JSON 中传 `callbackUrl`，命令会从环境变量读取并注入。

生成命令：

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --type html \
  --data "$HTML_DATA_JSON" \
  --output "$SITE_DIR/index.html"
```

生成的 `index.html` 已内联页面运行逻辑和钉钉身份读取能力，不依赖同目录的额外 JavaScript 文件。成功结果包含绝对 `output`、`siteRoot` 和实际 `submitUrl`。

页面在钉钉容器内读取当前用户身份；身份读取失败时禁止提交。Webhook 请求必须符合 `assets/weekly-feedback-webhook.schema.json`，一次表单提交对应一次请求。

### Markdown 消息

Markdown 输入样例见 `assets/weekly-report-markdown-data.example.json`。必填字段为 `schemaVersion`、`title`、`reportPeriod`、`reportUrl`、`summaryMarkdown`、`feedbackUrl` 和 `recipientName`。

命令会将原始 HTTPS `feedbackUrl` 转换为钉钉工作台深链，并使用当前登录态发送消息。Agent 不自行拼接 Markdown、深链或底层发送命令：

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --data "$MARKDOWN_DATA_JSON"
```

任何校验、托管或投递失败都直接报告安全错误摘要，不绕过校验，不声称已生成、已发布或已发送。
