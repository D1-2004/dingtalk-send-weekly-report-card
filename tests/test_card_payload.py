from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
TOOL = SKILL_DIR / "scripts" / "weekly_report_tool.py"
EXAMPLE = SKILL_DIR / "assets" / "card-request.example.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def decoded_project_rows(payload: dict) -> list[dict]:
    return json.loads(payload["cardData"]["cardParamMap"]["projectRows"])


def load_new_protocol_example() -> dict:
    return load_example()


def run_validator(payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "validate-card",
            "--skip-env-check",
            "-",
        ],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


def run_validator_with_env(
    payload: dict, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "validate-card", "-"],
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

    def test_rejects_secret_like_key_inside_project_rows(self) -> None:
        payload = load_new_protocol_example()
        rows = decoded_project_rows(payload)
        rows[0]["clientSecret"] = "dummy-test-value"
        payload["cardData"]["cardParamMap"]["projectRows"] = json.dumps(
            rows, ensure_ascii=False, separators=(",", ":")
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

    def test_rejects_unknown_project_row_property(self) -> None:
        payload = load_new_protocol_example()
        rows = decoded_project_rows(payload)
        rows[0]["unexpected"] = "value"
        payload["cardData"]["cardParamMap"]["projectRows"] = json.dumps(
            rows, ensure_ascii=False, separators=(",", ":")
        )

        result = run_validator(payload)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("decoded projectRows", result.stdout)


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
                [sys.executable, str(TOOL), "build-card", str(input_path)],
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
                [sys.executable, str(TOOL), "build-card", str(input_path)],
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
        self.assertNotIn("feedbackForm", card_params)
        self.assertEqual(card_params["formDisabled"], "false")
        rows = decoded_project_rows(payload)
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            rows[0],
            {
                "id": "p1",
                "name": "智能助理项目",
                "satisfaction": "",
                "satisfactionOptions": [
                    {"projectId": "p1", "value": "满意", "text": "满意", "checked": False},
                    {"projectId": "p1", "value": "不满意", "text": "不满意", "checked": False},
                ],
                "reasonOptions": [
                    {"value": "响应不及时", "text": {"zh_CN": "响应不及时"}},
                    {"value": "问题未解决", "text": {"zh_CN": "问题未解决"}},
                    {"value": "交付质量不佳", "text": {"zh_CN": "交付质量不佳"}},
                    {"value": "沟通体验不佳", "text": {"zh_CN": "沟通体验不佳"}},
                    {"value": "需求理解偏差", "text": {"zh_CN": "需求理解偏差"}},
                    {"value": "其他", "text": {"zh_CN": "其他"}},
                ],
                "selectedReasonIndexes": [],
                "feedback": "",
            },
        )
        self.assertEqual(rows[-1]["id"], "p5")
        self.assertEqual(rows[-1]["name"], "工单自动化")
        validation = run_validator(payload)
        self.assertEqual(validation.returncode, 0, validation.stdout)


class WeeklyReportToolTests(unittest.TestCase):
    @staticmethod
    def html_data() -> dict:
        return {
            "schemaVersion": 1,
            "iconUrl": "https://img.alicdn.com/example.png",
            "title": "维信诺项目回访",
            "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
            "summaryMarkdown": ["本周新增需求 **11** 项"],
            "projects": [
                {
                    "id": "p1",
                    "name": "智能助理项目",
                    "satisfaction": "",
                    "reasons": [],
                    "feedback": "",
                }
            ],
            "dissatisfactionOptions": ["响应不及时", "其他"],
            "reportPeriod": "2026年3月31日—2026年4月10日",
            "customer": "维信诺",
            "week": "2026-W15",
            "collector": "辰驷",
            "reportTime": "2026-08-26 10:00:00",
            "submissionId": "wf-1787690400000-a1b2",
        }

    def test_skill_docs_expose_only_the_unified_command_tool(self) -> None:
        documentation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                SKILL_DIR / "SKILL.md",
                SKILL_DIR / "references" / "input-output-contract.md",
                SKILL_DIR / "references" / "create-and-deliver-schema.md",
                SKILL_DIR / "references" / "html-generator-contract.md",
            ]
        )

        self.assertNotIn("scripts/build_card_payload.py", documentation)
        self.assertNotIn("scripts/validate_card_payload.py", documentation)
        self.assertIn("weekly_report_tool.py build-card", documentation)
        self.assertIn("weekly_report_tool.py validate-card", documentation)

    def test_gen_card_injects_submit_url_in_one_command(self) -> None:
        html_data = self.html_data()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "generated" / "feedback.html"
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "gen-card",
                    "--format",
                    "html",
                    "--data",
                    json.dumps(html_data, ensure_ascii=False),
                    "--submit-url",
                    "https://weekly-feedback.up.railway.app/submit",
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            generated = output.read_text(encoding="utf-8")
            self.assertIn(
                '"callbackUrl": "https://weekly-feedback.up.railway.app/submit"',
                generated,
            )

    def test_gen_card_rejects_missing_external_parameter(self) -> None:
        html_data = self.html_data()
        del html_data["iconUrl"]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "feedback.html"
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "gen-card",
                    "--format",
                    "html",
                    "--data",
                    json.dumps(html_data, ensure_ascii=False),
                    "--submit-url",
                    "https://weekly-feedback.up.railway.app/submit",
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("$.iconUrl", result.stderr)
            self.assertFalse(output.exists())



if __name__ == "__main__":
    unittest.main()
