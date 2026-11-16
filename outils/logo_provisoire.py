"""Dessine un logo provisoire, le temps qu'on en choisisse un vrai.

Un mur de briques au trait, en noir sur fond transparent : neutre, lisible à
vingt-cinq millimètres de large, et correct à la photocopie comme au fax —
là où un dégradé ou un aplat de couleur tournerait au gris sale.

    uv run python outils/logo_provisoire.py [chemin.png]

Sans argument, le fichier est écrit dans le dossier de données, à côté des
devis, et il suffit ensuite de le désigner dans Paramètres → Logo. Pour le
remplacer, on choisit simplement une autre image au même endroit.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

COTE = 600          # le fichier est carré, et large : 25 mm à 600 ppp
MARGE = 26
TRAIT = 16
RANGS = 4
NOIR = QColor("#1a1a1a")


def dessiner() -> QImage:
    image = QImage(COTE, COTE, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    peintre.setPen(QPen(NOIR, TRAIT, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))

    cadre = QRectF(MARGE, MARGE, COTE - 2 * MARGE, COTE - 2 * MARGE)
    peintre.drawRect(cadre)

    hauteur = cadre.height() / RANGS
    for rang in range(RANGS):
        haut = cadre.top() + rang * hauteur
        if rang:
            peintre.drawLine(int(cadre.left()), int(haut),
                             int(cadre.right()), int(haut))
        # Un rang sur deux est décalé d'une demi-brique : c'est ce décalage
        # qui fait tenir un mur, et qui le fait reconnaître d'un coup d'œil.
        largeur = cadre.width() / 2
        depart = cadre.left() + (largeur / 2 if rang % 2 else largeur)
        while depart < cadre.right() - 1:
            peintre.drawLine(int(depart), int(haut),
                             int(depart), int(haut + hauteur))
            depart += largeur
    peintre.end()
    return image


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    if len(sys.argv) > 1:
        destination = Path(sys.argv[1])
    else:
        destination = Path.home() / "Documents/Bata-plouf/logo-provisoire.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not dessiner().save(str(destination)):
        print(f"Échec de l'écriture de {destination}", file=sys.stderr)
        return 1
    print(f"Logo provisoire écrit : {destination}")
    print("À désigner dans Paramètres → Logo, et à remplacer quand le vrai "
          "logo sera prêt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
