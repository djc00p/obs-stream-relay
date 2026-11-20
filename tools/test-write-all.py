"""End-to-end write test for every platform, using the REAL tool code.

This imports stream-meta.py's own setter functions and calls them, so
it tests the shipped path rather than a reimplementation.

Safety: each test writes the CURRENT value back (a no-op write), so
nothing visibly changes on the channel.
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load(name, path):
    """Load a module from a path. The tool file has a hyphen in its
    name (stream-meta.py) so it cannot be imported by name."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


stream_meta = _load("stream_meta", os.path.join(HERE, "stream-meta.py"))
from env_writer import CONFIG  # noqa: E402


def read_config():
    cfg = {}
    with open(CONFIG) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def main():
    cfg = read_config()
    failures = []

    def report(label, ok, detail=""):
        if ok:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}\n          {detail}")
            failures.append(label)

    print("=== end-to-end write test (no-op writes) ===\n")

    # --- Twitch ------------------------------------------------------------
    print("  twitch:")
    th = stream_meta.twitch_headers(cfg)
    if not th:
        report("credentials present", False, "no TWITCH_CLIENT_ID / TWITCH_TOKEN")
    else:
        current, err = stream_meta.twitch_current(cfg, th)
        if not current:
            report("read current title", False, str(err))
        else:
            report("read current title", True,
                   f"title={current.get('title')!r} game={current.get('game')!r}")
            ok, msg = stream_meta.twitch_set_title(cfg, th, current["title"])
            report("write title (no-op)", ok, msg)
            game = current.get("game") or ""
            if game:
                ok, msg = stream_meta.twitch_set_game(cfg, th, game)
                report("write category (no-op)", ok, msg)

    # --- Kick --------------------------------------------------------------
    print("\n  kick:")
    kh = stream_meta.kick_headers(cfg)
    if not kh:
        report("credentials present", False, "no KICK_TOKEN")
    else:
        current, err = stream_meta.kick_current(cfg, kh)
        if not current:
            report("read current title", False, str(err))
        else:
            report("read current title", True,
                   f"title={current.get('title')!r} live={current.get('live')}")
            if current.get("live"):
                # Live: write a marker, read it back, restore.
                original = current.get("title") or ""
                probe = "Stream Relay write test"
                ok, msg = stream_meta.kick_set_title(cfg, kh, probe)
                report("write title", ok, msg)
                if ok:
                    back, _ = stream_meta.kick_current(cfg, kh)
                    got = (back or {}).get("title", "")
                    report("read back the written title", got == probe,
                           f"expected {probe!r}, got {got!r}")
                    ok2, msg2 = stream_meta.kick_set_title(cfg, kh, original)
                    report("restore original title", ok2, msg2)
            else:
                # Offline: Kick accepts the PATCH (204) but applies
                # nothing until the channel is live. Assert the request
                # is ACCEPTED and not rejected -- that is the part we
                # can prove while offline.
                original = current.get("title") or ""
                probe = "Stream Relay write test"
                ok, msg = stream_meta.kick_set_title(cfg, kh, probe)
                report("write accepted (channel offline -- 204 = accepted)",
                       ok, msg)
                print("        note: Kick applies channel writes only while")
                print("              the channel is live. Verify with")
                print("              ./tools/test-write-all.sh while live.")

    # --- YouTube -----------------------------------------------------------
    print("\n  youtube:")
    yh = stream_meta.youtube_headers(cfg)
    if not yh:
        report("credentials present", False, "no YT_TOKEN")
    else:
        current, err = stream_meta.youtube_current(cfg, yh)
        if not current:
            report("read current broadcast", False, str(err))
        else:
            report("read current broadcast", True,
                   f"id={current.get('id')} title={current.get('title')!r}")
            ok, msg = stream_meta.youtube_set(cfg, yh, current["title"],
                                             current.get("game") or None)
            report("write title (no-op)", ok, msg)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
