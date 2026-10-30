"""Dessine l'icône de l'application, au format attendu par chaque système.

L'icône est dessinée par le code, à chaque taille demandée, plutôt que
redimensionnée depuis une grande image : les traits restent nets en 16 et 32
pixels, les deux tailles où une icône mal faite devient une bouillie.

    uv run python outils/icone.py
"""

import platform
import struct
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath,
)

RACINE = Path(__file__).resolve().parent.parent
CIBLE = RACINE / "ressources"

# Terre cuite : la couleur du métier, et elle reste lisible en petit
ARGILE_CLAIRE = QColor("#b25f33")
ARGILE_FONCEE = QColor("#7d3d1e")
MORTIER = QColor("#f4efe9")
PAPIER = QColor("#ffffff")
ENCRE = QColor("#b9b2aa")

# Les tailles réclamées par macOS pour un jeu d'icônes complet
TAILLES = [
    (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
]


def dessiner(taille: int) -> QImage:
    image = QImage(taille, taille, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    u = taille / 1024  # tout est exprimé dans un carré de 1024
    # En 16 et 32 pixels, les détails fins se transforment en gris sale :
    # on garde moins de briques, plus grosses, et une seule ligne de texte.
    menu = taille <= 32

    # --- le fond arrondi, à la façon des icônes macOS ---
    fond = QRectF(40 * u, 40 * u, 944 * u, 944 * u)
    degrade = QLinearGradient(QPointF(fond.left(), fond.top()),
                              QPointF(fond.right(), fond.bottom()))
    degrade.setColorAt(0.0, ARGILE_CLAIRE)
    degrade.setColorAt(1.0, ARGILE_FONCEE)
    chemin = QPainterPath()
    chemin.addRoundedRect(fond, 220 * u, 220 * u)
    p.fillPath(chemin, QBrush(degrade))

    # --- la feuille de devis ---
    feuille = QRectF(236 * u, 176 * u, 552 * u, 672 * u)
    ombre = QPainterPath()
    ombre.addRoundedRect(feuille.adjusted(0, 14 * u, 0, 14 * u), 26 * u, 26 * u)
    p.fillPath(ombre, QColor(60, 25, 10, 90))
    papier = QPainterPath()
    papier.addRoundedRect(feuille, 26 * u, 26 * u)
    p.fillPath(papier, PAPIER)

    # --- trois lignes de texte en haut de la feuille ---
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ENCRE)
    for index, largeur in enumerate((380,) if menu else (300, 380, 220)):
        ligne = QRectF(300 * u, (248 + index * 56) * u, largeur * u, 26 * u)
        p.drawRoundedRect(ligne, 13 * u, 13 * u)

    # --- le mur de parpaings, en appareil décalé ---
    p.setClipPath(papier)
    if menu:
        haut, hauteur_rang, jointoiement = 400 * u, 148 * u, 22 * u
        largeur_brique, rangs = 268 * u, 3
    else:
        haut, hauteur_rang, jointoiement = 452 * u, 76 * u, 10 * u
        largeur_brique, rangs = 182 * u, 4
    for rang in range(rangs):
        y = haut + rang * hauteur_rang
        decalage = -largeur_brique / 2 if rang % 2 else 0
        x = feuille.left() + 36 * u + decalage
        while x < feuille.right() - 30 * u:
            brique = QRectF(x, y, largeur_brique - jointoiement,
                            hauteur_rang - jointoiement)
            visible = brique.intersected(
                QRectF(feuille.left() + 36 * u, haut,
                       feuille.width() - 72 * u, rangs * hauteur_rang))
            if visible.width() > 6 * u:
                p.setBrush(ARGILE_CLAIRE if (rang + int(x)) % 2 else ARGILE_FONCEE)
                p.drawRoundedRect(visible, 7 * u, 7 * u)
            x += largeur_brique
    p.setClipping(False)

    # --- le trait de mortier qui sépare le texte du mur ---
    p.setBrush(MORTIER)
    p.drawRect(QRectF(feuille.left(), (378 if menu else 430) * u,
                      feuille.width(), 8 * u))

    p.end()
    return image


# Tailles d'un fichier .ico Windows
TAILLES_ICO = [16, 24, 32, 48, 64, 128, 256]


def _png(taille: int) -> bytes:
    tampon = QBuffer()
    tampon.open(QIODevice.OpenModeFlag.WriteOnly)
    dessiner(taille).save(tampon, "PNG")
    return bytes(tampon.data())


def ecrire_ico(cible: Path) -> Path:
    """Produit un .ico Windows, sans outil externe.

    Un .ico n'est qu'un en-tête suivi d'un répertoire d'entrées et des images
    elles-mêmes ; depuis Windows Vista celles-ci peuvent être des PNG, ce qui
    permet de l'assembler en quelques lignes.
    """
    images = [(taille, _png(taille)) for taille in TAILLES_ICO]
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = len(entete) + 16 * len(images)

    repertoire, donnees = b"", b""
    for taille, png in images:
        mesure = 0 if taille >= 256 else taille  # 0 signifie 256 dans le format
        repertoire += struct.pack("<BBBBHHII", mesure, mesure, 0, 0, 1, 32,
                                  len(png), decalage)
        donnees += png
        decalage += len(png)

    cible.write_bytes(entete + repertoire + donnees)
    return cible


def ecrire_icns(cible: Path, jeu: Path) -> Path:
    """Produit un .icns macOS, via l'outil iconutil fourni avec le système."""
    jeu.mkdir(exist_ok=True)
    for taille, nom in TAILLES:
        dessiner(taille).save(str(jeu / nom))
    subprocess.run(["iconutil", "--convert", "icns", str(jeu), "--output", str(cible)],
                   check=True)
    return cible


def construire(cible: Path = CIBLE) -> Path:
    """Écrit tous les formats et renvoie celui qui convient à ce système."""
    cible.mkdir(parents=True, exist_ok=True)
    for taille in (256, 512):
        dessiner(taille).save(str(cible / f"icone-{taille}.png"))
    dessiner(512).save(str(cible / "icone.png"))

    ico = ecrire_ico(cible / "bata-plouf.ico")
    if platform.system() == "Darwin":
        return ecrire_icns(cible / "bata-plouf.icns", cible / "icone.iconset")
    if platform.system() == "Windows":
        return ico
    return cible / "icone.png"


def main() -> None:
    application = QGuiApplication(sys.argv)  # noqa: F841 — requis pour peindre
    produite = construire()
    print(f"icône produite : {produite} ({produite.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    main()
