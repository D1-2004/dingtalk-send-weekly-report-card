import json
import time


EXPECTED_ACTION = "view_weekly_feedback"
EXPECTED_SCHEMA_VERSION = 2


def _decode_payload(value):
    current = value
    for _ in range(3):
        if not isinstance(current, str):
            break
        try:
            current = json.loads(current)
        except (TypeError, ValueError):
            break
    if not isinstance(current, dict):
        raise ValueError("payload must be a JSON object")
    return current


def _text(payload, name):
    value = payload.get(name)
    return value.strip() if isinstance(value, str) else ""


def main(params: dict):
    payload = _decode_payload(params.get("payload", params))
    if payload.get("schemaVersion") != EXPECTED_SCHEMA_VERSION:
        raise ValueError("schemaVersion must be 2")
    if payload.get("action") != EXPECTED_ACTION:
        raise ValueError("unsupported action")

    submission_id = _text(payload, "submissionId")
    if not submission_id:
        raise ValueError("submissionId must be a non-empty string")
    view_env = _text(payload, "viewEnv")
    if view_env not in ("dingtalk", "anonymous"):
        view_env = "anonymous"

    # 键名 = 「周报回访·查看日志」表列名，逐列对应；查看时间为 createdTime 自动记录，不映射
    row = {
        "查看编号": "VIEW-%s-%d" % (submission_id, int(time.time() * 1000)),
        "回访记录ID": submission_id,
        "客户": _text(payload, "customer"),
        "周次": _text(payload, "week"),
        "查看人": _text(payload, "respondentNickname"),
        "查看人ID": _text(payload, "respondentId"),
        "查看环境": view_env,
    }
    return {"rows": [row], "rowCount": 1}
