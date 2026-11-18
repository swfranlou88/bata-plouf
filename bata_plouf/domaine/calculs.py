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

# --- taux réduits et attestation ------------------------------------------

# Les travaux au taux réduit — 10 % pour la rénovation, 5,5 % pour les
# travaux d'économie d'énergie — ne s'appliquent que sur présentation d'une
# attestation signée du client (articles 279-0 bis et 278-0 bis A du CGI).
# C'est elle qu'on joint au devis, et elle n'a rien à faire sur un devis au
# taux normal.
TAUX_REDUITS = (10.0, 5.5)


def taux_reduit(document) -> bool:
    """Le document porte-t-il au moins une ligne à taux réduit ?"""
    return any(l.taux_tva in TAUX_REDUITS
               for l in getattr(document, "lignes", []) or []
               if getattr(l, "chiffree", False))


def taux_dominant(document, defaut: float) -> float:
    """Le taux le plus répandu dans le document, hors 0 %.

    C'est celui que le sélecteur propose d'emblée : presque toujours celui
    qu'on veut étendre au reste, et jamais une valeur prise au hasard.
    """
    taux = [l.taux_tva for l in getattr(document, "lignes", []) or []
            if getattr(l, "chiffree", False) and l.taux_tva]
    return max(set(taux), key=taux.count) if taux else defaut


def appliquer_taux(document, taux: float) -> int:
    """Met toutes les lignes chiffrées au même taux ; renvoie le nombre changé.

    Les lignes à 0 % ne bougent pas : ce n'est pas un taux parmi d'autres mais
    l'autoliquidation, décidée pour la ligne et pour elle seule. Les sections
    et les textes libres n'ont pas de TVA du tout.
    """
    changees = 0
    for ligne in getattr(document, "lignes", []) or []:
        if not getattr(ligne, "chiffree", False):
            continue
        if ligne.taux_tva == 0.0 or ligne.taux_tva == taux:
            continue
        ligne.taux_tva = taux
        changees += 1
    return changees


# --- quel texte au bas d'un document --------------------------------------

def conditions_par_defaut(societe, est_facture: bool,
                          reduit: bool = False) -> str:
    """Le bas de page qui convient au document.

    Trois textes, parce que les trois cas ne disent pas la même chose : une
    facture réclame un paiement, un devis annonce un acompte, et un devis au
    taux réduit demande en plus l'attestation signée du client. Chacun est
    réglable dans les Paramètres ; vide, il retombe sur celui du devis.
    """
    if est_facture and societe.conditions_facture:
        return societe.conditions_facture
    reduites = getattr(societe, "conditions_devis_reduit", "")
    if not est_facture and reduit and reduites:
        return reduites
    return societe.conditions_paiement


def mentions_par_defaut(societe, est_facture: bool) -> str:
    """Les mentions qui conviennent au document.

    Un devis annonce sa validité et les avenants ; une facture porte les
    mentions obligatoires du code de commerce. Les deux se règlent dans les
    Paramètres, et c'est le type du document qui tranche — pas ce qui a été
    recopié dedans le jour de sa création.
    """
    return societe.mentions_facture if est_facture else societe.mentions_devis
