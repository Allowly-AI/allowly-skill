# Allowly Agent Skill

Use Allowly before an agent performs consequential work: contacting people,
handling personal data, making decisions about individuals, changing records,
invoking tools, or spending money.

## Use

```bash
/allowly check --authorization-id auth_... --action email.send
```

The skill calls the existing Allowly runtime API:

```bash
ALLOWLY_API_KEY=allowly_l1_s001_... \
python scripts/allowly_check.py \
  --authorization-id auth_... \
  --action email.send \
  --resource gmail:thread:abc123 \
  --context '{"visibility":"external"}'
```

Decisions:

- `allow`: proceed and log the receipt id.
- `deny`: stop and replan.
- `confirm`: pause for approval, then recheck the original authorization with
  the same action and resource.
- `escalate`: pause for the configured approver, then recheck the original
  request if approved; one matching allow consumes the approval.

Never perform the action from an approval response alone.

The check may return a pending receipt id. Signed receipts use wire format `3` (`schema_version`),
with signed top-level `alg` and `key_id` fields and an unpadded base64url
`signature`; verify them against the expected workspace's published keys.

## Setup

The skill does not create authorizations. Use the Allowly CLI for workspace
setup, then have the customer app create and store an `authorization_id`.

```bash
allowly login
allowly init --use-case email-agent
allowly actions apply allowly.setup.json
allowly policies apply allowly.setup.json
allowly keys create --write-env .env.local --var ALLOWLY_API_KEY
```

## Files

- `SKILL.md`: agent instructions and trigger description.
- `scripts/allowly_check.py`: stdlib `/v1/check` helper.
- `examples/agent_loop.py`: minimal branch loop.
