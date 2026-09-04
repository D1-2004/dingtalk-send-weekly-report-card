from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote


SKILL_DIR = Path(__file__).resolve().parents[1]
TOOL = SKILL_DIR / "scripts" / "weekly_report_tool.py"
SUBMIT_URL_ENV = "WEEKLY_FEEDBACK_SUBMIT_URL"
READ_URL_ENV = "WEEKLY_FEEDBACK_READ_URL"
AITABLE_WEBHOOK_URL = (
    "https://connector.dingtalk.com/webhook/flow/103b082bde2f2107d5c80007"
)
READ_WEBHOOK_URL = (
    "https://connector.dingtalk.com/webhook/flow/103b082bde2f2107d5c80008"
)


def html_data() -> dict:
    return {
        "schemaVersion": 2,
        "iconUrl": "https://img.alicdn.com/example.png",
        "title": "维信诺周报",
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
        "outTrackId": "wf-1787690400000-a1b2",
        "callbackHeaders": {},
        "formDisabled": False,
    }


def markdown_data() -> dict:
    return {
        "schemaVersion": 1,
        "title": "维信诺周报",
        "reportPeriod": "2026年3月31日—2026年4月10日",
        "reportUrl": "https://alidocs.dingtalk.com/i/nodes/example",
        "summaryMarkdown": [
            "新增需求 **11** 项，其中 **2** 项已完成",
            "当前 **6** 个工单处理中，**2** 个已关闭",
        ],
        "feedbackUrl": "https://fde-workbench.dingtalk.com/sites/feedback-example",
        "feedbackLinkText": "查看完整周报并反馈您的意见",
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
    read_url: str | None = None,
    fake_dws_dir: Path | None = None,
    fake_response: dict | str | None = None,
    fake_exit: int = 0,
    fake_stderr: str = "",
    record_path: Path | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        SUBMIT_URL_ENV,
        READ_URL_ENV,
        "FAKE_DWS_RECORD",
        "FAKE_DWS_STDOUT",
        "FAKE_DWS_STDERR",
        "FAKE_DWS_EXIT",
    ):
        environment.pop(name, None)
    if submit_url is not None:
        environment[SUBMIT_URL_ENV] = submit_url
    if read_url is not None:
        environment[READ_URL_ENV] = read_url
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
        self.assertFalse((SKILL_DIR / "automation").exists())

        schema_files = sorted(
            path.name for path in (SKILL_DIR / "assets").glob("*.schema.json")
        )
        self.assertEqual(
            schema_files,
            [
                "weekly-feedback-read.schema.json",
                "weekly-feedback-webhook.schema.json",
                "weekly-report-briefing.schema.json",
            ],
        )
        self.assertEqual(list((SKILL_DIR / "assets").glob("*.js")), [])

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
        self.assertNotIn("协议审计", skill)
        self.assertNotIn("变更记录", skill)
        self.assertNotIn("变更原因", skill)
        self.assertIn("Markdown", skill)
        self.assertIn("prepare_static_site_deploy", skill)
        self.assertNotIn("multica-fetch-proxy-config.js", skill)
        self.assertNotIn("dingtalk-identity.js", skill)
        self.assertNotIn("weekly-feedback-runtime.js", skill)
        self.assertIn("index.html", skill)
        self.assertIn("完整构建产物", skill)
        self.assertIn("## 历史记录", skill)

    def test_only_asset_schema_describes_webhook_payload(self) -> None:
        schema_path = SKILL_DIR / "assets" / "weekly-feedback-webhook.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["properties"]["action"]["const"], "submit_weekly_feedback")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 2)
        self.assertEqual(set(schema["required"]), {"action", "schemaVersion", "outTrackId", "rows"})
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("submissionId", schema["properties"])
        rows = schema["properties"]["rows"]
        self.assertEqual(rows["minItems"], 1)
        self.assertEqual(rows["maxItems"], 1)
        row = rows["items"]
        self.assertEqual(row["properties"]["项目"]["type"], "string")
        self.assertEqual(row["properties"]["本周进展"]["type"], "string")
        self.assertEqual(row["properties"]["不满意原因"]["type"], "string")
        self.assertEqual(row["properties"]["编号"]["minLength"], 1)
        self.assertTrue(row["allOf"], "不满意时原因文本不能为空")

    def test_read_schema_combines_base_data_with_read_status(self) -> None:
        schema_path = SKILL_DIR / "assets" / "weekly-feedback-read.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["properties"]["keyword"]["const"],
            "weekly_report_mark_read",
        )
        self.assertEqual(set(schema["required"]), {"keyword", "schemaVersion", "outTrackId", "row"})
        self.assertNotIn("submissionId", schema["properties"])
        row = schema["properties"]["row"]
        self.assertEqual(row["properties"]["项目"]["type"], "string")
        self.assertEqual(row["properties"]["本周进展"]["type"], "string")
        self.assertEqual(row["properties"]["是否已读"]["const"], "是")
        self.assertNotIn("反馈人ID", row["properties"])
        self.assertFalse(schema["additionalProperties"])

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
                environment=command_environment(
                    submit_url=AITABLE_WEBHOOK_URL,
                    read_url=READ_WEBHOOK_URL,
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            command_result = json.loads(result.stdout)
            generated_data = extract_html_data(output)
            generated_html = output.read_text(encoding="utf-8")
            generated_runtime = (output.parent / "weekly-feedback-app.js").read_text(
                encoding="utf-8"
            )
            generated_files = sorted(
                path.name for path in output.parent.iterdir() if path.is_file()
            )

        self.assertEqual(command_result["success"], True)
        self.assertEqual(command_result["type"], "html")
        self.assertEqual(command_result["output"], str(output.resolve()))
        self.assertEqual(
            command_result["runtimeOutput"],
            str((output.parent / "weekly-feedback-app.js").resolve()),
        )
        self.assertEqual(
            command_result["siteFiles"],
            ["feedback.html", "weekly-feedback-app.js"],
        )
        self.assertEqual(generated_data["callbackUrl"], AITABLE_WEBHOOK_URL)
        self.assertEqual(command_result["submitUrl"], AITABLE_WEBHOOK_URL)
        self.assertEqual(generated_data["readCallbackUrl"], READ_WEBHOOK_URL)
        self.assertEqual(command_result["readUrl"], READ_WEBHOOK_URL)
        self.assertIn("reportReadOnLoad", generated_runtime)
        self.assertIn("weekly_report_mark_read", generated_runtime)
        self.assertIn('"是否已读": "是"', generated_runtime)
        self.assertIn('"编号": params.outTrackId', generated_runtime)
        self.assertIn("outTrackId: params.outTrackId", generated_runtime)
        self.assertIn("rows: [{", generated_runtime)
        self.assertIn("row: {", generated_runtime)
        self.assertIn('(params.summaryMarkdown || []).join("\\n")', generated_runtime)
        self.assertIn('"项目": JSON.stringify(', generated_runtime)
        self.assertIn('"不满意原因": state.dissatisfactionReasons.join("；")', generated_runtime)
        self.assertIn(
            'window.addEventListener("load", reportReadOnLoad, { once: true });',
            generated_runtime,
        )
        self.assertEqual(
            generated_files,
            ["feedback.html", "weekly-feedback-app.js"],
        )
        self.assertIn(
            '<script src="./weekly-feedback-app.js"></script>',
            generated_html,
        )
        self.assertIn("<title>维信诺周报</title>", generated_html)
        executable_inline_scripts = re.findall(
            r'<script(?![^>]*\bsrc=)(?![^>]*type="application/json")[^>]*>',
            generated_html,
            flags=re.IGNORECASE,
        )
        self.assertEqual(executable_inline_scripts, [])
        self.assertNotIn("window.__MULTICA_FETCH_PROXY_ALLOWLIST__", generated_html)
        self.assertIn("window.__MULTICA_FETCH_PROXY_ALLOWLIST__", generated_runtime)
        self.assertNotIn("__WEEKLY_FEEDBACK_PROXY_ALLOWLIST__", generated_html)
        self.assertNotIn("__WEEKLY_FEEDBACK_PROXY_ALLOWLIST__", generated_runtime)
        self.assertIn(
            "internal.user.getCurrentUserInfo",
            generated_runtime,
        )
        self.assertIn("feedbackUser", generated_runtime)
        self.assertIn("dissatisfactionReasons", generated_runtime)
        self.assertIn('"具体反馈": state.feedback', generated_runtime)
        self.assertIn('"反馈人ID": feedbackUser.userId', generated_runtime)
        self.assertIn('"反馈人昵称"', generated_runtime)
        self.assertIn('"反馈时间": new Date().toISOString()', generated_runtime)
        self.assertNotIn("feedbackUserId", generated_runtime)
        self.assertNotIn("feedbackUserName", generated_runtime)
        self.assertNotIn("projectRows", generated_runtime)
        self.assertNotIn("projectRowsJson", generated_runtime)
        self.assertNotIn("feedbackDialog", generated_runtime)
        self.assertIn('id="projectNames"', generated_html)
        self.assertIn('id="satisfactionOptions"', generated_html)
        self.assertIn('id="dissatisfactionReasons"', generated_html)
        self.assertIn('id="feedbackInput"', generated_html)
        self.assertIn(
            json.dumps([AITABLE_WEBHOOK_URL, READ_WEBHOOK_URL]),
            generated_runtime,
        )

    def test_html_injects_read_url_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "generated" / "feedback.html"
            result = run_gen_card(
                "html",
                html_data(),
                output=output,
                environment=command_environment(
                    submit_url=AITABLE_WEBHOOK_URL,
                    read_url=READ_WEBHOOK_URL,
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            generated_data = extract_html_data(output)

        self.assertEqual(generated_data["readCallbackUrl"], READ_WEBHOOK_URL)

    def test_html_requires_read_webhook_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "feedback.html"
            result = run_gen_card(
                "html",
                html_data(),
                output=output,
                environment=command_environment(submit_url=AITABLE_WEBHOOK_URL),
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn(READ_URL_ENV, result.stderr)

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
        self.assertLess(
            markdown.index(data["reportPeriod"]),
            markdown.index(data["summaryMarkdown"][0]),
        )
        self.assertNotIn(data["reportUrl"], markdown)
        self.assertIn(data["feedbackLinkText"], markdown)
        normalized_feedback_url = data["feedbackUrl"] + "/"
        feedback_deep_link = (
            "dingtalk://dingtalkclient/page/link?web_wnd=workbench&url="
            + quote(normalized_feedback_url, safe="")
        )
        self.assertLess(
            markdown.index(data["summaryMarkdown"][0]),
            markdown.index(feedback_deep_link),
        )
        self.assertEqual(command_result["success"], True)
        self.assertEqual(command_result["type"], "markdown")
        self.assertEqual(command_result["recipientName"], "辰驷")
        self.assertEqual(command_result["markdown"], markdown)
        self.assertEqual(command_result["feedbackUrl"], normalized_feedback_url)
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


class SummaryAndIconUrlTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(TOOL.parent))
        import weekly_report_tool as w

        self.w = w

    def test_markdown_splits_progress_and_risk(self) -> None:
        data = markdown_data()
        data["riskMarkdown"] = ["数据看板加载偏慢"]
        rendered = self.w.render_markdown(data)
        # IM 消息只留本周进展；风险/下周不外显，用「更多信息……」引导点链接
        self.assertIn("**本周进展**", rendered)
        self.assertNotIn("**风险 · 关注**", rendered)
        self.assertNotIn("**下周重点**", rendered)
        self.assertNotIn("数据看板加载偏慢", rendered)
        self.assertIn("更多信息……", rendered)

    def test_markdown_renders_three_blocks(self) -> None:
        data = markdown_data()
        data["riskMarkdown"] = ["文档协同卡顿"]
        data["nextWeekMarkdown"] = ["下周完成看板性能优化"]
        rendered = self.w.render_markdown(data)
        self.assertIn("**本周进展**", rendered)
        self.assertNotIn("**风险 · 关注**", rendered)
        self.assertNotIn("**下周重点**", rendered)
        self.assertNotIn("文档协同卡顿", rendered)
        self.assertNotIn("下周完成看板性能优化", rendered)
        self.assertIn("更多信息……", rendered)

    def test_markdown_without_risk_stays_plain_list(self) -> None:
        data = markdown_data()
        rendered = self.w.render_markdown(data)
        self.assertIn("**本周进展**", rendered)
        self.assertIn(data["summaryMarkdown"][0], rendered)
        self.assertNotIn("更多信息……", rendered)

    def test_markdown_progress_truncated_to_three(self) -> None:
        data = markdown_data()
        data["summaryMarkdown"] = ["进展一", "进展二", "进展三", "进展四", "进展五"]
        rendered = self.w.render_markdown(data)
        self.assertIn("进展一", rendered)
        self.assertIn("进展三", rendered)
        self.assertNotIn("进展四", rendered)
        self.assertNotIn("进展五", rendered)

    def test_html_schema_icon_url_is_optional(self) -> None:
        data = html_data()
        data.pop("iconUrl", None)
        data["callbackUrl"] = AITABLE_WEBHOOK_URL
        data["readCallbackUrl"] = AITABLE_WEBHOOK_URL
        errors = self.w.iter_schema_errors(data, self.w.HTML_FORM_DATA_SCHEMA)
        self.assertEqual(errors, [])


class BriefingSchemaSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(TOOL.parent))
        import weekly_report_tool as w

        self.w = w

    def test_briefing_schema_file_is_source_of_truth(self) -> None:
        self.assertTrue(self.w.BRIEFING_SCHEMA_PATH.exists())
        # 内嵌 HTML schema 的简报字段直接引用外部文件加载来的属性（同一对象）
        self.assertIs(
            self.w.HTML_FORM_DATA_SCHEMA["properties"]["summaryMarkdown"],
            self.w.BRIEFING_PROPERTIES["summaryMarkdown"],
        )
        self.assertIs(
            self.w.MARKDOWN_DATA_SCHEMA["properties"]["nextWeekMarkdown"],
            self.w.BRIEFING_PROPERTIES["nextWeekMarkdown"],
        )

    def test_briefing_progress_item_cap_enforced(self) -> None:
        data = html_data()
        data["callbackUrl"] = AITABLE_WEBHOOK_URL
        data["readCallbackUrl"] = AITABLE_WEBHOOK_URL
        data["summaryMarkdown"] = [f"进展{i}" for i in range(6)]  # 超过 maxItems 5
        errors = self.w.iter_schema_errors(data, self.w.HTML_FORM_DATA_SCHEMA)
        self.assertTrue(errors, "超过条数上限应校验失败")


if __name__ == "__main__":
    unittest.main()
