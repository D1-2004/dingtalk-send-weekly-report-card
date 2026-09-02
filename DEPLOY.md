# 上线配置清单 · 钉钉周报回访卡片

部署 / 换环境时按此逐项核对，缺一项技能就跑不通或退化。

## 1. 环境变量

| 变量 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `LTC_SOURCE` | 是（否则退化为只按周报正文生成） | LTC 项目明细来源，值为一条**钉钉 AI 表格链接**；Agent 用 `dws aitable` 解析出 base-id / table-id 后按客户名反查"交付中"项目、金额排序 | `https://alidocs.dingtalk.com/i/nodes/{baseId}?iframeQuery=entrance%3Ddata%26sheetId%3D{tableId}%26viewId%3D{viewId}` |
| `WEEKLY_FEEDBACK_SUBMIT_URL` | 是（生成 HTML 反馈页时脚本强校验） | 客户提交反馈回写的钉钉 AI 表格 Webhook 流地址，格式固定 | `https://connector.dingtalk.com/webhook/flow/{flowId}` |

> 换表 / 换环境只改这两个环境变量，技能代码与 HTML 模板不动。

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
- 合同金额仅用于选项目 / 排序，**不写进页面数据、不展示给客户、不进 Webhook**。

## 5. 已知注意

- 发送脚本用 `dws chat +dm --content`；若目标环境 dws 版本改用 `--text`，发送会报 `unknown flag`，届时把 `scripts/weekly_report_tool.py` 里 `run_dws_dm` 的 `--content` 改为 `--text`。
- 反馈页在钉钉容器内读取当前用户身份，身份读取失败时禁止提交（防伪造）。
