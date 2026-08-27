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
CARD_EXAMPLE = SKILL_DIR / "assets" / "card-request.example.json"
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


def card_payload() -> dict:
    return json.loads(CARD_EXAMPLE.read_text(encoding="utf-8"))


def semantic_card_data() -> dict:
    return {
        "outTrackId": "wf-1787690400000-a1b2",
        "title": "维信诺项目回访",
        "iconUrl": "https://img.alicdn.com/example.png",
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


def make_fake_dws(directory: Path) -> Path:
    executable = directory / "dws"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

record = {"argv": sys.argv[1:], "stdin": sys.stdin.read()}
Path(os.environ["FAKE_DWS_RECORD"]).write_text(
    json.dumps(record, ensure_ascii=False), encoding="utf-8"
)
sys.stdout.write(os.environ.get("FAKE_DWS_STDOUT", ""))
sys.stderr.write(os.environ.get("FAKE_DWS_STDERR", ""))
raise SystemExit(int(os.environ.get("FAKE_DWS_EXIT", "0")))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def success_response(payload: dict) -> dict:
    return {
        "success": True,
        "result": {
            "outTrackId": payload["outTrackId"],
            "deliverResults": [
                {"success": True, "carrierId": "carrier-test-001"}
            ],
        },
    }


def command_environment(
    *,
    submit_url: str | None = None,
    ddws: bool = False,
    legacy_dws: bool = False,
    fake_dws_dir: Path | None = None,
    fake_response: dict | str | None = None,
    fake_exit: int = 0,
    fake_stderr: str = "",
    record_path: Path | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        SUBMIT_URL_ENV,
        "DDWS_CLIENT_ID",
        "DDWS_CLIENT_SECRET",
        "DWS_CLIENT_ID",
        "DWS_CLIENT_SECRET",
        "FAKE_DWS_RECORD",
        "FAKE_DWS_STDOUT",
        "FAKE_DWS_STDERR",
        "FAKE_DWS_EXIT",
    ):
        environment.pop(name, None)
    if submit_url is not None:
        environment[SUBMIT_URL_ENV] = submit_url
    if ddws:
        environment["DDWS_CLIENT_ID"] = "ddws-client-id"
        environment["DDWS_CLIENT_SECRET"] = "ddws-client-secret"
    if legacy_dws:
        environment["DWS_CLIENT_ID"] = "legacy-dws-client-id"
        environment["DWS_CLIENT_SECRET"] = "legacy-dws-client-secret"
    if fake_dws_dir is not None:
        environment["PATH"] = f"{fake_dws_dir}{os.pathsep}{environment['PATH']}"
    if record_path is not None:
        environment["FAKE_DWS_RECORD"] = str(record_path)
    if fake_response is not None:
        environment["FAKE_DWS_STDOUT"] = (
            fake_response
            if isinstance(fake_response, str)
            else json.dumps(fake_response, ensure_ascii=False)
        )
    environment["FAKE_DWS_EXIT"] = str(fake_exit)
    environment["FAKE_DWS_STDERR"] = fake_stderr
    return environment


def run_gen_card(
    card_type: str,
    data: dict,
    *,
    environment: dict[str, str],
    output: Path | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(TOOL),
        "gen-card",
        "--type",
        card_type,
        "--data",
        json.dumps(data, ensure_ascii=False),
    ]
    if output is not None:
        command.extend(["--output", str(output)])
    command.extend(extra_args or [])
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def extract_html_data(output: Path) -> dict:
    html = output.read_text(encoding="utf-8")
    marker = '<script type="application/json" id="weeklyReportCardData">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    return json.loads(html[start:end])


class SimplifiedSkillTests(unittest.TestCase):
    def test_repository_uses_one_skill_document_without_history(self) -> None:
        self.assertFalse((SKILL_DIR / "references").exists())
        self.assertFalse((SKILL_DIR / "assets" / "weekly-card-input.schema.json").exists())
        self.assertFalse((SKILL_DIR / "assets" / "weekly-card-input.example.json").exists())

        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        template = (SKILL_DIR / "assets" / "weekly-feedback-template.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("变更历史", skill)
        self.assertNotIn("变更历史", template)
        self.assertNotIn("dws api", skill)
        self.assertNotIn("dws doc", skill)
        self.assertIn("## 功能", skill)
        self.assertIn("## 参数规格与来源", skill)
        self.assertIn("## 命令使用", skill)

    def test_agent_prompt_only_calls_gen_card(self) -> None:
        prompt = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("gen-card", prompt)
        self.assertNotIn("按 DWS 流程", prompt)
        self.assertNotIn("dws api", prompt)


class HtmlGenerationTests(unittest.TestCase):
    def test_html_injects_submit_url_and_returns_output(self) -> None:
        submit_url = "https://weekly-feedback.example.com/html-submit"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "generated" / "feedback.html"
            result = run_gen_card(
                "html",
                html_data(),
                output=output,
                environment=command_environment(submit_url=submit_url),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            command_result = json.loads(result.stdout)
            generated_data = extract_html_data(output)

        self.assertEqual(command_result["success"], True)
        self.assertEqual(command_result["type"], "html")
        self.assertEqual(command_result["output"], str(output.resolve()))
        self.assertEqual(generated_data["callbackUrl"], submit_url)

    def test_html_requires_output_and_submit_url(self) -> None:
        result = run_gen_card(
            "html",
            html_data(),
            environment=command_environment(),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--output", result.stderr)


class DingCardDeliveryTests(unittest.TestCase):
    def run_with_fake_dws(
        self,
        payload: dict,
        *,
        ddws: bool = True,
        legacy_dws: bool = False,
        response: dict | str | None = None,
        exit_code: int = 0,
        stderr: str = "",
        extra_args: list[str] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        directory = Path(temp_dir.name)
        make_fake_dws(directory)
        record = directory / "record.json"
        result = run_gen_card(
            "card",
            payload,
            environment=command_environment(
                ddws=ddws,
                legacy_dws=legacy_dws,
                fake_dws_dir=directory,
                fake_response=response,
                fake_exit=exit_code,
                fake_stderr=stderr,
                record_path=record,
            ),
            extra_args=extra_args,
        )
        return result, record

    def test_card_requires_ddws_credentials_and_ignores_legacy_names(self) -> None:
        payload = card_payload()
        result, record = self.run_with_fake_dws(
            payload,
            ddws=False,
            legacy_dws=True,
            response=success_response(payload),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("DDWS_CLIENT_ID", result.stderr)
        self.assertIn("DDWS_CLIENT_SECRET", result.stderr)
        self.assertFalse(record.exists())

    def test_card_rejects_semantic_input_instead_of_building_a_payload(self) -> None:
        result, record = self.run_with_fake_dws(
            semantic_card_data(),
            response={"success": True},
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("card data failed validation", result.stderr)
        self.assertFalse(record.exists())

    def test_card_deep_validates_project_rows_before_invoking_dws(self) -> None:
        payload = card_payload()
        rows = json.loads(payload["cardData"]["cardParamMap"]["projectRows"])
        rows[0]["unexpected"] = "value"
        payload["cardData"]["cardParamMap"]["projectRows"] = json.dumps(
            rows, ensure_ascii=False
        )

        result, record = self.run_with_fake_dws(
            payload,
            response={"success": True},
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("decoded projectRows", result.stderr)
        self.assertFalse(record.exists())

    def test_card_invokes_dws_with_validated_payload_and_returns_delivery(self) -> None:
        payload = card_payload()
        response = success_response(payload)
        result, record_path = self.run_with_fake_dws(payload, response=response)

        self.assertEqual(result.returncode, 0, result.stderr)
        command_result = json.loads(result.stdout)
        record = json.loads(record_path.read_text(encoding="utf-8"))

        self.assertEqual(
            record["argv"],
            [
                "api",
                "POST",
                "/v1.0/card/instances/createAndDeliver",
                "--client-id",
                "ddws-client-id",
                "--client-secret",
                "ddws-client-secret",
                "--yes",
                "--data",
                "-",
            ],
        )
        self.assertEqual(json.loads(record["stdin"]), payload)
        self.assertEqual(command_result["success"], True)
        self.assertEqual(command_result["type"], "card")
        self.assertEqual(command_result["outTrackId"], payload["outTrackId"])
        self.assertEqual(command_result["projectCount"], 3)
        self.assertEqual(command_result["dwsResponse"], response)

    def test_card_rejects_output_argument(self) -> None:
        payload = card_payload()
        result, record = self.run_with_fake_dws(
            payload,
            response=success_response(payload),
            extra_args=["--output", "card-request.json"],
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--output is only valid with --type html", result.stderr)
        self.assertFalse(record.exists())

    def test_card_turns_dws_process_failure_into_an_error(self) -> None:
        payload = card_payload()
        result, _ = self.run_with_fake_dws(
            payload,
            response="",
            exit_code=7,
            stderr="remote failed and must not expose ddws-client-secret",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("DWS command failed with exit code 7", result.stderr)
        self.assertNotIn("ddws-client-secret", result.stderr)

    def test_card_rejects_unsuccessful_or_mismatched_delivery_response(self) -> None:
        payload = card_payload()
        unsuccessful, _ = self.run_with_fake_dws(
            payload,
            response={"success": False, "result": {}},
        )
        mismatched = success_response(payload)
        mismatched["result"]["outTrackId"] = "different-track-id"
        mismatch_result, _ = self.run_with_fake_dws(payload, response=mismatched)

        self.assertEqual(unsuccessful.returncode, 2)
        self.assertIn("DWS returned success=false", unsuccessful.stderr)
        self.assertEqual(mismatch_result.returncode, 2)
        self.assertIn("outTrackId does not match", mismatch_result.stderr)


if __name__ == "__main__":
    unittest.main()
