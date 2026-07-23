---
name: allowly
description: Use before consequential or regulated agent actions such as contacting people, sending or exposing personal data, making automated decisions about individuals, changing records, invoking MCP/tools, or spending money. Provides the /allowly check pattern for calling Allowly /v1/check with an existing authorization_id and branching on allow, deny, confirm, or escalate while retaining the receipt id.
---

# Allowly

Use Allowly before the agent performs a consequential action. The authorization
must already exist; setup and authorization creation belong to the customer app
and the Allowly CLI, not this skill.

## Runtime Check

For a manual check, use:

```bash
/allowly check --authorization-id auth_... --action email.send
```

That maps to:

```bash
python scripts/allowly_check.py \
  --authorization-id auth_... \
  --action email.send
```

Optional fields:

```bash
python scripts/allowly_check.py \
  --authorization-id auth_... \
  --action email.send \
  --resource gmail:thread:abc123 \
  --context '{"visibility":"external"}'
```

The script requires `ALLOWLY_API_KEY`. It uses `ALLOWLY_API_URL` when set,
otherwise `https://api.allowly.ai`.

## Decision Behavior

- `allow`: perform the action and retain the `receipt_id` in the action log.
- `deny`: do not perform the action; surface the reason and replan.
- `confirm`: pause; surface the prompt/nonce to the human loop. After approval,
  recheck the original `authorization_id` with the same action and resource.
- `escalate`: pause; route to the configured owner/manager. After approval,
  recheck the original request; one matching check is allowed and consumes the approval.

Never treat `confirm` or `escalate` as approval. They are control-flow stops.
Never perform the action from an approval response alone. A rejected escalation
becomes `deny` on the matching recheck.

The check response may contain only a pending receipt id. A fetched signed
receipt uses wire format `3` (`schema_version`), with signed top-level `alg` and `key_id` fields and
an unpadded base64url `signature` string. Signature presence is not verification;
verify with the published workspace keys and expected workspace id.

## Budget Settlement

A check sent with `--estimated-cost-micros` reserves that amount against the
authorization's budget, and the reservation stays charged until settled. After
the budgeted action completes, report the actual cost promptly — settlement
needs the check receipt to still exist:

```bash
python scripts/allowly_settle.py \
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
