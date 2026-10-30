"""Couleurs, mesures et échappement — les briques de bas niveau du rendu."""

import html as _html
from dataclasses import dataclass

from ...domaine.gabarit import Gabarit, eclaircir, texte_lisible_sur


@dataclass
class Palette:
    """Toutes les couleurs du devis, dérivées de la seule couleur d'accent."""

    accent: str
    texte_accent: str
    section: str
    texte_section: str
    cadre: str
    trait: str = "#dddddd"
    gris: str = "#555555"
    gris_clair: str = "#6b6b6b"
    texte: str = "#000000"


def palette(gabarit: Gabarit) -> Palette:
    accent = gabarit.couleur or "#333333"
    section = eclaircir(accent, 0.86)
    return Palette(
        accent=accent,
        texte_accent=texte_lisible_sur(accent),
        section=section,
        texte_section=texte_lisible_sur(section),
        cadre=eclaircir(accent, 0.93),
    )


def mm_en_px(mm: float, dpi: int) -> int:
    return int(round(mm / 25.4 * dpi))


def echapper(texte) -> str:
    """Échappe le texte saisi et conserve les retours à la ligne."""
    return _html.escape(str(texte or "")).replace("\n", "<br>")


def espace(hauteur_pt: float = 7.0) -> str:
    """Un écart vertical ; Qt ne gère pas les marges CSS sur les blocs."""
    return (f"<table width='100%' cellspacing='0' cellpadding='0'>"
            f"<tr><td style='font-size:{hauteur_pt}pt;'>&nbsp;</td></tr></table>")
