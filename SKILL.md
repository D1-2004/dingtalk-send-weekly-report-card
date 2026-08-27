---
name: dingtalk-send-weekly-report-card
description: Use when 用户提供钉钉或阿里云文档周报链接，并要求生成可托管的单 HTML 客户回访页，或构造、校验、发送钉钉满意度互动卡片；尤其适用于动态项目列表、独立满意度反馈和明确接收人的场景。
---

# 钉钉周报回访卡片

把用户提供的周报转换为客户满意度回访卡片。根据用户要求，产出可以是一个已绑定提交地址的独立 HTML 文件，也可以是钉钉互动卡片请求和 DWS 投递回执。

## 必须读取的资源

在构造请求前读取：

- `references/input-output-contract.md`：周报信息提取、字段映射与产物获取规则。
- `references/html-generator-contract.md`：独立 HTML 卡片的数据接口、提交地址和单命令生成规则；仅 HTML 模式必读。
- `references/create-and-deliver-schema.md`：DWS API 参数和响应判定。
- `assets/weekly-card-input.schema.json`：Agent 生成的未序列化业务对象约束。
- `assets/create-and-deliver.schema.json`：DWS 外层传输请求约束。
- `assets/project-rows.schema.json`：字符串化 `projectRows` 反序列化后的动态项目结构约束。
- `assets/weekly-report-card-data.schema.json`：独立 HTML 卡片外部参数约束。

使用 `assets/weekly-card-input.example.json` 作为输入样例，使用 `assets/card-request.example.json` 核对构造结果。不要直接发送样例中的接收人或 `outTrackId`。

HTML 模式使用 `assets/weekly-feedback-html-data.example.json` 核对 `--data`，并使用内置 `assets/weekly-feedback-template.html`；不要直接编辑模板结构。

技能包只暴露 `scripts/weekly_report_tool.py` 的 `gen-card` 命令。使用 `--type html` 或 `--type card` 选择产物；参数校验、分支生成和结果返回全部由这一命令完成，不要直接调用内部函数或其他脚本。

## 工作流

### 0. 选择产物模式

- 用户要求“HTML”“单文件”“可托管页面”或给出 HTML 输出路径时，使用 HTML 模式。只生成文件，不调用 DWS。
- 用户明确要求在钉钉中发送互动卡片时，继续执行下方 DWS 模式。

HTML 模式中，把周报和用户描述整理成 `WeeklyReportCardData`，然后只执行一条命令：

```bash
source ~/.zshrc
python3 scripts/weekly_report_tool.py gen-card \
  --type html \
  --data "$CARD_DATA_JSON" \
  --output "$OUTPUT_PATH"
```

这一条命令封装严格 JSON 解析、提交 URL 校验与注入、模板数据替换、`</script>` 安全转义、父目录创建和文件写入。内部先完成参数校验，再调用 `gen_html_card`，最后在标准输出返回结构化 JSON；`output` 是生成文件的绝对路径。不要再用脚本或文本替换工具二次编辑生成文件。

`WEEKLY_FEEDBACK_SUBMIT_URL` 必须由运行环境注入，并且必须是绝对 HTTP 或 HTTPS URL。它是 HTML 最终 `callbackUrl` 的唯一权威来源；命令会覆盖 `--data` 中可能残留的旧值。`--output` 接受相对路径、绝对路径和 `~` 路径。HTML 外部数据不接受按钮文案字段，界面统一使用“提交”和“已提交”。

HTML 模式完成后停止，不执行第 3～6 步的 DWS 构造、认证或发送。

### 1. 确认输入与接收人

从当前消息取得：

- 周报 URL。
- 用户补充描述，可为空。
- 当前消息发起人的 `userId` 和展示名称。

默认把卡片发送给当前消息发起人，并把该发起人写入卡片公有数据 `collector`。不要把应用机器人名称、Agent 名称或卡片提交人预填为收集人。

如果无法确定接收人的 `userId`，先询问或调用通讯录能力解析；不要猜测。

### 2. 获取周报产物

优先直接读取链接：

```bash
dws doc read --node "$REPORT_URL"
```

如果链接不是钉钉文档，使用可用的文档读取工具获取正文。读取失败或无权限时，请用户授权或粘贴正文；不要根据标题编造内容。

按照 `references/input-output-contract.md` 生成 `weekly-card-input.json`。用户明确补充或纠正的字段优先于文档；其余事实以文档为准。

### 3. 生成卡片请求

不要让模型直接拼接字符串化的 `projectRows`。先把未序列化业务对象保存为 `CARD_DATA_JSON`，再执行统一命令：

```bash
source ~/.zshrc
python3 scripts/weekly_report_tool.py gen-card --type card \
  --data "$CARD_DATA_JSON" \
  --output card-request.json
```

命令先校验参数与 `WEEKLY_FEEDBACK_SUBMIT_URL`、`DDWS_CLIENT_ID`、`DDWS_CLIENT_SECRET`，再调用 `gen_ding_card`，依次执行业务 Schema、反序列化变量 Schema、DWS 传输 Schema 和跨字段校验，并生成：

- 每次发送生成全新的 `outTrackId`。
- `openSpaceId` 使用 `dtv1.card//IM_ROBOT.<userId>`。
- `callbackType` 使用 `HTTP`。
- `callbackRouteKey` 默认使用 `customer_feedback_aitable_v1`。
- `cardData.cardParamMap` 的所有值必须是字符串。
- `projects` 在业务层是对象数组，只在 DWS 传输边界转换为动态 `projectRows`。
- 每个项目行包含独立 `id`、满意度、快捷不满意原因、具体反馈及当前选中状态；项目数不写死。
- 项目行的选择/填写事件只调用卡片回调更新当前用户的 `userPrivateData.projectRows`，不写 AI 表格；底部按钮一次性提交完整 `projectRows`。
- `customer`、`week`、`collector`、`reportTime`、`submissionId` 作为独立卡片变量传递，并在最终提交时一并回传。
- 初始 `formState` 使用 `normal`、`formDisabled` 使用字符串 `false`、`submitButtonText` 使用 `提交`。最终提交成功后 HTTP 回调更新共享 `cardData` 为 `disabled`、`true`、`已提交`，使同一卡片不能再次提交。
- `imRobotOpenSpaceModel.supportForward` 使用 `true`。
- `cardParamMap` 每个 key 不超过 100 UTF-8 字节；`projectRows` 必须先按内部 Schema 校验，再序列化为 JSON String。

不要沿用旧卡片的 `outTrackId`。卡片内容或接收人发生变化时也必须生成新值。

项目数量不在模板里写死：1、3、5 项或其他数量都由 `projects` 的实际长度决定。不要静默截断项目。

### 4. 调用前校验与结果核对

先加载用户终端配置，然后硬性检查 `DDWS_CLIENT_ID` 和 `DDWS_CLIENT_SECRET`：

```bash
source ~/.zshrc
if [[ -z "${WEEKLY_FEEDBACK_SUBMIT_URL:-}" || -z "${DDWS_CLIENT_ID:-}" || -z "${DDWS_CLIENT_SECRET:-}" ]]; then
  printf '错误：缺少 WEEKLY_FEEDBACK_SUBMIT_URL、DDWS_CLIENT_ID 或 DDWS_CLIENT_SECRET，停止生成。\n' >&2
  exit 1
fi
python3 scripts/weekly_report_tool.py gen-card --type card \
  --data "$CARD_DATA_JSON" \
  --output card-request.json
```

构造器和校验器依赖 `jsonschema>=4.18,<5`，版本声明位于 `scripts/requirements.txt`。依赖缺失时停止并提示安装，不得跳过 Schema 校验。

统一命令检查 `WEEKLY_FEEDBACK_SUBMIT_URL`、`DDWS_CLIENT_ID` 和 `DDWS_CLIENT_SECRET` 是否存在，但不会输出凭证值。任一变量不存在或为空时必须报错并终止，禁止继续调用 DWS API。旧变量 `DWS_CLIENT_ID` 和 `DWS_CLIENT_SECRET` 不作为有效凭证来源。

命令会重新解析 `projectRows` 并执行内部 Schema，检查项目 ID 连续、项目名唯一、选项归属和满意度状态一致，并递归扫描敏感字段。错误消息不会回显字段值。校验失败时停止发送，修复所有错误后重新运行。

`--type card` 的成功结果必须包含提示：`当前命令指定的数据提交地址是xxx，需核对ding-card实际提交地址`。这里的地址来自 `WEEKLY_FEEDBACK_SUBMIT_URL`，只用于提醒核对，不会写入 DWS 请求；ding-card 实际提交地址由卡片平台其他位置配置。

### 5. 显式传参调用 DWS API

必须显式传入应用凭证参数。环境变量只作为参数值来源，不能依赖 DWS 自动注入：

```bash
source ~/.zshrc
dws api POST /v1.0/card/instances/createAndDeliver \
  --client-id "$DDWS_CLIENT_ID" \
  --client-secret "$DDWS_CLIENT_SECRET" \
  --data - \
  --jq '{success,result}' \
  < card-request.json
```

不要使用缺少 `--client-id` 或 `--client-secret` 的 `dws api` 调用。不要把凭证值写入请求 JSON、文件、日志或回复。

### 6. 判定投递与回复用户

仅在同时满足以下条件时声明成功：

- 顶层 `success` 为 `true`。
- `result.outTrackId` 与请求一致。
- `result.deliverResults` 非空。
- 每个 `deliverResults[].success` 都为 `true`。

成功后回复：

> 卡片已发送，请在钉钉中查收。

可以附带 `outTrackId` 便于排查，但不要附带应用密钥、访问令牌或完整内部响应。

如果 API 返回失败，报告错误码和安全的错误摘要；不要声称卡片已发送。

## 产物与获取方式

HTML 模式产生一个独立 HTML 文件。命令成功时在标准输出返回结构化 JSON，其中 `output` 是绝对路径、`submitUrl` 是实际注入地址；文件内已包含渲染数据和 `callbackUrl`，可直接打开、托管或交付。

DWS 模式产生四类产物：

1. `weekly-card-input.json`：从周报提取的、未序列化的业务对象。
2. `card-request.json`：构造器生成并通过结构校验的最终 DWS 请求。
3. DWS 投递回执：从命令输出获取 `outTrackId`、`carrierId`、场域和成功状态。
4. 钉钉互动卡片：投递成功后，当前消息发起人在应用机器人单聊中查收；可转发能力由卡片参数控制。

若后续需要核验反馈写入，使用 `outTrackId` 或表单中的 `submissionId` 查询 AI 表格记录。

## 注意事项

- HTML 模式必须从 `WEEKLY_FEEDBACK_SUBMIT_URL` 读取提交地址，不要把地址硬编码进模板，也不要让模型把它混入展示数据。
- HTML 中的 `callbackHeaders` 对文件接收者可见，只能包含非敏感值；禁止写入令牌、密钥或长期凭证。
- HTML 模式只执行 `weekly_report_tool.py gen-card`；不要调用 DWS，也不要设置或修改 `callbackRouteKey`。
- HTML 生成成功后，不要再分步替换 JSON、提交地址或输出文件。
- 只把 `scripts/weekly_report_tool.py` 作为命令入口；不要引用或恢复独立构造器、校验器入口。
- 先 `source ~/.zshrc`，再显式传入两个 DWS 凭证参数。
- 不把 DWS 用户 OAuth 登录态误认为应用身份；创建卡片使用应用 AppKey/AppSecret。
- 不在获取不到正文时虚构客户、项目、数据或周期。
- 不把简要描述中的推测写成周报事实。
- 不把反馈人预填到卡片中；反馈人由提交回调的 `userId` 产生。
- 把收集人设置为发起本次卡片任务的用户。
- `iconUrl` 是必填的公网 HTTPS 图片 URL；缺失或格式不合法时停止构造。
- 不直接手写 `card-request.json` 中的 JSON 字符串；始终通过构造器生成。
- 只使用 `DDWS_CLIENT_ID` 和 `DDWS_CLIENT_SECRET`；任一变量缺失时立即报错并停止，不得执行 `dws api`。
- 发送前始终运行参数校验器，发送后始终检查每个投递结果。
- 已注册的回调路由是前置条件；本技能不自动覆盖回调注册。

## 变更历史

| 日期 | 版本 | 改动 | 原因 |
| --- | --- | --- | --- |
| 2026-08-27 | v10 | 命令面收敛为 `gen-card --type html` 和 `gen-card --type card`；提交地址改由环境变量注入；HTML 按钮文案固定，并为 card 返回实际地址核对提示 | 避免多子命令和多种按钮文案造成调用及体验不一致，同时明确 ding-card 的回调地址不由生成请求决定 |
| 2026-08-27 | v9 | 将 HTML 生成、DWS 请求构造和 DWS 请求校验合并到统一工具入口，并增加 HTML 数据 Schema | 对 Agent 只暴露一个稳定命令入口，同时保留对字符串化 `projectRows` 的深层校验，减少调用分支和漏校验风险 |
| 2026-08-27 | v8 | 增加独立 HTML 模式，把 JSON 解析、提交地址注入、模板替换和文件输出封装进 `weekly_report_tool.py gen-card` | 避免 Agent 分步操作造成转义错误、提交地址遗漏或输出路径处理不一致；本次不改变 DWS 协议 |
| 2026-08-27 | v7 | 从原生 `feedbackForm` 切回紧凑循环布局；交互项按项目回调更新用户私有草稿，最终按钮统一写表并更新共享禁用态 | 缩短每个项目的展示高度，同时避免旧循环版满意度串值和动态本地对象无法可靠汇总的问题 |
| 2026-08-27 | v6 | 改用动态原生 `feedbackForm`，图标变量统一为 `iconUrl`，增加快捷不满意原因并改为共享提交状态 | 修复循环交互状态串行、选项文案缺失和提交后仅个人禁用的问题，并与已保存模板协议对齐 |
| 2026-08-26 | v5 | 增加共享 `formDisabled` 状态，并明确动态项目数组不设固定数量上限 | 提交成功后统一禁用所有动态行，且按周报实际项目数渲染 |
| 2026-08-26 | v4 | 项目反馈由固定两组表单字段改为动态 `projectRows` 数组，明确 `icon` 必填 | 支持按周报实际项目数量循环渲染，避免 3 项、5 项场景被截断或写死 |
| 2026-08-26 | v3 | 认证环境变量迁移为 `DDWS_CLIENT_ID`、`DDWS_CLIENT_SECRET`，增加调用前硬性检查 | 避免 DWS 调用读取错误的应用凭证变量或在凭证缺失时继续执行 |
