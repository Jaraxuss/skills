#!/bin/bash
# Locate a Codex session rollout file by thread ID across all antigravity_cockpit instances.
# Usage: find_rollout.sh <thread-id>
# Prints the rollout_path on stdout and exits 0 on first hit; exits 1 if not found.

set -u

if [ $# -ne 1 ] || [ -z "$1" ]; then
  echo "Usage: find_rollout.sh <thread-id>" >&2
  exit 2
fi

ID="$1"
BASE="$HOME/.antigravity_cockpit/instances/codex"

if [ ! -d "$BASE" ]; then
  echo "NOT_FOUND: instances dir does not exist: $BASE" >&2
  exit 1
fi

for db in "$BASE"/*/state_5.sqlite; do
  [ -f "$db" ] || continue
  result=$(sqlite3 "$db" "SELECT rollout_path FROM threads WHERE id='$ID';" 2>/dev/null)
  if [ -n "$result" ]; then
    echo "$result"
    exit 0
  fi
done

echo "NOT_FOUND: thread id '$ID' not found in any state_5.sqlite under $BASE" >&2
exit 1
