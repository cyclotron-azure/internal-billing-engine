"""Tests for the rollout half of task 06 (desktop-usage-capture):
client-package/configure.py, client-package/build.py, client-package/VERSION,
deploy/managed-settings.json, and the repo root .gitattributes.

06a (deploy/claude-transcript-usage.py itself) has its own test file,
tests/test_transcript_hook.py, and is not re-tested here.

configure.py is imported by file path (like the hook scripts) so this file
does not depend on client-package/ being an importable package. Every test
that touches "the filesystem configure.py writes to" points HOME at tmp_path
via monkeypatching configure.home() -- never the real ~/.claude or this
repo's own settings. No test contacts a real receiver: configure.verify is
monkeypatched to a stub wherever install/uninstall would otherwise call it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_PACKAGE_DIR = REPO_ROOT / "client-package"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def configure():
    """Fresh import of configure.py per test, so monkeypatches never leak."""
    return _load_module(CLIENT_PACKAGE_DIR / "configure.py", "configure_under_test")


ALL_FIVE_EVENTS = ("SessionStart", "CwdChanged", "DirectoryAdded", "SessionEnd",
                   "UserPromptSubmit")


def _install_args(**overrides):
    ns = argparse.Namespace(
        token="A" * 32,
        endpoint="https://receiver.example.internal:4318",
        allow_insecure=False,
        interactive=False,
        dry_run=False,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def _events_for(hooks: dict, needle: str) -> set:
    """Every event a hook whose command contains `needle` is registered on."""
    found = set()
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            inner = (group or {}).get("hooks", [])
            for h in inner:
                cmd = (h or {}).get("command", "")
                if needle.lower() in str(cmd).replace("\\", "/").lower():
                    found.add(event)
    return found


# ---------------------------------------------------------------------------
# AC13 (client-package side): per-hook event map
# ---------------------------------------------------------------------------

def test_apply_config_does_not_register_retired_transcript_hook(configure):
    # claude-transcript-usage.py was retired 2026-09-10: enrolment configures
    # OTLP, which a desktop session against a local folder already exports
    # identically to the CLI, so shipping/registering this hook double-bills
    # (see session f315633b: 1,066,833 'otlp' tokens + 850,966 'transcript'
    # tokens for the same session). It must never be installed again by
    # apply_config -- do not "restore" this assertion.
    obj = {}
    configure.apply_config(obj, "https://receiver.example.internal:4318", "T" * 32)
    events = _events_for(obj["hooks"], "claude-transcript-usage.py")
    assert events == set()


def test_apply_config_keeps_repo_tag_on_all_five_events(configure):
    obj = {}
    configure.apply_config(obj, "https://receiver.example.internal:4318", "T" * 32)
    events = _events_for(obj["hooks"], "claude-repo-tag.py")
    assert events == set(ALL_FIVE_EVENTS)


def test_apply_config_repo_tag_stays_async_on_user_prompt_submit(configure):
    obj = {}
    configure.apply_config(obj, "https://receiver.example.internal:4318", "T" * 32)
    for group in obj["hooks"]["UserPromptSubmit"]:
        for h in group["hooks"]:
            if "claude-repo-tag.py" in h["command"].replace("\\", "/"):
                assert h.get("async") is True


def test_hook_events_by_file_is_a_real_per_hook_map(configure):
    # Mutation guard for "the map is genuinely per-hook, not one shared
    # tuple": each entry's event set is independently defined, so adding a
    # second hook with a different event set (as transcript-usage once was)
    # is expressible. Only one hook ships today, so we assert the map's shape
    # rather than compare two entries that no longer both exist.
    assert set(configure.HOOK_EVENTS_BY_FILE["claude-repo-tag.py"]) == set(ALL_FIVE_EVENTS)
    assert isinstance(configure.HOOK_EVENTS_BY_FILE, dict)
    assert set(configure.HOOK_FILES) == {"claude-repo-tag.py"}
    # the retired hook is tracked for cleanup but is NOT a shipped hook file
    assert "claude-transcript-usage.py" not in configure.HOOK_FILES
    assert configure.RETIRED_HOOK_FILES == ("claude-transcript-usage.py",)
    assert set(configure.CLEANUP_HOOK_FILES) == {"claude-repo-tag.py", "claude-transcript-usage.py"}


# ---------------------------------------------------------------------------
# AC10: install -> uninstall round trip, both hooks
# ---------------------------------------------------------------------------

def test_install_then_uninstall_round_trips_settings(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)

    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True)
    settings_file = settings_dir / "settings.json"
    starting = {
        "permissions": {"allow": ["Bash(ls:*)"]},
        "theme": "dark",
        "hooks": {"Notification": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
    }
    settings_file.write_text(json.dumps(starting), encoding="utf-8")

    rc = configure.cmd_install(_install_args())
    assert rc == 0

    for hook_name in configure.HOOK_FILES:
        assert os.path.exists(configure.hook_path(hook_name)), hook_name

    mid, _ = configure.read_settings(str(settings_file))
    assert mid["permissions"] == starting["permissions"]
    assert mid["theme"] == starting["theme"]
    # the pre-existing, unrelated hook registration survives the merge
    assert mid["hooks"]["Notification"] == starting["hooks"]["Notification"]
    # the retired hook is never (re-)registered by a fresh install
    assert _events_for(mid["hooks"], "claude-transcript-usage.py") == set()
    assert _events_for(mid["hooks"], "claude-repo-tag.py") == set(ALL_FIVE_EVENTS)

    rc2 = configure.cmd_uninstall(argparse.Namespace(dry_run=False))
    assert rc2 == 0

    for hook_name in configure.HOOK_FILES:
        assert not os.path.exists(configure.hook_path(hook_name)), hook_name

    final, _ = configure.read_settings(str(settings_file))
    assert final == starting, "settings must return to exactly their starting state"


def test_uninstall_leaves_no_orphan_hook_entry_for_either_hook(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    (tmp_path / ".claude").mkdir(parents=True)

    configure.cmd_install(_install_args())
    configure.cmd_uninstall(argparse.Namespace(dry_run=False))

    obj, existed = configure.read_settings(str(tmp_path / ".claude" / "settings.json"))
    hooks = obj.get("hooks", {}) if existed else {}
    assert _events_for(hooks, "claude-repo-tag.py") == set()
    assert _events_for(hooks, "claude-transcript-usage.py") == set()


def test_reinstall_is_idempotent_no_duplicate_entries(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    (tmp_path / ".claude").mkdir(parents=True)

    configure.cmd_install(_install_args())
    configure.cmd_install(_install_args())  # re-run

    obj, _ = configure.read_settings(str(tmp_path / ".claude" / "settings.json"))
    hooks = obj["hooks"]
    # exactly one registration per event per hook, not two
    session_end_repo_tag_cmds = [
        h["command"]
        for group in hooks["SessionEnd"]
        for h in group["hooks"]
        if "claude-repo-tag.py" in h["command"].replace("\\", "/")
    ]
    assert len(session_end_repo_tag_cmds) == 1


# ---------------------------------------------------------------------------
# Retirement mechanism: RETIRED_HOOK_FILES / CLEANUP_HOOK_FILES.
#
# Dropping a hook out of HOOK_EVENTS_BY_FILE stops it being installed, but
# does NOT uninstall it from a machine that already has it -- the cleanup
# loops (strip-before-register in apply_config, and both loops in
# cmd_uninstall) iterate the hooks the code currently knows how to ship.
# Without RETIRED_HOOK_FILES feeding into CLEANUP_HOOK_FILES, a retired hook
# becomes invisible to the very code meant to remove it and keeps running
# forever on any machine that installed it before the retirement. This is
# exactly the bug hit during the 1.2.1 -> 1.3.0 change (claude-transcript-
# usage.py silently surviving on already-enrolled machines).
# ---------------------------------------------------------------------------

def _seed_legacy_registration(settings_file, configure, events=("SessionEnd",)):
    """Write a settings.json registering claude-transcript-usage.py, as a
    1.2.1 install would have left it, without going through today's
    apply_config (which no longer knows how to write that registration)."""
    hooks = {}
    cmd = configure.hook_command("claude-transcript-usage.py")
    for event in events:
        hooks[event] = [{"hooks": [{"type": "command", "command": cmd}]}]
    settings_file.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")


def test_install_strips_retired_hook_registration(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True)
    settings_file = settings_dir / "settings.json"
    _seed_legacy_registration(settings_file, configure)

    rc = configure.cmd_install(_install_args())
    assert rc == 0

    obj, _ = configure.read_settings(str(settings_file))
    assert _events_for(obj["hooks"], "claude-transcript-usage.py") == set(), (
        "a pre-existing registration of the retired hook must be stripped on install")
    assert _events_for(obj["hooks"], "claude-repo-tag.py") == set(ALL_FIVE_EVENTS)


def test_install_deletes_retired_hook_file(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    (tmp_path / ".claude").mkdir(parents=True)
    hook_dir = tmp_path / ".cyclotron"
    hook_dir.mkdir(parents=True)
    stale = hook_dir / "claude-transcript-usage.py"
    stale.write_text("# leftover 1.2.1 hook\n", encoding="utf-8")

    rc = configure.cmd_install(_install_args())
    assert rc == 0

    assert not stale.exists(), (
        "a retired hook's on-disk file must be deleted on install, not just "
        "unregistered, or it keeps running the moment it is re-registered")
    assert os.path.exists(configure.hook_path("claude-repo-tag.py"))


def test_uninstall_removes_retired_hook_registration_and_file(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True)
    settings_file = settings_dir / "settings.json"
    hook_dir_path = tmp_path / ".cyclotron"
    hook_dir_path.mkdir(parents=True)

    # Seed a machine that carries BOTH the current hook's registration and
    # the retired hook's registration, written directly (not through
    # apply_config, which would already strip the retired one on its own --
    # that would make this test pass without cmd_uninstall doing anything).
    repo_tag_cmd = configure.hook_command("claude-repo-tag.py")
    transcript_cmd = configure.hook_command("claude-transcript-usage.py")
    hooks = {event: [{"hooks": [{"type": "command", "command": repo_tag_cmd}]}]
             for event in ALL_FIVE_EVENTS}
    hooks["SessionEnd"].append({"hooks": [{"type": "command", "command": transcript_cmd}]})
    settings_file.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    assert _events_for(json.loads(settings_file.read_text())["hooks"],
                        "claude-transcript-usage.py") == {"SessionEnd"}, \
        "seed did not actually land the retired hook's registration"

    (hook_dir_path / "claude-repo-tag.py").write_text("# copy\n", encoding="utf-8")
    stale = hook_dir_path / "claude-transcript-usage.py"
    stale.write_text("# leftover 1.2.1 hook\n", encoding="utf-8")
    assert stale.exists()

    rc = configure.cmd_uninstall(argparse.Namespace(dry_run=False))
    assert rc == 0

    assert not stale.exists(), "uninstall must delete the retired hook's file too"
    final, existed = configure.read_settings(str(settings_file))
    final_hooks = final.get("hooks", {}) if existed else {}
    assert _events_for(final_hooks, "claude-transcript-usage.py") == set(), (
        "uninstall must strip the retired hook's registration too")
    assert _events_for(final_hooks, "claude-repo-tag.py") == set()


def test_upgrade_from_1_2_1_round_trips_to_exact_new_state(tmp_path, monkeypatch, configure):
    """A machine that installed the old two-hook 1.2.1 package, upgrading to
    the current package, must end up in EXACTLY today's state: the retired
    hook gone (file + registration), and only claude-repo-tag.py present."""
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True)
    settings_file = settings_dir / "settings.json"
    hook_dir = tmp_path / ".cyclotron"
    hook_dir.mkdir(parents=True)

    # Seed the full 1.2.1 state: both hook files on disk, both registered
    # (claude-repo-tag.py on all five events, claude-transcript-usage.py on
    # SessionEnd only -- the old contract).
    (hook_dir / "claude-repo-tag.py").write_text("# old repo-tag copy\n", encoding="utf-8")
    (hook_dir / "claude-transcript-usage.py").write_text("# old transcript copy\n", encoding="utf-8")
    old_cmd_repo = configure.hook_command("claude-repo-tag.py")
    old_cmd_transcript = configure.hook_command("claude-transcript-usage.py")
    hooks = {event: [{"hooks": [{"type": "command", "command": old_cmd_repo}]}]
             for event in ALL_FIVE_EVENTS}
    hooks["SessionEnd"].append({"hooks": [{"type": "command", "command": old_cmd_transcript}]})
    settings_file.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")

    rc = configure.cmd_install(_install_args())
    assert rc == 0

    # Retired hook: gone from disk and from settings, on both fronts.
    assert not (hook_dir / "claude-transcript-usage.py").exists()
    obj, _ = configure.read_settings(str(settings_file))
    assert _events_for(obj["hooks"], "claude-transcript-usage.py") == set()
    # Current hook: present on disk, registered on exactly its five events,
    # exactly once each (upgrade must not stack a duplicate registration
    # alongside the old claude-repo-tag.py entry that was already there).
    assert (hook_dir / "claude-repo-tag.py").exists()
    assert _events_for(obj["hooks"], "claude-repo-tag.py") == set(ALL_FIVE_EVENTS)
    for event in ALL_FIVE_EVENTS:
        cmds = [h["command"] for group in obj["hooks"][event] for h in group["hooks"]
                if "claude-repo-tag.py" in h["command"].replace("\\", "/")]
        assert len(cmds) == 1, "event %s has %d claude-repo-tag.py entries, want 1" % (event, len(cmds))


# ---------------------------------------------------------------------------
# AC: cmd_verify checks both hooks (extends the receiver-only check)
# ---------------------------------------------------------------------------

def test_verify_hooks_installed_passes_after_install(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    (tmp_path / ".claude").mkdir(parents=True)

    configure.cmd_install(_install_args())
    assert configure.verify_hooks_installed() is True


def test_verify_hooks_installed_fails_when_a_hook_file_is_missing(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    (tmp_path / ".claude").mkdir(parents=True)

    configure.cmd_install(_install_args())
    os.remove(configure.hook_path("claude-repo-tag.py"))

    assert configure.verify_hooks_installed() is False


def test_verify_hooks_installed_fails_when_registration_missing(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    (tmp_path / ".claude").mkdir(parents=True)

    configure.cmd_install(_install_args())
    # strip the registration but leave the file on disk
    obj, _ = configure.read_settings(str(tmp_path / ".claude" / "settings.json"))
    configure.strip_our_hooks(obj["hooks"], configure.hook_path("claude-repo-tag.py"))
    configure.write_settings(str(tmp_path / ".claude" / "settings.json"), obj)

    assert configure.verify_hooks_installed() is False


def test_cmd_verify_fails_overall_when_hooks_not_installed(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    (tmp_path / ".claude").mkdir(parents=True)
    # No install has happened, so hook files do not exist.
    rc = configure.cmd_verify(argparse.Namespace(
        endpoint="https://receiver.example.internal:4318", token="A" * 32))
    assert rc == 1


def test_cmd_verify_succeeds_when_hooks_installed_and_receiver_ok(tmp_path, monkeypatch, configure):
    monkeypatch.setattr(configure, "home", lambda: str(tmp_path))
    monkeypatch.setattr(configure, "verify", lambda endpoint, token, timeout=5.0: True)
    (tmp_path / ".claude").mkdir(parents=True)

    configure.cmd_install(_install_args())
    rc = configure.cmd_verify(argparse.Namespace(
        endpoint="https://receiver.example.internal:4318", token="A" * 32))
    assert rc == 0


# ---------------------------------------------------------------------------
# AC11: the two hook copies, content-equal after newline normalization
# (NOT byte-equal -- see the requirement/criterion 11: core.autocrlf=true on
# this machine plus client-package/.gitattributes pinning `*.py text eol=lf`
# already makes the existing precedent pair, claude-repo-tag.py, differ
# byte-for-byte between deploy/ (CRLF) and client-package/ (LF) in the
# working tree. A byte-equality assertion here would pass on the machine that
# authored the files and fail on the very next clone. Do not "strengthen"
# this back to a byte comparison.)
# ---------------------------------------------------------------------------

def test_transcript_hook_copies_are_equal_after_newline_normalization():
    deploy_bytes = (REPO_ROOT / "deploy" / "claude-transcript-usage.py").read_bytes()
    client_bytes = (REPO_ROOT / "client-package" / "claude-transcript-usage.py").read_bytes()
    assert deploy_bytes.replace(b"\r\n", b"\n") == client_bytes.replace(b"\r\n", b"\n")


def test_transcript_hook_client_copy_is_stdlib_only_and_present():
    client_copy = REPO_ROOT / "client-package" / "claude-transcript-usage.py"
    assert client_copy.exists()
    import ast
    tree = ast.parse(client_copy.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("billing"), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("billing"), node.module


# ---------------------------------------------------------------------------
# AC12: build.py CONTENTS includes the new hook (and gates scan_for_secrets)
# ---------------------------------------------------------------------------

@pytest.fixture()
def build_module():
    # build.py does `import configure` (bare, same-directory import), so
    # client-package/ must be on sys.path while it loads.
    sys.path.insert(0, str(CLIENT_PACKAGE_DIR))
    try:
        yield _load_module(CLIENT_PACKAGE_DIR / "build.py", "build_under_test")
    finally:
        try:
            sys.path.remove(str(CLIENT_PACKAGE_DIR))
        except ValueError:
            pass


def test_build_contents_excludes_retired_transcript_hook(build_module):
    # claude-transcript-usage.py is deliberately NOT shipped (retired
    # 2026-09-10): OTLP already captures desktop-app usage on any machine
    # this installer configures, so shipping the hook double-bills sessions.
    # Do not "restore" it to CONTENTS -- see configure.HOOK_EVENTS_BY_FILE's
    # comment for the incident that caused the retirement.
    assert "claude-transcript-usage.py" not in build_module.CONTENTS
    assert "claude-repo-tag.py" in build_module.CONTENTS


def test_build_contents_files_all_exist_on_disk(build_module):
    # Every name build.py ships must actually exist next to it, or the
    # archive builds "fine" and installs nothing for the new hook.
    missing = [n for n in build_module.CONTENTS
               if not (CLIENT_PACKAGE_DIR / n).exists()]
    assert missing == []


def test_pilot_package_not_touched():
    # Task 06b's write fence forbids touching pilot-package/; assert nothing
    # here references it as a shipped path.
    assert not (REPO_ROOT / "pilot-package" / "claude-transcript-usage.py").exists()


# ---------------------------------------------------------------------------
# AC9 / AC13 (deploy side): deploy/managed-settings.json
# ---------------------------------------------------------------------------

def _load_managed_settings() -> dict:
    path = REPO_ROOT / "deploy" / "managed-settings.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_managed_settings_is_valid_json_dict():
    obj = _load_managed_settings()
    assert isinstance(obj, dict)
    assert isinstance(obj["hooks"], dict)


def test_managed_settings_preserves_every_existing_registration():
    obj = _load_managed_settings()
    hooks = obj["hooks"]
    for event in ALL_FIVE_EVENTS:
        assert event in hooks
        assert _events_for({event: hooks[event]}, "claude-repo-tag.py") == {event}


def test_managed_settings_registers_transcript_hook_session_end_only():
    obj = _load_managed_settings()
    hooks = obj["hooks"]
    assert _events_for(hooks, "claude-transcript-usage.py") == {"SessionEnd"}
    # and it must NOT have been added to any of the other four
    for event in ("SessionStart", "CwdChanged", "DirectoryAdded", "UserPromptSubmit"):
        assert "claude-transcript-usage.py" not in json.dumps(hooks.get(event, []))


def test_managed_settings_preserves_placeholder_token_convention():
    obj = _load_managed_settings()
    assert obj["env"]["CLAUDE_BILLING_TOKEN"] == "REPLACE_WITH_FLEET_BILLING_TOKEN"
    assert "REPLACE_WITH_FLEET_BILLING_TOKEN" in obj["env"]["OTEL_EXPORTER_OTLP_HEADERS"]
    # never a real-looking 64-char hex token committed here
    import re
    assert not re.search(r"\b[0-9a-f]{64}\b", json.dumps(obj))


# ---------------------------------------------------------------------------
# AC14: .gitattributes pins, and that the pre-existing ones survive
# ---------------------------------------------------------------------------

def test_gitattributes_pins_deploy_py_to_lf():
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "deploy/*.py text eol=lf" in text


def test_gitattributes_marks_golden_baseline_as_binary():
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "tests/golden/** -text" in text


def test_gitattributes_preserves_preexisting_entries():
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    for line in (
        "*.zip binary",
        "_goals/LEARNINGS.md merge=union",
        "_goals/ESCALATIONS.md merge=union",
        "_goals/*/orchestration-log.md merge=union",
        "*.sh text eol=lf",
        "*.ps1 text eol=lf",
    ):
        assert line in text


def test_git_check_attr_reports_lf_for_deploy_python_hooks():
    """Live proof, not just a text-file assertion: git itself resolves the
    attribute to eol=lf for the deploy/ hooks."""
    if shutil_which("git") is None:
        pytest.skip("git not on PATH")
    out = subprocess.run(
        ["git", "check-attr", "eol", "--", "deploy/claude-transcript-usage.py",
         "deploy/claude-repo-tag.py"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, check=True,
    ).stdout
    assert "deploy/claude-transcript-usage.py: eol: lf" in out
    assert "deploy/claude-repo-tag.py: eol: lf" in out


def shutil_which(name: str):
    import shutil as _shutil
    return _shutil.which(name)


# ---------------------------------------------------------------------------
# VERSION bump
# ---------------------------------------------------------------------------

def test_version_bumped_past_1_1_0():
    version = (REPO_ROOT / "client-package" / "VERSION").read_text(encoding="utf-8").strip()
    assert version != "1.1.0"
    parts = tuple(int(p) for p in version.split("."))
    assert parts > (1, 1, 0)
