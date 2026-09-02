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


def _opt_text(payload, name):
    value = payload.get(name)
    return value.strip() if isinstance(value, str) else ""


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


def _project_names(payload):
    value = payload.get("projects")
    if not isinstance(value, list) or not value:
        raise ValueError("projects must be a non-empty array")
    names = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("projects items must be objects")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("projects[].name must be a non-empty string")
        names.append(name.strip())
    return names


def main(params: dict):
    payload = _decode_payload(params.get("payload", params))
    if payload.get("schemaVersion") != EXPECTED_SCHEMA_VERSION:
        raise ValueError("schemaVersion must be 2")
    if payload.get("action") != EXPECTED_ACTION:
        raise ValueError("unsupported action")

    satisfaction = _required_text(payload, "satisfaction")
    if satisfaction not in ("满意", "不满意"):
        raise ValueError("satisfaction must be 满意 or 不满意")

    reasons = _string_list(payload, "dissatisfactionReasons")
    if satisfaction == "满意":
        reasons = []
    elif not reasons:
        raise ValueError("dissatisfactionReasons must not be empty when 不满意")
    feedback = _opt_text(payload, "feedback")

    # 键名 = 我们表「周报回访·客户反馈」的列名，逐列对应回传字段
    row = {
        "客户名称": _required_text(payload, "customer"),
        "项目名称": "、".join(_project_names(payload)),
        "交付PM": _required_text(payload, "collector"),
        "客户填写人": _required_text(payload, "respondentNickname"),
        "满意度": satisfaction,
        "不满意原因": reasons,
        "其他备注": feedback,
        "周报链接": _opt_text(payload, "reportUrl"),
        "回访周期": _opt_text(payload, "reportPeriod"),
        "周次": _required_text(payload, "week"),
        "提交人ID": _required_text(payload, "respondentId"),
        "回访记录ID": _required_text(payload, "submissionId"),
    }
    return {"rows": [row], "rowCount": 1}
