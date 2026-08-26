# DWS 创建并投递卡片协议

## 接口

```text
POST /v1.0/card/instances/createAndDeliver
```

调用前确保应用已发布、互动卡片模板已发布、机器人具备主动消息能力，并且 `callbackRouteKey` 已在卡片平台绑定到有效的 HTTP 回调。

## 请求参数

| 参数 | 必填 | 约束与生成方式 |
| --- | --- | --- |
| `cardTemplateId` | 是 | 当前模板为 `3ff383e6-adfa-4117-a10f-6691f6eec086.schema` |
| `outTrackId` | 是 | 每次投递新生成；模板、数据或接收人变化时不得复用 |
| `callbackType` | 是 | 本技能固定为大写 `HTTP` |
| `callbackRouteKey` | 是 | 当前路由为 `customer_feedback_aitable_v1` |
| `openSpaceId` | 是 | 单聊机器人场域：`dtv1.card//IM_ROBOT.<userId>` |
| `cardData.cardParamMap` | 是 | 模板变量映射；所有变量值均为字符串；key 不超过 100 UTF-8 字节 |
| `imRobotOpenSpaceModel.supportForward` | 是 | 固定为 `true`，允许转发 |
| `imRobotOpenDeliverModel.spaceType` | 是 | 固定为 `IM_ROBOT` |
| `imRobotOpenDeliverModel.robotCode` | 否 | 需要显式指定机器人时填写应用机器人 code |
| `userIdType` | 是 | 本技能固定为 `1`，表示 `openSpaceId` 中使用 `userId` |

## 分层 Schema

本技能不直接把模型生成的字符串交给 DWS：

| 层次 | Schema | 校验对象 |
| --- | --- | --- |
| 业务输入 | `../assets/weekly-card-input.schema.json` | 周报、接收人和项目组成的未序列化对象 |
| DWS 传输 | `../assets/create-and-deliver.schema.json` | `createAndDeliver` 最终请求 |
| 表单变量 | `../assets/feedback-form.schema.json` | `feedbackForm` 反序列化后的原生表单对象 |

所有 Schema 使用 JSON Schema Draft 2020-12，由 `jsonschema>=4.18,<5` 执行。依赖版本见 `../scripts/requirements.txt`。此外，Python 校验器只负责 JSON Schema 难以表达的跨字段关系、递归敏感字段扫描和参数 key 的 UTF-8 字节长度。

## 调用方式

先把业务对象确定性转换成传输请求，再从用户终端配置加载凭证，并把凭证作为命令行参数显式传给 DWS：

```bash
python3 scripts/build_card_payload.py weekly-card-input.json \
  --output card-request.json
source ~/.zshrc
if [[ -z "${DDWS_CLIENT_ID:-}" || -z "${DDWS_CLIENT_SECRET:-}" ]]; then
  printf '错误：缺少 DDWS_CLIENT_ID 或 DDWS_CLIENT_SECRET，停止发送。\n' >&2
  exit 1
fi
python3 scripts/validate_card_payload.py card-request.json
dws api POST /v1.0/card/instances/createAndDeliver \
  --client-id "$DDWS_CLIENT_ID" \
  --client-secret "$DDWS_CLIENT_SECRET" \
  --data - \
  --jq '{success,result}' \
  < card-request.json
```

只允许使用 `DDWS_CLIENT_ID` 和 `DDWS_CLIENT_SECRET` 作为显式参数值来源。任一变量缺失或为空时立即报错并停止，禁止调用 DWS API。旧变量 `DWS_CLIENT_ID`、`DWS_CLIENT_SECRET` 不视为有效凭证来源。

禁止省略 `--client-id` 和 `--client-secret` 后依赖 DWS 的隐式环境变量注入。禁止把凭证放入 `card-request.json`。

禁止直接手写 `feedbackForm` 字符串。真实发送不得使用校验器的 `--skip-env-check`。

## 响应判定

典型成功响应中应包含：

```json
{
  "success": true,
  "result": {
    "outTrackId": "weekly-feedback-2026w15-001",
    "deliverResults": [
      {
        "success": true
      }
    ]
  }
}
```

只有以下条件全部成立，Agent 才能回复“卡片已发送”：

1. 顶层 `success` 为 `true`。
2. 返回的 `outTrackId` 与请求一致。
3. `deliverResults` 至少有一项。
4. 所有 `deliverResults[].success` 均为 `true`。

任何一项失败时，保留 `outTrackId` 和非敏感错误信息用于排查，不要向用户宣称投递成功。

## 变更历史

| 日期 | 版本 | 改动 | 原因 |
| --- | --- | --- | --- |
| 2026-08-27 | v6 | 传输协议改为动态原生 `feedbackForm`，移除错误的单值 1024 字节自限，并把共享提交状态收口到回调 `cardData` | 支持 3–5 个及更多项目的独立表单字段，同时确保一次提交后整张卡片不可再次提交 |
| 2026-08-26 | v4 | 传输协议由固定 `feedbackForm` 改为动态 `projectRows`，增加项目行内部 Schema | 支持任意实际项目数并防止字符串化数组绕过结构校验 |
| 2026-08-26 | v5 | 增加 `formDisabled` 卡片参数 | 提交成功后由共享 cardData 控制所有项目行交互组件禁用 |
| 2026-08-26 | v3 | 认证变量改为 `DDWS_CLIENT_ID`、`DDWS_CLIENT_SECRET`，增加 DWS 调用前的阻断检查 | 确保凭证来源明确，并避免缺少应用凭证时继续发送 |
| 2026-08-26 | v2 | 增加业务、传输和反序列化变量的分层 Schema，收紧未知字段并加入 UTF-8 字节限制 | 修复字符串化嵌套结构可绕过 Schema 和敏感字段扫描的问题 |
| 2026-08-26 | v1 | 建立 createAndDeliver 请求、显式认证和成功判定契约 | 防止参数遗漏、身份误用和只检查顶层状态造成的误报 |
