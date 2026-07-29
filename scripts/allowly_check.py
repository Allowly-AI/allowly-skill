#!/usr/bin/env python3
"""Small stdlib helper for Allowly /v1/check."""

from __future__ import annotations

import json
import os
import sys
from argparse import ArgumentParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
    if args.context:
        context = json.loads(args.context)
        if not isinstance(context, dict):
            raise ValueError("--context must be a JSON object")
        payload["context"] = context
    return payload


def check(payload: dict[str, Any], *, api_key: str, api_url: str, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        f"{api_url.rstrip('/')}/v1/check",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Cloudflare bans urllib's default user-agent at the edge (error 1010).
            "User-Agent": "allowly-agent-skill",
        },
    )
    with urlopen(request, timeout=timeout) as response:
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
    confirm_summary = summarize(
        {
            "authorization_id": "auth_test",
            "results": {
                "email.send": {
                    "decision": "confirm",
                    "reason": "action_requires_user_confirmation",
                    "confirm_nonce": "cnf_test",
                    "confirm_expires_at": "2026-07-29T12:00:00.000Z",
                    "confirm_prompt_hint": "email.send",
                    "receipt": {"receipt_id": "rcp_confirm"},
                }
            },
        }
    )
    assert confirm_summary["confirm_expires_at"] == "2026-07-29T12:00:00.000Z"
    try:
        summarize({"results": {"a": {}, "b": {}}})
    except ValueError:
        pass
    else:
        raise AssertionError("multiple action results must fail closed")


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
        response = check(build_payload(args), api_key=api_key, api_url=args.api_url, timeout=args.timeout)
    except (ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Allowly API returned {exc.code}: {body}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Allowly API request failed: {exc.reason}", file=sys.stderr)
        return 1

    print(json.dumps(summarize(response), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
