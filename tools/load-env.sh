#!/usr/bin/env bash
# Load an env file WITHOUT executing it.
#
# The relay's scripts used to source stream-keys.env with `.`, which
# runs it as shell. A file with a stray line could execute anything.
# Quoting the values stops the observed bug (an unquoted `&` in an
# Instagram key backgrounded the command and silently dropped the
# variable) but it does not stop code execution.
#
# This reads KEY=VALUE lines and nothing else. A value is taken
# literally: no expansion, no substitution, no command execution.
#
# Usage:
#   . tools/load-env.sh /path/to/stream-keys.env
#
# After loading, $LOAD_ENV_ERRORS holds the number of lines that were
# skipped, and $LOAD_ENV_ERRORS_DETAIL lists them.

# Guard against double-loading.
if [ -n "${LOAD_ENV_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi

LOAD_ENV_LOADED=1
LOAD_ENV_ERRORS=0
LOAD_ENV_ERRORS_DETAIL=""

_load_env_file() {
  local file="$1"
  local lineno=0
  local line key value

  if [ ! -f "$file" ]; then
    echo "load-env: no such file: $file" >&2
    LOAD_ENV_ERRORS=$((LOAD_ENV_ERRORS + 1))
    return 1
  fi

  while IFS= read -r line || [ -n "$line" ]; do
    lineno=$((lineno + 1))

    # Strip a trailing CR so a CRLF file still works.
    line="${line%$'\r'}"

    # Trim leading and trailing whitespace. A line that is only
    # whitespace is blank, and an indented comment is a comment.
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"

    # Skip blank lines and comments.
    case "$line" in
      ''|\#*) continue ;;
    esac

    # Only KEY=VALUE. A line without an = is not a variable.
    case "$line" in
      *=*) ;;
      *)
        LOAD_ENV_ERRORS=$((LOAD_ENV_ERRORS + 1))
        LOAD_ENV_ERRORS_DETAIL="${LOAD_ENV_ERRORS_DETAIL}${file}:${lineno}: not KEY=VALUE"$'\n'
        continue
        ;;
    esac

    key="${line%%=*}"
    value="${line#*=}"

    # A key must be a valid shell identifier: a letter or underscore,
    # then letters, digits, or underscores. Anything else is a
    # malformed file, not a variable.
    #
    # The check has to cover the WHOLE key. A pattern like
    # `[A-Za-z_]*` matches any key that STARTS with a letter, so
    # "ALSO-BAD" would pass and then fail to export -- silently
    # producing a mangled variable.
    case "$key" in
      [A-Za-z_]*)
        if printf '%s' "$key" | grep -q '[^A-Za-z0-9_]'; then
          LOAD_ENV_ERRORS=$((LOAD_ENV_ERRORS + 1))
          LOAD_ENV_ERRORS_DETAIL="${LOAD_ENV_ERRORS_DETAIL}${file}:${lineno}: bad key name"$'\n'
          continue
        fi
        ;;
      *)
        LOAD_ENV_ERRORS=$((LOAD_ENV_ERRORS + 1))
        LOAD_ENV_ERRORS_DETAIL="${LOAD_ENV_ERRORS_DETAIL}${file}:${lineno}: bad key name"$'\n'
        continue
        ;;
    esac

    # Strip ONE layer of matching quotes. The value is otherwise taken
    # literally -- no expansion happens here.
    case "$value" in
      \"*\")
        value="${value#\"}"
        value="${value%\"}"
        ;;
      \'*\')
        value="${value#\'}"
        value="${value%\'}"
        ;;
    esac

    # Export it so child processes (the python helpers) see it.
    export "$key=$value"
  done < "$file"

  if [ "$LOAD_ENV_ERRORS" -gt 0 ]; then
    echo "load-env: skipped $LOAD_ENV_ERRORS line(s) in $file:" >&2
    printf '%s' "$LOAD_ENV_ERRORS_DETAIL" >&2
  fi

  return 0
}

if [ "$#" -ge 1 ]; then
  _load_env_file "$1"
  unset -f _load_env_file
fi
