"""Text I/O names its encoding (#191): Windows defaults to cp949 here, so an implicit encoding reads
the repo's UTF-8 files differently on a local Windows session than on Linux CI."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("harness", "stalker", "scripts", "tests")


def _text_open_mode(call: ast.Call) -> str | None:
    if not (isinstance(call.func, ast.Name) and call.func.id == "open"):
        return None
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    else:
        mode = next((k.value.value for k in call.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)), "r")
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
