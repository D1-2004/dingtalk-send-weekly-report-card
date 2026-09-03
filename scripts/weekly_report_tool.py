#!/usr/bin/env python3
"""Generate a validated weekly-feedback web form or Markdown message."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from string import Template
from typing import Any
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None  # type: ignore[assignment,misc]


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
DEFAULT_TEMPLATE = ASSET_DIR / "weekly-feedback-template.html"
BRIEFING_SCHEMA_PATH = ASSET_DIR / "weekly-report-briefing.schema.json"


def _load_briefing_properties() -> dict[str, Any]:
    """Single source of truth for the weekly briefing format (进展/风险/下周)."""
    try:
        raw = json.loads(BRIEFING_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(
            f"cannot load briefing schema {BRIEFING_SCHEMA_PATH}: {error}"
        ) from error
    properties = raw.get("properties")
    if not isinstance(properties, dict) or "summaryMarkdown" not in properties:
        raise RuntimeError("briefing schema missing summaryMarkdown property")
    return properties


BRIEFING_PROPERTIES = _load_briefing_properties()
HTML_RUNTIME_FILENAME = "weekly-feedback-app.js"
DATA_BLOCK_START = '<script type="application/json" id="weeklyFeedbackFormData">'
DATA_BLOCK_END = "</script>"
SUBMIT_URL_ENV = "WEEKLY_FEEDBACK_SUBMIT_URL"
VIEW_URL_ENV = "WEEKLY_FEEDBACK_VIEW_URL"
AITABLE_WEBHOOK_HOST = "connector.dingtalk.com"
AITABLE_WEBHOOK_PATH_PREFIX = "/webhook/flow/"
FLOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MULTICA_SITE_ROOT_PATTERN = re.compile(r"^/sites/[^/]+$")
SCRIPT_BLOCK_PATTERN = re.compile(
    r"(?P<indent>^[ \t]*)<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>",
    flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
SCRIPT_SRC_PATTERN = re.compile(r"\bsrc\s*=", flags=re.IGNORECASE)
SCRIPT_TYPE_PATTERN = re.compile(
    r"\btype\s*=\s*(['\"])(?P<value>.*?)\1",
    flags=re.IGNORECASE | re.DOTALL,
)
EXECUTABLE_SCRIPT_TYPES = {
    "",
    "application/ecmascript",
    "application/javascript",
    "module",
    "text/ecmascript",
    "text/javascript",
}
MARKDOWN_TEMPLATE = Template(
    """### $title
> 周期：$report_period

$summary

---

[👉 $feedback_link_text]($feedback_url)"""
)
HTML_FORM_DATA_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schemaVersion",
        "title",
        "reportUrl",
        "summaryMarkdown",
        "projects",
        "dissatisfactionOptions",
        "reportPeriod",
        "customer",
        "week",
        "collector",
        "reportTime",
        "submissionId",
        "callbackUrl",
    ],
    "properties": {
        "schemaVersion": {"const": 2},
        "iconUrl": {"type": "string", "minLength": 1, "pattern": "^https?://"},
        "title": {"type": "string", "minLength": 1, "maxLength": 100},
        "reportUrl": {"type": "string", "minLength": 1, "pattern": "^https?://"},
        "reportLinkText": {"type": "string", "minLength": 1, "maxLength": 50},
        "summaryMarkdown": BRIEFING_PROPERTIES["summaryMarkdown"],
        "riskMarkdown": BRIEFING_PROPERTIES["riskMarkdown"],
        "nextWeekMarkdown": BRIEFING_PROPERTIES["nextWeekMarkdown"],
        "projects": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/project"},
        },
        "satisfaction": {"enum": ["", "满意", "不满意"]},
        "dissatisfactionReasons": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 50},
        },
        "feedback": {"type": "string", "maxLength": 1000},
        "dissatisfactionOptions": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 50},
        },
        "reportPeriod": {"type": "string", "minLength": 1, "maxLength": 100},
        "customer": {"type": "string", "minLength": 1, "maxLength": 100},
        "week": {"type": "string", "minLength": 1, "maxLength": 50},
        "collector": {"type": "string", "minLength": 1, "maxLength": 100},
        "reportTime": {"type": "string", "minLength": 1, "maxLength": 50},
        "submissionId": {"type": "string", "minLength": 1, "maxLength": 120},
        "callbackUrl": {
            "type": "string",
            "minLength": 1,
            "pattern": "^https://connector\\.dingtalk\\.com/webhook/flow/[A-Za-z0-9_-]{1,128}$",
        },
        "viewCallbackUrl": {
            "type": "string",
            "pattern": "^(|https://connector\\.dingtalk\\.com/webhook/flow/[A-Za-z0-9_-]{1,128})$",
        },
        "callbackHeaders": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "formDisabled": {"type": "boolean"},
    },
    "$defs": {
        "project": {
            "type": "object",
            "required": ["id", "name"],
            "properties": {
                "id": {"type": "string", "minLength": 1, "maxLength": 80},
                "name": {"type": "string", "minLength": 1, "maxLength": 100},
            },
            "additionalProperties": False,
        }
    },
    "additionalProperties": False,
}
MARKDOWN_DATA_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schemaVersion",
        "title",
        "reportPeriod",
        "reportUrl",
        "summaryMarkdown",
        "feedbackUrl",
        "recipientName",
    ],
    "properties": {
        "schemaVersion": {"const": 1},
        "title": {"type": "string", "minLength": 1, "maxLength": 100},
        "reportPeriod": {"type": "string", "minLength": 1, "maxLength": 100},
        "reportUrl": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2048,
            "pattern": "^https?://",
        },
        "reportLinkText": {"type": "string", "minLength": 1, "maxLength": 50},
        "summaryMarkdown": BRIEFING_PROPERTIES["summaryMarkdown"],
        "riskMarkdown": BRIEFING_PROPERTIES["riskMarkdown"],
        "nextWeekMarkdown": BRIEFING_PROPERTIES["nextWeekMarkdown"],
        "feedbackUrl": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2048,
            "pattern": "^https?://",
        },
        "feedbackLinkText": {"type": "string", "minLength": 1, "maxLength": 50},
        "recipientName": {"type": "string", "minLength": 1, "maxLength": 100},
    },
    "additionalProperties": False,
}


class ToolError(Exception):
    """A user-facing CLI error."""


def require_jsonschema() -> None:
    if Draft202012Validator is None:
        raise RuntimeError(
            "missing dependency jsonschema; run: "
            "python3 -m pip install -r scripts/requirements.txt"
        )


def json_path(parts: Any) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def schema_error_path(error: Any) -> str:
    parts = list(error.absolute_path)
    if error.validator == "required" and isinstance(error.instance, dict):
        missing = sorted(set(error.validator_value) - set(error.instance))
        if missing:
            parts.append(missing[0])
    return json_path(parts)


def safe_schema_message(error: Any) -> str:
    validator = error.validator
    constraint = error.validator_value
    if validator in {"required", "additionalProperties"}:
        return error.message
    if validator == "type":
        return f"must be of type {constraint}"
    if validator == "pattern":
        return "must match the required pattern"
    if validator in {"const", "enum"}:
        return "must match an allowed value"
    if validator == "oneOf":
        return "must match exactly one allowed schema"
    if validator == "uniqueItems":
        return "must contain unique items"
    if validator == "minItems":
        return f"must contain at least {constraint} items"
    if validator == "maxItems":
        return f"must contain at most {constraint} items"
    if validator == "minLength":
        return f"must contain at least {constraint} characters"
    if validator == "maxLength":
        return f"must contain at most {constraint} characters"
    return f"violates the {validator} constraint"


def iter_schema_errors(instance: Any, schema: dict[str, Any]) -> list[Any]:
    require_jsonschema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    return sorted(
        validator.iter_errors(instance),
        key=lambda item: tuple(str(part) for part in item.path),
    )


def parse_inline_data(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as error:
        raise ToolError(
            f"--data must be valid JSON: line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        ) from error
    if not isinstance(data, dict):
        raise ToolError("--data must be a JSON object")
    return data


def require_submit_url() -> str:
    value = os.environ.get(SUBMIT_URL_ENV)
    if not value:
        raise ToolError(f"missing environment variable: {SUBMIT_URL_ENV}")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ToolError(
            f"{SUBMIT_URL_ENV} must be an absolute HTTP or HTTPS URL"
        )
    return value


def optional_view_url() -> str:
    value = os.environ.get(VIEW_URL_ENV, "")
    if not value:
        return ""
    validate_aitable_webhook_url(value, VIEW_URL_ENV)
    return value


def validate_aitable_webhook_url(
    aitable_webhook_url: str, env_name: str = SUBMIT_URL_ENV
) -> None:
    try:
        parsed = urlparse(aitable_webhook_url)
        port = parsed.port
    except ValueError as error:
        raise ToolError(f"{env_name} is invalid") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != AITABLE_WEBHOOK_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(AITABLE_WEBHOOK_PATH_PREFIX)
    ):
        raise ToolError(
            f"{env_name} must use "
            "https://connector.dingtalk.com/webhook/flow/{flowId}"
        )
    flow_id = parsed.path[len(AITABLE_WEBHOOK_PATH_PREFIX) :]
    if not FLOW_ID_PATTERN.fullmatch(flow_id):
        raise ToolError(
            f"{env_name} flowId must contain 1-128 letters, digits, "
            "underscores, or hyphens"
        )
    return None


def validate_html_form_data(data: dict[str, Any]) -> None:
    try:
        errors = iter_schema_errors(data, HTML_FORM_DATA_SCHEMA)
    except (ValueError, RuntimeError) as error:
        raise ToolError(f"cannot validate feedback form data: {error}") from error
    if errors:
        error = errors[0]
        raise ToolError(
            f"--data failed schema validation at {schema_error_path(error)}: "
            f"{error.message}"
        )


def validate_markdown_data(data: dict[str, Any]) -> None:
    try:
        errors = iter_schema_errors(data, MARKDOWN_DATA_SCHEMA)
    except (ValueError, RuntimeError) as error:
        raise ToolError(f"cannot validate Markdown data: {error}") from error
    if errors:
        error = errors[0]
        raise ToolError(
            f"--data failed Markdown schema validation at "
            f"{schema_error_path(error)}: {error.message}"
        )


def replace_data_block(template: str, data: dict[str, Any]) -> str:
    start_tag_index = template.find(DATA_BLOCK_START)
    if start_tag_index < 0:
        raise ToolError("template does not contain weeklyFeedbackFormData")
    content_start = start_tag_index + len(DATA_BLOCK_START)
    content_end = template.find(DATA_BLOCK_END, content_start)
    if content_end < 0:
        raise ToolError("weeklyFeedbackFormData script block is not closed")

    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    safe_json = re.sub(
        r"</script", lambda _: r"<\/script", serialized, flags=re.IGNORECASE
    )
    indented_json = "\n".join(f"      {line}" for line in safe_json.splitlines())
    return (
        template[:content_start]
        + "\n"
        + indented_json
        + "\n    "
        + template[content_end:]
    )


def write_output(output_value: str, content: str) -> Path:
    output_path = Path(output_value).expanduser()
    if output_path.exists() and output_path.is_dir():
        raise ToolError("--output must be a file path, not a directory")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
    except (OSError, ValueError) as error:
        raise ToolError(f"cannot write --output path {output_value!r}: {error}") from error
    return output_path


def configure_html_runtime(template: str, submit_url: str) -> str:
    placeholder = "__WEEKLY_FEEDBACK_PROXY_ALLOWLIST__"
    if template.count(placeholder) != 1:
        raise ToolError("template must contain one feedback proxy allowlist placeholder")
    return template.replace(
        placeholder,
        json.dumps([submit_url], ensure_ascii=False),
        1,
    )


def is_executable_inline_script(attrs: str) -> bool:
    if SCRIPT_SRC_PATTERN.search(attrs):
        return False
    type_match = SCRIPT_TYPE_PATTERN.search(attrs)
    script_type = type_match.group("value").strip().lower() if type_match else ""
    return script_type in EXECUTABLE_SCRIPT_TYPES


def externalize_html_runtime(html: str) -> tuple[str, str]:
    runtime_parts: list[str] = []
    runtime_tag_written = False

    def replace_script(match: re.Match[str]) -> str:
        nonlocal runtime_tag_written
        if not is_executable_inline_script(match.group("attrs")):
            return match.group(0)

        runtime_parts.append(match.group("body").strip())
        if runtime_tag_written:
            return ""
        runtime_tag_written = True
        return (
            f'{match.group("indent")}<script '
            f'src="./{HTML_RUNTIME_FILENAME}"></script>'
        )

    externalized = SCRIPT_BLOCK_PATTERN.sub(replace_script, html)
    if not runtime_parts:
        raise ToolError("template does not contain executable inline JavaScript")

    remaining_inline = [
        match.group(0)
        for match in SCRIPT_BLOCK_PATTERN.finditer(externalized)
        if is_executable_inline_script(match.group("attrs"))
    ]
    if remaining_inline:
        raise ToolError("generated HTML still contains executable inline JavaScript")

    runtime = "\n\n".join(part for part in runtime_parts if part) + "\n"
    return externalized, runtime


def gen_html_card(
    args: argparse.Namespace, data: dict[str, Any], submit_url: str
) -> dict[str, Any]:
    template_path = Path(args.template or DEFAULT_TEMPLATE).expanduser()
    try:
        template = template_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        raise ToolError(
            f"cannot read --template path {str(template_path)!r}: {error}"
        ) from error
    rendered = replace_data_block(template, data)
    configured = configure_html_runtime(rendered, submit_url)
    generated_html, generated_runtime = externalize_html_runtime(configured)

    output_path = Path(args.output).expanduser()
    if output_path.exists() and output_path.is_dir():
        raise ToolError("--output must be a file path, not a directory")
    if output_path.name == HTML_RUNTIME_FILENAME:
        raise ToolError(
            f"--output cannot use the reserved runtime filename "
            f"{HTML_RUNTIME_FILENAME!r}"
        )
    runtime_path = output_path.parent / HTML_RUNTIME_FILENAME
    write_output(str(runtime_path), generated_runtime)
    output_path = write_output(str(output_path), generated_html)
    return {
        "success": True,
        "type": "html",
        "output": str(output_path.resolve()),
        "runtimeOutput": str(runtime_path.resolve()),
        "siteRoot": str(output_path.parent.resolve()),
        "siteFiles": [output_path.name, runtime_path.name],
        "submitUrl": submit_url,
    }


def build_dingtalk_workbench_link(url: str) -> str:
    return (
        "dingtalk://dingtalkclient/page/link?web_wnd=workbench&url="
        + quote(normalize_hosted_site_url(url), safe="")
    )


def normalize_hosted_site_url(url: str) -> str:
    parsed = urlsplit(url)
    if MULTICA_SITE_ROOT_PATTERN.fullmatch(parsed.path):
        parsed = parsed._replace(path=parsed.path + "/")
    return urlunsplit(parsed)


def render_markdown(data: dict[str, Any]) -> str:
    sections = [
        ("**本周进展**", data["summaryMarkdown"]),
        ("**风险 · 关注**", data.get("riskMarkdown") or []),
        ("**下周重点**", data.get("nextWeekMarkdown") or []),
    ]
    non_empty = [(label, items) for label, items in sections if items]
    if len(non_empty) > 1:
        blocks = []
        for label, items in non_empty:
            block = [label] + [f"- {line}" for line in items]
            blocks.append("\n".join(block))
        summary = "\n\n".join(blocks)
    else:
        summary = "\n".join(f"- {line}" for line in sections[0][1])
    # 完整周报链接（reportUrl）不外显：客户需点开反馈入口才能看到完整周报，
    # 避免只读链接不填反馈。
    return MARKDOWN_TEMPLATE.substitute(
        title=data["title"],
        report_period=data["reportPeriod"],
        summary=summary,
        feedback_link_text=data.get(
            "feedbackLinkText", "查看完整周报并反馈您的意见"
        ),
        feedback_url=build_dingtalk_workbench_link(data["feedbackUrl"]),
    )


def validate_generation_parameters(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], str | None]:
    if args.type != "html" and args.template is not None:
        raise ToolError("--template is only valid with --type html")
    if args.type != "html" and args.output is not None:
        raise ToolError("--output is only valid with --type html")
    if args.type == "html" and args.output is None:
        raise ToolError("--output is required with --type html")
    data = parse_inline_data(args.data)
    if args.type == "html":
        aitable_webhook_url = require_submit_url()
        validate_aitable_webhook_url(aitable_webhook_url)
        data["callbackUrl"] = aitable_webhook_url
        data["viewCallbackUrl"] = optional_view_url()
        validate_html_form_data(data)
        return data, aitable_webhook_url

    validate_markdown_data(data)
    return data, None


def parse_dws_response(stdout: str) -> dict[str, Any]:
    try:
        response = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ToolError("DWS returned invalid JSON") from error
    if not isinstance(response, dict):
        raise ToolError("DWS returned invalid JSON object")
    return response


def run_dws_dm(recipient_name: str, content: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "dws",
                "chat",
                "+dm",
                "--to",
                recipient_name,
                "--content",
                content,
                "--yes",
                "--format",
                "json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise ToolError("dws command not found") from error
    except OSError as error:
        raise ToolError("cannot execute dws command") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        suffix = f": {detail[:1000]}" if detail else ""
        raise ToolError(
            f"DWS chat command failed with exit code {completed.returncode}{suffix}"
        )
    response = parse_dws_response(completed.stdout)
    if response.get("success") is False or response.get("ok") is False:
        raise ToolError("DWS chat returned an unsuccessful result")
    return response


def gen_markdown_card(data: dict[str, Any]) -> dict[str, Any]:
    markdown = render_markdown(data)
    feedback_url = normalize_hosted_site_url(data["feedbackUrl"])
    feedback_deep_link = build_dingtalk_workbench_link(feedback_url)
    response = run_dws_dm(data["recipientName"], markdown)
    return {
        "success": True,
        "type": "markdown",
        "recipientName": data["recipientName"],
        "markdown": markdown,
        "feedbackUrl": feedback_url,
        "feedbackDeepLink": feedback_deep_link,
        "dwsResponse": response,
    }


def generate_card(args: argparse.Namespace) -> int:
    data, submit_url = validate_generation_parameters(args)
    if args.type == "html":
        result = gen_html_card(args, data, submit_url or "")
    else:
        result = gen_markdown_card(data)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weekly_report_tool",
        description=(
            "Generate a validated weekly-feedback web form or Markdown message."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    generate = subcommands.add_parser(
        "gen-card",
        help="Generate a Markdown message or HTML feedback form from strict JSON data.",
    )
    generate.add_argument(
        "--type",
        choices=("markdown", "html"),
        default="markdown",
    )
    generate.add_argument(
        "--template",
        help="HTML template path; valid only with --type html.",
    )
    generate.add_argument("--data", required=True, help="Strict JSON object.")
    generate.add_argument(
        "--output", help="HTML output file path; valid only with --type html."
    )
    generate.set_defaults(handler=generate_card)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except ToolError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
