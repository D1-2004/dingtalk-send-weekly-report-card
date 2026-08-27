# 单 HTML 周报反馈卡片生成契约

## 适用范围

当用户需要一个可以独立打开、托管或转发的 HTML 周报反馈卡片时，使用本契约。此模式只生成文件，不调用 DWS，也不修改互动卡片的 `callbackRouteKey`。

## 单命令接口

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --type html \
  --data "$CARD_DATA_JSON" \
  --output "$OUTPUT_PATH"
```

命令内部依次完成：

1. 将 `--data` 解析为严格 JSON 对象。
2. 读取并校验 `WEEKLY_FEEDBACK_SUBMIT_URL` 是绝对 HTTP 或 HTTPS URL。
3. 用该环境变量覆盖数据体中可能残留的 `callbackUrl`。
4. 安全序列化 JSON，转义字符串中的 `</script>`。
5. 只替换模板的 `script#weeklyReportCardData` 数据体。
6. 创建缺失的父目录并写入 `--output` 指定的文件。

`weekly_report_tool.py gen-card` 是技能包唯一命令；HTML 模式使用 `--type html`，内部依次完成参数校验、调用 `gen_html_card` 和结果返回。

成功时标准输出返回结构化 JSON，包含 `success`、`type`、`output` 和 `submitUrl`；失败时返回非零退出码且不生成目标文件。

## 参数

| 参数 | 必填 | 约束 |
| --- | --- | --- |
| `--type` | 是 | HTML 模式固定为 `html`；另一个允许值为 `card` |
| `--data` | 是 | 严格 JSON 对象；不要传 Python 字面量或序列化后的嵌套 JSON 字符串 |
| `--output` | 是 | 输出文件地址；支持相对路径、绝对路径和 `~`，缺失父目录自动创建 |
| `--template` | 否 | 兼容模板文件；默认使用技能包内置模板 |

运行环境必须提供 `WEEKLY_FEEDBACK_SUBMIT_URL`，其值必须是绝对 `http://` 或 `https://` 地址，并作为最终 `callbackUrl`。

Agent 不读取或预检该环境变量，只拼接 `--data` 和 `--output` 后调用命令。变量缺失或格式错误时由命令报错并停止，不生成目标文件。

## `--data` 对象

完整样例见 `../assets/weekly-feedback-html-data.example.json`。核心接口为：

```text
WeeklyReportCardData {
  schemaVersion: 1
  iconUrl: string
  title: string
  reportUrl: string
  reportLinkText?: string
  summaryMarkdown: string[]
  projects: Array<{
    id: string
    name: string
    satisfaction?: "" | "满意" | "不满意"
    reasons?: string[]
    feedback?: string
    reasonOptions?: Array<{ value: string, text?: { zh_CN?: string } }>
  }>
  dissatisfactionOptions: string[]
  reportPeriod: string
  customer: string
  week: string
  collector: string
  reportTime: string
  submissionId: string
  callbackHeaders?: Record<string, string>
  formDisabled?: boolean
}
```

不要要求模型在 `--data` 中生成 `callbackUrl`。提交地址由可信运行环境通过 `WEEKLY_FEEDBACK_SUBMIT_URL` 注入，命令始终覆盖 JSON 中的同名旧值。

`--data` 不接受提交按钮文案字段。模板统一显示“提交”，成功后显示“已提交”，避免不同生成批次出现“提交反馈”等不一致文案。

`callbackHeaders` 会以明文写入交付给用户的 HTML，只能放公开且非敏感的固定头；不要写入令牌、密钥或长期凭证。需要鉴权时由提交服务采用短期签名地址、会话鉴权或服务端校验。

项目数量必须来自周报实际内容。每个项目分配稳定且唯一的 `id`，通常按 `p1`、`p2` 连续生成；不要固定为两行。

## 提交行为

生成后的卡片点击提交时，以 `POST application/json` 请求 `callbackUrl`。请求体包含客户、周次、收集人、提交编号和完整 `projectRows`。HTTP 响应状态为成功后，页面进入已提交状态并禁用表单；非 2xx 响应恢复按钮并展示错误。

## 变更历史

| 日期 | 版本 | 改动 | 原因 |
| --- | --- | --- | --- |
| 2026-08-27 | v4 | 删除 Agent 侧终端配置加载步骤，提交地址存在性和格式完全由生成命令校验 | 让调用方只提供业务参数，避免在技能指令中复制 CLI 的前置校验逻辑 |
| 2026-08-27 | v3 | 生成入口改为 `gen-card --type html`，提交地址改从环境变量读取，按钮文案固定 | 统一 HTML 与 ding-card 的命令面，并消除调用参数及界面文案漂移 |
| 2026-08-27 | v2 | 增加 HTML 数据 Draft 2020-12 Schema，并把生成命令纳入统一工具入口 | 确保图标、标题、周期、链接、简报、动态项目、快捷选项和提交地址在生成前都经过结构校验 |
| 2026-08-27 | v1 | 增加输出路径和 JSON 数据的一体化 HTML 生成命令 | 避免 Agent 分步编辑模板、拼接提交地址和创建文件，减少转义错误与提交到错误端点的风险 |
