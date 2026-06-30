#!/bin/bash
# Return 0 if Codex can execute a minimal prompt; 1 if auth is broken or codex missing.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
eval "$(python3 -c "from config import shell_exports; print(shell_exports())")"

if ! command -v codex >/dev/null 2>&1; then
  echo "ERROR: codex not found in PATH"
  exit 1
fi

TMP_LOG="$(mktemp)"
trap 'rm -f "$TMP_LOG"' EXIT

if timeout 90 codex exec \
  --cd "$ROOT" \
  --skip-git-repo-check \
  -c 'approval_policy="never"' \
  --color never \
  - <<< 'Reply with exactly: OK' >"$TMP_LOG" 2>&1; then
  if grep -q '^OK' "$TMP_LOG" || grep -qi 'assistant.*OK' "$TMP_LOG"; then
    echo "Codex auth OK"
    exit 0
  fi
fi

if grep -qiE 'sign in again|token_expired|refresh_token_reused|401 Unauthorized' "$TMP_LOG"; then
  echo "ERROR: Codex authentication expired or invalid."
  echo "       Run: codex logout && codex login"
  tail -5 "$TMP_LOG" >&2
  exit 1
fi

echo "ERROR: Codex exec failed (unknown reason)."
tail -10 "$TMP_LOG" >&2
exit 1
