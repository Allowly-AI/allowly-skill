#!/usr/bin/env python3
"""Small stdlib helper for Allowly /v1/budget-settlements."""

from __future__ import annotations

import json
import os
import sys
from argparse import ArgumentParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def build_payload(args: Any) -> dict[str, Any]:
    if args.actual_cost_micros < 0:
        raise ValueError("--actual-cost-micros must be a non-negative integer")
    return {
        "check_receipt_id": args.check_receipt_id,
        "actual_cost_micros": args.actual_cost_micros,
    }


def settle(
    payload: dict[str, Any],
    *,
    api_key: str,
    api_url: str,
    idempotency_key: str,
    timeout: float,
) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        f"{api_url.rstrip('/')}/v1/budget-settlements",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": idempotency_key,
            # Cloudflare bans urllib's default user-agent at the edge (error 1010).
            "User-Agent": "allowly-agent-skill",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_args(argv: list[str]) -> Any:
    parser = ArgumentParser(description="Report the actual cost of a budgeted Allowly check.")
    parser.add_argument("--check-receipt-id", required=True)
    parser.add_argument("--actual-cost-micros", type=int, required=True)
    parser.add_argument(
        "--idempotency-key",
        help="Replay key; defaults to the check receipt id so retries replay instead of erroring",
    )
    parser.add_argument("--api-url", default=os.getenv("ALLOWLY_API_URL", "https://api.allowly.ai"))
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def self_test() -> None:
    class Args:
        check_receipt_id = "rcp_test"
        actual_cost_micros = 25

    assert build_payload(Args()) == {"check_receipt_id": "rcp_test", "actual_cost_micros": 25}
    Args.actual_cost_micros = -1
    try:
        build_payload(Args())
    except ValueError:
        pass
    else:
        raise AssertionError("negative actual cost must fail closed")


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
        response = settle(
            build_payload(args),
            api_key=api_key,
            api_url=args.api_url,
            idempotency_key=args.idempotency_key or args.check_receipt_id,
            timeout=args.timeout,
        )
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

    print(json.dumps(response, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
