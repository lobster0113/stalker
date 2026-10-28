#!/usr/bin/env bash
# Commit and push ops:budget/ledger.jsonl and ops:cloud/results/ (launcher publish, #264) from the ops
# worktree (cloud.yml). Exit nonzero if the push fails.
# Usage: push_ledger.sh <ops worktree> <commit message>
set -euo pipefail
cd "$1"
paths=()
for p in budget/ledger.jsonl cloud/results; do [[ -e "$p" ]] && paths+=("$p"); done
[[ ${#paths[@]} -gt 0 ]] || exit 0
git add -- "${paths[@]}"
git diff --cached --quiet && exit 0
git config user.name "stalker-ci"
git config user.email "stalker-ci@users.noreply.github.com"
git commit -qm "$2"
for _ in 1 2 3; do
  git push -q origin ops && exit 0
  git pull -q --rebase origin ops || true
done
echo "ledger push failed 3x — ledger lines:"; cat budget/ledger.jsonl
exit 1
