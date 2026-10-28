"""Text I/O names its encoding (#191): Windows defaults to cp949 here, so an implicit encoding reads
the repo's UTF-8 files differently on a local Windows session than on Linux CI."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("harness", "stalker", "scripts", "tests")


MODE = re.compile(r"^[rwxabt+]+$")


def _text_open_mode(call: ast.Call) -> str | None:
    """Text mode of open(file, mode) or path.open(mode); None for binary or a non-file .open (zip.open(name))."""
    kw = next((k.value.value for k in call.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)), None)
    if isinstance(call.func, ast.Name) and call.func.id == "open":
        pos = call.args[1].value if len(call.args) > 1 and isinstance(call.args[1], ast.Constant) else None
        mode = pos or kw or "r"
    elif isinstance(call.func, ast.Attribute) and call.func.attr == "open":
        first = call.args[0].value if call.args and isinstance(call.args[0], ast.Constant) else None
        if isinstance(first, str) and MODE.match(first):
            mode = first
        elif kw is not None or not call.args:
            mode = kw or "r"           # Path.open() defaults to text
        else:
            return None
    else:
        return None
    return None if "b" in str(mode) else str(mode)


def _text_subprocess(call: ast.Call) -> bool:
    """subprocess.run/check_output/Popen/... decoding output as text (text=True or universal_newlines=True)."""
    if not (isinstance(call.func, ast.Attribute) and call.func.attr in ("run", "check_output", "Popen", "check_call", "call")):
        return False
    return any(k.arg in ("text", "universal_newlines") and isinstance(k.value, ast.Constant) and k.value.value is True
               for k in call.keywords)


def test_text_reads_and_writes_name_utf8():
    bad = []
    for d in DIRS:
        for f in (ROOT / d).rglob("*.py"):
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if not isinstance(n, ast.Call) or any(k.arg == "encoding" for k in n.keywords):
                    continue
                rw = isinstance(n.func, ast.Attribute) and n.func.attr in ("read_text", "write_text")
                if rw or _text_open_mode(n) is not None or _text_subprocess(n):
                    bad.append(f"{f.relative_to(ROOT).as_posix()}:{n.lineno}")
    assert not bad, "add encoding=\"utf-8\" to: " + ", ".join(bad)


def test_the_check_sees_method_form_open():
    calls = [ast.parse(src).body[0].value for src in ('p.open("a")', "p.open()", 'p.open("rb")', 'z.open("member.txt")',
                                                       'open(f, "w")', 'p.open("w", encoding="utf-8")')]
    assert [_text_open_mode(c) for c in calls[:5]] == ["a", "r", None, None, "w"]
