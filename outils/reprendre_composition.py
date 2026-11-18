"""Rattache à chaque ouvrage déjà repris ce dont il est fait.

La première reprise n'avait gardé des ouvrages que leur prix et leur temps de
pose, parce que la composition semblait tenir dans une note. Elle est en fait
dans une table à part, ARTOUV : une ligne par article et par heure, avec la
quantité pour une unité d'ouvrage. Cet outil va la chercher et la pose sur la
bibliothèque existante, sans toucher au reste.

    uv run python outils/reprendre_composition.py "/chemin/vers/BatAppli 2000"

Les fiches sont rapprochées par leur référence d'origine — « batappli:ouv:412 »,
« batappli:art:9768 » —, donc rien ne se devine au libellé. Fermez le logiciel
avant : il garde la bibliothèque en mémoire et la réécrirait.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from reprendre_batappli import composer  # noqa: E402  (après sys.path)


def main() -> int:
    import collections

    from bata_plouf.adaptateurs.depot_fichiers import DOSSIER_DEFAUT, DepotFichiers

    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1]).expanduser()
    if not (source / "ARTOUV.FIC").exists():
        print(f"ARTOUV.FIC introuvable dans {source}")
        return 1
    destination = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else DOSSIER_DEFAUT

    depot = DepotFichiers(destination)
    depot.charger()
    depot.creer_sauvegarde()
    avant = sum(1 for a in depot.articles() if a.composants)

    bilan = collections.Counter()
    composer(depot, source, bilan)

    apres = sum(1 for a in depot.articles() if a.composants)
    print(f"{apres - avant} ouvrages reçoivent leur composition "
          f"({apres} au total), "
          f"{bilan.get('lignes de composition', 0)} lignes posées.")
    if bilan.get("composition orpheline"):
        print(f"{bilan['composition orpheline']} ligne(s) laissées de côté : "
              "elles renvoient à une fiche absente de la reprise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
