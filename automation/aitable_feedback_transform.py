import json


EXPECTED_ACTION = "submit_weekly_feedback"
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


def _required_text(payload, name):
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " must be a non-empty string")
    return value.strip()


def _string_list(payload, name, required=False):
    value = payload.get(name)
    if value is None and not required:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(name + " must be an array of non-empty strings")
    if required and not value:
        raise ValueError(name + " must not be empty")
    return [item.strip() for item in value]


def _feedback_text(reasons, feedback):
    parts = []
    if reasons:
        parts.append("不满意原因：" + "、".join(reasons))
    if feedback:
        parts.append("具体反馈：" + feedback)
    return "；".join(parts)


def main(params: dict):
    payload = _decode_payload(params.get("payload", params))
    if payload.get("schemaVersion") != EXPECTED_SCHEMA_VERSION:
        raise ValueError("schemaVersion must be 2")
    if payload.get("action") != EXPECTED_ACTION:
        raise ValueError("unsupported action")

    satisfaction = _required_text(payload, "satisfaction")
    if satisfaction not in ("满意", "不满意"):
        raise ValueError("satisfaction must be 满意 or 不满意")

    projects = _string_list(payload, "projects", required=True)
    reasons = _string_list(payload, "dissatisfactionReasons")
    if satisfaction == "满意":
        reasons = []

    feedback = payload.get("feedback", "")
    if not isinstance(feedback, str):
        raise ValueError("feedback must be a string")
    feedback = feedback.strip()

    row = {
        "编号": _required_text(payload, "submissionId"),
        "客户": _required_text(payload, "customer"),
        "项目": "、".join(projects),
        "周次": _required_text(payload, "week"),
        "满意度": satisfaction,
        "反馈": _feedback_text(reasons, feedback),
        "反馈人": _required_text(payload, "feedbackUserId"),
        "收集人": _required_text(payload, "collector"),
        "反馈时间": _required_text(payload, "reportTime"),
    }
    return {"rows": [row], "rowCount": 1}
