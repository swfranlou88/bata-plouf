"""Vérifie que les dépendances vont bien vers le centre de l'hexagone.

Le domaine doit pouvoir s'importer seul : ni Qt, ni les adaptateurs, ni les
écrans. C'est la seule règle qui tienne l'architecture, et elle se perd vite
sans contrôle.

    uv run python outils/verifier_architecture.py
"""

import ast
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOMAINE = RACINE / "bata_plouf" / "domaine"
INTERDITS = ("PySide6", "adaptateur", "interface", "impression", "depot_fichiers")


def modules_importes(chemin: Path):
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom):
            yield noeud.module or ""
        elif isinstance(noeud, ast.Import):
            for alias in noeud.names:
                yield alias.name


def main() -> int:
    fautes = []
    for chemin in sorted(DOMAINE.glob("*.py")):
        for module in modules_importes(chemin):
            if any(interdit in module for interdit in INTERDITS):
                fautes.append(f"  {chemin.name} importe {module}")

    if fautes:
        print("Le domaine dépend de l'extérieur :")
        print("\n".join(fautes))
        return 1
    print(f"Domaine propre : {len(list(DOMAINE.glob('*.py')))} modules, "
          "aucune dépendance vers l'extérieur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
