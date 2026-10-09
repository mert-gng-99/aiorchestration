#!/usr/bin/env python3
"""Install only the portable skill, without copying personal credentials/config."""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent / "aiorchestration"


def manifest(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def install(target="both", home=None, replace=False):
    home = Path(home or Path.home()).resolve()
    targets = []
    if target in {"codex", "both"}:
        targets.append(home / ".agents" / "skills" / "aiorchestration")
    if target in {"claude", "both"}:
        targets.append(home / ".claude" / "skills" / "aiorchestration")
    if not (SOURCE / "SKILL.md").is_file():
        raise ValueError("Package is incomplete: SKILL.md missing.")
    content = manifest(SOURCE)
    # Preflight all targets before any copy/backup; no silent partial conflict handling.
    for dest in targets:
        if dest.is_symlink():
            raise ValueError("Skill destination is a symlink; resolve it manually: " + str(dest))
        resolved = dest.resolve()
        if home not in resolved.parents or resolved == home or SOURCE.resolve() == resolved:
            raise ValueError("Destination must be a separate skill directory inside the selected home.")
        if dest.exists() and (not dest.is_dir() or manifest(dest) != content) and not replace:
            raise ValueError("Existing skill differs; inspect it and use --replace to back it up: " + str(dest))
    results = []
    for dest in targets:
        if dest.is_dir() and manifest(dest) == content:
            results.append((dest, "unchanged"))
            continue
        backup = None
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Complete the new copy before moving any existing installation.
        with tempfile.TemporaryDirectory(prefix=".aiorchestration-install-", dir=dest.parent) as tmp:
            staged = Path(tmp) / "aiorchestration"
            shutil.copytree(SOURCE, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if dest.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                # Outside discovery roots so the old skill does not appear as a duplicate.
                backup = home / ".aiorchestration" / "backups" / (dest.parent.parent.name + "-" + stamp)
                if home not in backup.resolve().parents:
                    raise ValueError("Backup path escaped the selected home.")
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest), str(backup))
            try:
                staged.rename(dest)
            except OSError:
                if backup and not dest.exists():
                    shutil.move(str(backup), str(dest))
                raise
        results.append((dest, "installed" + ("; backup: " + str(backup) if backup else "")))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["both", "codex", "claude"], default="both")
    parser.add_argument("--home", type=Path, help="Optional target user home (for portable/test installs)")
    parser.add_argument("--replace", action="store_true", help="Back up an existing different skill before replacing")
    args = parser.parse_args()
    try:
        for dest, status in install(args.target, args.home, args.replace):
            print(str(dest) + " — " + status)
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
