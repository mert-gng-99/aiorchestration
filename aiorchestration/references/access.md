# Access, configuration, and real calls

## Personal profile

Default: `~/.aiorchestration/profile.json`. Override with
`AIORCHESTRATION_CONFIG` or `--config <path>` before the subcommand.
`init` does not replace existing files. Every template entry is disabled;
sharing the skill does not share account access.

| Field | Meaning |
| --- | --- |
| `onboarding_complete` | True after inventory and manager selection with the user |
| `manager` | Selected entry ID; null uses preference order |
| `allow_paid` | User's paid API/quota permission; false by default |
| `max_calls_per_task` | Call limit tracked by the coordinator in the task record |
| `max_output_tokens` | Per-call API cap; treatment of thinking is model-specific |
| `timeout_seconds` | API/CLI timeout |
| `entries` | Model entries; lower `rank` means earlier preference |
| `transport` | api, cli, native, or manual; helper executes api/cli only |
| `provider` | anthropic, openai, gemini, or opencode |
| `key_env` | Environment variable name, **never the key value** |

Entries include `id`, `label`, `rank`, `provider`, `transport`, `model`, `effort`,
`enabled`, `cost_class`, optional `key_env`, and optional `free_verified_on`.
Obtain model IDs from the catalog/menu. Version labels may map to different
IDs or be unavailable. `max`/`high` are effort settings, not model-name suffixes.
Use null when a model does not support the setting and explain the change.

## Subscription and CLI access

Prefer an existing authorized signed-in Claude Code, Codex, or OpenCode path
when appropriate, without requesting an unnecessary API key. Sign in through
official `claude auth login`, `codex login`, or `opencode auth login` flows.
Do not repurpose session cookies or subscription tokens as API keys. Web/app
subscriptions do not automatically establish CLI/API rights. For native host
tools, inspect their actual supported model options.

`doctor` is local-only: it does not execute CLIs or print keys. A model menu
or catalog is preliminary evidence; the first real task call confirms usable
generation. OpenCode catalog listing does not prove free pricing or quota.

## When an API key is required

Ask the user to configure the specific provider's environment variable locally,
not paste the key in chat. The helper reads only the configured variable;
never dump the whole environment. Hidden input in the user's terminal:

```python
import getpass, os, subprocess
os.environ["OPENAI_API_KEY"] = getpass.getpass("OpenAI API key: ")
subprocess.run(["python", "<skill-dir>/scripts/orchestrate.py", "models", "--provider", "openai"])
```

This applies only to that Python process and its children. If the coordinator
cannot see it, use the host's secret settings or the user's secure environment
setup; a temporary child process does not configure future sessions. API fees
may be separate from subscriptions. Establish authorization/budget before paid calls.

```text
python <skill-dir>/scripts/orchestrate.py models --provider anthropic
python <skill-dir>/scripts/orchestrate.py models --provider openai
python <skill-dir>/scripts/orchestrate.py models --provider gemini
python <skill-dir>/scripts/orchestrate.py models --provider opencode
```

Listing does not generate text or modify the profile. Visibility does not prove
generation permissions or effort support. Record verified IDs and authorized
paths; keep missing providers disabled.

## Text bridge

The dependency-free helper uses Anthropic Messages, OpenAI Responses, and
Gemini generateContent. API calls have no file/test tools. Supply necessary
content in the prompt; the local coordinator applies and checks returned
proposals/patches. Use the same bridge for manager planning and review.

CLI paths use Claude Code print with built-in/MCP tools disabled, Codex exec
with a read-only sandbox, and OpenCode run with inline deny permissions.
These are not full OS isolation: host/managed settings and installed CLI
plugins/hooks still apply. No bypass flag is added. Calls run in an empty
temporary directory with task context supplied in the prompt.

Examples, only with existing user authorization for paid usage:

```text
python <skill-dir>/scripts/orchestrate.py call --entry opus --prompt-file plan.txt --output plan-result.txt --allow-paid
python <skill-dir>/scripts/orchestrate.py call --entry sol --prompt-file worker.txt --output worker-result.txt --allow-paid
python <skill-dir>/scripts/orchestrate.py call --entry opus --prompt-file review.txt --output review-result.txt --allow-paid
```

Receipts record requested model, provider-reported model when available, usage,
and status. Do not invent a reported model by copying the requested ID.
Incomplete/failed responses are rejected. Generation POSTs are not retried
automatically; internal CLI retries depend on the installed software.

## Free models and budgets

Verify free pricing using current official provider/account information before
setting `cost_class: free` and `free_verified_on: YYYY-MM-DD`. The helper
rejects free verification older than seven days or dated in the future.
Conditions may change sooner, so recheck each task. A name containing "free"
is not sufficient evidence. Paid fallback needs existing authorization.

The helper enforces API output-token caps and timeouts, not cumulative dollar
budgets or task call counts. The coordinator tracks those in the task record.
Use provider spend controls for strict financial limits. Token caps are not
dollar caps; CLI quota/limits differ from API limits.

## Official references

Installation and endpoint references checked on 2026-10-09.
Reverify current model availability, pricing, and account access during setup.

- [Codex skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex CLI](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
- [OpenAI Responses](https://developers.openai.com/api/docs/guides/text)
- [OpenAI model catalog](https://developers.openai.com/api/reference/resources/models/methods/list)
- [GPT 6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code CLI](https://code.claude.com/docs/en/cli-reference)
- [Anthropic models](https://platform.claude.com/docs/en/api/models/list)
- [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create)
- [Anthropic effort](https://platform.claude.com/docs/en/build-with-claude/effort)
- [Gemini models](https://ai.google.dev/api/models)
- [Gemini generateContent](https://ai.google.dev/api/generate-content)
- [OpenCode CLI](https://opencode.ai/docs/cli/)
- [OpenCode configuration](https://opencode.ai/docs/config/)
