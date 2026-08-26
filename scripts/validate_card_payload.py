#!/usr/bin/env python3
"""Validate a weekly-feedback createAndDeliver payload before DWS invocation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None  # type: ignore[assignment,misc]


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
MAX_PARAM_KEY_BYTES = 100
MAX_PARAM_VALUE_BYTES = 1024
REQUIRED_HIDDEN_FIELDS = {
    "submissionId",
    "customer",
    "week",
    "collector",
    "reportTime",
}
FORBIDDEN_NORMALIZED_KEYS = {
    "accesstoken",
    "appkey",
    "appsecret",
    "authorization",
    "clientid",
    "clientsecret",
    "dwsclientid",
    "dwsclientsecret",
    "secretkey",
    "xacsdingtalkaccesstoken",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a DingTalk weekly-feedback card request JSON."
    )
    parser.add_argument("payload", help="JSON file path, or '-' to read stdin")
    parser.add_argument(
        "--skip-env-check",
        action="store_true",
        help="Skip credential-presence checks for offline schema work only",
    )
    return parser.parse_args()


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
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


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


def schema_errors(instance: Any, schema_filename: str, prefix: str) -> list[str]:
    schema = load_schema(schema_filename)
    validator = Draft202012Validator(schema)
    return [
        f"{prefix}{json_path(error.absolute_path)}: {safe_schema_message(error)}"
        for error in sorted(
            validator.iter_errors(instance),
            key=lambda item: tuple(str(part) for part in item.path),
        )
    ]


def parse_json_string(value: Any, field_name: str, errors: list[str]) -> Any:
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        errors.append(f"{field_name} is not valid JSON: {exc.msg}")
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


def field_indexes(fields: list[dict[str, Any]], prefix: str) -> set[int]:
    indexes: set[int] = set()
    for field in fields:
        match = re.fullmatch(rf"{re.escape(prefix)}_(\d+)", str(field.get("name", "")))
        if match:
            indexes.add(int(match.group(1)))
    return indexes


def validate_cross_fields(
    payload: dict[str, Any], decoded_form: Any, errors: list[str]
) -> int:
    if not isinstance(decoded_form, dict) or not isinstance(decoded_form.get("fields"), list):
        return 0
    fields = decoded_form["fields"]
    object_fields = [field for field in fields if isinstance(field, dict)]
    names = [field.get("name") for field in object_fields]
    if len(names) != len(set(names)):
        errors.append("feedbackForm field names must be unique")

    indexed = {
        field["name"]: field
        for field in object_fields
        if isinstance(field.get("name"), str)
    }
    hidden_names = {
        name for name, field in indexed.items() if field.get("hidden") is True
    }
    if hidden_names != REQUIRED_HIDDEN_FIELDS:
        errors.append("feedbackForm hidden fields must match the required metadata set")

    submission = indexed.get("submissionId", {}).get("defaultValue")
    if submission != payload.get("outTrackId"):
        errors.append("submissionId defaultValue must equal outTrackId")

    week = indexed.get("week", {}).get("defaultValue")
    if not isinstance(week, str) or not re.fullmatch(
        r"[0-9]{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3])", week
    ):
        errors.append("feedbackForm week must use YYYY-Www format")

    report_time = indexed.get("reportTime", {}).get("defaultValue")
    try:
        if not isinstance(report_time, str):
            raise ValueError
        datetime.strptime(report_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        errors.append("feedbackForm reportTime must be a valid YYYY-MM-DD HH:mm:ss")

    project_indexes = field_indexes(object_fields, "project")
    satisfaction_indexes = field_indexes(object_fields, "satisfaction")
    feedback_indexes = field_indexes(object_fields, "feedback")
    if not (
        project_indexes == satisfaction_indexes == feedback_indexes
        and project_indexes
    ):
        errors.append("project/satisfaction/feedback indexes must match")
        return len(project_indexes)
    if project_indexes != set(range(1, len(project_indexes) + 1)):
        errors.append("project indexes must be contiguous and start at 1")
    return len(project_indexes)


def validate_card_param_sizes(card_params: Any, errors: list[str]) -> None:
    if not isinstance(card_params, dict):
        return
    for key, value in card_params.items():
        key_bytes = len(str(key).encode("utf-8"))
        if key_bytes > MAX_PARAM_KEY_BYTES:
            errors.append(
                f"cardParamMap key {key!r} exceeds {MAX_PARAM_KEY_BYTES} UTF-8 bytes"
            )
        if isinstance(value, str):
            value_bytes = len(value.encode("utf-8"))
            if value_bytes > MAX_PARAM_VALUE_BYTES:
                errors.append(
                    f"cardParamMap.{key} exceeds {MAX_PARAM_VALUE_BYTES} UTF-8 bytes "
                    f"({value_bytes} bytes)"
                )


def validate_payload(payload: Any, check_env: bool) -> tuple[list[str], int]:
    require_jsonschema()
    errors: list[str] = []
    project_count = 0

    if check_env:
        for name in ("DWS_CLIENT_ID", "DWS_CLIENT_SECRET"):
            if not os.environ.get(name):
                errors.append(f"missing environment variable: {name}")

    errors.extend(
        schema_errors(payload, "create-and-deliver.schema.json", "request")
    )
    if not isinstance(payload, dict):
        return errors, project_count

    for path in find_forbidden_keys(payload):
        errors.append(f"secret-like field is forbidden in payload: {path}")

    card_params = payload.get("cardData", {}).get("cardParamMap")
    validate_card_param_sizes(card_params, errors)
    if not isinstance(card_params, dict):
        return errors, project_count

    decoded_form = parse_json_string(
        card_params.get("feedbackForm"), "cardParamMap.feedbackForm", errors
    )
    decoded_options = parse_json_string(
        card_params.get("satisfactionOptions"),
        "cardParamMap.satisfactionOptions",
        errors,
    )

    for decoded_name, decoded_value in (
        ("feedbackForm", decoded_form),
        ("satisfactionOptions", decoded_options),
    ):
        if decoded_value is not None:
            for path in find_forbidden_keys(decoded_value, f"$.{decoded_name}"):
                errors.append(
                    f"secret-like field is forbidden in decoded payload: {path}"
                )

    if decoded_form is not None:
        errors.extend(
            schema_errors(
                decoded_form, "feedback-form.schema.json", "decoded feedbackForm"
            )
        )
        project_count = validate_cross_fields(payload, decoded_form, errors)
    if decoded_options is not None:
        errors.extend(
            schema_errors(
                decoded_options,
                "satisfaction-options.schema.json",
                "decoded satisfactionOptions",
            )
        )
    return errors, project_count


def main() -> int:
    args = parse_args()
    try:
        payload = load_json(args.payload)
        errors, project_count = validate_payload(
            payload, check_env=not args.skip_env_check
        )
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(
            json.dumps(
                {"valid": False, "errors": [f"cannot validate payload: {exc}"]},
                ensure_ascii=False,
            )
        )
        return 1

    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "valid": True,
                "outTrackId": payload["outTrackId"],
                "recipientSpace": payload["openSpaceId"],
                "projectCount": project_count,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
