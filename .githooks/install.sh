#!/usr/bin/env bash
# Install all git hooks from .githooks/ into .git/hooks/
# Idempotent — safe to re-run.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC="${REPO_ROOT}/.githooks"
DST="${REPO_ROOT}/.git/hooks"

if [[ ! -d "${SRC}" ]]; then
  echo "❌ .githooks/ not found at ${SRC}"
  exit 1
fi

for hook_file in "${SRC}"/*; do
  name="$(basename "${hook_file}")"
  target="${DST}/${name}"
  if [[ -f "${hook_file}" ]]; then
    # Symlink so edits to .githooks/* propagate automatically
    ln -sf "../../.githooks/${name}" "${target}"
    chmod +x "${hook_file}"
    echo "✓ installed ${name}"
  fi
done

echo ""
echo "✅ git hooks installed. Try:  git commit -m 'test'  (should run gitleaks)"