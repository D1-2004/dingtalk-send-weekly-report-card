#!/usr/bin/env python3
"""Build a DWS createAndDeliver request from normalized weekly-card input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from validate_card_payload import load_json, schema_errors, validate_payload


CARD_TEMPLATE_ID = "3ff383e6-adfa-4117-a10f-6691f6eec086.schema"
CALLBACK_ROUTE_KEY = "customer_feedback_aitable_v1"
SATISFACTION_OPTIONS = [
    {"value": "满意", "text": "满意"},
    {"value": "不满意", "text": "不满意"},
]
REASON_OPTIONS = [
    {"value": value, "text": value}
    for value in (
        "响应不及时",
        "问题未解决",
        "交付质量不佳",
        "沟通体验不佳",
        "需求理解偏差",
        "其他",
    )
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a validated DingTalk weekly-feedback card request."
    )
    parser.add_argument("input", help="Normalized weekly-card input JSON")
    parser.add_argument(
        "--output",
        help="Write request JSON to this path; defaults to stdout",
    )
    return parser.parse_args()


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_feedback_form(data: dict[str, Any]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = [
        {
            "name": name,
            "hidden": True,
            "defaultValue": value,
        }
        for name, value in (
            ("submissionId", data["outTrackId"]),
            ("customer", data["customer"]),
            ("week", data["week"]),
            ("collector", data["collector"]),
            ("reportTime", data["reportTime"]),
        )
    ]
    for index, project in enumerate(data["projects"], start=1):
        name = project["name"]
        fields.extend(
            [
                {
                    "name": f"project_{index}",
                    "hidden": True,
                    "defaultValue": name,
                },
                {
                    "name": f"satisfaction_{index}",
                    "label": name,
                    "type": "CHECKBOX_GROUP",
                    "required": True,
                    "requiredMsg": f"请选择{name}的满意度",
                    "options": SATISFACTION_OPTIONS,
                },
                {
                    "name": f"reasons_{index}",
                    "label": "不满意原因（可多选）",
                    "type": "MULTI_SELECT",
                    "placeholder": "快速选择不满意原因",
                    "options": REASON_OPTIONS,
                },
                {
                    "name": f"feedback_{index}",
                    "label": "具体反馈",
                    "type": "TEXT_AREA",
                    "placeholder": f"请输入对{name}的具体反馈（可选）",
                },
            ]
        )
    return {"fields": fields}


def build_payload(data: dict[str, Any]) -> dict[str, Any]:
    feedback_form = build_feedback_form(data)
    return {
        "cardTemplateId": CARD_TEMPLATE_ID,
        "outTrackId": data["outTrackId"],
        "callbackType": "HTTP",
        "callbackRouteKey": CALLBACK_ROUTE_KEY,
        "openSpaceId": f'dtv1.card//IM_ROBOT.{data["recipientUserId"]}',
        "cardData": {
            "cardParamMap": {
                "title": data["title"],
                "iconUrl": data["iconUrl"],
                "reportUrl": data["reportUrl"],
                "summaryMarkdown": data["summaryMarkdown"],
                "weeklySummary": data["summaryMarkdown"],
                "feedbackGuide": data["feedbackGuide"],
                "reportPeriod": data["reportPeriod"],
                "customer": data["customer"],
                "week": data["week"],
                "collector": data["collector"],
                "reportTime": data["reportTime"],
                "submissionId": data["outTrackId"],
                "feedbackForm": compact_json(feedback_form),
                "submitButtonText": "提交",
                "formState": "normal",
            }
        },
        "imRobotOpenSpaceModel": {"supportForward": True},
        "imRobotOpenDeliverModel": {"spaceType": "IM_ROBOT"},
        "userIdType": 1,
    }


def main() -> int:
    args = parse_args()
    try:
        data = load_json(args.input)
        input_errors = schema_errors(
            data, "weekly-card-input.schema.json", "input"
        )
        if input_errors:
            print(
                json.dumps(
                    {"valid": False, "errors": input_errors}, ensure_ascii=False
                ),
                file=sys.stderr,
            )
            return 1
        payload = build_payload(data)
        payload_errors, _ = validate_payload(payload, check_env=False)
        if payload_errors:
            print(
                json.dumps(
                    {"valid": False, "errors": payload_errors}, ensure_ascii=False
                ),
                file=sys.stderr,
            )
            return 1
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(
            json.dumps(
                {"valid": False, "errors": [f"cannot build payload: {exc}"]},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
