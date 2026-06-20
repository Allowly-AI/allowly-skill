---
name: allowly
description: Use before consequential or regulated agent actions such as contacting people, sending or exposing personal data, making automated decisions about individuals, changing records, invoking MCP/tools, or spending money. Provides the /allowly check pattern for calling Allowly /v1/check with an existing authorization_id and branching on allow, deny, confirm, or escalate while retaining the signed receipt id.
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
- `confirm`: pause; surface the prompt/nonce to the human loop; retry only after approval.
- `escalate`: pause; route to the configured owner/manager; retry only after approval.

Never treat `confirm` or `escalate` as approval. They are control-flow stops.

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
