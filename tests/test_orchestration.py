import copy
from datetime import date, timedelta
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


bridge = module("bridge", PACKAGE / "aiorchestration/scripts/orchestrate.py")
installer = module("installer", PACKAGE / "install.py")
TEMPLATE = json.loads((PACKAGE / "aiorchestration/assets/profile.example.json").read_text(encoding="utf-8"))


def configured():
    cfg = copy.deepcopy(TEMPLATE)
    cfg["onboarding_complete"] = True
    for e in cfg["entries"]:
        e["enabled"] = True
        e["model"] = "provider/fixture-model" if e["provider"] == "opencode" else "fixture-model"
    return cfg


class ProfileTests(unittest.TestCase):
    def test_template_does_not_assume_account_access(self):
        bridge.validate(copy.deepcopy(TEMPLATE))
        self.assertIsNone(bridge.plan(TEMPLATE)["manager_suggestion"])
        self.assertFalse(any(e["enabled"] for e in TEMPLATE["entries"]))

    def test_preference_order_and_missing_model_fallback(self):
        cfg = configured()
        cfg["allow_paid"] = True
        cfg["entries"][0]["enabled"] = False
        with patch.object(bridge, "executable", return_value="fixture"), patch.dict(os.environ, {"GEMINI_API_KEY": "fixture-key"}):
            result = bridge.plan(cfg)
        self.assertEqual(result["manager_suggestion"], "sol")
        self.assertEqual(result["candidates"], ["sol", "sonnet", "haiku", "gemini", "free"])

    def test_explicit_manager_is_not_silently_replaced(self):
        cfg = configured()
        cfg["allow_paid"] = True
        cfg["manager"] = "opus"
        cfg["entries"][0]["enabled"] = False
        with patch.object(bridge, "executable", return_value="fixture"):
            result = bridge.plan(cfg)
        self.assertTrue(result["selected_manager_unavailable"])
        self.assertIsNone(result["manager_suggestion"])

    def test_paid_and_stale_free_entries_are_excluded(self):
        cfg = configured()
        entry = cfg["entries"][-1]
        entry.update(cost_class="free", free_verified_on=(date.today() - timedelta(days=8)).isoformat())
        with patch.object(bridge, "executable", return_value="fixture"):
            self.assertEqual(bridge.plan(cfg)["candidates"], [])
            entry["free_verified_on"] = date.today().isoformat()
            self.assertEqual(bridge.plan(cfg)["candidates"], ["free"])

    def test_future_free_verification_is_rejected(self):
        entry = {"cost_class": "free", "free_verified_on": "2026-10-10"}
        self.assertFalse(bridge.free_current(entry, date(2026, 10, 9)))

    def test_missing_key_is_not_marked_ready(self):
        cfg = configured()
        cfg["allow_paid"] = True
        with patch.dict(os.environ, {}, clear=True), patch.object(bridge, "executable", return_value="fixture"):
            row = next(r for r in bridge.plan(cfg)["entries"] if r["id"] == "gemini")
        self.assertEqual(row["status"], "missing_key_environment")

    def test_reject_secret_fields_and_command_in_model(self):
        cfg = configured()
        cfg["entries"][0]["api_key"] = "fixture-secret"
        with self.assertRaises(bridge.BridgeError):
            bridge.validate(cfg)
        del cfg["entries"][0]["api_key"]
        cfg["entries"][0]["model"] = "opus & echo unwanted"
        with self.assertRaises(bridge.BridgeError):
            bridge.validate(cfg)

    def test_config_requires_real_bool_and_valid_limits(self):
        cfg = configured()
        cfg["allow_paid"] = "false"
        with self.assertRaises(bridge.BridgeError):
            bridge.validate(cfg)
        cfg["allow_paid"] = False
        cfg["max_output_tokens"] = -1
        with self.assertRaises(bridge.BridgeError):
            bridge.validate(cfg)


class AdapterTests(unittest.TestCase):
    def test_payloads_use_provider_specific_effort_and_caps(self):
        for provider, field in [("openai", "reasoning"), ("anthropic", "output_config"), ("gemini", "generationConfig")]:
            e = {"provider": provider, "model": "fixture", "effort": "high"}
            url, body = bridge.api_payload(e, "task", 900)
            self.assertTrue(url.startswith(bridge.BASES[provider]))
            self.assertIn(field, body)
            self.assertNotIn("tools", body)
            self.assertIn("900", json.dumps(body))
        _, body = bridge.api_payload({"provider": "openai", "model": "gpt-6.1-sol", "effort": "medium"}, "task", 900)
        self.assertFalse(body["store"])

    def test_successful_outputs_and_model_receipts(self):
        cases = [
            ("openai", {"status": "completed", "model": "actual", "usage": {"output_tokens": 4},
                        "output": [{"type": "message", "content": [{"type": "output_text", "text": "answer"}]}]}),
            ("anthropic", {"stop_reason": "end_turn", "model": "actual", "usage": {},
                           "content": [{"type": "thinking", "thinking": "private"}, {"type": "text", "text": "answer"}]}),
            ("gemini", {"modelVersion": "actual", "usageMetadata": {}, "candidates": [{"finishReason": "STOP",
                        "content": {"parts": [{"thought": True, "text": "private"}, {"text": "answer"}]}}]})
        ]
        for provider, data in cases:
            text, model, _ = bridge.api_result(provider, data)
            self.assertEqual((text, model), ("answer", "actual"))

    def test_incomplete_outputs_are_not_success(self):
        cases = [("openai", {"status": "incomplete"}), ("anthropic", {"stop_reason": "max_tokens"}),
                 ("gemini", {"candidates": [{"finishReason": "MAX_TOKENS"}]})]
        for provider, data in cases:
            with self.assertRaises(bridge.BridgeError):
                bridge.api_result(provider, data)

    def test_gemini_catalog_pagination_and_generation_filter(self):
        pages = [{"models": [{"name": "models/one", "supportedGenerationMethods": ["generateContent"]},
                             {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}],
                  "nextPageToken": "a/b"},
                 {"models": [{"name": "models/two", "supportedGenerationMethods": ["generateContent"]}]}]
        with patch.object(bridge, "request_json", side_effect=pages) as request:
            result = bridge.list_models("gemini", "fixture-key")
        self.assertEqual(result["models"], ["models/one", "models/two"])
        self.assertIn("pageToken=a%2Fb", request.call_args_list[1].args[0])

    def test_cli_uses_fixed_commands_and_no_bypass(self):
        for provider in ("openai", "anthropic", "opencode"):
            entry = {"provider": provider, "model": "fixture/model", "effort": "medium"}
            cmd = bridge.cli_command(entry, "fixture-executable", Path("scratch"))
            self.assertFalse(any("bypass" in arg or "skip-permissions" in arg for arg in cmd))
            self.assertIn("fixture/model", cmd)
            if provider == "openai":
                self.assertIn("read-only", cmd)
                self.assertEqual(cmd[-1], "-")
            if provider == "anthropic":
                self.assertEqual(cmd[cmd.index("--tools") + 1], "")
                self.assertIn("--strict-mcp-config", cmd)

    def test_cli_does_not_fabricate_reported_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "answer.txt").write_text("result", encoding="utf-8")
            result = bridge.cli_result("openai", '{"type":"turn.completed","usage":{"input_tokens":4}}', folder)
            self.assertIsNone(result[1])
            with self.assertRaises(bridge.BridgeError):
                bridge.cli_result("openai", '{"type":"turn.failed"}', folder)

    def test_opencode_requires_final_stop(self):
        events = '\n'.join([json.dumps({"type": "text", "part": {"text": "result"}}),
                            json.dumps({"type": "step_finish", "part": {"reason": "stop", "tokens": {"output": 2}}})])
        self.assertEqual(bridge.cli_result("opencode", events, Path("unused"))[0], "result")
        with self.assertRaises(bridge.BridgeError):
            bridge.cli_result("opencode", '{"type":"text","part":{"text":"partial"}}', Path("unused"))

    def test_opencode_message_is_not_parsed_as_another_attachment(self):
        cmd = bridge.cli_command({"provider": "opencode", "model": "fixture/model", "effort": None},
                                 "fixture", Path("scratch"))
        self.assertLess(2, cmd.index("--file"))
        self.assertEqual(cmd[-2:], ["--file", str(Path("scratch/input.txt"))])


class CallTests(unittest.TestCase):
    def setUp(self):
        self.cfg = configured()
        self.e = self.cfg["entries"][1]
        self.e.update(transport="api", key_env="TEST_AI_KEY", model="fixture")
        self.response = {"status": "completed", "model": "reported-fixture", "usage": {"output_tokens": 2},
                         "output": [{"type": "message", "content": [{"type": "output_text", "text": "result"}]}]}

    def test_paid_guard_prevents_network_call(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TEST_AI_KEY": "fixture-secret"}), \
                patch.object(bridge, "request_json") as request:
            with self.assertRaises(bridge.BridgeError):
                bridge.call(self.cfg, "sol", "task", Path(tmp) / "output.txt")
            request.assert_not_called()

    def test_key_in_prompt_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TEST_AI_KEY": "fixture-secret"}), \
                patch.object(bridge, "request_json") as request:
            with self.assertRaises(bridge.BridgeError):
                bridge.call(self.cfg, "sol", "task fixture-secret", Path(tmp) / "output.txt", True)
            request.assert_not_called()

    def test_success_receipt_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TEST_AI_KEY": "fixture-secret"}), \
                patch.object(bridge, "request_json", return_value=self.response) as request:
            out = Path(tmp) / "output.txt"
            result = bridge.call(self.cfg, "sol", "task", out, True)
            self.assertEqual(out.read_text(), "result")
            receipt = json.loads(Path(result["receipt"]).read_text())
            self.assertEqual(receipt["reported_model"], "reported-fixture")
            self.assertEqual(receipt["status"], "completed")
            with self.assertRaises(bridge.BridgeError):
                bridge.call(self.cfg, "sol", "task", out, True)
            self.assertEqual(request.call_count, 1)

    def test_failure_receipt_has_no_secret_and_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TEST_AI_KEY": "fixture-secret"}), \
                patch.object(bridge, "request_json", side_effect=bridge.BridgeError("HTTP 429 fixture-secret")) as request:
            out = Path(tmp) / "output.txt"
            with self.assertRaises(bridge.BridgeError):
                bridge.call(self.cfg, "sol", "task", out, True)
            raw = Path(str(out) + ".receipt.json").read_text()
            self.assertNotIn("fixture-secret", raw)
            self.assertEqual(json.loads(raw)["status"], "failed")
            self.assertFalse(out.exists())
            self.assertEqual(request.call_count, 1)


class InstallerTests(unittest.TestCase):
    def test_failed_staging_leaves_existing_skill_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = installer.install("codex", root)[0][0]
            (original / "SKILL.md").write_text("old skill", encoding="utf-8")
            with patch.object(installer.shutil, "copytree", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    installer.install("codex", root, replace=True)
            self.assertEqual((original / "SKILL.md").read_text(), "old skill")

    def test_both_targets_idempotence_and_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = installer.install("both", root)
            self.assertEqual(len(installed), 2)
            for path, status in installed:
                self.assertEqual(status, "installed")
                self.assertTrue((path / "SKILL.md").is_file())
            self.assertTrue(all(status == "unchanged" for _, status in installer.install("both", root)))
            altered = installed[0][0] / "SKILL.md"
            altered.write_text("old skill", encoding="utf-8")
            with self.assertRaises(ValueError):
                installer.install("both", root)
            replaced = installer.install("both", root, replace=True)
            self.assertIn("backup:", replaced[0][1])
            backups = list((root / ".aiorchestration/backups").rglob("SKILL.md"))
            self.assertEqual(backups[0].read_text(), "old skill")
            self.assertFalse((root / ".aiorchestration/profile.json").exists())


if __name__ == "__main__":
    unittest.main()
