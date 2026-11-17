"""Contrôle que l'encre tombe bien là où les marges la promettent.

Le HTML d'un devis peut être parfait et la feuille fausse : c'est la
peinture sur l'imprimante qui place le document, et une origine mal comprise
l'avait longtemps décalé vers la droite d'autant que la marge gauche — jusqu'à
ne rien laisser à droite. Cela ne se voit sur aucun contrôle de texte, et pas
non plus sur un écran : il faut mesurer la page.

On rend donc un devis en PDF, on regarde où commence et où finit l'encre, et
on compare aux marges demandées.

    uv run python outils/verifier_impression.py
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# Deux millimètres de tolérance : le filet du cadre ne commence pas au premier
# point de la marge, et le rendu arrondit au pixel.
TOLERANCE_MM = 2.0
LARGEUR_RENDU = 1050  # cinq points par millimètre


def mesurer(pdf: Path) -> tuple[float, float]:
    """Les marges gauche et droite de l'encre, en millimètres."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtPdf import QPdfDocument

    document = QPdfDocument()
    document.load(str(pdf))
    rendue = document.render(
        0, QSize(LARGEUR_RENDU, int(LARGEUR_RENDU * 297 / 210)))
    # Le rendu est transparent là où il n'y a rien : sans fond blanc, le vide
    # compterait pour de l'encre noire.
    page = QImage(rendue.size(), QImage.Format.Format_RGB32)
    page.fill(QColor("white"))
    peintre = QPainter(page)
    peintre.drawImage(0, 0, rendue)
    peintre.end()

    par_mm = LARGEUR_RENDU / 210
    colonnes = [
        x for x in range(page.width())
        # Trois points sombres au moins : un isolé serait un artefact du rendu.
        if sum(1 for y in range(0, page.height(), 2)
               if QColor(page.pixelColor(x, y)).lightness() < 200) > 2
    ]
    if not colonnes:
        raise SystemExit("La page est blanche : rien n'a été peint.")
    return colonnes[0] / par_mm, (page.width() - colonnes[-1]) / par_mm


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from bata_plouf.adaptateurs.depot_fichiers import DepotFichiers
    from bata_plouf.adaptateurs.impression import RenduDocument
    from bata_plouf.domaine import Client, Devis, Ligne
    from bata_plouf.domaine.gabarit import MODELES_PREDEFINIS, Gabarit

    QApplication([])
    echecs = []
    with tempfile.TemporaryDirectory() as atelier:
        depot = DepotFichiers(Path(atelier))
        depot.charger()
        client = depot.enregistrer_client(
            Client(nom="Dupont", adresse="4 Rue des Chalets", cp="88120",
                   ville="SAINT-AMÉ"))
        devis = depot.enregistrer_devis(Devis(
            client_id=client.id, objet="Réfection d'un mur",
            lignes=[Ligne(designation="Maçonnerie de moellons", quantite=12,
                          unite="m²", prix_unitaire=84.0)]))

        for modele in ("Sobre", "Artisan (classique)"):
            reglages = MODELES_PREDEFINIS.get(modele, {})
            gabarit = Gabarit(**{**{}, **reglages})
            depot.enregistrer_gabarit(gabarit)
            sortie = Path(atelier) / "essai.pdf"
            RenduDocument(depot, devis).vers_pdf(sortie, haute_qualite=False)
            gauche, droite = mesurer(sortie)
            voulues = (gabarit.marge_gauche, gabarit.marge_droite)
            print(f"  {modele} : marges demandées {voulues[0]:.0f} et "
                  f"{voulues[1]:.0f} mm, encre à {gauche:.1f} et {droite:.1f} mm")
            for cote, mesure, voulue in (("gauche", gauche, voulues[0]),
                                         ("droite", droite, voulues[1])):
                if abs(mesure - voulue) > TOLERANCE_MM:
                    echecs.append(
                        f"{modele} : marge {cote} de {mesure:.1f} mm au lieu "
                        f"de {voulue:.0f} mm")

    if echecs:
        print("\n".join("  ✗ " + e for e in echecs))
        return 1
    print("L'encre tombe où les marges la promettent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
