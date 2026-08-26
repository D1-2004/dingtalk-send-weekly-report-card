---
name: dingtalk-send-weekly-report-card
description: 当用户向 Agent 提供钉钉/阿里云文档周报链接，并希望生成、校验和发送客户满意度回访互动卡片时使用。读取周报及用户补充描述，提取客户、项目、周期和简报，构造 DingTalk createAndDeliver 请求，校验后通过显式 AppKey/AppSecret 参数调用 DWS API，将卡片发送给当前消息发起人，并返回可核验的投递结果。不要用于普通文档摘要、非互动卡片消息或缺少明确接收人的批量发送。
---

# 钉钉周报回访卡片

把用户提供的周报转换为客户满意度回访卡片，并投递给当前消息发起人。产出包括规范化卡片请求 JSON、DWS 投递回执和面向用户的发送确认。

## 必须读取的资源

在构造请求前读取：

- `references/input-output-contract.md`：周报信息提取、字段映射与产物获取规则。
- `references/create-and-deliver-schema.md`：DWS API 参数和响应判定。
- `assets/weekly-card-input.schema.json`：Agent 生成的未序列化业务对象约束。
- `assets/create-and-deliver.schema.json`：DWS 外层传输请求约束。
- `assets/feedback-form.schema.json` 和 `assets/satisfaction-options.schema.json`：字符串化变量反序列化后的结构约束。

使用 `assets/weekly-card-input.example.json` 作为输入样例，使用 `assets/card-request.example.json` 核对构造结果。不要直接发送样例中的接收人或 `outTrackId`。

## 工作流

### 1. 确认输入与接收人

从当前消息取得：

- 周报 URL。
- 用户补充描述，可为空。
- 当前消息发起人的 `userId` 和展示名称。

默认把卡片发送给当前消息发起人，并把该发起人写入表单隐藏字段 `collector`。不要把应用机器人名称、Agent 名称或卡片提交人预填为收集人。

如果无法确定接收人的 `userId`，先询问或调用通讯录能力解析；不要猜测。

### 2. 获取周报产物

优先直接读取链接：

```bash
dws doc read --node "$REPORT_URL"
```

如果链接不是钉钉文档，使用可用的文档读取工具获取正文。读取失败或无权限时，请用户授权或粘贴正文；不要根据标题编造内容。

按照 `references/input-output-contract.md` 生成 `weekly-card-input.json`。用户明确补充或纠正的字段优先于文档；其余事实以文档为准。

### 3. 生成卡片请求

不要让模型直接拼接字符串化的 `feedbackForm`。先生成未序列化的业务对象，再调用确定性构造器：

```bash
python3 scripts/build_card_payload.py weekly-card-input.json \
  --output card-request.json
```

构造器会依次执行业务 Schema、反序列化变量 Schema、DWS 传输 Schema 和跨字段校验，并生成：

- 每次发送生成全新的 `outTrackId`。
- `openSpaceId` 使用 `dtv1.card//IM_ROBOT.<userId>`。
- `callbackType` 使用 `HTTP`。
- `callbackRouteKey` 默认使用 `customer_feedback_aitable_v1`。
- `cardData.cardParamMap` 的所有值必须是字符串。
- `feedbackForm` 在业务层是对象，只在 DWS 传输边界序列化为 JSON 字符串。
- 每个项目生成一组 `project_N`、`satisfaction_N`、`feedback_N` 字段。
- `submissionId` 必须等于本次 `outTrackId`。
- 初始 `formState` 使用 `normal`，`submitButtonText` 使用 `提交`。
- `imRobotOpenSpaceModel.supportForward` 使用 `true`。
- `cardParamMap` 每个 key 不超过 100 UTF-8 字节，每个 value 不超过 1024 UTF-8 字节。

不要沿用旧卡片的 `outTrackId`。卡片内容或接收人发生变化时也必须生成新值。

当前已发布模板一次支持 1 至 2 个项目。超过 2 个项目时停止构造并报告需要扩展卡片模板；不要静默丢弃项目。

### 4. 调用前校验

先加载用户终端配置，然后硬性检查 `DDWS_CLIENT_ID` 和 `DDWS_CLIENT_SECRET`：

```bash
source ~/.zshrc
if [[ -z "${DDWS_CLIENT_ID:-}" || -z "${DDWS_CLIENT_SECRET:-}" ]]; then
  printf '错误：缺少 DDWS_CLIENT_ID 或 DDWS_CLIENT_SECRET，停止发送。\n' >&2
  exit 1
fi
python3 scripts/validate_card_payload.py card-request.json
```

构造器和校验器依赖 `jsonschema>=4.18,<5`，版本声明位于 `scripts/requirements.txt`。依赖缺失时停止并提示安装，不得跳过 Schema 校验。

校验器默认同时检查 `DDWS_CLIENT_ID` 和 `DDWS_CLIENT_SECRET` 是否存在，但不会输出其值。任一变量不存在或为空时必须报错并终止，禁止继续调用 DWS API。旧变量 `DWS_CLIENT_ID` 和 `DWS_CLIENT_SECRET` 不作为有效凭证来源。

校验器会重新解析 `feedbackForm` 和 `satisfactionOptions` 并执行内部 Schema，递归扫描敏感字段，且错误消息不会回显字段值。校验失败时停止发送，修复所有错误后重新运行。

### 5. 显式传参调用 DWS API

必须显式传入应用凭证参数。环境变量只作为参数值来源，不能依赖 DWS 自动注入：

```bash
source ~/.zshrc
python3 scripts/validate_card_payload.py card-request.json
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

本技能产生四类产物：

1. `weekly-card-input.json`：从周报提取的、未序列化的业务对象。
2. `card-request.json`：构造器生成并通过结构校验的最终 DWS 请求。
3. DWS 投递回执：从命令输出获取 `outTrackId`、`carrierId`、场域和成功状态。
4. 钉钉互动卡片：投递成功后，当前消息发起人在应用机器人单聊中查收；可转发能力由卡片参数控制。

若后续需要核验反馈写入，使用 `outTrackId` 或表单中的 `submissionId` 查询 AI 表格记录。

## 注意事项

- 先 `source ~/.zshrc`，再显式传入两个 DWS 凭证参数。
- 不把 DWS 用户 OAuth 登录态误认为应用身份；创建卡片使用应用 AppKey/AppSecret。
- 不在获取不到正文时虚构客户、项目、数据或周期。
- 不把简要描述中的推测写成周报事实。
- 不把反馈人预填到卡片中；反馈人由提交回调的 `userId` 产生。
- 把收集人设置为发起本次卡片任务的用户。
- 不直接手写 `card-request.json` 中的 JSON 字符串；始终通过构造器生成。
- 不使用 `--skip-env-check` 执行真实发送；该选项只供离线 Schema 测试。
- 只使用 `DDWS_CLIENT_ID` 和 `DDWS_CLIENT_SECRET`；任一变量缺失时立即报错并停止，不得执行 `dws api`。
- 发送前始终运行参数校验器，发送后始终检查每个投递结果。
- 已注册的回调路由是前置条件；本技能不自动覆盖回调注册。

## 变更历史

| 日期 | 版本 | 改动 | 原因 |
| --- | --- | --- | --- |
| 2026-08-26 | v3 | 认证环境变量迁移为 `DDWS_CLIENT_ID`、`DDWS_CLIENT_SECRET`，增加调用前硬性检查 | 避免 DWS 调用读取错误的应用凭证变量或在凭证缺失时继续执行 |
