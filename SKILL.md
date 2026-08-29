---
name: dingtalk-send-weekly-report-card
description: Use when 用户提供周报链接或周报内容，并要求生成反馈网页、发送默认 Markdown 周报回访消息，或显式发送钉钉互动卡片。
---

# 钉钉周报回访

## 功能

读取用户提供的周报链接和补充描述，提取标题、周期、简报、客户与项目数据。默认产物是带反馈入口的钉钉 Markdown 消息；反馈入口指向先生成并托管到 Multica 的 HTML 反馈页。

Agent 负责理解周报和构造 JSON，只调用统一命令完成数据校验、模板渲染、HTML 生成或消息发送：

```text
scripts/weekly_report_tool.py gen-card
```

支持三种类型：

- `markdown`：默认类型。校验 Markdown 数据，使用脚本内置的 Python `Template` 渲染消息，再通过当前用户登录态发送给指定用户。
- `html`：校验反馈页数据，生成 HTML 和两个运行时文件，供 Multica 静态网站托管。
- `card`：兼容已有钉钉互动卡片；仅在用户明确要求互动卡片时使用。

Agent 不自行调用 DWS。Markdown 模式由命令调用 `dws chat +dm`，使用当前 DWS 登录用户身份，不读取 Client ID 或 Client Secret；只有互动 Card 兼容模式使用应用凭证。

## 默认工作流

用户要求发送周报回访但没有指定格式时，按以下顺序执行：

1. 读取周报并构造 HTML 数据，按照 `assets/weekly-report-card-data.schema.json` 校验字段来源。
2. 调用 `gen-card --type html`，输出到一个独立网站目录的 `index.html`。
3. 将命令返回的 `siteRoot` 整体打成 ZIP。ZIP 根目录必须直接包含：
   - `index.html`
   - `dingtalk-identity.js`
   - `weekly-feedback-runtime.js`
4. 使用 Multica MCP：
   - 调用 `prepare_static_site_deploy`，传 ZIP 的 `expected_sha256` 和 `content_length`。
   - 按返回的上传方法、地址和一次性凭证流式上传原始 ZIP，不使用 multipart 或 base64。
   - 调用 `get_static_site_deploy`，确认状态为 `active` 并取得 `site_url`。
5. 将 `site_url` 写入 Markdown 数据的 `feedbackUrl`。
6. 调用 `gen-card`，省略 `--type` 即使用默认 `markdown`，完成校验、模板渲染和发送。
7. 只有 HTML 发布成功且 Markdown 命令返回 `success: true` 时，才回复用户“已发送，请查收”。

HTML 发布失败时不得发送一个缺少反馈入口或使用本地文件地址的 Markdown 消息。

## 参数规格与来源

### 命令参数

| 参数 | Markdown | HTML | Card | 说明 |
| --- | --- | --- | --- | --- |
| `--type` | 可省略 | 必填 `html` | 必填 `card` | 可选值 `markdown`、`html`、`card`；默认 `markdown` |
| `--data` | 必填 | 必填 | 必填 | 严格 JSON 对象，不接受 Python 字面量 |
| `--output` | 禁止 | 必填 | 禁止 | HTML 输出文件；支持相对路径、绝对路径和 `~` |
| `--template` | 禁止 | 可选 | 禁止 | 自定义 HTML 模板；默认使用内置模板 |

运行环境由部署方注入：

- HTML：`WEEKLY_FEEDBACK_SUBMIT_URL`，作为反馈页提交地址。
- Markdown：不需要环境变量，使用当前 DWS 登录态。
- Card：`WEEKLY_FEEDBACK_SUBMIT_URL`、`DDWS_CLIENT_ID`、`DDWS_CLIENT_SECRET`。

环境变量缺失或格式错误时由命令报错并停止；Agent 不在调用前自行检查。

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
| 接收人 | 用户明确指定的姓名或花名；未指定时询问用户，不猜测 |
| `iconUrl` | 用户或业务配置提供的公网 HTTP/HTTPS 图片地址 |
| `reportTime` | 当前生成时间，格式 `YYYY-MM-DD HH:mm:ss` |

使用当前 Agent 已有的文档读取能力获取周报正文；读取失败时请求授权或让用户粘贴正文，不根据标题猜测正文。

## 命令使用

### HTML 反馈页

数据按照 `assets/weekly-report-card-data.schema.json` 构造，样例见 `assets/weekly-feedback-html-data.example.json`。

关键字段：

- `schemaVersion` 固定为 `1`。
- `iconUrl`、`title`、`reportUrl`、`reportPeriod`、`customer`、`week`、`collector`、`reportTime`、`submissionId`。
- `summaryMarkdown` 是简报字符串数组。
- `projects` 是动态项目数组；每项包含唯一 `id`、项目 `name`、初始满意度、原因数组和反馈文本。
- `dissatisfactionOptions` 是快捷不满意原因数组。

不要在数据中构造 `callbackUrl`。`WEEKLY_FEEDBACK_SUBMIT_URL` 必须是 `https://connector.dingtalk.com/webhook/flow/{flowId}`；命令会严格校验并把原始地址注入 HTML，同时生成 `multica-fetch-proxy-config.js`：

```javascript
window.__MULTICA_FETCH_PROXY_ALLOWLIST__ = ["https://connector.dingtalk.com/webhook/flow/{flowId}"];
```

HTML 模板会在反馈业务脚本之前加载该同源配置文件，业务提交仍调用标准 `fetch(callbackUrl, ...)`。Multica 服务端不会注入默认白名单；平台 Runtime 只代理页面明确声明且精确命中的地址，未命中的请求继续使用浏览器原生 `fetch`。生成结果不是单文件，发布时必须包含命令返回的全部 `assets`。

反馈页按照 dm-bind 的方式加载钉钉内部身份能力：

```javascript
import "@ali/dingtalk-jsapi/entry/union";
import getCurrentUserInfo from "@ali/dingtalk-jsapi/api/internal/user/getCurrentUserInfo";
```

页面不使用 `requestAuthCode`，也不需要 Client ID 或 Client Secret。页面加载后调用 `internal.user.getCurrentUserInfo({})`；提交时把当前用户写入：

- `feedbackUser`: `{ userId, name, avatar, corpId }`
- `feedbackUserId`
- `feedbackUserName`

身份读取失败时禁止提交并展示错误。该能力要求页面在钉钉客户端容器内打开。

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

字段：

- `schemaVersion` 固定为 `1`。
- `title`：周报回访标题。
- `reportPeriod`：时间周期。
- `reportUrl`、可选 `reportLinkText`：周报详情入口。
- `summaryMarkdown`：简报字符串数组，可保留必要的 Markdown 加粗。
- `feedbackUrl`、可选 `feedbackLinkText`：已发布 HTML 反馈页的原始 HTTPS 地址和入口文案。
- `recipientName`：接收人的姓名或花名；`dws chat +dm` 会解析唯一联系人，多候选时停止发送。

不要让模型拼接最终 Markdown 文本或钉钉跳转协议。命令会对 `feedbackUrl` 做 URL 编码并转换成：

```text
dingtalk://dingtalkclient/page/link?web_wnd=workbench&url=<encoded-feedback-url>
```

固定 Python 模板按以下顺序渲染：标题、时间周期、周报详情链接、简报、使用上述深链的反馈入口。JSON 中的 `feedbackUrl` 始终保持原始 HTTPS 地址，禁止提前传入 `dingtalk://`，避免重复编码。

默认发送命令：

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --data "$MARKDOWN_DATA_JSON"
```

也可以显式指定：

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --type markdown \
  --data "$MARKDOWN_DATA_JSON"
```

命令内部固定调用：

```bash
dws chat +dm \
  --to "$RECIPIENT_NAME" \
  --content "$RENDERED_MARKDOWN" \
  --yes \
  --format json
```

Markdown 发送只使用上述 `dws chat +dm` 登录态命令，不传入 `--client-id` 或 `--client-secret`。成功结果包含 `success: true`、`type: markdown`、`recipientName`、实际渲染的 `markdown`、原始 `feedbackUrl`、最终 `feedbackDeepLink` 和 DWS 投递响应。

### 互动 Card 兼容模式

仅当用户明确要求钉钉互动卡片时使用 `--type card`。输入是符合以下文件的最终卡片请求 JSON，不是中间业务对象：

- `assets/create-and-deliver.schema.json`
- `assets/project-rows.schema.json`
- `assets/card-request.example.json`

命令会完成深层 Schema、跨字段、敏感字段和提交目标校验，尽力注册固定 callback key，再发送卡片。callback 注册失败只作为非阻塞诊断；卡片投递本身必须成功。

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --type card \
  --data "$DING_CARD_REQUEST_JSON"
```

任何模式校验或投递失败时，直接报告命令的安全错误摘要，不绕过校验，不声称已生成、已发布或已发送。
