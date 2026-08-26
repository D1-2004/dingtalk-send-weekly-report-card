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


def decoded_feedback_form(payload: dict) -> dict:
    return json.loads(payload["cardData"]["cardParamMap"]["feedbackForm"])


def load_new_protocol_example() -> dict:
    return load_example()


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
        payload = load_new_protocol_example()
        form = decoded_feedback_form(payload)
        form["fields"][0]["clientSecret"] = "dummy-test-value"
        payload["cardData"]["cardParamMap"]["feedbackForm"] = json.dumps(
            form, ensure_ascii=False, separators=(",", ":")
        )

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("secret-like field", result.stdout)
        self.assertNotIn("dummy-test-value", result.stdout)

    def test_rejects_unknown_outer_property(self) -> None:
        payload = load_new_protocol_example()
        payload["unexpected"] = "value"

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("unexpected", result.stdout)

    def test_rejects_unknown_feedback_form_field_property(self) -> None:
        payload = load_new_protocol_example()
        form = decoded_feedback_form(payload)
        form["fields"][0]["unexpected"] = "value"
        payload["cardData"]["cardParamMap"]["feedbackForm"] = json.dumps(
            form, ensure_ascii=False, separators=(",", ":")
        )

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("decoded feedbackForm", result.stdout)


class CardPayloadBuilderTests(unittest.TestCase):
    def test_rejects_semantic_input_without_required_icon(self) -> None:
        semantic_input = {
            "outTrackId": "wf-1787690400000-a1b2",
            "title": "维信诺项目回访",
            "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
            "summaryMarkdown": "- 本周新增需求 11 项",
            "feedbackGuide": "请按项目填写反馈。",
            "reportPeriod": "2026年3月31日—2026年4月10日",
            "customer": "维信诺",
            "week": "2026-W15",
            "collector": "辰驷",
            "reportTime": "2026-08-26 10:00:00",
            "recipientUserId": "323179",
            "projects": [{"name": "智能助理项目"}],
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

        self.assertEqual(result.returncode, 1)
        self.assertIn("iconUrl", result.stderr)

    def test_builds_valid_payload_from_semantic_input(self) -> None:
        semantic_input = {
            "outTrackId": "wf-1787690400000-a1b2",
            "title": "维信诺项目回访",
            "iconUrl": "https://img.alicdn.com/example.png",
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
                {"name": "客户服务平台"},
                {"name": "知识库升级"},
                {"name": "工单自动化"},
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
        card_params = payload["cardData"]["cardParamMap"]
        self.assertEqual(card_params["iconUrl"], semantic_input["iconUrl"])
        self.assertNotIn("icon", card_params)
        self.assertNotIn("projectRows", card_params)
        self.assertNotIn("satisfactionOptions", card_params)
        self.assertNotIn("formDisabled", card_params)
        form = decoded_feedback_form(payload)
        fields = form["fields"]
        self.assertEqual(len(fields), 25)
        self.assertEqual(
            fields[5],
            {
                "name": "project_1",
                "hidden": True,
                "defaultValue": "智能助理项目",
            },
        )
        self.assertEqual(fields[6]["name"], "satisfaction_1")
        self.assertEqual(fields[6]["label"], "智能助理项目")
        self.assertEqual(fields[6]["type"], "CHECKBOX_GROUP")
        self.assertEqual(
            fields[6]["options"],
            [
                {"value": "满意", "text": "满意"},
                {"value": "不满意", "text": "不满意"},
            ],
        )
        self.assertEqual(fields[7]["name"], "reasons_1")
        self.assertEqual(fields[7]["type"], "MULTI_SELECT")
        self.assertEqual(fields[8]["name"], "feedback_1")
        self.assertEqual(fields[-4]["defaultValue"], "工单自动化")
        self.assertEqual(fields[-3]["name"], "satisfaction_5")
        self.assertEqual(fields[-2]["name"], "reasons_5")
        self.assertEqual(fields[-1]["name"], "feedback_5")
        self.assertGreater(len(card_params["feedbackForm"].encode("utf-8")), 1024)
        validation = run_validator(payload)
        self.assertEqual(validation.returncode, 0, validation.stdout)


if __name__ == "__main__":
    unittest.main()
