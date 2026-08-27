#!/usr/bin/env python3
"""Generate validated HTML or DingTalk weekly-feedback cards."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None  # type: ignore[assignment,misc]


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
DEFAULT_TEMPLATE = ASSET_DIR / "weekly-feedback-template.html"
DATA_BLOCK_START = '<script type="application/json" id="weeklyReportCardData">'
DATA_BLOCK_END = "</script>"
MAX_PARAM_KEY_BYTES = 100
SUBMIT_URL_ENV = "WEEKLY_FEEDBACK_SUBMIT_URL"
DWS_CARD_ENDPOINT = "/v1.0/card/instances/createAndDeliver"
FIXED_CALLBACK_TYPE = "HTTP"
FIXED_CALLBACK_ROUTE_KEY = "customer_feedback_aitable_v1"
FORBIDDEN_NORMALIZED_KEYS = {
    "accesstoken",
    "appkey",
    "appsecret",
    "authorization",
    "clientid",
    "clientsecret",
    "ddwsclientid",
    "ddwsclientsecret",
    "dwsclientid",
    "dwsclientsecret",
    "secretkey",
    "xacsdingtalkaccesstoken",
}


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


def schema_errors(instance: Any, schema_filename: str, prefix: str) -> list[str]:
    return [
        f"{prefix}{json_path(error.absolute_path)}: {safe_schema_message(error)}"
        for error in iter_schema_errors(instance, schema_filename)
    ]


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


def validate_html_card_data(data: dict[str, Any]) -> None:
    try:
        errors = iter_schema_errors(data, "weekly-report-card-data.schema.json")
    except (OSError, ValueError, RuntimeError) as error:
        raise ToolError(f"cannot load card data schema: {error}") from error
    if errors:
        error = errors[0]
        raise ToolError(
            f"--data failed schema validation at {schema_error_path(error)}: "
            f"{error.message}"
        )


def replace_data_block(template: str, data: dict[str, Any]) -> str:
    start_tag_index = template.find(DATA_BLOCK_START)
    if start_tag_index < 0:
        raise ToolError("template does not contain weeklyReportCardData")
    content_start = start_tag_index + len(DATA_BLOCK_START)
    content_end = template.find(DATA_BLOCK_END, content_start)
    if content_end < 0:
        raise ToolError("weeklyReportCardData script block is not closed")

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
    return {
        "success": True,
        "type": "html",
        "output": str(output_path.resolve()),
        "submitUrl": submit_url,
    }


def parse_json_string(value: Any, field_name: str, errors: list[str]) -> Any:
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        errors.append(f"{field_name} is not valid JSON: {error.msg}")
        return None


def normalize_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if normalize_key(key) in FORBIDDEN_NORMALIZED_KEYS:
                findings.append(child_path)
            findings.extend(find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_forbidden_keys(child, f"{path}[{index}]"))
    return findings


def validate_cross_fields(
    payload: dict[str, Any],
    card_params: dict[str, Any],
    decoded_rows: Any,
    errors: list[str],
) -> int:
    if not isinstance(decoded_rows, list):
        return 0
    if card_params.get("submissionId") != payload.get("outTrackId"):
        errors.append("cardParamMap.submissionId must equal outTrackId")
    report_time = card_params.get("reportTime")
    try:
        if not isinstance(report_time, str):
            raise ValueError
        datetime.strptime(report_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        errors.append("cardParamMap.reportTime must be a valid YYYY-MM-DD HH:mm:ss")

    rows = [row for row in decoded_rows if isinstance(row, dict)]
    ids = [row.get("id") for row in rows]
    expected_ids = [f"p{index}" for index in range(1, len(rows) + 1)]
    if ids != expected_ids:
        errors.append("projectRows ids must be contiguous and start at p1")
    names = [row.get("name") for row in rows]
    if len(names) != len(set(names)):
        errors.append("projectRows project names must be unique")
    for index, row in enumerate(rows, start=1):
        if any(
            option.get("projectId") != row.get("id")
            for option in row.get("satisfactionOptions", [])
            if isinstance(option, dict)
        ):
            errors.append(f"projectRows p{index} satisfaction option projectId mismatch")
        checked = [
            option.get("value")
            for option in row.get("satisfactionOptions", [])
            if isinstance(option, dict) and option.get("checked") is True
        ]
        satisfaction = row.get("satisfaction")
        if satisfaction == "" and checked:
            errors.append(f"projectRows p{index} has checked option without satisfaction")
        if satisfaction and checked != [satisfaction]:
            errors.append(f"projectRows p{index} satisfaction state is inconsistent")
    return len(rows)


def validate_card_param_sizes(card_params: Any, errors: list[str]) -> None:
    if not isinstance(card_params, dict):
        return
    for key in card_params:
        if len(str(key).encode("utf-8")) > MAX_PARAM_KEY_BYTES:
            errors.append(
                f"cardParamMap key {key!r} exceeds {MAX_PARAM_KEY_BYTES} UTF-8 bytes"
            )


def validate_payload(payload: Any) -> tuple[list[str], int]:
    require_jsonschema()
    errors: list[str] = []
    project_count = 0
    errors.extend(schema_errors(payload, "create-and-deliver.schema.json", "request"))
    if not isinstance(payload, dict):
        return errors, project_count
    for path in find_forbidden_keys(payload):
        errors.append(f"secret-like field is forbidden in payload: {path}")

    card_data = payload.get("cardData")
    card_params = card_data.get("cardParamMap") if isinstance(card_data, dict) else None
    validate_card_param_sizes(card_params, errors)
    if not isinstance(card_params, dict):
        return errors, project_count
    decoded_rows = parse_json_string(
        card_params.get("projectRows"), "cardParamMap.projectRows", errors
    )
    if decoded_rows is not None:
        for path in find_forbidden_keys(decoded_rows, "$.projectRows"):
            errors.append(f"secret-like field is forbidden in decoded payload: {path}")
        errors.extend(
            schema_errors(decoded_rows, "project-rows.schema.json", "decoded projectRows")
        )
        project_count = validate_cross_fields(
            payload, card_params, decoded_rows, errors
        )
    return errors, project_count


def validate_generation_parameters(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], str | None, dict[str, str] | None]:
    if args.type == "card" and args.template is not None:
        raise ToolError("--template is only valid with --type html")
    if args.type == "card" and args.output is not None:
        raise ToolError("--output is only valid with --type html")
    if args.type == "html" and args.output is None:
        raise ToolError("--output is required with --type html")

    data = parse_inline_data(args.data)
    if args.type == "html":
        submit_url = require_submit_url()
        data["callbackUrl"] = submit_url
        validate_html_card_data(data)
        return data, submit_url, None

    missing = [
        name
        for name in ("DDWS_CLIENT_ID", "DDWS_CLIENT_SECRET")
        if not os.environ.get(name)
    ]
    if missing:
        raise ToolError("missing environment variables: " + ", ".join(missing))
    try:
        errors, _ = validate_payload(data)
    except (OSError, ValueError, RuntimeError) as error:
        raise ToolError(f"cannot validate DingTalk card data: {error}") from error
    if errors:
        raise ToolError("card data failed validation: " + "; ".join(errors))
    credentials = {
        "client_id": os.environ["DDWS_CLIENT_ID"],
        "client_secret": os.environ["DDWS_CLIENT_SECRET"],
    }
    return data, None, credentials


def parse_dws_response(stdout: str) -> dict[str, Any]:
    try:
        response = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ToolError("DWS returned invalid JSON") from error
    if not isinstance(response, dict):
        raise ToolError("DWS returned invalid JSON object")
    return response


def validate_delivery_response(
    response: dict[str, Any], expected_out_track_id: str
) -> None:
    if response.get("success") is not True:
        raise ToolError("DWS returned success=false")
    result = response.get("result")
    if not isinstance(result, dict):
        raise ToolError("DWS response is missing result")
    if result.get("outTrackId") != expected_out_track_id:
        raise ToolError("DWS result outTrackId does not match request")
    deliver_results = result.get("deliverResults")
    if not isinstance(deliver_results, list) or not deliver_results:
        raise ToolError("DWS result deliverResults must be non-empty")
    if any(
        not isinstance(item, dict) or item.get("success") is not True
        for item in deliver_results
    ):
        raise ToolError("DWS returned a failed delivery result")


def gen_ding_card(
    data: dict[str, Any], credentials: dict[str, str]
) -> dict[str, Any]:
    request_payload = {
        **data,
        "callbackType": FIXED_CALLBACK_TYPE,
        "callbackRouteKey": FIXED_CALLBACK_ROUTE_KEY,
    }
    try:
        completed = subprocess.run(
            [
                "dws",
                "api",
                "POST",
                DWS_CARD_ENDPOINT,
                "--client-id",
                credentials["client_id"],
                "--client-secret",
                credentials["client_secret"],
                "--yes",
                "--data",
                "-",
            ],
            input=json.dumps(request_payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise ToolError("dws command not found") from error
    except OSError as error:
        raise ToolError("cannot execute dws command") from error
    if completed.returncode != 0:
        raise ToolError(f"DWS command failed with exit code {completed.returncode}")

    response = parse_dws_response(completed.stdout)
    validate_delivery_response(response, data["outTrackId"])
    _, project_count = validate_payload(data)
    return {
        "success": True,
        "type": "card",
        "outTrackId": data["outTrackId"],
        "recipientSpace": data["openSpaceId"],
        "projectCount": project_count,
        "dwsResponse": response,
    }


def generate_card(args: argparse.Namespace) -> int:
    data, submit_url, credentials = validate_generation_parameters(args)
    if args.type == "html":
        result = gen_html_card(args, data, submit_url or "")
    else:
        result = gen_ding_card(data, credentials or {})
    print(json.dumps(result, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weekly_report_tool",
        description="Generate a validated HTML or DingTalk weekly-feedback card.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    generate = subcommands.add_parser(
        "gen-card", help="Generate an HTML or DingTalk card from strict JSON data."
    )
    generate.add_argument("--type", choices=("html", "card"), required=True)
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
