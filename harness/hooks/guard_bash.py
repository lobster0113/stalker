"""PreToolUse hook: block irreversible / out-of-policy shell commands (exit 2 = deny)."""
from __future__ import annotations

import json
import re
import sys

BLOCK = [
    (r"git\s+push\b.*(\s--force\b|\s-f\b|--force-with-lease|\s\+\S)", "force push is forbidden"),
    (r"git\s+push\s+(-\S+\s+)*\S+\s+(\S+:)?(refs/heads/)?(main|master)(\s|$)", "direct push to main is forbidden; open a PR"),
    (r"git\s+filter-(branch|repo)\b", "history rewriting is forbidden"),
    (r"gh\s+repo\s+(delete|edit|rename|archive)\b", "repository settings are off-limits"),
    (r"gh\s+secret\b", "secrets are off-limits"),
    (r"gh\s+api\b.*(-X|--method)\s*(DELETE|PUT|PATCH)\b", "mutating GitHub API calls are off-limits; use gh pr/issue commands"),
    (r"gh\s+api\b.*(branches/[^ ]+/protection|rulesets)", "branch protection is off-limits"),
    (r"git\s+push\b.*\s--delete\s+(main|ops)\b|git\s+push\b.*\s:(main|ops)\b", "deleting main/ops is forbidden"),
]


# Rules apply per shell command, so a `+` or `-f` in another command of the same line (a jq
# expression, a comment body) cannot read as part of a `git push`.
SEPARATORS = re.compile(r"&&|\|\||[;|\n]")


def check(cmd: str) -> str | None:
    for part in SEPARATORS.split(cmd):
        for pat, why in BLOCK:
            if re.search(pat, part):
                return why
    return None


if __name__ == "__main__":
    data = json.load(sys.stdin)
    reason = check(data.get("tool_input", {}).get("command", ""))
    if reason:
        print(f"Blocked by harness policy: {reason}. See CLAUDE.md '절대 규칙'.", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
