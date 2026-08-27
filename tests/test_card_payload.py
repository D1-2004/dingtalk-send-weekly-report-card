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
SUBMIT_URL_ENV = "WEEKLY_FEEDBACK_SUBMIT_URL"


def html_data() -> dict:
    return {
        "schemaVersion": 1,
        "iconUrl": "https://img.alicdn.com/example.png",
        "title": "维信诺项目回访",
        "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
        "reportLinkText": "查看完整周报",
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
        "callbackHeaders": {},
        "formDisabled": False,
    }


def ding_card_data() -> dict:
    return {
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
            {"name": "知识库升级"},
        ],
    }


def command_environment(
    *,
    submit_url: str | None = "https://weekly-feedback.example.com/submit",
    ddws: bool = False,
    legacy_dws: bool = False,
) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        SUBMIT_URL_ENV,
        "DDWS_CLIENT_ID",
        "DDWS_CLIENT_SECRET",
        "DWS_CLIENT_ID",
        "DWS_CLIENT_SECRET",
    ):
        environment.pop(name, None)
    if submit_url is not None:
        environment[SUBMIT_URL_ENV] = submit_url
    if ddws:
        environment["DDWS_CLIENT_ID"] = "ddws-client-id"
        environment["DDWS_CLIENT_SECRET"] = "ddws-client-secret"
    if legacy_dws:
        environment["DWS_CLIENT_ID"] = "legacy-client-id"
        environment["DWS_CLIENT_SECRET"] = "legacy-client-secret"
    return environment


def run_gen_card(
    card_type: str,
    data: dict,
    output: Path,
    *,
    environment: dict[str, str],
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "gen-card",
            "--type",
            card_type,
            "--data",
            json.dumps(data, ensure_ascii=False),
            "--output",
            str(output),
            *(extra_args or []),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def extract_html_data(output: Path) -> dict:
    html = output.read_text(encoding="utf-8")
    start = html.index(
        '<script type="application/json" id="weeklyReportCardData">'
    )
    start = html.index(">", start) + 1
    end = html.index("</script>", start)
    return json.loads(html[start:end])


class UnifiedGenerationCommandTests(unittest.TestCase):
    def test_command_surface_exposes_one_generation_command(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOL), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("{gen-card}", result.stdout)
        self.assertNotIn("build-card", result.stdout)
        self.assertNotIn("validate-card", result.stdout)

    def test_skill_docs_use_gen_card_type_dispatch_only(self) -> None:
        documentation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                SKILL_DIR / "SKILL.md",
                SKILL_DIR / "references" / "input-output-contract.md",
                SKILL_DIR / "references" / "create-and-deliver-schema.md",
                SKILL_DIR / "references" / "html-generator-contract.md",
            ]
        )

        self.assertNotIn("weekly_report_tool.py build-card", documentation)
        self.assertNotIn("weekly_report_tool.py validate-card", documentation)
        self.assertNotIn("--format", documentation)
        self.assertNotIn("--submit-url", documentation)
        self.assertIn("gen-card --type html", documentation)
        self.assertIn("gen-card --type card", documentation)
        self.assertIn(SUBMIT_URL_ENV, documentation)

    def test_skill_delegates_environment_validation_to_the_command(self) -> None:
        documentation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                SKILL_DIR / "SKILL.md",
                SKILL_DIR / "references" / "input-output-contract.md",
                SKILL_DIR / "references" / "create-and-deliver-schema.md",
                SKILL_DIR / "references" / "html-generator-contract.md",
            ]
        )

        self.assertNotIn("source ~/.zshrc", documentation)
        self.assertNotIn("if [[", documentation)
        self.assertNotIn("printf '错误：缺少", documentation)
        self.assertIn("Agent 不得自行检查环境变量", documentation)
        self.assertIn("环境变量缺失时由命令报错并停止", documentation)

    def test_html_reads_submit_url_from_environment_and_returns_result(self) -> None:
        submit_url = "https://weekly-feedback.example.com/html-submit"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "generated" / "feedback.html"
            result = run_gen_card(
                "html",
                html_data(),
                output,
                environment=command_environment(submit_url=submit_url),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            command_result = json.loads(result.stdout)
            generated_data = extract_html_data(output)

        self.assertEqual(command_result["success"], True)
        self.assertEqual(command_result["type"], "html")
        self.assertEqual(command_result["output"], str(output.resolve()))
        self.assertEqual(command_result["submitUrl"], submit_url)
        self.assertEqual(generated_data["callbackUrl"], submit_url)
        self.assertNotIn("submitButtonText", generated_data)
        self.assertNotIn("submittedButtonText", generated_data)

    def test_html_rejects_missing_submit_url_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "feedback.html"
            result = run_gen_card(
                "html",
                html_data(),
                output,
                environment=command_environment(submit_url=None),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn(SUBMIT_URL_ENV, result.stderr)
            self.assertFalse(output.exists())

    def test_html_rejects_invalid_submit_url_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "feedback.html"
            result = run_gen_card(
                "html",
                html_data(),
                output,
                environment=command_environment(submit_url="not-a-url"),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn(SUBMIT_URL_ENV, result.stderr)
            self.assertFalse(output.exists())

    def test_html_rejects_custom_submit_button_text(self) -> None:
        data = html_data()
        data["submitButtonText"] = "提交反馈"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "feedback.html"
            result = run_gen_card(
                "html",
                data,
                output,
                environment=command_environment(),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("submitButtonText", result.stderr)
            self.assertFalse(output.exists())

    def test_html_template_uses_fixed_submit_copy(self) -> None:
        template = (SKILL_DIR / "assets" / "weekly-feedback-template.html").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("params.submitButtonText", template)
        self.assertNotIn("params.submittedButtonText", template)
        self.assertIn('elements.submitButton.textContent = "提交"', template)
        self.assertIn('elements.submitButton.textContent = "已提交"', template)

    def test_validation_happens_before_html_generation(self) -> None:
        data = html_data()
        del data["iconUrl"]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "feedback.html"
            result = run_gen_card(
                "html",
                data,
                output,
                environment=command_environment(),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("$.iconUrl", result.stderr)
            self.assertFalse(output.exists())

    def test_card_requires_ddws_credentials_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "card-request.json"
            result = run_gen_card(
                "card",
                ding_card_data(),
                output,
                environment=command_environment(legacy_dws=True),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("DDWS_CLIENT_ID", result.stderr)
            self.assertIn("DDWS_CLIENT_SECRET", result.stderr)
            self.assertFalse(output.exists())

    def test_card_generates_valid_payload_and_returns_callback_warning(self) -> None:
        submit_url = "https://weekly-feedback.example.com/intended-card-submit"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "card-request.json"
            result = run_gen_card(
                "card",
                ding_card_data(),
                output,
                environment=command_environment(submit_url=submit_url, ddws=True),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            command_result = json.loads(result.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))

        expected_warning = (
            f"当前命令指定的数据提交地址是{submit_url}，"
            "需核对ding-card实际提交地址"
        )
        self.assertEqual(command_result["success"], True)
        self.assertEqual(command_result["type"], "card")
        self.assertEqual(command_result["output"], str(output.resolve()))
        self.assertEqual(command_result["submitUrl"], submit_url)
        self.assertEqual(command_result["warning"], expected_warning)
        self.assertEqual(command_result["projectCount"], 3)
        self.assertEqual(payload["outTrackId"], "wf-1787690400000-a1b2")
        self.assertEqual(
            payload["cardData"]["cardParamMap"]["submitButtonText"], "提交"
        )
        self.assertNotIn(submit_url, json.dumps(payload, ensure_ascii=False))

    def test_card_rejects_html_only_template_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "card-request.json"
            result = run_gen_card(
                "card",
                ding_card_data(),
                output,
                environment=command_environment(ddws=True),
                extra_args=["--template", "custom.html"],
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--template", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
