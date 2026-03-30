#!/usr/bin/env bash
# Collect local LLM session data and push to the central repo.
# Run this on each machine (macOS, Linux, Windows Git Bash / WSL).
#
# Usage:
#   ./sync.sh                    # auto-detect hostname
#   ./sync.sh --name mybox       # custom machine name

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Pull latest
git pull --rebase --quiet 2>/dev/null || true

# Collect local data
python3 collect.py "$@"

# Stage and push
MACHINE=$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo "unknown")
# Allow override from args
for arg in "$@"; do
  if [ "$prev" = "--name" ] 2>/dev/null; then MACHINE="$arg"; fi
  prev="$arg"
done

git add "machines/data-*.json"
if git diff --cached --quiet; then
  echo "No changes to push."
else
  git commit -m "update data from ${MACHINE}"
  git push
  echo "Pushed data from ${MACHINE}."
fi
