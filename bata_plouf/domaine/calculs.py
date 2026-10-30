"""Calculs du domaine : totaux, ventilation de la TVA, sous-totaux.

Ces fonctions ne connaissent ni les fichiers, ni l'écran. Elles travaillent
sur tout objet qui expose des lignes, une remise et un acompte — un devis
comme une facture — ce qui garantit qu'une facture ne peut pas diverger du
devis dont elle est issue.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP


def sou(x) -> Decimal:
    """Convertit en Decimal arrondi au centime."""
    return Decimal(str(x or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class LigneTVA:
    taux: float
    base_ht: Decimal
    montant: Decimal


@dataclass
class Totaux:
    brut_ht: Decimal = Decimal("0.00")
    remise: Decimal = Decimal("0.00")
    total_ht: Decimal = Decimal("0.00")
    tva: list[LigneTVA] = field(default_factory=list)
    total_tva: Decimal = Decimal("0.00")
    total_ttc: Decimal = Decimal("0.00")
    acompte: Decimal = Decimal("0.00")
    solde: Decimal = Decimal("0.00")


def calculer_totaux(document) -> Totaux:
    """Totaux d'un devis ou d'une facture, avec ventilation de la TVA par taux.

    Les deux documents portent les mêmes attributs (lignes, remise globale,
    acompte), donc un seul calcul suffit et les totaux d'une facture ne peuvent
    pas diverger de ceux du devis dont elle est issue.

    La remise globale s'applique au prorata sur chaque ligne, sinon la base de
    TVA par taux ne correspondrait plus au total HT remisé.
    """
    t = Totaux()
    coef_remise = (Decimal("1")
                   - Decimal(str(document.remise_globale_pct or 0)) / Decimal("100"))

    bases: dict[float, Decimal] = {}
    for ligne in document.lignes:
        if not ligne.chiffree:
            continue
        ht = ligne.total_ht
        t.brut_ht += ht
        bases[ligne.taux_tva] = bases.get(ligne.taux_tva, Decimal("0.00")) + sou(ht * coef_remise)

    t.brut_ht = sou(t.brut_ht)
    t.total_ht = sou(sum(bases.values(), Decimal("0.00")))
    t.remise = sou(t.brut_ht - t.total_ht)

    for taux in sorted(bases, reverse=True):
        base = bases[taux]
        if not base:
            continue
        montant = sou(base * Decimal(str(taux)) / Decimal("100"))
        t.tva.append(LigneTVA(taux=taux, base_ht=base, montant=montant))
        t.total_tva += montant

    t.total_tva = sou(t.total_tva)
    t.total_ttc = sou(t.total_ht + t.total_tva)
    t.acompte = sou(t.total_ttc * Decimal(str(document.acompte_pct or 0)) / Decimal("100"))
    t.solde = sou(t.total_ttc - t.acompte)
    return t


def sous_totaux_sections(document) -> dict[str, Decimal]:
    """Sous-total HT par section, indexé sur l'id de la ligne de section."""
    resultat: dict[str, Decimal] = {}
    section_courante = None
    for ligne in document.lignes:
        if ligne.type == "section":
            section_courante = ligne.id
            resultat.setdefault(section_courante, Decimal("0.00"))
        elif ligne.chiffree and section_courante:
            resultat[section_courante] += ligne.total_ht
    return resultat
