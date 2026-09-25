#!/usr/bin/env python3
"""Small stdlib helper for Allowly /v1/check."""

from __future__ import annotations

import json
import os
import re
import sys
from argparse import ArgumentParser
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


# The API writes these into the receipt itself, so /v1/check rejects them in
# caller context with 422. Fail locally instead of round-tripping to find out.
RESERVED_CONTEXT_KEYS = frozenset(
    {
        "authorization_provenance",
        "budget",
        "client_timestamp",
        "client_timestamp_source",
        "escalation",
        "execution",
        "identity_verification",
        "session_id",
    }
)
MAX_CONTEXT_BYTES = 4 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _open_no_redirect(request: Request, timeout: float) -> Any:
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _client_timestamp(value: str) -> str:
    if not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value, re.IGNORECASE):
        raise ValueError("--client-timestamp must include a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--client-timestamp must be a valid timestamp with a timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--client-timestamp must include a timezone")
    return value


def build_payload(args: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "authorization_id": args.authorization_id,
        "actions": args.action,
    }
    if args.resource:
        payload["resource"] = args.resource
    if args.session_id:
        payload["session_id"] = args.session_id
    if args.estimated_cost_micros is not None:
        payload["estimated_cost_micros"] = args.estimated_cost_micros
    if getattr(args, "client_timestamp", None):
        payload["client_timestamp"] = _client_timestamp(args.client_timestamp)
    if args.context:
        context = json.loads(args.context)
        if not isinstance(context, dict):
            raise ValueError("--context must be a JSON object")
        reserved = sorted(RESERVED_CONTEXT_KEYS.intersection(context))
        if reserved:
            raise ValueError(f"--context uses server-reserved keys: {reserved}")
        size = len(json.dumps(context, separators=(",", ":")).encode("utf-8"))
        if size > MAX_CONTEXT_BYTES:
            raise ValueError(f"--context is {size} bytes, over the {MAX_CONTEXT_BYTES} byte limit")
        payload["context"] = context
    return payload


def check(
    payload: dict[str, Any],
    *,
    api_key: str,
    api_url: str,
    timeout: float,
    idempotency_key: str | None = None,
    agent_token: str | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Cloudflare bans urllib's default user-agent at the edge (error 1010).
        "User-Agent": "allowly-agent-skill",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if agent_token:
        headers["X-Allowly-Agent-Token"] = agent_token
    request = Request(
        f"{api_url.rstrip('/')}/v1/check",
        data=body,
        method="POST",
        headers=headers,
    )
    with _open_no_redirect(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def summarize(response: dict[str, Any]) -> dict[str, Any]:
    results = response.get("results") or {}
    if len(results) != 1:
        raise ValueError(f"expected one action result, got {len(results)}")
    action, result = next(iter(results.items()), (None, {}))
    receipt = result.get("receipt") or {}
    summary = {
        "authorization_id": response.get("authorization_id"),
        "action": action,
        "decision": result.get("decision"),
        "reason": result.get("reason"),
        "receipt_id": receipt.get("receipt_id"),
    }
    for key in (
        "confirm_nonce",
        "confirm_expires_at",
        "confirm_prompt_hint",
        "escalation_id",
        "escalation_to",
        "escalation_expires_at",
    ):
        if key in result:
            summary[key] = result[key]
    summary["response"] = response
    return summary


def parse_args(argv: list[str]) -> Any:
    parser = ArgumentParser(description="Call Allowly /v1/check.")
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--action", action="append", required=True)
    parser.add_argument("--resource")
    parser.add_argument("--context", help="JSON object copied into the check context")
    parser.add_argument("--session-id")
    parser.add_argument("--estimated-cost-micros", type=int)
    parser.add_argument(
        "--client-timestamp",
        help="customer-reported event time with a timezone; does not replace Allowly server time",
    )
    parser.add_argument(
        "--idempotency-key",
        help="replay key; a retried budgeted check reserves budget twice without one",
    )
    parser.add_argument("--api-url", default=os.getenv("ALLOWLY_API_URL", "https://api.allowly.ai"))
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    if len(args.action) != 1:
        parser.error("exactly one --action is supported")
    return args


def self_test() -> None:
    response = {
        "authorization_id": "auth_test",
        "results": {
            "email.send": {
                "decision": "allow",
                "reason": "authorization_granted_action_active",
                "receipt": {"receipt_id": "rcp_test"},
            }
        },
    }
    summary = summarize(response)
    assert summary["decision"] == "allow"
    assert summary["receipt_id"] == "rcp_test"
    response["results"]["email.send"]["confirm_expires_at"] = "2026-07-29T12:00:00.000Z"
    assert summarize(response)["confirm_expires_at"] == "2026-07-29T12:00:00.000Z"
    try:
        summarize({"results": {"a": {}, "b": {}}})
    except ValueError:
        pass
    else:
        raise AssertionError("multiple action results must fail closed")

    class _Args:
        authorization_id = "auth_test"
        action = ["email.send"]
        resource = None
        session_id = None
        estimated_cost_micros = None
        client_timestamp = None
        context = None

    args = _Args()
    for reserved_key in RESERVED_CONTEXT_KEYS:
        args.context = json.dumps({reserved_key: "caller-value"})
        try:
            build_payload(args)
        except ValueError as exc:
            assert "reserved" in str(exc)
        else:
            raise AssertionError(f"reserved context key {reserved_key} must be rejected locally")

    args.context = json.dumps({"pad": "x" * (MAX_CONTEXT_BYTES + 1)})
    try:
        build_payload(args)
    except ValueError as exc:
        assert "over the" in str(exc)
    else:
        raise AssertionError("oversized context must be rejected locally")

    args.context = json.dumps({"visibility": "external"})
    assert build_payload(args)["context"] == {"visibility": "external"}
    args.client_timestamp = "2026-09-24T20:01:02.123Z"
    assert build_payload(args)["client_timestamp"] == args.client_timestamp
    args.client_timestamp = "2026-09-24T20:01:02"
    try:
        build_payload(args)
    except ValueError as exc:
        assert "timezone" in str(exc)
    else:
        raise AssertionError("timezone-free client timestamps must fail locally")


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        self_test()
        print("ok")
        return 0

    args = parse_args(argv)
    api_key = os.getenv("ALLOWLY_API_KEY")
    if not api_key:
        print("ALLOWLY_API_KEY is required", file=sys.stderr)
        return 2

    try:
        response = check(
            build_payload(args),
            api_key=api_key,
            api_url=args.api_url,
            timeout=args.timeout,
            idempotency_key=args.idempotency_key,
            agent_token=os.getenv("ALLOWLY_AGENT_TOKEN"),
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except HTTPError as exc:
        print(f"Allowly API returned HTTP {exc.code}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Allowly API request failed: {exc.reason}", file=sys.stderr)
        return 1

    print(json.dumps(summarize(response), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
