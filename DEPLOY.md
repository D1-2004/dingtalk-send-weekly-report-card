# 上线配置清单 · 钉钉周报回访卡片

部署 / 换环境时按此逐项核对，缺一项技能就跑不通或退化。

## 1. 环境变量

| 变量 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `LTC_SOURCE` | 是（否则退化为只按周报正文生成） | LTC 项目明细来源，值为一条**钉钉 AI 表格链接**；Agent 用 `dws aitable` 解析出 base-id / table-id 后按客户名反查"交付中"项目、金额排序 | `https://alidocs.dingtalk.com/i/nodes/{baseId}?iframeQuery=entrance%3Ddata%26sheetId%3D{tableId}%26viewId%3D{viewId}` |
| `WEEKLY_FEEDBACK_SUBMIT_URL` | 是（生成 HTML 反馈页时脚本强校验） | 客户提交反馈回写的钉钉 AI 表格 Webhook 流地址，格式固定 | `https://connector.dingtalk.com/webhook/flow/{flowId}` |
| `WEEKLY_FEEDBACK_READ_URL` | 是（生成 HTML 反馈页时脚本强校验） | 页面 `load` 事件触发时上报已读状态的钉钉 AI 表格 Webhook 流地址 | `https://connector.dingtalk.com/webhook/flow/{flowId}` |

> 换表 / 换环境只改两个 Webhook 环境变量，技能代码与 HTML 模板不写死流地址。

## 2. 依赖

- Python 3 + `jsonschema`：`python3 -m pip install -r scripts/requirements.txt`
- 钉钉连接器（`dws`）已登录，具备 `aitable`（读 LTC 底表）与 `chat`（发回访消息）权限。
- Multica Site 托管能力（`prepare_static_site_deploy` / `get_static_site_deploy`），用于托管生成的反馈网页并取回 `site_url`。

## 3. 部署步骤

1. 在 FDE 工作台该技能的环境变量配置里，填入 `LTC_SOURCE`、`WEEKLY_FEEDBACK_SUBMIT_URL` 与 `WEEKLY_FEEDBACK_READ_URL`。
2. 从 GitHub 仓库**重新导入 / 同步**技能（技能源码在本仓库，改动只有重新拉取才生效）。
3. 首次使用建议先跑一份样例周报，确认：底表能按客户名匹配到项目、HTML 页能打开并提交、Webhook 有回写。

## 4. 数据契约（勿随意改）

- 反馈页样式由 `assets/weekly-feedback-template.html` 固定；内容结构由 `assets/weekly-report-briefing.schema.json`（进展 / 风险 / 下周重点三段）约束，脚本 `weekly_report_tool.py` 引用它作为单一真源。
- 客户提交的回写格式见 `assets/weekly-feedback-webhook.schema.json`。
- 两条 Webhook 都使用 `Content-Type: application/json`。反馈触发词为 `submit_weekly_feedback`；已读触发词为 `weekly_report_mark_read`。
- v2 顶层只保留触发标识、`schemaVersion`、`outTrackId` 和表格行数据。反馈使用单元素 `rows`，已读使用单对象 `row`；行对象已由前端拼成与表格列同名的记录，`编号` 与顶层 `outTrackId` 使用同一个值，项目和列表字段已经序列化为文本。
- 反馈报文的 `rows[0]` 包含基础信息与「是否满意 / 不满意原因 / 具体反馈 / 反馈人ID / 反馈人昵称 / 反馈时间」；不满意时原因文本不能为空。协议见 `assets/weekly-feedback-webhook.schema.json`。
- 已读报文的 `row` 包含基础信息与「是否已读=是」，在页面 `load` 事件触发时发送，不等待身份接口。协议见 `assets/weekly-feedback-read.schema.json`。
- 反馈自动化的原生循环直接消费 Webhook 的 `rows`；已读自动化直接引用 Webhook 的 `row`，两者都不使用 Python 或其他脚本解析节点。
- 两条自动化都按「编号 = `outTrackId`」查找后 upsert：反馈流程仅更新基础信息与反馈字段；已读流程仅更新基础信息与「是否已读」。这样无论两个请求的到达顺序如何，都只保留同一行并避免互相清空字段。
- 身份与匿名：钉钉内打开自动取身份实名提交；浏览器取不到身份时**允许匿名提交**，提交人记「匿名客户」（`respondentId=anonymous`），不硬拦外部客户。
- 同一 `outTrackId` 的重复上报更新原行，不新增重复记录。
- 钉钉 Webhook 返回成功仅表示已受理，自动化仍在异步执行。联调用 curl 连续模拟“页面已读 → 人工反馈”时，两次请求之间至少等待前一条执行记录完成（建议 5 秒）；生产页面中用户填写表单天然提供了这个间隔。两条请求真正并发到达时，底表的“先查后增”不是原子操作，可能出现重复行。
- 不满意原因固定四项：`产品能力不满足期望`、`交付进度不满意`、`沟通响应不及时`、`其他`（首项 2026-09-03 由「所得与期望效果不符合」改名，AI 表格多选项同步改名，选项 ID 不变）。勾选「其他」时页面展开内联输入框，内容并入 `feedback`（格式「其他：…」），落表仍走「其他备注」列。
- Markdown 回访消息正文**不外显完整周报链接**（`reportUrl` 仅留档），反馈入口文案默认「查看完整周报并反馈您的意见」；客户点进反馈页后才可见完整周报链接。
- Markdown 消息**只外显本周进展要点（最多 3 条）**+ 末尾「- 更多信息……」；风险 / 下周重点即使传入也不在 IM 里挤屏，仍在反馈页完整呈现。三段摘要 schema 收 maxItems=3、单条 ≤ 120 字，文字精炼引导点链接看完整周报。
- HTML `<title>` 由 `gen-card --type html` 静态注入为「{客户或项目}周报」，钉钉聊天粘贴链接的卡片/预览能读到具体客户名而非笼统标题；运行时 JS 也会同步 `document.title`。
- 合同金额仅用于选项目 / 排序，**不写进页面数据、不展示给客户、不进 Webhook**。

## 5. 已知注意

- 发送脚本用 `dws chat +dm --content`；若目标环境 dws 版本改用 `--text`，发送会报 `unknown flag`，届时把 `scripts/weekly_report_tool.py` 里 `run_dws_dm` 的 `--content` 改为 `--text`。
- 反馈页在钉钉容器内读取当前用户身份用于实名；身份读取失败（浏览器/外部客户）时降级为**匿名提交**（记「匿名客户」），不硬拦。已读上报不依赖身份读取，因此页面加载即可触发。
