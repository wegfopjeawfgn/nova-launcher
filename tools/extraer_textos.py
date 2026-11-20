"""Lista los textos en español de la interfaz para traducirlos: `python3 tools/extraer_textos.py` imprime JSON {texto: ""}.
Las f-strings salen como plantillas con {} en lugar de cada valor (i18n.tr las reconoce al mostrarlas)."""
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"i18n.py", "nova_version.py", "extraer_textos.py"}
CODE = re.compile(r"^[a-z0-9_.\-/:#@%{}\[\]()*+=<>|\\$^~`'\",;&?!]+$")


def wanted(text):
    if not 2 <= len(text) <= 600 or "\x00" in text or not re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]{2}", text):
        return False
    if CODE.match(text) or text.startswith(("http", "/", ".", "#")) or re.fullmatch(r"[A-Za-z0-9_.\-]+", text) and text.islower():
        return False
    return bool(re.match(r"[A-ZÁÉÍÓÚÑ¿¡«\"'(0-9]", text)) or " " in text


def pieces(node):
    out = []
    for value in node.values:
        out.append(value.value if isinstance(value, ast.Constant) else "{}")
    return "".join(out)


def harvest():
    found = {}
    for path in sorted(ROOT.glob("*.py")):
        if path.name in SKIP:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body
                      and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        inside = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for node in ast.walk(tree):
            if id(node) in docstrings or id(node) in inside:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and wanted(node.value):
                found.setdefault(node.value, "")
            elif isinstance(node, ast.JoinedStr):
                text = pieces(node)
                if wanted(text.replace("{}", "")) and re.search(r"[a-záéíóúñ]{3}", text.replace("{}", "")):
                    found.setdefault(text, "")
    return found


if __name__ == "__main__":
    json.dump(harvest(), sys.stdout, ensure_ascii=False, indent=0)
