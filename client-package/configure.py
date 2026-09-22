#!/usr/bin/env python3
"""Install/uninstall the Claude Code usage-billing client config.

Cross-platform core. `install.sh` (macOS) and `install.ps1` (Windows) are thin
shims that locate a Python 3 and hand off to this file, so the settings-merge
logic exists exactly once instead of being reimplemented per shell.

    python3 configure.py install   --token <TOKEN> --endpoint https://host:4318
    python3 configure.py uninstall
    python3 configure.py verify    --token <TOKEN> --endpoint https://host:4318

Stdlib only, Python 3.8+ (macOS system python3 is 3.9).

ONE-CLICK MODE
  If `billing-config.json` sits next to this file, the endpoint and token are
  read from it and both flags become optional - that is what makes the
  double-clickable launchers (Install.command / Install.bat) work with no
  arguments at all. `build.py` stamps that file into the zip; it is never
  committed. Explicit flags still win over the baked values.

  A packaged config carries a live token, so the built zip IS a credential.
  See ADMIN.md before you decide how to distribute it.

WHY THIS EXISTS AND pilot-package/install.sh DOES NOT SUFFICE
  * install.sh refuses to touch an existing ~/.claude/settings.json and tells the
    developer to hand-merge JSON. Most developers already have that file, so at
    company scale that is a support ticket per developer. This does a real merge.
  * install.sh is bash; Windows developers cannot run it. The hook also cannot be
    invoked by bare path on Windows (no .py association without the py launcher),
    so the hook command must name the interpreter explicitly.
  * the earlier, now-removed pilot package's settings.json set OTEL_LOGS_EXPORTER=none,
    which deploy/README.md warns makes Claude Code error on startup and exit. We omit
    the key, and delete it from machines that ran the pilot.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import stat
import sys
import time
import urllib.error
import urllib.request

CONFIG_NAME = "billing-config.json"

# Every hook this installer manages, and the event set each is registered on.
# claude-repo-tag.py keeps all five events, unchanged from before the second
# hook existed. claude-transcript-usage.py is SessionEnd ONLY: it walks the
# transcript tree for unshipped usage, and registering that walk on
# UserPromptSubmit would run a full transcript sweep on every prompt -
# precisely the latency ASYNC_EVENTS below exists to keep off the critical
# path. Generalizing this to a per-hook map (instead of one shared tuple) is
# what makes that distinction expressible at all.
# claude-transcript-usage.py is DELIBERATELY NOT REGISTERED (2026-09-10).
# It was built to capture desktop-app usage the OTLP exporter was believed not
# to emit. Measured on a live receiver, that premise is false: a desktop session
# run against a LOCAL folder exports OTLP exactly like the CLI, because the
# desktop app reads the same ~/.claude/settings.json env block this installer
# writes. Session f315633b arrived twice -- 1,066,833 tokens via `otlp` and
# 850,966 via `transcript` -- and bill.py's double-billing detector flagged it.
# Enrolment is what configures OTLP, so on any machine where this hook would be
# installed, it is redundant by construction and inflates the invoice.
# The hook itself is kept in the repo (deploy/claude-transcript-usage.py) for
# the case it was designed for: a machine that runs Claude Code WITHOUT OTLP
# configured. Re-add the entry below to ship it. Cloud-executed desktop sessions
# write no local transcript at all and are out of its reach either way -- those
# are covered by the Analytics reconciliation residual instead.
HOOK_EVENTS_BY_FILE = {
    "claude-repo-tag.py": ("SessionStart", "CwdChanged", "DirectoryAdded",
                           "SessionEnd", "UserPromptSubmit"),
}
HOOK_FILES = tuple(HOOK_EVENTS_BY_FILE.keys())

# Hooks this installer USED to ship and must now actively remove. Dropping a
# name out of HOOK_EVENTS_BY_FILE stops it being installed, but it does NOT
# uninstall it from a machine that already has it -- the cleanup loops iterate
# the hooks we know about, so a forgotten hook becomes invisible to the very
# code meant to remove it, and keeps running forever. (Observed exactly that
# during the 1.2.1 -> 1.3.0 change.) Anything retired here stays listed so
# install and uninstall both strip it.
RETIRED_HOOK_FILES = (
    "claude-transcript-usage.py",   # retired 2026-09-10, see note above
)

# Every hook name cleanup must consider: what we ship now, plus what we retired.
CLEANUP_HOOK_FILES = HOOK_FILES + RETIRED_HOOK_FILES

# UserPromptSubmit re-tags on every prompt so a single missed delivery
# self-heals; async so a slow receiver never adds latency to a prompt. Only
# claude-repo-tag.py is ever registered on this event, so in practice this
# applies to it alone.
ASYNC_EVENTS = frozenset({"UserPromptSubmit"})

# Env keys this installer owns. Uninstall removes exactly these and nothing else.
OWNED_ENV_KEYS = (
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "OTEL_METRICS_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_METRIC_EXPORT_INTERVAL",
    "OTEL_METRICS_INCLUDE_SESSION_ID",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "CLAUDE_BILLING_RECEIVER",
    "CLAUDE_BILLING_TOKEN",
    # Not set by us. Listed so install/uninstall strip the pilot's bad value.
    "OTEL_LOGS_EXPORTER",
)


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def package_dir() -> str:
    """The unpacked package directory - where this script and its siblings live."""
    return os.path.dirname(os.path.abspath(__file__))


def load_baked_config() -> dict:
    """Read `billing-config.json` from the package, if the build stamped one in.

    Absent file is the normal case for a source checkout and for a zip built with
    `--no-config`; it just means the flags are required. A present-but-broken file
    is fatal - silently falling back to "no endpoint" would turn a typo in the
    build into a confusing "--endpoint is required" for every developer.
    """
    path = os.path.join(package_dir(), CONFIG_NAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            obj = json.load(fh)
    except ValueError as e:
        raise SystemExit("%s is not valid JSON (%s) - rebuild the package." % (path, e))
    if not isinstance(obj, dict):
        raise SystemExit("%s must contain a JSON object." % path)
    return obj


COLLECTION_NOTICE = """
This configures Claude Code to report usage to your company's billing receiver.

  Collected:     the git remote of the repo you work in, the model, token counts
                 and cost, your work email, a session id, timestamps, and the
                 working directory path of the repo you're in.
  Not collected: your prompts, your code, or file contents.

It installs under your home directory only, needs no administrator rights, and
is reversible - see INSTRUCTIONS.md, or run the Uninstall launcher.
"""


def confirm_or_exit() -> None:
    """Show what is collected and take one keystroke before writing anything.

    The launchers are double-clicked, so this is the only point at which someone
    who opened the wrong file can back out. If stdin is not a terminal (piped or
    scripted install) there is nobody to ask, so proceed.
    """
    print(COLLECTION_NOTICE)
    if not sys.stdin or not sys.stdin.isatty():
        return
    try:
        answer = input("Press Enter to install, or type n and press Enter to cancel: ")
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nCancelled - nothing was changed.")
    if answer.strip().lower().startswith("n"):
        raise SystemExit("Cancelled - nothing was changed.")


def home() -> str:
    return os.path.expanduser("~")


def settings_path() -> str:
    return os.path.join(home(), ".claude", "settings.json")


def hook_dir() -> str:
    return os.path.join(home(), ".cyclotron")


def hook_path(hook_name: str) -> str:
    return os.path.join(hook_dir(), hook_name)


def interpreter() -> str:
    """Absolute path to the Python that will run the hook.

    Uses the interpreter running this installer, so the hook is guaranteed to
    run under a Python that actually exists. On Windows the Microsoft Store
    aliases under WindowsApps are stubs that fail when invoked non-interactively
    - refuse them rather than register a hook that silently never fires.
    """
    exe = os.path.realpath(sys.executable)
    if not exe or not os.path.exists(exe):
        raise SystemExit("Cannot determine the running Python interpreter.")
    if "windowsapps" in exe.replace("\\", "/").lower():
        raise SystemExit(
            "This Python is a Microsoft Store alias stub (%s), which cannot run\n"
            "the hook. Install real Python 3 and re-run:\n"
            "    winget install --id Python.Python.3.12 --scope user" % exe)
    return exe


def hook_command(hook_name: str) -> str:
    """Shell command Claude Code runs for each hook event.

    Both paths are quoted: a Windows profile directory or a macOS home can
    contain spaces, and Claude Code passes this string to a shell.
    """
    return '"%s" "%s"' % (interpreter(), hook_path(hook_name))


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate_endpoint(url: str, allow_insecure: bool) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise SystemExit(
            "No receiver endpoint. This package has no %s baked in, so pass one:\n"
            "    --endpoint https://otel-billing.internal.example.com:4318" % CONFIG_NAME)
    if not re.match(r"^https?://", url):
        raise SystemExit("--endpoint must start with https:// (or http:// with --allow-insecure): %r" % url)
    if url.startswith("http://") and not allow_insecure:
        raise SystemExit(
            "Refusing to install against a plaintext endpoint:\n"
            "    %s\n"
            "Every export carries the developer's work email, repo names and cost,\n"
            "plus the shared token, in cleartext - anyone who captures the token can\n"
            "write billing rows. Use an https:// endpoint, or pass --allow-insecure\n"
            "if you have accepted that risk in writing." % url)
    return url


def validate_token(token: str) -> str:
    token = (token or "").strip()
    if not token:
        raise SystemExit(
            "No token. This package has no %s baked in, so pass one:\n"
            "    --token <TOKEN>   (get it from the billing owner)" % CONFIG_NAME)
    if token.startswith("PASTE_") or token.startswith("REPLACE_"):
        raise SystemExit("--token is still the placeholder %r - paste the real token." % token)
    if len(token) < 16:
        raise SystemExit("--token looks too short (%d chars); expected a 32-byte hex value." % len(token))
    return token


def mask(token: str) -> str:
    return (token[:6] + "..." + token[-4:]) if len(token) > 12 else "..."


def _hint(launcher: str, command: str) -> str:
    """Name the double-clickable launcher when the package ships one, else the CLI.

    A developer who got here by double-clicking should be told to double-click
    something, not handed a shell incantation.
    """
    if os.path.exists(os.path.join(package_dir(), launcher)):
        return "double-click %s (in this folder)" % launcher
    return command


def uninstall_hint() -> str:
    """The uninstall step for the platform the developer is actually on."""
    if os.name == "nt":
        return _hint("Uninstall.bat", ".\\install.ps1 -Uninstall")
    return _hint("Uninstall.command", "bash install.sh uninstall")


def verify_hint() -> str:
    if os.name == "nt":
        return _hint("Verify.bat", ".\\install.ps1 -Verify -Endpoint <RECEIVER_URL>")
    return _hint("Verify.command", "bash install.sh verify --endpoint <RECEIVER_URL>")


# --------------------------------------------------------------------------
# settings.json read / merge / write
# --------------------------------------------------------------------------

def read_settings(path: str):
    """Parse settings.json, tolerating a UTF-8 BOM. Returns (obj, existed)."""
    if not os.path.exists(path):
        return {}, False
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()
    if not text.strip():
        return {}, True
    try:
        obj = json.loads(text)
    except ValueError as e:
        raise SystemExit(
            "%s is not valid JSON (%s).\n"
            "Fix or move it, then re-run - refusing to overwrite a file we cannot parse."
            % (path, e))
    if not isinstance(obj, dict):
        raise SystemExit("%s must contain a JSON object, got %s." % (path, type(obj).__name__))
    return obj, True


def write_settings(path: str, obj) -> None:
    """Write atomically, without a BOM, so a crash cannot truncate settings.json."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def backup_settings(path: str) -> str:
    if not os.path.exists(path):
        return ""
    dest = "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, dest)
    return dest


def strip_our_hooks(hooks: dict, hook_file: str) -> int:
    """Remove hook entries pointing at our hook file. Returns how many went.

    Makes install idempotent (re-running never stacks duplicates) and lets
    uninstall reverse precisely, including entries written by the older
    pilot-package installer whose command was a bare path.
    """
    needle = os.path.basename(hook_file).lower()
    removed = 0
    for event in list(hooks.keys()):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            inner = group.get("hooks")
            if not isinstance(inner, list):
                kept_groups.append(group)
                continue
            kept = []
            for h in inner:
                cmd = (h or {}).get("command", "") if isinstance(h, dict) else ""
                if needle in str(cmd).replace("\\", "/").lower():
                    removed += 1
                else:
                    kept.append(h)
            if kept:
                group["hooks"] = kept
                kept_groups.append(group)
            # a group emptied of our hook is dropped entirely
        if kept_groups:
            hooks[event] = kept_groups
        else:
            hooks.pop(event, None)
    return removed


def apply_config(obj: dict, endpoint: str, token: str) -> dict:
    env = obj.get("env")
    if not isinstance(env, dict):
        env = {}
    # Strip the pilot's OTEL_LOGS_EXPORTER=none, which breaks startup/exit.
    env.pop("OTEL_LOGS_EXPORTER", None)
    env.update({
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
        "OTEL_METRIC_EXPORT_INTERVAL": "10000",
        "OTEL_METRICS_INCLUDE_SESSION_ID": "true",
        "OTEL_EXPORTER_OTLP_HEADERS": "X-Billing-Token=%s" % token,
        "CLAUDE_BILLING_RECEIVER": endpoint,
        "CLAUDE_BILLING_TOKEN": token,
    })
    obj["env"] = env

    hooks = obj.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    # Strip both hooks' prior entries first (idempotent re-install), THEN
    # register each on its own event set - a hook removed from one machine's
    # settings must never leave the other hook's entries behind either.
    for hook_name in CLEANUP_HOOK_FILES:
        strip_our_hooks(hooks, hook_path(hook_name))
    for hook_name, events in HOOK_EVENTS_BY_FILE.items():
        cmd = hook_command(hook_name)
        for event in events:
            entry = {"type": "command", "command": cmd}
            if event in ASYNC_EVENTS:
                entry["async"] = True
            groups = hooks.get(event)
            if not isinstance(groups, list):
                groups = []
            groups.append({"hooks": [entry]})
            hooks[event] = groups
    obj["hooks"] = hooks
    return obj


# --------------------------------------------------------------------------
# receiver verification
# --------------------------------------------------------------------------

def verify(endpoint: str, token: str, timeout: float = 5.0) -> bool:
    """Check the receiver is reachable and accepts the token.

    POSTs an empty body to /v1/ping. The receiver checks auth before routing the
    path, and acknowledges unrecognised paths without storing anything, so this
    proves reachability + auth while writing nothing into billing truth.
    """
    url = endpoint.rstrip("/") + "/v1/ping"
    req = urllib.request.Request(
        url, data=b"{}", method="POST",
        headers={"Content-Type": "application/json", "X-Billing-Token": token})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        resp.read()
        print("  [ok]   receiver reachable and token accepted (HTTP %s)" % resp.status)
        print("         note: a receiver running without RECEIVER_AUTH_TOKEN accepts any")
        print("         token, so this confirms reachability, not that the token is right.")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("  [FAIL] receiver reachable but REJECTED the token (HTTP 401).")
            print("         Telemetry would be silently dropped. Check the token with the billing owner.")
        else:
            print("  [WARN] receiver returned HTTP %s. Reachable, but not the expected 200." % e.code)
        return False
    except Exception as e:  # noqa: BLE001 - report any failure mode plainly
        print("  [FAIL] cannot reach %s" % url)
        print("         %s: %s" % (type(e).__name__, e))
        print("         On VPN? Claude Code buffers in memory only and drops datapoints")
        print("         on exit, so sessions started while unreachable are never billed.")
        return False


def verify_hooks_installed() -> bool:
    """Confirm BOTH hooks are registered on their correct event set and their
    files exist on disk. Static check only - never runs a hook, never
    contacts the receiver.

    Extends `cmd_verify`, which previously checked only receiver reachability
    and no hook registration at all.
    """
    ok = True
    obj, existed = read_settings(settings_path())
    hooks = obj.get("hooks") if existed else {}
    if not isinstance(hooks, dict):
        hooks = {}
    for hook_name, expected_events in HOOK_EVENTS_BY_FILE.items():
        dest = hook_path(hook_name)
        if not os.path.exists(dest):
            print("  [FAIL] %s is not installed (expected at %s)" % (hook_name, dest))
            ok = False
            continue
        needle = hook_name.lower()
        registered = set()
        for event, groups in hooks.items():
            if not isinstance(groups, list):
                continue
            for group in groups:
                inner = (group or {}).get("hooks") if isinstance(group, dict) else None
                if not isinstance(inner, list):
                    continue
                for h in inner:
                    cmd = (h or {}).get("command", "") if isinstance(h, dict) else ""
                    if needle in str(cmd).replace("\\", "/").lower():
                        registered.add(event)
        missing = set(expected_events) - registered
        extra = registered - set(expected_events)
        if missing:
            print("  [FAIL] %s missing from event(s): %s" % (hook_name, ", ".join(sorted(missing))))
            ok = False
        elif extra:
            print("  [WARN] %s also registered on unexpected event(s): %s" % (hook_name, ", ".join(sorted(extra))))
        else:
            print("  [ok]   %s registered on %s" % (hook_name, ", ".join(expected_events)))
    return ok


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_install(args) -> int:
    cfg = load_baked_config()
    # Explicit flags beat the baked values, so an admin can retarget a packaged
    # zip at a staging receiver without rebuilding it.
    endpoint = validate_endpoint(
        args.endpoint or cfg.get("endpoint", ""),
        args.allow_insecure or bool(cfg.get("allow_insecure", False)))
    token = validate_token(args.token or cfg.get("token", ""))
    py = interpreter()

    if args.interactive:
        confirm_or_exit()
        print("")

    srcs = {}
    for hook_name in HOOK_FILES:
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), hook_name)
        if not os.path.exists(src):
            raise SystemExit("Cannot find %s next to this script - is the package intact?" % hook_name)
        srcs[hook_name] = src

    print("Claude Code usage-billing client - install")
    print("  platform    %s (%s)" % (platform.system(), platform.machine()))
    print("  python      %s  (%s)" % (platform.python_version(), py))
    print("  endpoint    %s%s" % (endpoint, "   [INSECURE]" if endpoint.startswith("http://") else ""))
    print("  token       %s" % mask(token))
    print("  settings    %s" % settings_path())
    for hook_name in HOOK_FILES:
        print("  hook        %s" % hook_path(hook_name))
    if cfg and not (args.endpoint and args.token):
        print("  source      %s (baked into this package)" % CONFIG_NAME)

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    os.makedirs(hook_dir(), exist_ok=True)

    # Delete retired hooks left behind by an older version of this package.
    # Their registrations are stripped above, but an orphaned .py sitting in
    # the hook dir is confusing to anyone debugging later, and would run again
    # the moment someone re-added a registration by hand.
    for hook_name in RETIRED_HOOK_FILES:
        stale = hook_path(hook_name)
        if os.path.exists(stale):
            os.remove(stale)
            print("    removed retired hook -> %s" % stale)

    for hook_name, src in srcs.items():
        dest = hook_path(hook_name)
        shutil.copy2(src, dest)
        if os.name == "posix":
            st = os.stat(dest)
            os.chmod(dest, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print("\n  copied hook -> %s" % dest)

    path = settings_path()
    obj, existed = read_settings(path)
    if existed:
        bak = backup_settings(path)
        print("  backed up existing settings -> %s" % bak)
        print("  merging (your other settings are preserved)")
    else:
        print("  creating a new settings.json")
    apply_config(obj, endpoint, token)
    write_settings(path, obj)
    print("  wrote %s" % path)

    print("\nVerifying receiver:")
    ok = verify(endpoint, token)

    if ok:
        print("\nDone. Telemetry starts with your NEXT Claude Code session.")
        print("Sessions must start inside a git repo that has an 'origin' remote,")
        print("otherwise usage is recorded as 'unknown' and cannot be attributed.")
    else:
        # Settings are written, but nothing will actually be recorded. Say so
        # plainly rather than reporting success the developer cannot rely on.
        print("\nSettings were written, but the receiver check above FAILED.")
        print("Nothing will be billed until that is resolved - resolve it, then re-run:")
        print("    %s" % verify_hint())
    print("To remove: %s" % uninstall_hint())
    return 0 if ok else 1


def cmd_uninstall(args) -> int:
    print("Claude Code usage-billing client - uninstall")
    path = settings_path()
    obj, existed = read_settings(path)

    if existed:
        if not args.dry_run:
            bak = backup_settings(path)
            print("  backed up settings -> %s" % bak)
        env = obj.get("env")
        removed_env = []
        if isinstance(env, dict):
            for k in OWNED_ENV_KEYS:
                if k in env:
                    env.pop(k)
                    removed_env.append(k)
            if not env:
                obj.pop("env", None)
        hooks = obj.get("hooks")
        removed_hooks = 0
        if isinstance(hooks, dict):
            for hook_name in CLEANUP_HOOK_FILES:
                removed_hooks += strip_our_hooks(hooks, hook_path(hook_name))
            if not hooks:
                obj.pop("hooks", None)
        print("  removed %d env keys, %d hook entries" % (len(removed_env), removed_hooks))
        for k in removed_env:
            print("    - %s" % k)
        if not args.dry_run:
            write_settings(path, obj)
            print("  wrote %s" % path)
    else:
        print("  no %s - nothing to clean" % path)

    for hook_name in CLEANUP_HOOK_FILES:
        dest = hook_path(hook_name)
        if os.path.exists(dest):
            if not args.dry_run:
                os.remove(dest)
            print("  removed hook %s" % dest)
    try:
        if not args.dry_run and os.path.isdir(hook_dir()) and not os.listdir(hook_dir()):
            os.rmdir(hook_dir())
            print("  removed empty %s" % hook_dir())
    except OSError:
        pass

    if args.dry_run:
        print("\n--dry-run: nothing written.")
    else:
        print("\nRemoved. Telemetry stops with your next Claude Code session.")
    return 0


def cmd_verify(args) -> int:
    cfg = load_baked_config()
    endpoint = validate_endpoint(args.endpoint or cfg.get("endpoint", ""), True)
    token = (args.token or "").strip()
    if not token:
        # Prefer what is actually installed - verifying the machine's real
        # configuration is the point. Fall back to the packaged value.
        obj, _ = read_settings(settings_path())
        token = (obj.get("env") or {}).get("CLAUDE_BILLING_TOKEN", "")
        if token:
            print("Using token from %s" % settings_path())
        else:
            token = (cfg.get("token") or "").strip()
            if not token:
                raise SystemExit(
                    "No --token given, none in settings.json, and no %s in this "
                    "package." % CONFIG_NAME)
            print("Using token baked into this package (%s)" % CONFIG_NAME)
    print("Checking installed hooks:")
    hooks_ok = verify_hooks_installed()

    print("Verifying %s with token %s:" % (endpoint, mask(token)))
    receiver_ok = verify(endpoint, token)
    return 0 if (hooks_ok and receiver_ok) else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install the Claude Code usage-billing client config.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # --token/--endpoint are optional: a packaged zip carries billing-config.json
    # and the launchers pass no arguments at all. Missing in both places is
    # caught by validate_* with a message that says so.
    p = sub.add_parser("install")
    p.add_argument("--token", default="")
    p.add_argument("--endpoint", default="")
    p.add_argument("--allow-insecure", action="store_true",
                   help="permit a plaintext http:// endpoint (not for fleet use)")
    p.add_argument("--interactive", action="store_true",
                   help="show what is collected and wait for a keystroke first "
                        "(used by the double-click launchers)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("uninstall")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("verify")
    p.add_argument("--endpoint", default="")
    p.add_argument("--token", default="")
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
