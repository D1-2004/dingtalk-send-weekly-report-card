---
name: dingtalk-send-weekly-report-card
description: Use when 用户提供周报链接或周报内容，并要求生成可填写的周报反馈网页，或发送带反馈入口的钉钉 Markdown 周报回访消息。
---

# 钉钉周报回访

## 功能

读取用户提供的周报链接和补充描述，提取标题、周期、本周进展、风险与进行中的项目。默认产物是钉钉 Markdown 消息；消息中的反馈入口指向先生成并托管到 Multica Site 的 HTML 表单。

Agent 只负责理解周报、关联项目、构造 JSON，并调用统一命令：

```text
scripts/weekly_report_tool.py gen-card
```

命令支持：

- `markdown`：默认类型，渲染并发送带周报链接和反馈入口的 Markdown 消息。
- `html`：生成符合 Multica Site CSP 的响应式网页构建产物，供 Multica Site 托管。

网页只收集一份整体反馈（整页一组满意度，不按项目拆分）。客户与项目只读展示，用户填写一次满意度、不满意原因和具体反馈。提交给 Webhook 的数据协议见 `assets/weekly-feedback-webhook.schema.json`。

## 工作流

1. 读取周报，关联项目底表（见「项目底表与关联」），根据下方参数规格构造 HTML 数据。
2. 调用 `gen-card --type html`，将网站入口输出为构建目录下的 `index.html`；命令同时生成页面依赖的同源 JavaScript 文件。
3. 按 Multica Site 当前托管协议打包并上传完整构建产物 ZIP。ZIP 应保持构建产物的目录结构，并以根目录的 `index.html` 作为默认入口；不要假设或写死其他文件名。
4. 使用 Multica MCP 的 `prepare_static_site_deploy` 准备上传，完成上传后调用 `get_static_site_deploy`，确认部署状态为 `active` 并取得 `site_url`。
5. 将 `site_url` 写入 Markdown 数据的 `feedbackUrl`。
6. 调用 `gen-card`，省略 `--type` 即使用默认 `markdown` 完成发送。
7. 只有 HTML 发布成功且 Markdown 命令返回 `success: true`，才回复用户“已发送，请查收”。

HTML 发布失败时，不发送缺少反馈入口或使用本地文件地址的消息。

## 项目底表与关联

需要发周报的项目通常是「交付中」且合同金额较大的项目。项目基础信息（LTC 项目明细）**从环境变量 `LTC_SOURCE` 读取，不写死在技能里**：`LTC_SOURCE` 的值是一条指向钉钉 AI 表格的链接，形如 `https://alidocs.dingtalk.com/i/nodes/{baseId}?iframeQuery=...sheetId={tableId}...`。Agent 用钉钉 AI 表格能力（`dws aitable`，如 `record query --base-id … --table-id …`）从该链接解析出 base-id / table-id 后再查询。

- 关键字段：项目名称、项目编号、客户名称、交付PM、项目状态、合同金额、风险级别、详细进展、是否超期。
- 若 `LTC_SOURCE` 未配置或读取失败：跳过底表关联，仅按周报正文生成，并可提示运维补配 `LTC_SOURCE`；不猜项目名、金额或状态。
- 换环境/换表只改 `LTC_SOURCE`，技能代码与模板不动。

关联与取数规则（运行时按此执行）：

1. **以「客户名称」为主键**查底表：用周报里的客户（全称或简称/关键词）在 LTC 表匹配 `客户名称`，筛出 `项目状态=交付中` 的行，取该行的**规范项目全名**、`交付PM`、`合同金额`。项目名一律用底表规范值，不要用周报里的长名/简写原样。
2. **多项目默认取金额最大的一个**：该客户有多个交付中项目时，**默认选 `合同金额` 最大的那个项目**作为本次回访项目，不必列全部、也不必为此专门追问。只有当周报正文明确点名了另一个项目时才改用点名的那个；连金额最大的也不确定是否是本次对象时，才向交付PM确认一次（"本次是给〈客户〉发送〈项目名〉的周报回访，对吗？"），未回复可再追问，仍不确定就不发送、不猜。
3. **进展与风险完全按 PM 周报原文提炼，不自行加工**：不把底表的 `是否超期`、`风险级别` 当成风险原因自己写进「风险 · 关注」（超期成因复杂，以周报为准）；底表字段只用于选项目，不用于生成文案。
4. **合同金额只用于选项目/排序**，绝不写进 HTML/Markdown 数据、不展示给客户、不进 Webhook。
5. 匹配不到任何项目时，按周报正文照常生成，不猜测金额或状态。

## 参数规格与来源

### 命令参数

| 参数 | Markdown | HTML | 说明 |
| --- | --- | --- | --- |
| `--type` | 可省略 | 必填 `html` | 可选值为 `markdown`、`html`；默认 `markdown` |
| `--data` | 必填 | 必填 | 严格 JSON 对象，不接受 Python 字面量 |
| `--output` | 禁止 | 必填 | HTML 入口文件；支持相对路径、绝对路径和 `~`，托管时使用 `{siteRoot}/index.html` |
| `--template` | 禁止 | 可选 | 自定义 HTML 模板；默认使用内置模板 |

HTML 模式需要部署方注入 `WEEKLY_FEEDBACK_SUBMIT_URL`，值为 `https://connector.dingtalk.com/webhook/flow/{flowId}`。环境变量缺失或格式错误由命令直接报错，Agent 不在命令外重复校验。

### 周报数据来源

| 信息 | 来源与规则 |
| --- | --- |
| 周报链接 | 用户消息中的原始链接 |
| 客户 | 用户明确说明优先，否则从周报标题和正文提取，可对照底表 `客户名称` |
| 标题 | 通常为“{客户或项目}周报回访” |
| 时间周期、周次 | 周报正文；缺少周次时根据日期范围计算 ISO 周次 |
| 本周进展 `summaryMarkdown` | **先写"做成了什么"**：可交付成果、上线/完成的功能、关键里程碑（如"意图识别模型完成迭代，准确率 +3%"），一条一句、客户视角可读；数量（新增需求/工单等）只作佐证放句末或括号，禁止只有流水数字、看不出内容。3–5 条，不编造 |
| 风险 · 关注 `riskMarkdown` | 从周报正文提炼需客户知悉的风险/待办，可为空数组；与底表 `风险级别`、`是否超期` 相互印证但不编造 |
| 下周重点 `nextWeekMarkdown` | 从周报"下周计划"提炼 2–4 条将推进事项，客户视角可读、可验收，可为空数组；不编造 |
| 项目列表 `projects` | 从周报提取、去重、按合同金额降序；每项仅含 `id`、`name`，数量动态不写死 |
| `collector` | 发起本次生成或发送任务的用户，不是 Agent 或机器人 |
| 接收人 | 用户明确指定的姓名或花名；未指定时询问，不猜测 |
| `reportTime` | 当前生成时间，格式 `YYYY-MM-DD HH:mm:ss` |

使用当前 Agent 已有的文档读取能力获取周报正文；读取失败时请求授权或让用户粘贴正文，不根据标题猜测正文。

## 命令使用

### HTML 反馈表单

HTML 输入样例见 `assets/weekly-feedback-html-data.example.json`。必填字段为：

- `schemaVersion`：固定为 `2`。
- `title`、`reportUrl`、`reportPeriod`、`customer`、`week`、`collector`、`reportTime`、`submissionId`：非空字符串。
- `summaryMarkdown`：本周进展字符串数组。
- `projects`：只读项目数组，每项包含唯一 `id` 和 `name`。
- `dissatisfactionOptions`：不满意原因快捷选项数组，**固定为四项**：`所得与期望效果不符合`、`交付进度不满意`、`沟通响应不及时`、`其他`。

可选字段：

- `riskMarkdown`：风险 · 关注字符串数组；缺省或空数组时网页不显示风险块。
- `nextWeekMarkdown`：下周重点字符串数组；缺省或空数组时网页不显示下周重点块。
- `iconUrl`：已弃用，网页头部使用内置内联图标，不再展示客户 logo，可不传。

`satisfaction`、`dissatisfactionReasons`、`feedback` 是表单初始值，通常分别传 `""`、`[]`、`""`。不要在 JSON 中传 `callbackUrl`，命令会从环境变量读取并注入。

生成命令：

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --type html \
  --data "$HTML_DATA_JSON" \
  --output "$SITE_DIR/index.html"
```

页面数据仍保存在 `index.html` 的 `application/json` 数据块中；可执行逻辑和钉钉身份读取能力由命令输出为同目录的 JavaScript 文件，HTML 通过相对地址加载。生成结果不得包含可执行的内联脚本，以兼容 Multica Site 的 `script-src 'self'` 策略。

成功结果包含绝对 `output`、`runtimeOutput`、`siteRoot`、`siteFiles` 和实际 `submitUrl`。部署时必须打包 `siteRoot` 下的完整构建产物，不能只上传 `index.html`。使用托管地址时保留末尾 `/`，以便浏览器从站点目录正确解析相对资源；Markdown 命令会自动规范化 Multica Site 根地址。

页面在钉钉容器内读取当前用户身份；身份读取失败时禁止提交。满意度为整页一组，选择「不满意」后才展开四项原因下钻。Webhook 请求必须符合 `assets/weekly-feedback-webhook.schema.json`，一次表单提交对应一次请求。

### Markdown 消息

Markdown 输入样例见 `assets/weekly-report-markdown-data.example.json`。必填字段为 `schemaVersion`、`title`、`reportPeriod`、`reportUrl`、`summaryMarkdown`、`feedbackUrl` 和 `recipientName`；可选 `riskMarkdown`、`nextWeekMarkdown`。

当传入 `riskMarkdown` 或 `nextWeekMarkdown` 时，卡片会分成「本周进展 / 风险 · 关注 / 下周重点」若干组（空块自动省略），让客户不点进网页也能看到本周做了什么、有什么风险、下周推进什么；只有进展时保持单一要点列表。

命令会将原始 HTTPS `feedbackUrl` 转换为钉钉工作台深链，并使用当前登录态发送消息。Agent 不自行拼接 Markdown、深链或底层发送命令：

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --data "$MARKDOWN_DATA_JSON"
```

任何校验、托管或投递失败都直接报告安全错误摘要，不绕过校验，不声称已生成、已发布或已发送。

## 历史记录

- 2026-08-30：HTML 产物改为入口文件加同源 JavaScript 构建资源，原因是 Multica Site 的严格 CSP 会阻止内联可执行脚本，导致页面只能显示静态布局。
- 2026-08-31：样式与信息结构升级——头部去掉依赖外链的客户 logo 改用内联图标、PC/移动端字号与间距收紧、摘要拆「本周进展 + 风险 · 关注」两块（新增可选 `riskMarkdown`）、满意度改为两个大按钮、不满意下钻固定四项；`iconUrl` 转为可选。明确以 LTC 项目底表关联项目并按合同金额降序排序（金额仅内部排序用，不外发）。
- 2026-08-31：摘要升级为三段式「本周进展 / 风险 · 关注 / 下周重点」，新增可选 `nextWeekMarkdown`（蓝色 callout，空则不显示），卡片与网页同步；本周进展强调先写可交付成果而非流水数字。
