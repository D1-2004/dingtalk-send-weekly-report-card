# 输入、提取与产物契约

## 输入

| 字段 | 必填 | 来源 | 说明 |
| --- | --- | --- | --- |
| `reportUrl` | 是 | 用户消息 | 周报链接，优先为钉钉文档或知识库节点 |
| `userDescription` | 否 | 用户消息 | 对客户、项目、周期、收件人或简报的补充与纠正 |
| `senderUserId` | 是 | 当前会话上下文 | 当前任务发起人的钉钉 `userId`，同时作为默认接收人 |
| `senderDisplayName` | 是 | 当前会话上下文或通讯录 | 发起人的展示名称，写入隐藏字段 `collector` |

缺少周报链接、接收人、客户、周期或项目列表时，先读取文档和会话上下文；仍无法确定时询问用户。不要用占位符发送真实卡片。

## 信息来源优先级

字段冲突时，按以下顺序取值：

1. 用户对具体字段的明确纠正或指示。
2. 周报正文中的明确事实。
3. 用户未指向具体字段的概括性描述。
4. 可重复验证的派生值，例如由日期范围计算 ISO 周次。

用户描述可以补充周报没有的信息，但不能把猜测包装成周报事实。

## 获取并处理周报

读取钉钉文档：

```bash
dws doc read --node "$REPORT_URL"
```

从正文中提取：

- `customer`：客户名称，不包含“周报”“回访”等后缀。
- `reportPeriod`：正文标注的统计周期，保留用户易读格式。
- `week`：优先采用正文中的周次；否则依据报告周期生成，例如 `2026-W15`。
- `projects`：需要逐项反馈的项目名。去重但保留原始顺序，不把问题标题或工单标题误当项目。
- `summaryMarkdown`：3 至 5 条对外可见的事实性要点，优先包含新增需求、完成量、处理中问题和重点风险。

不要把整份周报直接塞入卡片；卡片只展示摘要和原文链接。

## 业务层产物

先生成 `weekly-card-input.json`，严格遵循 `../assets/weekly-card-input.schema.json`。此时 `projects` 必须还是对象数组，不得提前转换成字符串：

```json
{
  "outTrackId": "wf-1787690400000-a1b2",
  "title": "维信诺项目回访",
  "iconUrl": "https://img.alicdn.com/example.png",
  "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
  "summaryMarkdown": "- 本周新增需求 11 项\n- 当前 6 个工单处理中",
  "feedbackGuide": "请按项目选择满意度，并填写具体反馈。",
  "reportPeriod": "2026年3月31日—2026年4月10日",
  "customer": "维信诺",
  "week": "2026-W15",
  "collector": "辰驷",
  "reportTime": "2026-08-26 10:00:00",
  "recipientUserId": "323179",
  "projects": [
    {"name": "智能助理项目"},
    {"name": "数据看板项目"}
  ]
}
```

约束：

- `outTrackId` 每次生成新值，推荐 `wf-<毫秒时间戳>-<4位随机串>`，总长度不超过 40 个字符。
- `collector` 是本次任务发起人，不是应用机器人、Agent 或表单提交人。
- 项目数量由 `projects` 的实际长度决定，构造器动态生成原生表单字段，不写死 2 行或其他固定数量。
- `iconUrl` 必须是可公网读取的 HTTPS 图片 URL。
- 不允许业务对象出现未声明字段。

## 确定性构造

不要让模型直接构造 `cardData.cardParamMap`。使用构造器：

```bash
python3 scripts/build_card_payload.py weekly-card-input.json \
  --output card-request.json
```

构造器负责：

1. 用 `weekly-card-input.schema.json` 校验业务对象。
2. 按项目实际数量生成原生 `feedbackForm` 对象；每个项目拥有独立满意度、快捷原因和具体反馈字段。
3. 只在 DWS 传输边界把 `feedbackForm` 序列化为紧凑 JSON String。
4. 用内部 Schema 校验反序列化结果。
5. 用外层 Schema 校验最终 DWS 请求。
6. 检查跨字段编号、隐藏元数据、敏感字段和参数 key 的 UTF-8 字节上限。

## 卡片变量映射

钉钉接口要求 `cardData.cardParamMap` 的值全部为字符串：

| 卡片变量 | 取值 |
| --- | --- |
| `title` | 客户或项目回访标题 |
| `iconUrl` | 可公网读取的 HTTPS 图片 URL |
| `reportUrl` | 原始周报链接 |
| `summaryMarkdown` | 周报事实摘要，Markdown 字符串 |
| `weeklySummary` | 与 `summaryMarkdown` 一致，用于兼容当前模板变量 |
| `feedbackGuide` | 简短的反馈引导语 |
| `reportPeriod` | 周报周期 |
| `customer` | 客户名称 |
| `week` | ISO 周次，例如 `2026-W15` |
| `collector` | 发起本次卡片任务的用户展示名称 |
| `reportTime` | 卡片生成时间 |
| `submissionId` | 与本次 `outTrackId` 相同的提交唯一编号 |
| `feedbackForm` | 动态原生表单对象序列化后的紧凑 JSON String |
| `submitButtonText` | 初始为 `提交` |
| `formState` | 初始为 `normal` |

`feedbackForm.fields` 先包含 `submissionId`、`customer`、`week`、`collector`、`reportTime` 五个隐藏字段。随后每个项目按连续编号生成：隐藏项目名 `project_N`、必填满意度 `satisfaction_N`、快捷不满意原因 `reasons_N`、具体反馈 `feedback_N`。四组编号必须从 1 连续递增并完全一致。

传输层每个 key 不超过 100 UTF-8 字节。钉钉官方原生表单示例会将完整表单对象作为一个 `cardParamMap` 字符串值发送，因此不要再使用旧技能中的 1024 字节自定义上限。构造器仍采用紧凑字段定义，并对反序列化后的完整结构执行 Schema 校验。

## 产物及获取

### 业务产物

`weekly-card-input.json` 是从周报提取的可读业务对象，适合审阅、修改和审计。

### 请求产物

`card-request.json` 是构造器输出的 DWS 请求。发送前再次运行：

```bash
source ~/.zshrc
python3 scripts/validate_card_payload.py card-request.json
```

### 投递产物

DWS 返回的 `result.outTrackId` 是本次卡片实例的主要追踪标识。命令输出中同时保留每个 `deliverResults` 的成功状态。

### 用户侧产物

成功投递后，接收人在钉钉中与该应用机器人的单聊里收到互动卡片。技能随后向任务发起人回复“卡片已发送，请在钉钉中查收”。

### 反馈数据

卡片提交后，用 `outTrackId` 在 AI 表格中查询同一次提交产生的项目反馈行。反馈人来自提交回调的 `userId`，收集人来自卡片变量 `collector`。`reasons_N` 会与 `feedback_N` 合并写入“反馈”列，避免快捷原因丢失。

## 变更历史

| 日期 | 版本 | 改动 | 原因 |
| --- | --- | --- | --- |
| 2026-08-27 | v5 | 业务图标字段改为 `iconUrl`，传输层恢复动态 `feedbackForm` 并增加 `reasons_N` | 与已保存的原生 Form 模板变量保持一致，并保留快捷不满意原因 |
| 2026-08-26 | v3 | 用动态 `projectRows` 取代固定编号表单字段，项目数不再限制为 2 | 让模板按实际项目数量循环渲染并保持结构化校验 |
| 2026-08-26 | v4 | 增加共享布尔状态 `formDisabled` | 让动态满意度组件与输入框在任一用户提交成功后统一进入禁用态 |
| 2026-08-26 | v2 | 增加未序列化业务对象、确定性构造器、内部 Schema 和 1KB 限制 | 防止 JSON String 抹平内部结构并绕过发送前校验 |
| 2026-08-26 | v1 | 建立周报提取、卡片变量和反馈字段映射 | 统一 Agent 从周报到卡片请求的输入输出 |
