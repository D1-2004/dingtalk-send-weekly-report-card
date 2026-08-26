from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL_DIR / "scripts" / "validate_card_payload.py"
BUILDER = SKILL_DIR / "scripts" / "build_card_payload.py"
EXAMPLE = SKILL_DIR / "assets" / "card-request.example.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def decoded_fields(payload: dict) -> list[dict]:
    form = json.loads(payload["cardData"]["cardParamMap"]["feedbackForm"])
    if isinstance(form, list):
        return form
    return form["fields"]


def encode_fields(payload: dict, fields: list[dict]) -> None:
    original = json.loads(payload["cardData"]["cardParamMap"]["feedbackForm"])
    encoded_form = fields if isinstance(original, list) else {"fields": fields}
    payload["cardData"]["cardParamMap"]["feedbackForm"] = json.dumps(
        encoded_form, ensure_ascii=False, separators=(",", ":")
    )


def run_validator(payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--skip-env-check", "-"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


def run_validator_with_env(
    payload: dict, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "-"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


class CardPayloadValidationTests(unittest.TestCase):
    def test_rejects_legacy_dws_credentials_when_ddws_credentials_are_missing(
        self,
    ) -> None:
        environment = os.environ.copy()
        environment.pop("DDWS_CLIENT_ID", None)
        environment.pop("DDWS_CLIENT_SECRET", None)
        environment["DWS_CLIENT_ID"] = "legacy-client-id"
        environment["DWS_CLIENT_SECRET"] = "legacy-client-secret"

        result = run_validator_with_env(load_example(), environment)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("missing environment variable: DDWS_CLIENT_ID", result.stdout)
        self.assertIn(
            "missing environment variable: DDWS_CLIENT_SECRET", result.stdout
        )

    def test_accepts_ddws_credentials_without_legacy_dws_credentials(self) -> None:
        environment = os.environ.copy()
        environment.pop("DWS_CLIENT_ID", None)
        environment.pop("DWS_CLIENT_SECRET", None)
        environment["DDWS_CLIENT_ID"] = "ddws-client-id"
        environment["DDWS_CLIENT_SECRET"] = "ddws-client-secret"

        result = run_validator_with_env(load_example(), environment)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('"valid": true', result.stdout)

    def test_rejects_secret_like_key_inside_feedback_form(self) -> None:
        payload = load_example()
        fields = decoded_fields(payload)
        fields.append(
            {
                "name": "extra",
                "hidden": True,
                "defaultValue": "x",
                "clientSecret": "dummy-test-value",
            }
        )
        encode_fields(payload, fields)

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("secret-like field", result.stdout)
        self.assertNotIn("dummy-test-value", result.stdout)

    def test_rejects_card_param_value_over_1kb(self) -> None:
        payload = load_example()
        payload["cardData"]["cardParamMap"]["summaryMarkdown"] = "x" * 1025

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("1024 UTF-8 bytes", result.stdout)

    def test_rejects_unknown_outer_property(self) -> None:
        payload = load_example()
        payload["unexpected"] = "value"

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("unexpected", result.stdout)

    def test_rejects_orphan_satisfaction_field(self) -> None:
        payload = load_example()
        fields = decoded_fields(payload)
        fields.append(
            {
                "name": "satisfaction_99",
                "type": "CHECKBOX_GROUP",
                "required": True,
                "options": [
                    {"value": "满意", "text": "满意"},
                    {"value": "不满意", "text": "不满意"},
                ],
            }
        )
        encode_fields(payload, fields)

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("project/satisfaction/feedback indexes", result.stdout)

    def test_rejects_invalid_report_time_inside_feedback_form(self) -> None:
        payload = load_example()
        fields = decoded_fields(payload)
        report_time = next(field for field in fields if field["name"] == "reportTime")
        report_time["defaultValue"] = "2026-99-99 99:99:99"
        encode_fields(payload, fields)

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("reportTime", result.stdout)


class CardPayloadBuilderTests(unittest.TestCase):
    def test_builds_valid_payload_from_semantic_input(self) -> None:
        semantic_input = {
            "outTrackId": "wf-1787690400000-a1b2",
            "title": "维信诺项目回访",
            "icon": "https://img.alicdn.com/example.png",
            "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
            "summaryMarkdown": "- 本周新增需求 11 项\n- 当前 6 个工单处理中",
            "feedbackGuide": "请按项目填写反馈。",
            "reportPeriod": "2026年3月31日—2026年4月10日",
            "customer": "维信诺",
            "week": "2026-W15",
            "collector": "辰驷",
            "reportTime": "2026-08-26 10:00:00",
            "recipientUserId": "323179",
            "projects": [
                {"name": "智能助理项目"},
                {"name": "数据看板项目"},
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "weekly-card-input.json"
            input_path.write_text(
                json.dumps(semantic_input, ensure_ascii=False), encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, str(BUILDER), str(input_path)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["outTrackId"], semantic_input["outTrackId"])
        self.assertEqual(
            payload["openSpaceId"], "dtv1.card//IM_ROBOT.323179"
        )
        form = json.loads(payload["cardData"]["cardParamMap"]["feedbackForm"])
        self.assertIsInstance(form, dict)
        self.assertEqual(len(form["fields"]), 11)
        self.assertLessEqual(
            len(
                payload["cardData"]["cardParamMap"]["feedbackForm"].encode(
                    "utf-8"
                )
            ),
            1024,
        )
        validation = run_validator(payload)
        self.assertEqual(validation.returncode, 0, validation.stdout)


if __name__ == "__main__":
    unittest.main()
