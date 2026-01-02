# fix_imports.py — делайте backup перед запуском!
import os
from pathlib import Path

ROOT = Path(".")
PYFILES = [p for p in ROOT.rglob("*.py") if "venv" not in str(p) and "site-packages" not in str(p)]
REPL_IMPORT = ""
REPL_IMPORT2 = ""

for p in PYFILES:
    text = p.read_text(encoding="utf-8")
    new = text
    changed = False

    if REPL_IMPORT in new:
        new = new.replace(REPL_IMPORT, "")
        changed = True
    if REPL_IMPORT2 in new:
        new = new.replace(REPL_IMPORT2, "")
        changed = True

    # осторожно: заменить вызовы db.make_product_key( -> db.db.make_product_key(
    if "db.make_product_key(" in new:
        new = new.replace("db.make_product_key(", "db.db.make_product_key(")
        changed = True

    if "db.normalize_url(" in new:
        new = new.replace("db.normalize_url(", "db.db.normalize_url(")
        changed = True

    if changed:
        bak = p.with_suffix(p.suffix + ".bak")
        if not bak.exists():
            p.rename(bak)
            bak.write_text(text, encoding="utf-8")
            p.write_text(new, encoding="utf-8")
            print(f"Patched {p} (backup -> {bak})")
        else:
            # если .bak уже есть — просто перезаписываем оригинал
            p.write_text(new, encoding="utf-8")
            print(f"Patched {p} (backup existed)")

print("Готово — проверь изменения вручную.")