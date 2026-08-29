#!/usr/bin/env python3
"""Generate a validated weekly-feedback web form or Markdown message."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from string import Template
from typing import Any
from urllib.parse import quote, urlparse

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None  # type: ignore[assignment,misc]


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
DEFAULT_TEMPLATE = ASSET_DIR / "weekly-feedback-template.html"
HTML_RUNTIME_ASSETS = ("dingtalk-identity.js", "weekly-feedback-runtime.js")
FETCH_PROXY_CONFIG_ASSET = "multica-fetch-proxy-config.js"
DATA_BLOCK_START = '<script type="application/json" id="weeklyFeedbackFormData">'
DATA_BLOCK_END = "</script>"
SUBMIT_URL_ENV = "WEEKLY_FEEDBACK_SUBMIT_URL"
AITABLE_WEBHOOK_HOST = "connector.dingtalk.com"
AITABLE_WEBHOOK_PATH_PREFIX = "/webhook/flow/"
FLOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MARKDOWN_TEMPLATE = Template(
    """### $title
> 周期：$report_period

[$report_link_text]($report_url)

$summary

---

[👉 $feedback_link_text]($feedback_url)"""
)
class ToolError(Exception):
    """A user-facing CLI error."""


def require_jsonschema() -> None:
    if Draft202012Validator is None:
        raise RuntimeError(
            "missing dependency jsonschema; run: "
            "python3 -m pip install -r scripts/requirements.txt"
        )


def load_json(path: str | Path) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_schema(filename: str) -> dict[str, Any]:
    require_jsonschema()
    schema = load_json(ASSET_DIR / filename)
    Draft202012Validator.check_schema(schema)
    return schema


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


def iter_schema_errors(instance: Any, schema_filename: str) -> list[Any]:
    validator = Draft202012Validator(load_schema(schema_filename))
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


def validate_aitable_webhook_url(aitable_webhook_url: str) -> None:
    try:
        parsed = urlparse(aitable_webhook_url)
        port = parsed.port
    except ValueError as error:
        raise ToolError(f"{SUBMIT_URL_ENV} is invalid") from error
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
            f"{SUBMIT_URL_ENV} must use "
            "https://connector.dingtalk.com/webhook/flow/{flowId}"
        )
    flow_id = parsed.path[len(AITABLE_WEBHOOK_PATH_PREFIX) :]
    if not FLOW_ID_PATTERN.fullmatch(flow_id):
        raise ToolError(
            f"{SUBMIT_URL_ENV} flowId must contain 1-128 letters, digits, "
            "underscores, or hyphens"
        )
    return None


def validate_html_form_data(data: dict[str, Any]) -> None:
    try:
        errors = iter_schema_errors(data, "weekly-report-card-data.schema.json")
    except (OSError, ValueError, RuntimeError) as error:
        raise ToolError(f"cannot load feedback form schema: {error}") from error
    if errors:
        error = errors[0]
        raise ToolError(
            f"--data failed schema validation at {schema_error_path(error)}: "
            f"{error.message}"
        )


def validate_markdown_data(data: dict[str, Any]) -> None:
    try:
        errors = iter_schema_errors(
            data, "weekly-report-markdown-data.schema.json"
        )
    except (OSError, ValueError, RuntimeError) as error:
        raise ToolError(f"cannot load Markdown data schema: {error}") from error
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
    output_path = write_output(args.output, replace_data_block(template, data))
    proxy_config_path = output_path.parent / FETCH_PROXY_CONFIG_ASSET
    proxy_config = (
        "window.__MULTICA_FETCH_PROXY_ALLOWLIST__ = "
        + json.dumps([submit_url], ensure_ascii=False)
        + ";\n"
    )
    try:
        proxy_config_path.write_text(proxy_config, encoding="utf-8")
    except (OSError, ValueError) as error:
        raise ToolError(
            f"cannot write HTML runtime asset {FETCH_PROXY_CONFIG_ASSET}: {error}"
        ) from error
    runtime_outputs: list[str] = [str(proxy_config_path.resolve())]
    for filename in HTML_RUNTIME_ASSETS:
        source = ASSET_DIR / filename
        target = output_path.parent / filename
        try:
            shutil.copyfile(source, target)
        except (OSError, ValueError) as error:
            raise ToolError(f"cannot copy HTML runtime asset {filename}: {error}") from error
        runtime_outputs.append(str(target.resolve()))
    return {
        "success": True,
        "type": "html",
        "output": str(output_path.resolve()),
        "assets": runtime_outputs,
        "siteRoot": str(output_path.parent.resolve()),
        "submitUrl": submit_url,
    }


def build_dingtalk_workbench_link(url: str) -> str:
    return (
        "dingtalk://dingtalkclient/page/link?web_wnd=workbench&url="
        + quote(url, safe="")
    )


def render_markdown(data: dict[str, Any]) -> str:
    summary = "\n".join(f"- {line}" for line in data["summaryMarkdown"])
    return MARKDOWN_TEMPLATE.substitute(
        title=data["title"],
        report_period=data["reportPeriod"],
        report_link_text=data.get("reportLinkText", "查看周报详情"),
        report_url=data["reportUrl"],
        summary=summary,
        feedback_link_text=data.get("feedbackLinkText", "填写反馈"),
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
    feedback_deep_link = build_dingtalk_workbench_link(data["feedbackUrl"])
    response = run_dws_dm(data["recipientName"], markdown)
    return {
        "success": True,
        "type": "markdown",
        "recipientName": data["recipientName"],
        "markdown": markdown,
        "feedbackUrl": data["feedbackUrl"],
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
