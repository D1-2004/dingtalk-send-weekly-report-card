# 上线配置清单 · 钉钉周报回访卡片

部署 / 换环境时按此逐项核对，缺一项技能就跑不通或退化。

## 1. 环境变量

| 变量 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `LTC_SOURCE` | 是（否则退化为只按周报正文生成） | LTC 项目明细来源，值为一条**钉钉 AI 表格链接**；Agent 用 `dws aitable` 解析出 base-id / table-id 后按客户名反查"交付中"项目、金额排序 | `https://alidocs.dingtalk.com/i/nodes/{baseId}?iframeQuery=entrance%3Ddata%26sheetId%3D{tableId}%26viewId%3D{viewId}` |
| `WEEKLY_FEEDBACK_SUBMIT_URL` | 是（生成 HTML 反馈页时脚本强校验） | 客户提交反馈回写的钉钉 AI 表格 Webhook 流地址，格式固定 | `https://connector.dingtalk.com/webhook/flow/{flowId}` |
| `WEEKLY_FEEDBACK_VIEW_URL` | 否 | 客户「打开反馈页」心跳的回写 Webhook 流地址（写入「周报回访·查看日志」表，用于统计已读未填）。未配置时页面不打心跳 | `https://connector.dingtalk.com/webhook/flow/{flowId}` |

> 换表 / 换环境改两个必填环境变量即可，技能代码与 HTML 模板不动；`WEEKLY_FEEDBACK_VIEW_URL` 为可选增强，按需配置。

## 2. 依赖

- Python 3 + `jsonschema`：`python3 -m pip install -r scripts/requirements.txt`
- 钉钉连接器（`dws`）已登录，具备 `aitable`（读 LTC 底表）与 `chat`（发回访消息）权限。
- Multica Site 托管能力（`prepare_static_site_deploy` / `get_static_site_deploy`），用于托管生成的反馈网页并取回 `site_url`。

## 3. 部署步骤

1. 在 FDE 工作台该技能的环境变量配置里，填入 `LTC_SOURCE` 与 `WEEKLY_FEEDBACK_SUBMIT_URL`。
2. 从 GitHub 仓库**重新导入 / 同步**技能（技能源码在本仓库，改动只有重新拉取才生效）。
3. 首次使用建议先跑一份样例周报，确认：底表能按客户名匹配到项目、HTML 页能打开并提交、Webhook 有回写。

## 4. 数据契约（勿随意改）

- 反馈页样式由 `assets/weekly-feedback-template.html` 固定；内容结构由 `assets/weekly-report-briefing.schema.json`（进展 / 风险 / 下周重点三段）约束，脚本 `weekly_report_tool.py` 引用它作为单一真源。
- 客户提交的回写格式见 `assets/weekly-feedback-webhook.schema.json`。
- 正式 Webhook（2026-09-02 通过落表验收，验收记录 `AUTO-ACCEPT-20260902-001`）：`https://connector.dingtalk.com/webhook/flow/103b2bb12b6b212c3a440006`，触发关键词 `submit_weekly_feedback`，`Content-Type: application/json`。换表 / 换环境时把 `WEEKLY_FEEDBACK_SUBMIT_URL` 指向新流地址即可。
- v2 落表 payload 要点：身份字段为 `respondentId` / `respondentNickname` / `feedbackTime`（ISO 8601）；`projects` 为 `{id,name}` 对象数组；满意度为「不满意」时 `dissatisfactionReasons` 至少一项。
- 回写流 Python 节点的解析代码见仓库根目录 `feedback_webhook_transform.py`（输出键名与表列名一一对应，换表重建自动化流时直接复用）。
- 查看心跳：页面加载后向 `WEEKLY_FEEDBACK_VIEW_URL` 静默 POST `action=view_weekly_feedback`（钉钉内带身份记 `dingtalk`、浏览器记 `anonymous`，并带 `collector`），协议见 `assets/weekly-feedback-view.schema.json`，解析见 `feedback_view_transform.py`（输出含可更新列「最后查看时间」）。
- 查看日志流按 **upsert** 配置（技术评审定稿，替换"每次打开新增一行"）：Webhook 触发 → Python 节点（`feedback_view_transform.py`）→ **查找记录**（条件：`回访记录ID` 等于 payload 回访记录ID **且** `查看环境` 等于 payload 查看环境）→ **条件分支**（是否找到）→ 找到：**更新记录**（最后查看时间、查看人、查看人ID）；未找到：**新增记录**（整行）。效果：同一链接 × 环境只留一行，`查看时间`（createdTime）记首次打开、`最后查看时间` 记最近打开。
- 「已读未填」口径：存在 `查看环境=anonymous` 的行、且反馈表无同 `回访记录ID` 提交记录；upsert 后无需去重。实名（钉钉内）行 = 内部预览，排除；PM 自己预览或 PM 未发给客户，均不产生误报。
- 身份与匿名：钉钉内打开自动取身份实名提交；浏览器取不到身份时**允许匿名提交**，提交人记「匿名客户」（`respondentId=anonymous`），不硬拦外部客户。
- 反馈统计去重口径：同一 `回访记录ID + 提交人ID` 多次提交时，取 `客户反馈时间` 最新的一行；历史全量留痕。
- 不满意原因固定四项：`产品能力不满足期望`、`交付进度不满意`、`沟通响应不及时`、`其他`（首项 2026-09-03 由「所得与期望效果不符合」改名，AI 表格多选项同步改名，选项 ID 不变）。勾选「其他」时页面展开内联输入框，内容并入 `feedback`（格式「其他：…」），落表仍走「其他备注」列。
- Markdown 回访消息正文**不外显完整周报链接**（`reportUrl` 仅留档），反馈入口文案默认「查看完整周报并反馈您的意见」；客户点进反馈页后才可见完整周报链接。
- 合同金额仅用于选项目 / 排序，**不写进页面数据、不展示给客户、不进 Webhook**。

## 5. 已知注意

- 发送脚本用 `dws chat +dm --content`；若目标环境 dws 版本改用 `--text`，发送会报 `unknown flag`，届时把 `scripts/weekly_report_tool.py` 里 `run_dws_dm` 的 `--content` 改为 `--text`。
- 反馈页在钉钉容器内读取当前用户身份用于实名；身份读取失败（浏览器/外部客户）时降级为**匿名提交**（记「匿名客户」），不硬拦。查看心跳以 `查看环境` 区分实名/匿名，供已读未填统计排除内部预览。
