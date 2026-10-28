import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_adr_numbers_are_unique():
    # Two ADR 0014s merged on 2026-10-28 (#304): "ADR NNNN" must name one decision.
    nums = Counter(m.group(1) for p in (ROOT / "docs" / "decisions").glob("*.md")
                   if (m := re.match(r"(\d{4})-", p.name)))
    dup = sorted(n for n, c in nums.items() if c > 1)
    assert not dup, f"duplicate ADR numbers {dup}: renumber the later one and fix its references"
