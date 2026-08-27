# 单 HTML 周报反馈卡片生成契约

## 适用范围

当用户需要一个可以独立打开、托管或转发的 HTML 周报反馈卡片时，使用本契约。此模式只生成文件，不调用 DWS，也不修改互动卡片的 `callbackRouteKey`。

## 单命令接口

```bash
python3 scripts/weekly_report_tool.py gen-card \
  --format html \
  --data "$CARD_DATA_JSON" \
  --submit-url "$SUBMIT_URL" \
  --output "$OUTPUT_PATH"
```

命令内部依次完成：

1. 将 `--data` 解析为严格 JSON 对象。
2. 校验 `--submit-url` 是绝对 HTTP 或 HTTPS URL。
3. 用 `--submit-url` 覆盖数据体中可能残留的 `callbackUrl`。
4. 安全序列化 JSON，转义字符串中的 `</script>`。
5. 只替换模板的 `script#weeklyReportCardData` 数据体。
6. 创建缺失的父目录并写入 `--output` 指定的文件。

`weekly_report_tool.py` 是技能包唯一命令工具；同一脚本还提供 `build-card` 和 `validate-card`，HTML 模式只使用 `gen-card`。

成功时标准输出只有生成文件的绝对路径；失败时返回非零退出码且不生成目标文件。

## 参数

| 参数 | 必填 | 约束 |
| --- | --- | --- |
| `--format` | 是 | 当前只接受 `html` |
| `--data` | 是 | 严格 JSON 对象；不要传 Python 字面量或序列化后的嵌套 JSON 字符串 |
| `--submit-url` | 是 | 绝对 `http://` 或 `https://` 地址；作为最终 `callbackUrl` |
| `--output` | 是 | 输出文件地址；支持相对路径、绝对路径和 `~`，缺失父目录自动创建 |
| `--template` | 否 | 兼容模板文件；默认使用技能包内置模板 |

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
  submitButtonText?: string
  submittedButtonText?: string
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

不要要求模型在 `--data` 中生成 `callbackUrl`。提交地址由可信调用方通过 `--submit-url` 独立传入，命令行参数始终覆盖 JSON 中的同名旧值。

`callbackHeaders` 会以明文写入交付给用户的 HTML，只能放公开且非敏感的固定头；不要写入令牌、密钥或长期凭证。需要鉴权时由提交服务采用短期签名地址、会话鉴权或服务端校验。

项目数量必须来自周报实际内容。每个项目分配稳定且唯一的 `id`，通常按 `p1`、`p2` 连续生成；不要固定为两行。

## 提交行为

生成后的卡片点击提交时，以 `POST application/json` 请求 `callbackUrl`。请求体包含客户、周次、收集人、提交编号和完整 `projectRows`。HTTP 响应状态为成功后，页面进入已提交状态并禁用表单；非 2xx 响应恢复按钮并展示错误。

## 变更历史

| 日期 | 版本 | 改动 | 原因 |
| --- | --- | --- | --- |
| 2026-08-27 | v2 | 增加 HTML 数据 Draft 2020-12 Schema，并把生成命令纳入统一工具入口 | 确保图标、标题、周期、链接、简报、动态项目、快捷选项和提交地址在生成前都经过结构校验 |
| 2026-08-27 | v1 | 增加 `--submit-url`、`--output` 和 JSON 数据的一体化 HTML 生成命令 | 避免 Agent 分步编辑模板、拼接提交地址和创建文件，减少转义错误与提交到错误端点的风险 |
