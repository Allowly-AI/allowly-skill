"""Offline checks for the helper CLI boundaries."""

import contextlib
import io
import json
from http.client import IncompleteRead
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import allowly_check
import allowly_settle


class HelpersTest(unittest.TestCase):
    def run_error(self, module, body, headers=None):
        argv = (
            ["--authorization-id", "auth_test", "--action", "email.send"]
            if module is allowly_check
            else ["--check-receipt-id", "rcp_test", "--actual-cost-micros", "25"]
        )
        error = HTTPError("https://example.invalid/check", 429, "private reason", headers, body)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"ALLOWLY_API_KEY": "synthetic-only"}, clear=True),
            patch.object(module, "_open_no_redirect", side_effect=error),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(module.main(argv), 1)
        self.assertEqual(stdout.getvalue(), "")
        return stderr.getvalue()

    def test_error_code_and_retry_after(self):
        for module in (allowly_check, allowly_settle):
            for code, retry in (("rate_limited", "7"), ("quota_exceeded", None)):
                with self.subTest(module=module.__name__, code=code):
                    body = io.BytesIO(json.dumps({"error": {
                        "code": code, "message": "private response data",
                    }}).encode())
                    headers = {"Retry-After": retry} if retry else None
                    expected = f"Allowly API returned HTTP 429; code={code}"
                    if retry:
                        expected += f"; Retry-After={retry}"
                    self.assertEqual(self.run_error(module, body, headers), expected + "\n")

    def test_invalid_error_fields_are_not_logged(self):
        bodies = (
            b"private non-JSON response",
            b'[{"error":{"code":"private"}}]',
            b'{"error":"private"}',
            b'{"error":{"code":"private@example.invalid","message":"private"}}',
            b'{"error":{"code":"private\\ncode"}}',
            json.dumps({"error": {"code": "x" * 65}}).encode(),
        )
        for module in (allowly_check, allowly_settle):
            for body in bodies:
                with self.subTest(module=module.__name__, body=body):
                    self.assertEqual(
                        self.run_error(module, io.BytesIO(body), {"Retry-After": "7\nprivate"}),
                        "Allowly API returned HTTP 429\n",
                    )

    def test_error_body_read_is_bounded(self):
        for module in (allowly_check, allowly_settle):
            body = io.BytesIO(json.dumps({"error": {
                "code": "quota_exceeded", "message": "x" * 5000,
            }}).encode())
            self.assertEqual(
                self.run_error(module, body, {"Retry-After": "7"}),
                "Allowly API returned HTTP 429; Retry-After=7\n",
            )
            self.assertEqual(body.tell(), 4097)

    def test_error_body_read_failure_keeps_status_and_retry_after(self):
        for module in (allowly_check, allowly_settle):
            for failure in (OSError("private read failure"), IncompleteRead(b"private", 1)):
                body = io.BytesIO()
                with patch.object(body, "read", side_effect=failure):
                    self.assertEqual(
                        self.run_error(module, body, {"Retry-After": "0"}),
                        "Allowly API returned HTTP 429; Retry-After=0\n",
                    )

    def test_http_date_retry_after(self):
        for module in (allowly_check, allowly_settle):
            retry = "Wed, 21 Oct 2015 07:28:00 GMT"
            self.assertEqual(
                self.run_error(module, io.BytesIO(b"{}"), {"Retry-After": retry}),
                f"Allowly API returned HTTP 429; Retry-After={retry}\n",
            )

    def test_server_reserved_context_keys_are_rejected(self):
        for key in (
            "budget", "escalation", "session_id", "authorization_provenance",
            "identity_verification", "client_timestamp", "client_timestamp_source",
            "execution", "seal_origin", "policy_ref", "policy_eval", "engine_version",
        ):
            with self.subTest(key=key):
                args = allowly_check.parse_args([
                    "--authorization-id", "auth_test", "--action", "email.send",
                    "--context", json.dumps({key: "caller-value"}),
                ])
                with self.assertRaisesRegex(ValueError, "server-reserved"):
                    allowly_check.build_payload(args)


if __name__ == "__main__":
    unittest.main()
