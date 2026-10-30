"""Mise en forme française des montants, des nombres et des dates.

Pur affichage, sans dépendance : utilisable aussi bien par les écrans que
par les documents imprimés.
"""

from datetime import date

from .calculs import sou


def euros(montant) -> str:
    """1234.5 -> '1 234,50 €' (format français)."""
    d = sou(montant)
    entier, _, dec = f"{abs(d):.2f}".partition(".")
    groupes = []
    while len(entier) > 3:
        groupes.insert(0, entier[-3:])
        entier = entier[:-3]
    groupes.insert(0, entier)
    signe = "-" if d < 0 else ""
    return f"{signe}{' '.join(groupes)},{dec} €"


def nombre(valeur, decimales: int = 2) -> str:
    txt = f"{float(valeur or 0):.{decimales}f}".rstrip("0").rstrip(".")
    return (txt or "0").replace(".", ",")


def date_fr(iso: str) -> str:
    """'2026-10-25' -> '25/10/2026'."""
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def date_iso(fr: str) -> str:
    """'25/10/2026' -> '2026-10-25'."""
    fr = (fr or "").strip()
    if not fr:
        return ""
    for sep in ("/", "-", "."):
        morceaux = fr.split(sep)
        if len(morceaux) == 3:
            j, m, a = morceaux
            if len(a) == 2:
                a = ("20" if int(a) < 70 else "19") + a
            if len(j) == 4:  # déjà en ISO
                return fr.replace(sep, "-")
            try:
                return date(int(a), int(m), int(j)).isoformat()
            except ValueError:
                return ""
    return ""


def taux_tva_txt(taux: float) -> str:
    return f"{nombre(taux)} %"
