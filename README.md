# Allowly Agent Skill

Use Allowly before an agent performs consequential work: contacting people,
handling personal data, making decisions about individuals, changing records,
invoking tools, or spending money.

## Prerequisites

An agent can start without human signup using `allowly trial create --json`.
Follow the [canonical onboarding recipe](https://allowly.ai/docs/agents/) to
author its own policy, enroll a native key, create a new authorization, check a
real tool, and verify a fresh signed receipt. Free includes 1,000 lifetime
decisions; the trial's unclaimed runtime access lasts seven days. The service
must be enabled and your CLI release must include the trial command.

- An Allowly trial or existing human-owned workspace.
- A runtime API key from `allowly keys create`.
- An existing `authorization_id`, created by your app from an agent policy. See
  [Authorizations](https://allowly.ai/docs/api-reference/authorizations/). This
  skill checks authorizations; it does not create them.
- Python 3.9+. The scripts use only the standard library.

## Install

Clone into your agent's skills directory. The directory must be named `allowly`
to match the `name` in the SKILL.md frontmatter:

```bash
git clone https://github.com/Allowly-AI/allowly-skill.git ~/.claude/skills/allowly
```

For a single project instead of your whole account, clone to
`.claude/skills/allowly/` in the project root.

Confirm it loaded by asking the agent to run `/allowly check --help`, or run the
script's self-test directly:

```bash
python3 ~/.claude/skills/allowly/scripts/allowly_check.py --self-test
```

## Use

```bash
/allowly check --authorization-id auth_... --action email.send
```

The skill calls the existing Allowly runtime API. Take the key from the
environment rather than typing it on the command line, so it stays out of shell
history:

```bash
source .env.local   # written by: allowly keys create --write-env .env.local --var ALLOWLY_API_KEY

python3 scripts/allowly_check.py \
  --authorization-id auth_... \
  --action email.send \
  --resource gmail:thread:abc123 \
  --context '{"visibility":"external"}'
```

If the authorization carries a budget, `--estimated-cost-micros` is required and
exactly one action is permitted; without it the API returns 422. Pass
`--idempotency-key` on budgeted checks so a retry replays instead of reserving
the budget twice.

Decisions:

- `allow`: proceed and log the receipt id.
- `deny`: stop and replan.
- `confirm`: pause for approval, then recheck the original authorization with the
  same action, resource, and the identical `context` you sent — the approval is
  bound to the evaluated condition, not the action alone. The post-approval grant
  is short-lived (60s by default), so recheck immediately.
- `escalate`: pause for the configured approver, then recheck the original
  request if approved; one matching allow consumes the approval.

Any non-2xx response is not an authorization. Do not perform the action.

### Auth0 agent identity and customer time

For an authorization linked to the customer's Auth0 machine identity, set
`ALLOWLY_AGENT_TOKEN` to a current access token. The check script sends it separately
from the Allowly runtime key. Token acquisition and renewal remain with the
customer's Auth0 integration. Never place a client secret or token in action
context, workflow output, or shell history.

Pass `--client-timestamp` to the check script to record your reported event time,
including a timezone. Keep it stable when retrying the same request. It does
not replace Allowly's recorded time or provide an independent timestamp.

These scripts check permission; your caller runs the allowed action. The
[SDK execution operation](https://allowly.ai/docs/api-reference/execute/) can
send an allowed request from your host with local provider credentials and
retain linked outcome evidence. Do not send the same action a second time.

Never perform the action from an approval response alone.

The check may return a pending receipt id. Signed receipts have a `schema_version`,
signed top-level `alg` and `key_id` fields, and an unpadded base64url
`signature`; verify them against the expected workspace's published keys.

## Budget Settlement

A budgeted check reserves its estimate, and the reservation stays charged until
settled. Report the actual cost once the action completes, while the check
receipt still exists:

```bash
python3 scripts/allowly_settle.py \
  --check-receipt-id rcp_... \
  --actual-cost-micros 25
```

Retries are safe: the idempotency key defaults to the check receipt id, so
repeating the call replays the original settlement. A different cost for an
already-settled receipt is rejected; never resettle to change a number.

## Security

- Never commit `ALLOWLY_API_KEY`, `ALLOWLY_AGENT_TOKEN`, or an Auth0 client secret. `allowly keys create --write-env .env.local`
  writes it to a gitignored file.
- Keep the key server-side. It is shown once at creation.
- Rotate immediately on exposure.

## Setup

For signup-free setup, start here:

```bash
allowly trial create --json
allowly trial status --json
```

The CLI keeps recovery proof and the claim link in protected local files and
prints safe metadata/paths. Resume uncertain bootstrap in the same directory.
Do not print the claim secret; deliberately hand its protected link to the
intended human through a private channel. Claim preserves used decisions and
replaces old credentials/grants. At 429 `quota_exceeded`, stop the tool and
follow the reviewed claim/paid-capacity path. Waiting does not refill Free.

Use the native-identity SDK recipe on the onboarding page for trials. It signs
tokens locally and verifies receipts. The stdlib helper below accepts an
already supplied `ALLOWLY_AGENT_TOKEN`; it does not sign a native private key.

For an existing human-owned workspace, use the Allowly CLI for setup, then
create and store an `authorization_id` after enrollment:

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
- `scripts/allowly_settle.py`: stdlib budget settlement helper.
- `agents/openai.yaml`: OpenAI agent tool definition.
- `examples/agent_loop.py`: minimal branch loop.

## License

MIT. See [LICENSE](LICENSE).
