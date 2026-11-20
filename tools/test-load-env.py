#!/usr/bin/env python3
"""Test that load-env.sh loads values WITHOUT executing the file.

The old approach sourced the env file, which ran it as shell. This
test proves the parser:

  1. reads a normal KEY=VALUE file
  2. preserves values containing shell metacharacters (an &, a $, a
     backtick) literally
  3. does NOT execute a command in the file
  4. does NOT perform variable expansion in a value
  5. strips one layer of quotes
  6. rejects malformed lines and reports them
  7. ignores comments and blank lines

Usage:
    python3 tools/test-load-env.py
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOADER = os.path.join(HERE, "load-env.sh")

failures = []


def check(label, ok, detail=""):
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}")
        if detail:
            print(f"          {detail}")
        failures.append(label)


def load(env_body, extra=""):
    """Source load-env.sh against a temp env file; return the values.

    The loader runs inside a function so it does not pollute the
    caller's shell, and the values are printed from inside that scope.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
        f.write(env_body)
        path = f.name
    try:
        # Print every variable that was loaded, one per line, as
        # KEY=value. This runs in the same shell as the loader so the
        # loaded variables are in scope.
        # Print the loaded variables using printenv, which reads the
        # exported environment. Referencing ${ALSO-BAD-} in shell
        # would be parsed as ${ALSO} minus "BAD", which is a test bug,
        # not a loader bug.
        printer = ""
        for key in ("A", "B", "KEY", "TOKEN", "GOOD", "ALSO-BAD", "EVIL",
                    "SAFE"):
            printer += (f'v=$(printenv "{key}" 2>/dev/null || true); '
                        f'printf "%s=%s\\n" "{key}" "$v"\n')
        script = f'. "{LOADER}" "{path}"\n{printer}{extra}\n'
        p = subprocess.run(["bash", "-c", script],
                           capture_output=True, text=True, timeout=30)
        return p.stdout, p.stderr, p.returncode
    finally:
        os.unlink(path)


print("=== load-env.sh self-test ===\n")

# 1. A normal file loads.
out, err, rc = load('A="one"\nB=two\n')
check("normal file loads without error", "error" not in err.lower(), err)
check("quoted value loads", "A=one" in out, out)
check("unquoted value loads", "B=two" in out, out)

# 2. Shell metacharacters survive literally.
out, err, rc = load('KEY="a&b"\n')
check("ampersand preserved", "KEY=a&b" in out, out)

out, err, rc = load('KEY="a b c"\n')
check("spaces preserved", "KEY=a b c" in out, out)

out, err, rc = load("KEY='x$y'\n")
check("dollar NOT expanded", "KEY=x$y" in out,
      f"expected a literal x$y, got: {out}")

out, err, rc = load('KEY="`id`"\n')
check("backticks NOT executed", "KEY=`id`" in out,
      f"expected literal backticks, got: {out}")

# 3. A command in the file must not run.
with tempfile.TemporaryTemporaryFile if False else tempfile.NamedTemporaryFile(
        "w", suffix=".env", delete=False) as f:
    f.write("EVIL=$(touch /tmp/load-env-pwned)\nSAFE=ok\n")
    evil_path = f.name
marker = "/tmp/load-env-pwned"
if os.path.exists(marker):
    os.unlink(marker)
try:
    script = f'. "{LOADER}" "{evil_path}"\n'
    subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                   timeout=30)
    check("command substitution does NOT execute", not os.path.exists(marker),
          f"{marker} was created -- the file was executed")
finally:
    if os.path.exists(marker):
        os.unlink(marker)
    os.unlink(evil_path)

# 4. A quoted value with a leading $ is not expanded.
out, err, rc = load('TOKEN="$HOME"\n')
check("no HOME expansion in a quoted value", "TOKEN=$HOME" in out, out)

# The single-quoted form must keep the dollar too.
out, err, rc = load("TOKEN='$HOME'\n")
check("no HOME expansion in a single-quoted value", "TOKEN=$HOME" in out, out)

# 5. One layer of quotes is stripped; a bare $ is kept.
out, err, rc = load('A="x"\nB=\'y\'\n')
check("double quotes stripped", "A=x" in out, out)
check("single quotes stripped", "B=y" in out, out)

# 6. Malformed lines are reported, not silently accepted.
out, err, rc = load('GOOD=1\nthis is not valid\nALSO-BAD=2\n')
check("malformed lines are reported", "skipped" in err.lower(), err)
check("malformed count is right", "2 line(s)" in err, err)
check("good line still loads", "GOOD=1" in out, out)
# The printer echoes "ALSO-BAD=" for every key it checks, so the
# assertion is that the VALUE is empty -- the key was refused, not
# loaded with a mangled value.
check("bad key name is refused", "ALSO-BAD=\n" in out, out)

# 7. Comments and blank lines are ignored.
out, err, rc = load('# a comment\n\nA=1\n   # indented comment\n')
check("comments ignored", "A=1" in out, out)
check("no errors for comments", "skipped" not in err.lower(), err)

# 8. A CRLF file still works.
out, err, rc = load('A=1\r\nB=2\r\n')
check("CRLF file loads", "A=1" in out, out)
check("CRLF value has no stray CR", "\r" not in out, repr(out))

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
