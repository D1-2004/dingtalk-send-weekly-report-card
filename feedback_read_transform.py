import json


EXPECTED_KEYWORD = "weekly_report_mark_read"
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


def _string_list(payload, name):
    value = payload.get(name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(name + " must be an array of strings")
    return value


def _projects(payload):
    value = payload.get("projects")
    if not isinstance(value, list) or not value:
        raise ValueError("projects must be a non-empty array")
    projects = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("projects items must be objects")
        projects.append(
            {
                "id": _required_text(item, "id"),
                "name": _required_text(item, "name"),
            }
        )
    return projects


def _read_value(payload):
    value = payload.get("isRead")
    if value is True:
        return "是"
    if value is False:
        return "否"
    raise ValueError("isRead must be a boolean")


def main(params: dict):
    payload = _decode_payload(params.get("payload", params))
    if payload.get("schemaVersion") != EXPECTED_SCHEMA_VERSION:
        raise ValueError("schemaVersion must be 2")
    if payload.get("keyword") != EXPECTED_KEYWORD:
        raise ValueError("unsupported keyword")

    row = {
        "编号": _required_text(payload, "outTrackId"),
        "客户": _required_text(payload, "customer"),
        "项目": json.dumps(_projects(payload), ensure_ascii=False),
        "周次": _required_text(payload, "week"),
        "收集人": _required_text(payload, "collector"),
        "周报链接": _required_text(payload, "reportUrl"),
        "周报周期": _required_text(payload, "reportPeriod"),
        "周报时间": _required_text(payload, "reportTime"),
        "数据版本": EXPECTED_SCHEMA_VERSION,
        "本周进展": "\n".join(_string_list(payload, "summaryMarkdown")),
        "风险关注": "\n".join(_string_list(payload, "riskMarkdown")),
        "下周重点": "\n".join(_string_list(payload, "nextWeekMarkdown")),
        "不满意原因选项": json.dumps(
            _string_list(payload, "dissatisfactionOptions"), ensure_ascii=False
        ),
        "是否已读": _read_value(payload),
    }
    return {"row": row}
