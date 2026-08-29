from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote


SKILL_DIR = Path(__file__).resolve().parents[1]
TOOL = SKILL_DIR / "scripts" / "weekly_report_tool.py"
AUTOMATION_TRANSFORMER = SKILL_DIR / "automation" / "aitable_feedback_transform.py"
SUBMIT_URL_ENV = "WEEKLY_FEEDBACK_SUBMIT_URL"
AITABLE_WEBHOOK_URL = (
    "https://connector.dingtalk.com/webhook/flow/103b082bde2f2107d5c80007"
)


def html_data() -> dict:
    return {
        "schemaVersion": 2,
        "iconUrl": "https://img.alicdn.com/example.png",
        "title": "维信诺项目回访",
        "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
        "reportLinkText": "查看完整周报",
        "summaryMarkdown": ["本周新增需求 **11** 项"],
        "projects": [
            {
                "id": "p1",
                "name": "智能助理项目",
            }
        ],
        "satisfaction": "",
        "dissatisfactionReasons": [],
        "feedback": "",
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


def markdown_data() -> dict:
    return {
        "schemaVersion": 1,
        "title": "维信诺项目周报回访",
        "reportPeriod": "2026年3月31日—2026年4月10日",
        "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
        "reportLinkText": "查看本周服务报告",
        "summaryMarkdown": [
            "新增需求 **11** 项，其中 **2** 项已完成",
            "当前 **6** 个工单处理中，**2** 个已关闭",
        ],
        "feedbackUrl": "https://fde-workbench.dingtalk.com/sites/feedback-example/",
        "feedbackLinkText": "填写本周反馈",
        "recipientName": "辰驷",
    }


def make_fake_dws(directory: Path) -> Path:
    executable = directory / "dws"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

record_path = Path(os.environ["FAKE_DWS_RECORD"])
records = json.loads(record_path.read_text()) if record_path.exists() else []
records.append({"argv": sys.argv[1:], "stdin": sys.stdin.read()})
record_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
sys.stdout.write(os.environ.get("FAKE_DWS_STDOUT", ""))
sys.stderr.write(os.environ.get("FAKE_DWS_STDERR", ""))
raise SystemExit(int(os.environ.get("FAKE_DWS_EXIT", "0")))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def command_environment(
    *,
    submit_url: str | None = None,
    fake_dws_dir: Path | None = None,
    fake_response: dict | str | None = None,
    fake_exit: int = 0,
    fake_stderr: str = "",
    record_path: Path | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        SUBMIT_URL_ENV,
        "FAKE_DWS_RECORD",
        "FAKE_DWS_STDOUT",
        "FAKE_DWS_STDERR",
        "FAKE_DWS_EXIT",
    ):
        environment.pop(name, None)
    if submit_url is not None:
        environment[SUBMIT_URL_ENV] = submit_url
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
    card_type: str | None,
    data: dict,
    *,
    environment: dict[str, str],
    output: Path | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(TOOL), "gen-card"]
    if card_type is not None:
        command.extend(["--type", card_type])
    command.extend(["--data", json.dumps(data, ensure_ascii=False)])
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
    marker = '<script type="application/json" id="weeklyFeedbackFormData">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    return json.loads(html[start:end])


class SimplifiedSkillTests(unittest.TestCase):
    def test_repository_documents_only_the_supported_web_form_protocol(self) -> None:
        self.assertFalse((SKILL_DIR / "references").exists())
        self.assertFalse((SKILL_DIR / "assets" / "weekly-card-input.schema.json").exists())
        self.assertFalse((SKILL_DIR / "assets" / "weekly-card-input.example.json").exists())
        self.assertFalse((SKILL_DIR / "assets" / "create-and-deliver.schema.json").exists())
        self.assertFalse((SKILL_DIR / "assets" / "project-rows.schema.json").exists())
        self.assertFalse((SKILL_DIR / "assets" / "card-request.example.json").exists())

        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        template = (SKILL_DIR / "assets" / "weekly-feedback-template.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("协议变更记录", skill)
        self.assertNotIn("变更历史", template)
        self.assertIn("weeklyFeedbackFormData", template)
        self.assertNotIn("weeklyReportCardData", template)
        self.assertNotIn("dws api", skill)
        self.assertNotIn("dws doc", skill)
        self.assertNotIn("互动 Card", skill)
        self.assertNotIn("DDWS_CLIENT_ID", skill)
        self.assertIn("## 功能", skill)
        self.assertIn("## 参数规格与来源", skill)
        self.assertIn("## 命令使用", skill)
        self.assertIn("## 协议审计", skill)
        self.assertIn("Markdown", skill)
        self.assertIn("prepare_static_site_deploy", skill)

    def test_agent_prompt_only_calls_gen_card(self) -> None:
        prompt = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("gen-card", prompt)
        self.assertNotIn("按 DWS 流程", prompt)
        self.assertNotIn("dws api", prompt)


class HtmlGenerationTests(unittest.TestCase):
    def test_html_injects_submit_url_and_returns_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "generated" / "feedback.html"
            result = run_gen_card(
                "html",
                html_data(),
                output=output,
                environment=command_environment(submit_url=AITABLE_WEBHOOK_URL),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            command_result = json.loads(result.stdout)
            generated_data = extract_html_data(output)
            generated_html = output.read_text(encoding="utf-8")
            identity_runtime = output.parent / "dingtalk-identity.js"
            feedback_runtime = output.parent / "weekly-feedback-runtime.js"
            proxy_config = output.parent / "multica-fetch-proxy-config.js"
            identity_runtime_exists = identity_runtime.exists()
            feedback_runtime_exists = feedback_runtime.exists()
            proxy_config_exists = proxy_config.exists()
            identity_runtime_text = identity_runtime.read_text(encoding="utf-8")
            feedback_runtime_text = feedback_runtime.read_text(encoding="utf-8")
            proxy_config_text = proxy_config.read_text(encoding="utf-8")

        self.assertEqual(command_result["success"], True)
        self.assertEqual(command_result["type"], "html")
        self.assertEqual(command_result["output"], str(output.resolve()))
        self.assertEqual(generated_data["callbackUrl"], AITABLE_WEBHOOK_URL)
        self.assertEqual(command_result["submitUrl"], AITABLE_WEBHOOK_URL)
        self.assertTrue(identity_runtime_exists)
        self.assertTrue(feedback_runtime_exists)
        self.assertTrue(proxy_config_exists)
        self.assertIn("multica-fetch-proxy-config.js", generated_html)
        self.assertIn("dingtalk-identity.js", generated_html)
        self.assertIn("weekly-feedback-runtime.js", generated_html)
        self.assertLess(
            generated_html.index("multica-fetch-proxy-config.js"),
            generated_html.index("weekly-feedback-runtime.js"),
        )
        self.assertIn(
            "internal.user.getCurrentUserInfo",
            identity_runtime_text,
        )
        self.assertIn("feedbackUser", feedback_runtime_text)
        self.assertIn("dissatisfactionReasons", feedback_runtime_text)
        self.assertIn("feedback: state.feedback", feedback_runtime_text)
        self.assertNotIn("projectRows", feedback_runtime_text)
        self.assertNotIn("projectRowsJson", feedback_runtime_text)
        self.assertNotIn("feedbackDialog", generated_html)
        self.assertIn('id="customerName"', generated_html)
        self.assertIn('id="projectNames"', generated_html)
        self.assertIn('id="satisfactionOptions"', generated_html)
        self.assertIn('id="dissatisfactionReasons"', generated_html)
        self.assertIn('id="feedbackInput"', generated_html)
        self.assertNotIn(
            "__MULTICA_FETCH_PROXY_ALLOWLIST__", feedback_runtime_text
        )
        self.assertEqual(
            proxy_config_text,
            "window.__MULTICA_FETCH_PROXY_ALLOWLIST__ = "
            f"{json.dumps([AITABLE_WEBHOOK_URL], ensure_ascii=False)};\n",
        )

    def test_html_requires_output_and_submit_url(self) -> None:
        result = run_gen_card(
            "html",
            html_data(),
            environment=command_environment(),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--output", result.stderr)

    def test_card_type_is_no_longer_supported(self) -> None:
        result = run_gen_card(
            "card",
            {"schemaVersion": 1},
            environment=command_environment(submit_url=AITABLE_WEBHOOK_URL),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)


class DirectFormAutomationTests(unittest.TestCase):
    def test_direct_form_payload_becomes_one_ai_table_row(self) -> None:
        self.assertTrue(
            AUTOMATION_TRANSFORMER.exists(),
            "AI 表格自动化解析脚本尚未加入技能仓库",
        )
        spec = importlib.util.spec_from_file_location(
            "aitable_feedback_transform", AUTOMATION_TRANSFORMER
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        result = module.main(
            {
                "payload": {
                    "schemaVersion": 2,
                    "action": "submit_weekly_feedback",
                    "submissionId": "web-form-001",
                    "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
                    "customer": "维信诺",
                    "week": "2026-W35",
                    "projects": ["智能助理项目", "数据看板项目"],
                    "satisfaction": "不满意",
                    "dissatisfactionReasons": ["响应不及时", "问题未解决"],
                    "feedback": "希望下周给出明确计划",
                    "collector": "辰驷",
                    "reportTime": "2026-08-30 07:00:00",
                    "feedbackUserId": "323179",
                    "feedbackUserName": "辰驷",
                }
            }
        )

        self.assertEqual(result["rowCount"], 1)
        self.assertEqual(
            result["rows"],
            [
                {
                    "编号": "web-form-001",
                    "客户": "维信诺",
                    "项目": "智能助理项目、数据看板项目",
                    "周次": "2026-W35",
                    "满意度": "不满意",
                    "反馈": "不满意原因：响应不及时、问题未解决；具体反馈：希望下周给出明确计划",
                    "反馈人": "323179",
                    "收集人": "辰驷",
                    "反馈时间": "2026-08-30 07:00:00",
                }
            ],
        )


class MarkdownDeliveryTests(unittest.TestCase):
    def test_markdown_is_default_and_sends_rendered_template(self) -> None:
        data = markdown_data()
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            make_fake_dws(directory)
            record = directory / "record.json"
            result = run_gen_card(
                None,
                data,
                environment=command_environment(
                    fake_dws_dir=directory,
                    fake_response={
                        "success": True,
                        "result": {"openTaskId": "markdown-task-1"},
                    },
                    record_path=record,
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            command_result = json.loads(result.stdout)
            records = json.loads(record.read_text(encoding="utf-8"))

        self.assertEqual(len(records), 1)
        argv = records[0]["argv"]
        self.assertEqual(argv[:2], ["chat", "+dm"])
        self.assertNotIn("api", argv)
        self.assertNotIn("--client-id", argv)
        self.assertNotIn("--client-secret", argv)
        self.assertEqual(argv[argv.index("--to") + 1], "辰驷")
        self.assertIn("--yes", argv)
        self.assertEqual(argv[argv.index("--format") + 1], "json")
        markdown = argv[argv.index("--content") + 1]
        self.assertEqual(records[0]["stdin"], "")
        self.assertLess(markdown.index(data["title"]), markdown.index(data["reportPeriod"]))
        self.assertLess(markdown.index(data["reportPeriod"]), markdown.index(data["reportUrl"]))
        self.assertLess(markdown.index(data["reportUrl"]), markdown.index(data["summaryMarkdown"][0]))
        feedback_deep_link = (
            "dingtalk://dingtalkclient/page/link?web_wnd=workbench&url="
            + quote(data["feedbackUrl"], safe="")
        )
        self.assertLess(
            markdown.index(data["summaryMarkdown"][0]),
            markdown.index(feedback_deep_link),
        )
        self.assertEqual(command_result["success"], True)
        self.assertEqual(command_result["type"], "markdown")
        self.assertEqual(command_result["recipientName"], "辰驷")
        self.assertEqual(command_result["markdown"], markdown)
        self.assertEqual(command_result["feedbackDeepLink"], feedback_deep_link)

    def test_markdown_validates_feedback_url_before_invoking_dws(self) -> None:
        data = markdown_data()
        data.pop("feedbackUrl")
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            make_fake_dws(directory)
            record = directory / "record.json"
            result = run_gen_card(
                "markdown",
                data,
                environment=command_environment(
                    fake_dws_dir=directory,
                    fake_response={"success": True, "result": {}},
                    record_path=record,
                ),
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("feedbackUrl", result.stderr)
        self.assertFalse(record.exists())


if __name__ == "__main__":
    unittest.main()
