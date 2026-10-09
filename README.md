# AI Orchestration

**One task. Your available AI models. A manager that plans and reviews the work.**

A portable Agent Skill for **Claude Code and Codex**. It asks which AI services
you can access, verifies the available connection paths, helps you choose a
manager, and coordinates workers using the relevant skills already installed
in your environment.

[Türkçe rehber](README.tr.md) · [Access and configuration](aiorchestration/references/access.md) · [Task handoff examples](aiorchestration/references/workflow.md)

## Quick start

Requirements: **Python 3.10+**, Claude Code and/or a Codex environment that loads
local skills. Provider access is configured separately; no third-party Python
packages are required.

Clone the repository:

```sh
git clone https://github.com/mert-gng-99/aiorchestration.git
cd aiorchestration
python install.py --target both
```

Alternatively, download and extract the ZIP from the
[latest release](https://github.com/mert-gng-99/aiorchestration/releases/latest),
then run `python install.py --target both` inside the extracted folder.
On systems where Python is named `python3`, use that command instead.

Install for one product with `--target claude` or `--target codex`.
The installer copies the skill to:

| Product | User-level skill directory |
| --- | --- |
| Codex | `~/.agents/skills/aiorchestration/` |
| Claude Code | `~/.claude/skills/aiorchestration/` |

Open a new session after installing. In Claude Code, use `/reload-skills` if
needed. An identical reinstall leaves files unchanged. If an existing skill
differs, inspect it first, then use `--replace`; the old version is backed up
outside the skill discovery directories.

## Give it a task

**Claude Code**

```text
/aiorchestration Build the login screen for this project using the installed design skill.
```

**Codex**

```text
$aiorchestration Build the login screen for this project using the installed design skill.
```

The skill responds in your language. On first use, it asks:

1. Which services can you access: Claude, Codex/ChatGPT, Gemini, OpenCode, or others?
2. Is each access path a signed-in CLI, an API, or only a website/app?
3. Are paid calls allowed, and what budget or call limit applies to this task?

It checks the available paths and asks whether the highest eligible model in
your preference order should be the manager. It saves your selection locally
in `~/.aiorchestration/profile.json`. API keys are configured locally in your
terminal or secret settings; they should never be pasted into the chat or profile.

## Default preference order

| Priority | Preference label | Typical responsibility |
| --- | --- | --- |
| 1 | Opus 5.5 · max | Planning, critical decisions, final review |
| 2 | GPT 6.1 Sol · medium | Complex implementation, architecture, independent review |
| 3 | Sonnet 5.5 | Implementation and revisions of moderate complexity |
| 4 | Haiku 5.5 | Small, clearly scoped tasks, extraction, drafts |
| 5 | Gemini 3.8 · high | Suitable research, analysis, second opinions |
| 6 | Verified free models through OpenCode | Simple tasks with easy-to-check outputs |

These are **editable preference labels**, not a benchmark ranking or a claim
that every listed version is available to every account. Exact model IDs and
supported effort settings must be verified. Unavailable entries are skipped;
the profile template starts with every entry disabled.

## How it works

The manager receives the task, acceptance criteria, available workers, budget,
and relevant skill instructions. It proposes scoped subtasks. Workers return
results or patches; the local coordinator applies changes and runs the real
checks. The manager then reviews the actual output and verification evidence.

- Relevant installed skills are loaded and their necessary instructions are
  passed to workers. Other skills are not bundled with this repository.
- Independent tasks can run in parallel when the host supports it. Conflicting
  edits and dependent tasks run sequentially.
- Simple work can use one worker; each task does not need every model.
- A manager on another provider is contacted through a real API/CLI call.
  The current chat remains the coordinator that operates local tools.

`SKILL.md` defines the orchestration workflow. The included Python helper
provides local checks, model catalog lookup, candidate selection, and actual
text calls. It is a text bridge, not a standalone autonomous agent runtime.

## Supported connections

| Provider | Included bridge |
| --- | --- |
| Anthropic | Claude Code CLI; Messages API |
| OpenAI | Codex CLI; Responses API |
| Google | Gemini generateContent API |
| OpenCode | OpenCode CLI with a verified `provider/model` ID |

Native host delegation and manual handoffs can also be used when available.
There is no Gemini CLI adapter in this package.

The skill cannot switch the live chat's model, grant subscriptions, or turn
web-only access into API access. A plain `/aiorchestration` message does not
register a command in every chat product. This package installs local skills;
it does not upload a skill to a claude.ai/Cowork account.

## Helper commands

Run these from the repository root:

```sh
python aiorchestration/scripts/orchestrate.py doctor
python aiorchestration/scripts/orchestrate.py init
python aiorchestration/scripts/orchestrate.py models --provider openai
python aiorchestration/scripts/orchestrate.py plan
```

`doctor` only checks local CLI/key-variable presence; it does not authenticate
or generate text. `init` creates a disabled personal profile without replacing
an existing one. Model lookup does not enable entries automatically.

After configuring an enabled entry and completing onboarding:

```sh
python aiorchestration/scripts/orchestrate.py call --entry sol --prompt-file task.txt --output result.txt
```

Paid or unknown-cost entries require either recorded `allow_paid` permission
or `--allow-paid`. The skill may grant neither without the user's authorization.
Each call writes a `.receipt.json` beside the output with the requested model,
the provider-reported model when available, usage, and completion status.

API calls have output-token limits and timeouts, and failed generation POSTs
are not automatically retried. Total task call counts and dollar budgets are
tracked by the coordinator; strict spending limits also require provider-side
controls. CLI quotas and limits differ from API limits.

## Sharing and development

Send your friends the repository or release link. Each person installs the
skill and completes onboarding with their own accounts. Personal profiles,
credentials, authentication files, and task outputs are not included in releases.

Run the offline tests:

```sh
python -m unittest discover -s tests -v
```

The initial release includes **22 passing offline tests** covering selection,
paid-call guards, free-access freshness, provider payloads and response parsing,
secret redaction, CLI arguments, receipts, and installation/backups. These tests
do not verify live paid generation or every host environment.

See [CONTRIBUTING.md](CONTRIBUTING.md) for changes and validation.
Released under the [MIT license](LICENSE).

## Official references

Installation and invocation follow the
[Codex skill documentation](https://learn.chatgpt.com/docs/build-skills) and
[Claude Code skill documentation](https://code.claude.com/docs/en/skills).
Provider-specific sources are listed in the
[access guide](aiorchestration/references/access.md).
