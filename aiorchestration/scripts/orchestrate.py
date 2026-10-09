#!/usr/bin/env python3
"""Portable text bridge. No third-party dependencies; no automatic POST retries."""
import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
CLIS = {"anthropic": "claude", "openai": "codex", "opencode": "opencode"}
BASES = {"anthropic": "https://api.anthropic.com/v1", "openai": "https://api.openai.com/v1",
         "gemini": "https://generativelanguage.googleapis.com/v1beta"}
GUARD = ("You are one participant in an AI orchestration task. Work only on the supplied task. "
         "Do not delegate, invoke orchestration, request credentials, or claim tests you did not run. "
         "Return a usable result or patch for the local coordinator to verify and apply.\n\n")


class BridgeError(Exception):
    pass


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value)


def config_path(arg=None):
    return Path(arg or os.environ.get("AIORCHESTRATION_CONFIG") or
                Path.home() / ".aiorchestration" / "profile.json").expanduser()


def validate(cfg):
    if not isinstance(cfg, dict) or cfg.get("version") != 1:
        raise BridgeError("Profile version must be 1.")
    allowed = {"version", "onboarding_complete", "manager", "allow_paid", "max_calls_per_task",
               "max_output_tokens", "timeout_seconds", "entries"}
    if set(cfg) - allowed:
        raise BridgeError("Unknown profile field; store credentials only in environment variables.")
    for key in ("onboarding_complete", "allow_paid"):
        if type(cfg.get(key)) is not bool:
            raise BridgeError("Profile flags must be booleans.")
    for key, cap in (("max_calls_per_task", 100), ("max_output_tokens", 128000), ("timeout_seconds", 1800)):
        val = cfg.get(key)
        if type(val) is not int or not 1 <= val <= cap:
            raise BridgeError("Invalid profile limit: " + key)
    if not isinstance(cfg.get("entries"), list):
        raise BridgeError("Profile entries must be a list.")
    ids = set()
    fields = {"id", "label", "rank", "provider", "transport", "model", "effort", "enabled",
              "cost_class", "free_verified_on", "key_env"}
    for e in cfg["entries"]:
        if not isinstance(e, dict) or set(e) - fields:
            raise BridgeError("Unknown entry field; do not put API keys in profiles.")
        ident = e.get("id", "")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9-]+", ident) or ident in ids:
            raise BridgeError("Entry IDs must be unique lowercase names.")
        ids.add(ident)
        if e.get("provider") not in {*KEYS, "opencode"} or e.get("transport") not in {"api", "cli", "native", "manual"}:
            raise BridgeError("Unsupported provider or transport.")
        if e["transport"] == "api" and e["provider"] not in KEYS:
            raise BridgeError("OpenCode uses the CLI transport.")
        if e["transport"] == "cli" and e["provider"] not in CLIS:
            raise BridgeError("Gemini CLI is not implemented; use API/native/manual.")
        if type(e.get("enabled")) is not bool or type(e.get("rank")) is not int or e["rank"] < 1:
            raise BridgeError("Invalid entry enabled/rank.")
        if e.get("cost_class") not in {"paid", "free", "unknown"}:
            raise BridgeError("Invalid cost_class.")
        model = e.get("model")
        if not isinstance(model, str) or (model and not re.fullmatch(r"[A-Za-z0-9._/-]+", model)):
            raise BridgeError("Model ID must be a catalog ID, not a command or secret.")
        if e["enabled"] and not model:
            raise BridgeError("Enabled entries require a verified model ID.")
        if e["provider"] == "opencode" and model and "/" not in model:
            raise BridgeError("OpenCode model must use provider/model format.")
        effort = e.get("effort")
        if effort is not None and effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise BridgeError("Unsupported effort; use null when not supported.")
        env = e.get("key_env", KEYS.get(e["provider"], "UNUSED"))
        if not isinstance(env, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", env):
            raise BridgeError("key_env must contain an environment variable NAME only.")
    if cfg.get("manager") is not None and cfg["manager"] not in ids:
        raise BridgeError("Manager entry does not exist.")
    return cfg


def load_config(path):
    if not path.is_file():
        raise BridgeError("No personal profile. Ask the access questions first, then run init.")
    return validate(json.loads(path.read_text(encoding="utf-8-sig")))


def executable(provider):
    name = CLIS[provider]
    if os.name == "nt":
        return shutil.which(name + ".exe") or shutil.which(name + ".cmd") or shutil.which(name)
    return shutil.which(name)


def key_for(e):
    return os.environ.get(e.get("key_env", KEYS[e["provider"]]), "")


def redact(value, cfg=None, extra_names=()):
    names = set(KEYS.values()) | set(extra_names)
    if cfg:
        names.update(e.get("key_env", KEYS.get(e["provider"], "")) for e in cfg["entries"])
    for name in names:
        secret = os.environ.get(name, "")
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def free_current(e, today=None):
    try:
        age = ((today or date.today()) - date.fromisoformat(e.get("free_verified_on") or "")).days
        return e["cost_class"] == "free" and 0 <= age <= 7
    except (ValueError, TypeError):
        return False


def readiness(e, paid_allowed):
    if not e["enabled"]:
        return "disabled"
    if not free_current(e) and not paid_allowed:
        return "paid_or_unknown_not_authorized"
    if e["transport"] == "api" and not key_for(e):
        return "missing_key_environment"
    if e["transport"] == "cli" and not executable(e["provider"]):
        return "missing_cli"
    if e["transport"] in {"native", "manual"}:
        return "host_or_manual_verification_required"
    return "locally_ready_network_access_unverified"


def plan(cfg, allow_paid=False):
    entries = sorted(cfg["entries"], key=lambda e: e["rank"])
    rows = [{"id": e["id"], "model": e["model"], "rank": e["rank"],
             "status": readiness(e, cfg["allow_paid"] or allow_paid)} for e in entries]
    candidates = [r["id"] for r in rows if r["status"] in
                  {"locally_ready_network_access_unverified", "host_or_manual_verification_required"}]
    chosen = cfg.get("manager")
    # An explicit unavailable manager must be resolved with the user, not silently replaced.
    suggested = chosen if chosen in candidates else (candidates[0] if not chosen and candidates else None)
    return {"onboarding_complete": cfg["onboarding_complete"], "manager_suggestion": suggested,
            "selected_manager_unavailable": bool(chosen and chosen not in candidates),
            "candidates": candidates, "entries": rows,
            "note": "Local prerequisites only. Confirm model/effort/account access before dispatch."}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BridgeError("Unexpected API redirect refused; verify the official endpoint.")


def request_json(url, headers, payload=None, timeout=60):
    req = urllib.request.Request(url, headers=headers,
                                 data=None if payload is None else json.dumps(payload).encode("utf-8"),
                                 method="GET" if payload is None else "POST")
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as res:
            return json.loads(res.read(20 * 1024 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        retry = exc.headers.get("Retry-After", "unspecified")
        raise BridgeError(f"API HTTP {exc.code}; Retry-After: {retry}. No generation retry was made.") from None
    except (urllib.error.URLError, TimeoutError):
        raise BridgeError("API connection failed/timed out; no generation retry was made.") from None


def headers_for(provider, secret):
    if not secret:
        raise BridgeError("API key environment variable is missing; set it locally, not in chat.")
    common = {"Content-Type": "application/json"}
    if provider == "anthropic":
        common.update({"x-api-key": secret, "anthropic-version": "2023-06-01"})
    elif provider == "openai":
        common["Authorization"] = "Bearer " + secret
    else:
        common["x-goog-api-key"] = secret
    return common


def api_payload(e, prompt, max_tokens):
    provider, model, effort = e["provider"], e["model"], e.get("effort")
    if provider == "openai":
        body = {"model": model, "instructions": GUARD, "input": prompt,
                "max_output_tokens": max_tokens, "store": False}
        if effort:
            body["reasoning"] = {"effort": effort}
        return BASES[provider] + "/responses", body
    if provider == "anthropic":
        body = {"model": model, "system": GUARD, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens}
        if effort:
            body["output_config"] = {"effort": effort}
        return BASES[provider] + "/messages", body
    model = model.removeprefix("models/")
    body = {"systemInstruction": {"parts": [{"text": GUARD}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens}}
    if effort:
        if effort not in {"minimal", "low", "medium", "high"}:
            raise BridgeError("Gemini thinkingLevel supports minimal/low/medium/high, when the model supports it.")
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": effort.upper()}
    return BASES[provider] + "/models/" + urllib.parse.quote(model, safe="") + ":generateContent", body


def api_result(provider, data):
    if data.get("error"):
        raise BridgeError("Provider returned an error; output was not accepted.")
    if provider == "openai":
        if data.get("status") != "completed":
            raise BridgeError("OpenAI response was incomplete/failed; output was not accepted.")
        parts = [p.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                 for p in item.get("content", []) if p.get("type") == "output_text"]
        reported, usage = data.get("model"), data.get("usage")
    elif provider == "anthropic":
        if data.get("stop_reason") not in {"end_turn", "stop_sequence"}:
            raise BridgeError("Anthropic response was cut short/required tools; output was not accepted.")
        parts = [p.get("text", "") for p in data.get("content", []) if p.get("type") == "text"]
        reported, usage = data.get("model"), data.get("usage")
    else:
        candidates = data.get("candidates", [])
        if not candidates or candidates[0].get("finishReason") != "STOP":
            raise BridgeError("Gemini response was blocked/incomplete; output was not accepted.")
        parts = [p.get("text", "") for p in candidates[0].get("content", {}).get("parts", [])
                 if not p.get("thought")]
        reported, usage = data.get("modelVersion"), data.get("usageMetadata")
    result = "\n".join(parts).strip()
    if not result:
        raise BridgeError("Provider returned no final text.")
    return result, reported, usage


def cli_command(e, exe, workdir):
    model, effort = e["model"], e.get("effort")
    if e["provider"] == "anthropic":
        args = [exe, "-p", "--model", model, "--output-format", "json", "--tools", "",
                "--disallowedTools", "mcp__*", "--strict-mcp-config", "--no-session-persistence",
                "--disable-slash-commands"]
        if effort:
            args += ["--effort", effort]
    elif e["provider"] == "openai":
        args = [exe, "exec", "--model", model, "--sandbox", "read-only", "--skip-git-repo-check",
                "--ephemeral", "--json", "--output-last-message", str(workdir / "answer.txt")]
        if effort:
            args += ["-c", 'model_reasoning_effort="' + effort + '"']
        args += ["-"]
    else:
        # The positional message precedes --file, whose CLI parser accepts an array.
        args = [exe, "run", "Return the result for the task in the attached input file. Do not use tools or delegate.",
                "--model", model, "--format", "json", "--file", str(workdir / "input.txt")]
        if effort:
            args += ["--variant", effort]
    return args


def events_from(stdout):
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return [e for e in events if isinstance(e, dict)]


def cli_result(provider, stdout, workdir):
    if provider == "anthropic":
        data = json.loads(stdout)
        if data.get("is_error") or data.get("subtype") != "success":
            raise BridgeError("Claude CLI did not finish successfully.")
        text = data.get("result", "")
        models = list(data.get("modelUsage", {}))
        return text, models[0] if len(models) == 1 else None, data.get("usage")
    events = events_from(stdout)
    if any(e.get("type") in {"error", "turn.failed"} for e in events):
        raise BridgeError("CLI reported failure; output was not accepted.")
    if provider == "openai":
        if not any(e.get("type") == "turn.completed" for e in events):
            raise BridgeError("Codex turn completion was not confirmed.")
        result_path = workdir / "answer.txt"
        if not result_path.is_file():
            raise BridgeError("Codex did not write a final result.")
        usage = next((e.get("usage") for e in reversed(events) if e.get("usage")), None)
        return result_path.read_text(encoding="utf-8"), None, usage
    finishes = [e.get("part", {}) for e in events if e.get("type") == "step_finish"]
    if not finishes or finishes[-1].get("reason") != "stop":
        raise BridgeError("OpenCode final stop was not confirmed.")
    parts = [e.get("part", {}).get("text", "") for e in events if e.get("type") == "text"]
    return "\n".join(parts), None, finishes[-1].get("tokens")


def cli_call(e, prompt, timeout):
    exe = executable(e["provider"])
    if not exe:
        raise BridgeError("Required CLI is not installed.")
    with tempfile.TemporaryDirectory(prefix="aiorchestration-") as tmp:
        workdir = Path(tmp)
        text = GUARD + prompt
        (workdir / "input.txt").write_text(text, encoding="utf-8")
        env = os.environ.copy()
        if e["provider"] == "opencode":
            env["OPENCODE_CONFIG_CONTENT"] = json.dumps({"permission": {"*": "deny"}, "share": "disabled"})
        proc = subprocess.run(cli_command(e, exe, workdir), input=text if e["provider"] != "opencode" else None,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, cwd=workdir, env=env)
        if proc.returncode:
            raise BridgeError(f"CLI exited {proc.returncode}. Check login, quota, model and effort locally.")
        return cli_result(e["provider"], proc.stdout, workdir)


def list_models(provider, secret=None, timeout=60):
    if provider == "opencode":
        exe = executable(provider)
        if not exe:
            raise BridgeError("OpenCode CLI is not installed.")
        with tempfile.TemporaryDirectory(prefix="aiorchestration-models-") as tmp:
            proc = subprocess.run([exe, "models"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout, cwd=tmp)
        if proc.returncode:
            raise BridgeError("OpenCode model listing failed.")
        return {"models": [line.strip() for line in proc.stdout.splitlines()
                            if re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+", line.strip())],
                "note": "Catalog visibility is not proof of free pricing or usable quota."}
    headers = headers_for(provider, secret or os.environ.get(KEYS[provider], ""))
    url, results = BASES[provider] + "/models", []
    for _ in range(100):
        data = request_json(url, headers, timeout=timeout)
        if provider == "gemini":
            results += [m["name"] for m in data.get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", [])]
            token = data.get("nextPageToken")
            url = BASES[provider] + "/models?" + urllib.parse.urlencode({"pageToken": token or ""})
        else:
            results += [m["id"] for m in data.get("data", [])]
            token = data.get("last_id") if data.get("has_more") else None
            url = BASES[provider] + "/models?" + urllib.parse.urlencode({"after_id": token or ""})
        if not token:
            return {"models": results, "note": "Catalog visibility is not a generation/effort access test."}
    raise BridgeError("Model catalog exceeded the pagination limit.")


def call(cfg, ident, prompt, output, allow_paid=False):
    if not cfg["onboarding_complete"]:
        raise BridgeError("Complete the access inventory and manager selection first.")
    entry = next((e for e in cfg["entries"] if e["id"] == ident), None)
    if not entry:
        raise BridgeError("Unknown entry ID.")
    status = readiness(entry, cfg["allow_paid"] or allow_paid)
    if status != "locally_ready_network_access_unverified":
        raise BridgeError("Entry cannot be called by this bridge: " + status)
    if not prompt.strip() or len(prompt.encode("utf-8")) > 1024 * 1024:
        raise BridgeError("Prompt must be nonempty and at most 1 MiB; send only necessary context.")
    if redact(prompt, cfg) != prompt:
        raise BridgeError("Prompt contains a configured API key; remove it before dispatch.")
    output = Path(output)
    receipt_path = output.with_name(output.name + ".receipt.json")
    if output.exists() or receipt_path.exists():
        raise BridgeError("Output/receipt already exists; choose a new output path.")
    # Check writable location before starting a potentially billable operation.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=output.parent):
        pass
    receipt = {"entry": ident, "provider": entry["provider"], "transport": entry["transport"],
               "requested_model": entry["model"], "requested_effort": entry.get("effort"),
               "started_at": datetime.now(timezone.utc).isoformat(), "status": "started"}
    write_new(receipt_path, dump(receipt))
    try:
        if entry["transport"] == "api":
            url, body = api_payload(entry, prompt, cfg["max_output_tokens"])
            raw = request_json(url, headers_for(entry["provider"], key_for(entry)), body, cfg["timeout_seconds"])
            result, reported, usage = api_result(entry["provider"], raw)
        else:
            result, reported, usage = cli_call(entry, prompt, cfg["timeout_seconds"])
        if not isinstance(result, str) or not result.strip():
            raise BridgeError("No final text was returned.")
        write_new(output, redact(result, cfg))
        receipt.update({"status": "completed", "reported_model": reported, "usage": usage})
    except (BridgeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        receipt.update({"status": "failed", "error": redact(str(exc), cfg)})
        raise
    finally:
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
        receipt_path.write_text(redact(dump(receipt), cfg), encoding="utf-8")
    return {"output": str(output), "receipt": str(receipt_path), "status": receipt["status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Personal profile path (before the subcommand)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("init")
    planner = commands.add_parser("plan")
    planner.add_argument("--allow-paid", action="store_true")
    models = commands.add_parser("models")
    models.add_argument("--provider", choices=[*KEYS, "opencode"], required=True)
    models.add_argument("--key-env", help="Environment variable NAME, not the key")
    caller = commands.add_parser("call")
    caller.add_argument("--entry", required=True)
    caller.add_argument("--prompt-file", type=Path, required=True)
    caller.add_argument("--output", type=Path, required=True)
    caller.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    path, cfg = config_path(args.config), None
    extra_names = [args.key_env] if getattr(args, "key_env", None) else []
    try:
        if args.command == "init":
            if path.exists():
                result = {"profile": str(path), "status": "already_exists_unchanged"}
            else:
                template = (ROOT / "assets" / "profile.example.json").read_text(encoding="utf-8")
                validate(json.loads(template))
                write_new(path, template)
                if os.name != "nt":
                    path.chmod(0o600)
                result = {"profile": str(path), "status": "created_all_entries_disabled"}
        elif args.command == "doctor":
            result = {"python": sys.version.split()[0], "profile_exists": path.is_file(),
                      "cli_present": {p: bool(executable(p)) for p in CLIS},
                      "key_environment_present": {n: bool(os.environ.get(n)) for n in KEYS.values()},
                      "note": "Local checks only; no authentication or generation test was performed."}
        elif args.command == "models":
            if args.key_env and not re.fullmatch(r"[A-Z][A-Z0-9_]*", args.key_env):
                raise BridgeError("--key-env must be a variable name.")
            if args.key_env and not os.environ.get(args.key_env):
                raise BridgeError("Requested key environment variable is missing.")
            result = list_models(args.provider, os.environ.get(args.key_env) if args.key_env else None)
        else:
            cfg = load_config(path)
            result = plan(cfg, args.allow_paid) if args.command == "plan" else call(
                cfg, args.entry, args.prompt_file.read_text(encoding="utf-8-sig"), args.output, args.allow_paid)
        print(redact(dump(result), cfg, extra_names), end="")
        return 0
    except (BridgeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # Never dump provider response bodies, stderr, auth files or stack traces.
        print(dump({"error": redact(str(exc), cfg, extra_names)}), file=sys.stderr, end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
