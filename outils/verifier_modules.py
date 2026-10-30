"""Importe tous les modules du logiciel, pour attraper les imports cassés.

Un renommage ou un déplacement de fichier ne se voit pas tant qu'on n'a pas
ouvert l'écran concerné : ce contrôle ouvre tout, d'un coup.

    uv run python outils/verifier_modules.py
"""

import importlib
import pkgutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


def main() -> int:
    import bata_plouf

    modules = [nom for _, nom, _ in
               pkgutil.walk_packages(bata_plouf.__path__, "bata_plouf.")
               if not nom.endswith("__main__")]
    echecs = []
    for nom in sorted(modules):
        try:
            importlib.import_module(nom)
        except Exception as erreur:  # noqa: BLE001 — on veut tout rapporter
            echecs.append(f"  {nom} : {type(erreur).__name__} — {erreur}")

    if echecs:
        print(f"{len(echecs)} module(s) refusent de s'importer :")
        print("\n".join(echecs))
        return 1
    print(f"{len(modules)} modules importés sans erreur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
