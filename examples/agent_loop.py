#!/usr/bin/env python3
"""Minimal Allowly branch loop example."""

from __future__ import annotations

import pathlib
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from allowly_check import check, summarize  # noqa: E402


def send_email() -> None:
    print("sent email")


def main() -> int:
    authorization_id = sys.argv[1]
    response = check(
        {
            "authorization_id": authorization_id,
            "actions": ["email.send"],
            "resource": "gmail:thread:abc123",
            "context": {"agent_loop": "example"},
            "client_timestamp": datetime.now(timezone.utc).isoformat(),
        },
        api_key=os.environ["ALLOWLY_API_KEY"],
        api_url=os.environ.get("ALLOWLY_API_URL", "https://api.allowly.ai"),
        timeout=30,
        agent_token=os.environ.get("ALLOWLY_AGENT_TOKEN"),
    )
    result = summarize(response)

    if result["decision"] == "allow":
        send_email()
        print(f"receipt: {result['receipt_id']}")
        return 0
    if result["decision"] == "deny":
        print(f"blocked: {result['reason']}")
        return 1
    if result["decision"] == "confirm":
        print(
            "pause for confirmation: "
            f"{result.get('confirm_prompt_hint')} "
            f"(expires {result.get('confirm_expires_at')})"
        )
        return 2
    if result["decision"] == "escalate":
        print(f"pause for escalation: {result.get('escalation_to')}")
        return 2

    print(f"unknown decision: {result['decision']}")
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: examples/agent_loop.py auth_...", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main())
