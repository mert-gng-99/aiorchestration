---
name: aiorchestration
description: Coordinate multiple AI models when the user requests AI orchestration, manager selection, or task delegation. Verify access, choose a manager from the user's preference order, and route scoped work through relevant installed skills. Invoke with /aiorchestration or $aiorchestration.
---

# AI Orchestration

Respond in the user's language. The highest eligible model in the user's
preference order plans and reviews the work; workers handle suitable subtasks.
Use relevant installed skills and avoid unnecessary model calls.

## First use: ask the user first

If no profile exists, make this the first user question; do not ask for a task
again if one was already given:

> Which AI services can you access: Claude, Codex/ChatGPT, Gemini, OpenCode,
> or others? For each, do you use a signed-in CLI, an API, or only a web/app?
> Are paid calls allowed, and what budget or call limit applies to this task?

While awaiting the answer, inspect relevant files and skills, but do not assume
access, a manager choice, or paid-call permission. Never ask for the key itself.
If an API key is needed, identify the provider and follow the local setup in the
[access guide](references/access.md).

If a profile exists, recheck access and ask only about missing or changed fields.
Preserve the scope of existing paid-call authorization; do not assume a budget
for a new task. Profiles are personal and must stay outside repositories/releases.

## Verify access and select the manager

1. Locate this skill's actual directory. The helper is
   `<skill-dir>/scripts/orchestrate.py` and requires Python 3.10+.
   Keep the task workspace distinct from the installed skill directory.
2. Run `doctor` to check CLI presence and whether key environment variables are
   set. A CLI installation does not prove login, model access, or free quota.
3. Use the user's inventory and CLI model menu or API `models` to verify exact
   model IDs and supported effort settings. Catalog visibility is not proof of
   successful generation. Web/app access does not imply API/CLI access.
4. Fill the profile's `entries` and enable verified paths. Labels are preferences;
   never guess an exact ID. `init` copies a safe disabled template to a personal path.
5. Suggest the first eligible candidate from `plan` and ask during initial setup:
   "X is the highest eligible model in this order. Should X be the manager,
   or would you prefer another model?" Save the choice in `manager`.
   Do not ask again when the choice has already been made.

Default preferences reflect the requested order, not a universal capability ranking:

| Rank | Preference label | Starting role |
| --- | --- | --- |
| 1 | Opus 5.5 · max | Manager: planning, critical decisions, final review |
| 2 | GPT 6.1 Sol · medium | Complex implementation, architecture, independent review |
| 3 | Sonnet 5.5 | Moderate implementation and revisions |
| 4 | Haiku 5.5 | Small scoped tasks, extraction, drafts |
| 5 | Gemini 3.8 · high | Suitable research, analysis, second opinions |
| 6 | Verified free model through OpenCode | Simple, easily verified tasks |

Skip unavailable candidates. The user may change the order. If they request
newer/stronger candidates, verify current official information and account access;
do not silently replace this list with different models.

If the manager is the current chat model, manage here. Otherwise, make actual
native/CLI/API calls for its plan and final review; this chat remains the local
coordinator operating tools. The skill cannot change the live chat's model.
If the manager cannot be reached, explain and resolve an accessible selection.
With no working connections, use a user-selected single-model or manual-handoff
workflow and report it accurately.

## Complete the task

- Establish acceptance criteria and applicable repository/artifact instructions.
  Discover relevant skills and read their SKILL.md files. Do not invent installed
  skills, load every skill at once, or recursively invoke this skill.
- Give the manager necessary context and relevant skill instructions so it can
  choose subtasks, workers, output formats, and acceptance checks.
- A simple task may need one worker. Do not route every task through every model.
  Parallelize independent work when available; serialize dependent tasks and
  conflicting file edits.
- The user's request for multi-AI coordination includes scoped delegation.
  Use the host's actual delegation tools and supported model options; do not
  invent options. Use the [access guide](references/access.md) for other providers.
- Give workers the task, necessary file contents/skill instructions, constraints,
  and acceptance criteria. The helper exchanges text; it is not a file-editing
  autonomous worker. The local coordinator reviews, applies, and verifies its
  output using real tools. Make file ownership explicit for native workers.
  See [handoff and review](references/workflow.md).
- Stay within authorized budgets. The helper does not retry generation POSTs.
  Resolve login/permissions on 401/403 and verify IDs on 404. For 429, respect
  retry information and remaining limits, with at most two controlled retries
  or an authorized fallback. Never silently replace a free path with a paid one.
  Allow at most two worker correction rounds before escalating to the manager.
- Have the manager assess actual outputs, files/tests, sources, and acceptance
  criteria. A claim of manager approval requires a real response. Verify worker
  claims about tests and sources.
- Report the result, actual model IDs used, meaningful checks, and any fallback
  caused by missing access, concisely.

## Helper

```text
python <skill-dir>/scripts/orchestrate.py doctor
python <skill-dir>/scripts/orchestrate.py init
python <skill-dir>/scripts/orchestrate.py models --provider openai
python <skill-dir>/scripts/orchestrate.py plan
python <skill-dir>/scripts/orchestrate.py call --entry sol --prompt-file task.txt --output result.txt
```

`call` requires a completed profile, an enabled model ID, and access. Paid or
unknown-cost entries require recorded `allow_paid` or `--allow-paid`, used only
within the user's existing authorization. Outputs get a `.receipt.json` file.
Place `--config` before the subcommand to select a custom personal profile.

Do not include keys, auth files, passwords, or `.env` contents in worker context.
Profiles contain environment variable names only. Host permissions still apply;
the skill creates no model access, publication, or external messaging authority.
