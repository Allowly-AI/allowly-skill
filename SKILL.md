---
name: allowly
description: Set up signup-free agent trials and check policy before tool calls, sending data, changing records, contacting people, or spending money. Use Allowly native enrollment and SDK checks with signed receipt verification; branch on allow, deny, confirm, or escalate with action limits and human approval.
---

# Allowly

Use Allowly before the agent performs a consequential action. Follow the
canonical [agent onboarding page](https://allowly.ai/docs/agents/) for a live
trial: `allowly trial create --json` needs no human signup or browser approval.
The service must be enabled and your CLI release must include this command.

Author the policy for your real tool, apply it with the existing CLI, enroll a
local native agent key, create a runtime key, then create and save a **new
authorization after enrollment** with the SDK. The SDK recipe on that page
uses the native private credential locally, checks the four outcomes, and
verifies fresh signed receipts against the trusted saved workspace ID.
Existing human-owned workspaces keep the browser-approved `allowly login` flow.

Bootstrap prints safe metadata and protected file paths. Keep setup/runtime
credentials, recovery proof, native keys, and the claim link out of logs and
chat. Resume interrupted bootstrap in the same config directory; do not make
a new account to retry. `allowly trial status --json` reports the 1,000 lifetime
Free allowance. At 429 `quota_exceeded`, stop and intentionally hand the secret
claim link from its protected file to the intended human. Claim keeps usage
and replaces trial authority. Unclaimed runtime access expires after seven days.

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

For a native-enrolled trial, use the canonical SDK recipe or the CLI's
`allowly check --agent-credential <protected-file>` instead of this stdlib
helper. They generate a fresh short-lived token locally. The helper can accept
an already generated token through `ALLOWLY_AGENT_TOKEN`; it does not read or
sign native private keys. Keep receipt verification in your SDK integration.

For an Auth0-bound authorization, also provide a current machine access token
through `ALLOWLY_AGENT_TOKEN`. Obtain it with the customer's Auth0 setup. Keep
the token and client secret out of action context, logs, and command-line
arguments. A missing, invalid, or expired required token stops the action.

`--client-timestamp 2026-09-24T20:01:02Z` adds customer-reported event time.
Keep this value unchanged on an exact retry. It is not an independent clock or
an acknowledgment that the resulting receipt was received.

The script calls `/v1/check`; the caller still runs the allowed action. For a
linked decision and outcome, use the SDK's customer-side
[`execute` operation](https://allowly.ai/docs/api-reference/execute/). The SDK
sends an allowed provider request from your host with local credentials. Do not
send it again outside the SDK. An unknown execution outcome requires checking
the stored operation and provider, not generating a new ID and retrying the
side effect.

## Decision Behavior

A decision is only the four verbs below. Any non-2xx response from `/v1/check`
is **not** an authorization: do not perform the action. On 429 or 5xx, retry per
`Retry-After` when present. `quota_exceeded` never clears through waiting or
key rotation: stop and hand off the protected claim link for reviewed paid
continuation. A check that fails to complete
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

Use the [canonical agent onboarding](https://allowly.ai/docs/agents/) for a
signup-free trial:

```bash
allowly trial create --json
allowly trial status --json
```

It covers agent-authored policy, native enrollment, new authorization, fresh
receipt verification, bounded recovery, and human claim in one place.
For an existing human-owned workspace, use the original CLI flow:

```bash
allowly login
allowly init --use-case email-agent
allowly actions apply allowly.setup.json
allowly policies apply allowly.setup.json
allowly keys create --write-env .env.local --var ALLOWLY_API_KEY
```

After setup, the customer app creates and stores an `authorization_id`. This
skill only checks that stored authorization before actions.
