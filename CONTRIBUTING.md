# Contributing

Keep the skill portable between Claude Code and Codex. Use Python 3.10+
and the standard library for the installer and bridge.

## Local validation

```sh
python -m unittest discover -s tests -v
python aiorchestration/scripts/orchestrate.py doctor
```

Tests use fixtures and temporary directories, without paid generation calls.
Test installer changes with `--home <temporary-user-directory>` so you do not
replace your own installed skill unintentionally.

For workflow changes, review onboarding, manager selection, unavailable
providers, free-only use, existing paid authorization, and manual handoffs.
Keep README instructions consistent with the actual helper behavior.

For adapter changes, check the provider's official documentation and test
payloads, response parsing, incomplete outputs, and receipts. Live calls
require an authorized account and budget; never include keys, auth files,
personal profiles, or private task prompts in issues, tests, or commits.

Explain the concrete behavior changed and the checks run in your pull request.
The project is distributed under the MIT license in [LICENSE](LICENSE).
