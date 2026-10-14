"""Bounded, safe HTTP error details shared by the helper CLIs."""

import json
import re
from datetime import timezone
from email.utils import format_datetime, parsedate_to_datetime
from http.client import HTTPException
from urllib.error import HTTPError


def http_error_message(error: HTTPError) -> str:
    message = f"Allowly API returned HTTP {error.code}"
    try:
        body = error.read(4097)
        if len(body) <= 4096:
            envelope = json.loads(body)
            detail = envelope.get("error") if isinstance(envelope, dict) else None
            code = detail.get("code") if isinstance(detail, dict) else None
            if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
                message += f"; code={code}"
    except (HTTPException, OSError, ValueError, RecursionError):
        pass

    retry_after = error.headers.get("Retry-After", "") if error.headers else ""
    if (
        not isinstance(retry_after, str)
        or len(retry_after) > 64
        or any(ord(char) < 32 or ord(char) > 126 for char in retry_after)
    ):
        retry_after = ""
    if retry_after and not re.fullmatch(r"[0-9]{1,10}", retry_after):
        try:
            parsed = parsedate_to_datetime(retry_after)
            retry_after = (
                format_datetime(parsed.astimezone(timezone.utc), usegmt=True)
                if parsed.tzinfo is not None else ""
            )
        except (TypeError, ValueError, OverflowError):
            retry_after = ""
    if retry_after:
        message += f"; Retry-After={retry_after}"
    return message
