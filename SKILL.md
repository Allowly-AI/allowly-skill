---
name: allowly
description: Use before consequential or regulated agent actions such as contacting people, sending or exposing personal data, making automated decisions about individuals, changing records, invoking MCP/tools, or spending money. Provides the /allowly check pattern for calling Allowly /v1/check with an existing authorization_id and branching on allow, deny, confirm, or escalate while retaining the receipt id.
---

# Allowly

Use Allowly before the agent performs a consequential action. The authorization
must already exist; setup and authorization creation belong to the customer app
and the Allowly CLI, not this skill.

Script paths below are relative to this SKILL.md file, not to the working
directory. Resolve them against the skill directory before running.

## Runtime Check

For a manual check, use:

```bash
/allowly check --authorization-id auth_... --action email.send
```

That maps to:

```bash
python3 scripts/allowly_check.py \
  --authorization-id auth_... \
  --action email.send
```

Optional fields:

```bash
python3 scripts/allowly_check.py \
  --authorization-id auth_... \
  --action email.send \
  --resource gmail:thread:abc123 \
  --context '{"visibility":"external"}'
```

If the authorization carries a budget, `--estimated-cost-micros` is required and
exactly one action is permitted; without it `/v1/check` returns 422:

```bash
python3 scripts/allowly_check.py \
  --authorization-id auth_... \
  --action email.send \
  --estimated-cost-micros 25 \
  --idempotency-key send-invoice-4821
```

Pass `--idempotency-key` on any budgeted check. A retry without one reserves the
budget a second time. Use a stable business-operation identifier, not a
timestamp or random value.

`context` may not use `budget`, `escalation`, `session_id`,
`authorization_provenance`, `identity_verification`, `client_timestamp`,
`client_timestamp_source`, or `execution`. These are server-owned receipt
fields; the API rejects caller use with 422. Pass a session label with
`--session-id` and event time with `--client-timestamp`. Keep context under 4KB.

The script requires `ALLOWLY_API_KEY`. It uses `ALLOWLY_API_URL` when set,
otherwise `https://api.allowly.ai`.

For an Auth0-bound authorization, also provide a current machine access token
through `ALLOWLY_AGENT_TOKEN`. Obtain it with the customer's Auth0 setup. Keep
the token and client secret out of action context, logs, and command-line
arguments. A missing, invalid, or expired required token stops the action.

`--client-timestamp 2026-09-24T20:01:02Z` adds customer-reported event time.
Keep this value unchanged on an exact retry. It is not an independent clock or
an acknowledgment that the resulting receipt was received.

The script calls `/v1/check`; the caller still runs the allowed action. For a
registered destination that Allowly should call itself, use the SDK's
[`execute` operation](https://allowly.ai/docs/api-reference/execute/). Do not
call that destination again after a gateway execution. An unknown execution
outcome requires checking the stored operation and destination, not generating
a new ID and retrying the side effect.

## Decision Behavior

A decision is only the four verbs below. Any non-2xx response from `/v1/check`
is **not** an authorization: do not perform the action. On 429 or 5xx, retry per
`Retry-After` and stop if it does not clear. A check that fails to complete
means the action does not happen.

- `allow`: perform the action and retain the `receipt_id` in the action log.
- `deny`: do not perform the action; surface the reason and replan.
- `confirm`: pause; surface the prompt, nonce, and `confirm_expires_at` deadline
  to the human loop. Do not present or approve an expired prompt.
  `confirm_prompt_hint` is the raw action name, not a human-readable prompt —
  compose that from the action plus the `resource` and `context` you sent.
  After approval, recheck the original `authorization_id` with the same action,
  the same resource, and the **identical `context` object** from the check that
  produced the confirm. The approval is bound to the evaluated condition value,
  not to the action alone.
  Approval opens a short-lived grant (default 60s, max 300s, set by the
  approving caller's `ttl_seconds`). Issue the recheck immediately. A second
  `confirm` on the recheck usually means the grant expired, not that approval
  failed.
- `escalate`: pause; route to the configured owner/manager. After approval,
  recheck the original request with the same action, resource, and context; one
  matching check is allowed and consumes the approval.

Never treat `confirm` or `escalate` as approval. They are control-flow stops.
Never perform the action from an approval response alone. A rejected escalation
becomes `deny` on the matching recheck.

The check response may contain only a pending receipt id. A fetched signed
receipt has a `schema_version`, signed top-level `alg` and `key_id` fields, and
an unpadded base64url `signature` string. Signature presence is not verification;
verify with the published workspace keys and expected workspace id.

## Budget Settlement

A check sent with `--estimated-cost-micros` reserves that amount against the
authorization's budget only when the authorization has a budget configured. On a
non-budgeted authorization the value is ignored and the resulting receipt cannot
be settled.

A reservation stays charged until settled. After the budgeted action completes,
report the actual cost promptly — settlement needs the check receipt to still
exist:

```bash
python3 scripts/allowly_settle.py \
  --check-receipt-id rcp_... \
  --actual-cost-micros 25
```

Use the `receipt_id` from the check output. Retries are safe: the idempotency
key defaults to the check receipt id, so repeating the call replays the original
settlement instead of erroring. A different cost for an already-settled receipt
is rejected by the API; never resettle to change a number.

## Setup Boundary

Teach setup by pointing users to the CLI:

```bash
allowly login
allowly init --use-case email-agent
allowly actions apply allowly.setup.json
allowly policies apply allowly.setup.json
allowly keys create --write-env .env.local --var ALLOWLY_API_KEY
```

After setup, the customer app creates and stores an `authorization_id`. This
skill only checks that stored authorization before actions.
