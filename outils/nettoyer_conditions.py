"""Retire des devis et factures repris deux phrases qui n'ont plus lieu d'être.

L'ancien logiciel recopiait dans les conditions de chaque pièce un acompte
« pour la commande des matériaux » qui ne figurait pas sur les documents
d'origine, et une mention d'attestation qui ne vaut que pour les travaux au
taux réduit. La première s'en va ; la seconde est désormais imprimée selon la
TVA du document, donc elle n'a plus à être figée dans le texte.

    uv run python outils/nettoyer_conditions.py            sur le vrai dossier
    uv run python outils/nettoyer_conditions.py --simuler  pour voir d'abord

Fermez le logiciel avant : il garde les pièces en mémoire et les réécrirait.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "outils"))

from reprendre_batappli import nettoyer_conditions  # noqa: E402


def main() -> int:
    from bata_plouf.adaptateurs.depot_fichiers import DOSSIER_DEFAUT, DepotFichiers

    simuler = "--simuler" in sys.argv
    dossier = next((a for a in sys.argv[1:] if not a.startswith("-")),
                   str(DOSSIER_DEFAUT))
    depot = DepotFichiers(Path(dossier))
    depot.charger()
    if not simuler:
        depot.creer_sauvegarde()

    touches = 0
    for pieces, enregistrer in ((depot.devis(), depot.enregistrer_devis),
                                (depot.factures(), depot.enregistrer_facture)):
        for piece in pieces:
            propre = nettoyer_conditions(piece.conditions)
            if propre == (piece.conditions or ""):
                continue
            touches += 1
            if touches <= 3:
                print(f"  {piece.numero} :")
                print(f"    avant : {piece.conditions[:100]!r}")
                print(f"    après : {propre[:100]!r}")
            if not simuler:
                piece.conditions = propre
                enregistrer(piece)

    verbe = "seraient nettoyées" if simuler else "nettoyées"
    print(f"\n{touches} pièce(s) {verbe}.")
    if simuler:
        print("Relancez sans --simuler pour appliquer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
