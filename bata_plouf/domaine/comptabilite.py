"""Comptabilité des ventes : ce qu'on remet au comptable.

Deux sorties, parce que les cabinets ne travaillent pas tous pareil :

  le journal des ventes   une ligne par facture, lisible tel quel dans un
                          tableur — c'est ce que réclame un comptable qui
                          ressaisit lui-même ;
  les écritures           la même chose en partie double, prête à être
                          importée dans un logiciel comptable.

Une troisième sortie, le récapitulatif de TVA par taux, sert à remplir la
déclaration.

Ce module ne sait pas écrire un fichier : il produit des lignes, l'adaptateur
s'occupe du reste.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .calculs import calculer_totaux, sou
from .entites import Facture, Societe
from .formats import nombre
from .ports import RegistreVentes

# Un brouillon n'a pas d'existence comptable. Une facture annulée, si : elle a
# été émise, et c'est l'avoir qui la contrepasse — exclure l'une sans l'autre
# déséquilibrerait le journal.
STATUTS_COMPTABLES = ("émise", "payée", "annulée")

ZERO = Decimal("0.00")


# --- période --------------------------------------------------------------


@dataclass(frozen=True)
class Periode:
    debut: str  # ISO, inclus
    fin: str    # ISO, inclus
    libelle: str = ""

    def contient(self, jour: str) -> bool:
        return bool(jour) and self.debut <= jour[:10] <= self.fin

    def __str__(self) -> str:
        return self.libelle or f"du {self.debut} au {self.fin}"


def periode_annee(annee: int) -> Periode:
    return Periode(f"{annee}-01-01", f"{annee}-12-31", f"Année {annee}")


def periode_trimestre(annee: int, trimestre: int) -> Periode:
    premier = 3 * (trimestre - 1) + 1
    dernier = premier + 2
    fin_jour = 31 if dernier in (3, 12) else 30
    return Periode(f"{annee}-{premier:02d}-01", f"{annee}-{dernier:02d}-{fin_jour:02d}",
                   f"{trimestre}ᵉ trimestre {annee}")


def periode_mois(annee: int, mois: int) -> Periode:
    import calendar
    dernier = calendar.monthrange(annee, mois)[1]
    nom = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"][mois - 1]
    return Periode(f"{annee}-{mois:02d}-01", f"{annee}-{mois:02d}-{dernier:02d}",
                   f"{nom.capitalize()} {annee}")


def annees_disponibles(depot: RegistreVentes) -> list[int]:
    annees = {int(f.date_facture[:4]) for f in depot.factures()
              if f.statut in STATUTS_COMPTABLES and len(f.date_facture) >= 4}
    return sorted(annees, reverse=True) or [date.today().year]


# --- sélection ------------------------------------------------------------


def factures_de_la_periode(depot: RegistreVentes, periode: Periode) -> list[Facture]:
    retenues = [f for f in depot.factures()
                if f.statut in STATUTS_COMPTABLES and periode.contient(f.date_facture)]
    return sorted(retenues, key=lambda f: (f.date_facture, f.numero))


# --- journal des ventes ---------------------------------------------------


@dataclass
class LigneJournal:
    date_facture: str
    numero: str
    type: str
    client: str
    objet: str
    bases: dict[float, Decimal] = field(default_factory=dict)
    tva: dict[float, Decimal] = field(default_factory=dict)
    total_ht: Decimal = ZERO
    total_tva: Decimal = ZERO
    total_ttc: Decimal = ZERO
    statut: str = ""
    mode_paiement: str = ""
    date_paiement: str = ""


def journal_des_ventes(depot: RegistreVentes, periode: Periode) -> list[LigneJournal]:
    lignes = []
    for facture in factures_de_la_periode(depot, periode):
        totaux = calculer_totaux(facture)
        lignes.append(LigneJournal(
            date_facture=facture.date_facture,
            numero=facture.numero,
            type=facture.libelle_type,
            client=depot.nom_client(facture.client_id) or "(client inconnu)",
            objet=facture.objet,
            bases={l.taux: l.base_ht for l in totaux.tva},
            tva={l.taux: l.montant for l in totaux.tva},
            total_ht=totaux.total_ht,
            total_tva=totaux.total_tva,
            total_ttc=totaux.total_ttc,
            statut=facture.statut,
            mode_paiement=facture.mode_paiement,
            date_paiement=facture.date_paiement,
        ))
    return lignes


def taux_rencontres(lignes: list[LigneJournal]) -> list[float]:
    """Les taux de TVA présents sur la période, du plus fort au plus faible."""
    return sorted({taux for ligne in lignes for taux in ligne.bases}, reverse=True)


# --- écritures comptables -------------------------------------------------


@dataclass
class Ecriture:
    date_ecriture: str
    journal: str
    compte: str
    piece: str
    libelle: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO


def _poser(compte: str, montant: Decimal, au_debit: bool, date_: str, journal: str,
           piece: str, libelle: str) -> Ecriture:
    """Place un montant du bon côté.

    Un montant négatif — le cas d'un avoir — bascule de l'autre côté plutôt
    que d'apparaître en négatif : c'est ainsi que se tient une comptabilité.
    """
    if montant < 0:
        montant, au_debit = -montant, not au_debit
    return Ecriture(
        date_ecriture=date_, journal=journal, compte=compte, piece=piece,
        libelle=libelle,
        debit=sou(montant) if au_debit else ZERO,
        credit=ZERO if au_debit else sou(montant),
    )


def ecritures_ventes(depot: RegistreVentes, periode: Periode) -> list[Ecriture]:
    societe: Societe = depot.societe
    journal = societe.journal_ventes or "VE"
    ecritures: list[Ecriture] = []

    for facture in factures_de_la_periode(depot, periode):
        totaux = calculer_totaux(facture)
        client = depot.nom_client(facture.client_id) or "(client inconnu)"
        intitule = f"{client} — {facture.libelle_type}"
        commun = (facture.date_facture, journal, facture.numero)

        # Le client doit le TTC
        ecritures.append(_poser(societe.compte_client, totaux.total_ttc, True,
                                *commun, intitule))
        # La vente et la TVA viennent en face, taux par taux
        for ligne in totaux.tva:
            ecritures.append(_poser(
                societe.compte_ventes, ligne.base_ht, False, *commun,
                f"{intitule} — TVA {nombre(ligne.taux)} %"))
            compte_tva = societe.compte_tva(ligne.taux)
            if compte_tva and ligne.montant:
                ecritures.append(_poser(
                    compte_tva, ligne.montant, False, *commun,
                    f"TVA collectée {nombre(ligne.taux)} % — {facture.numero}"))
    return ecritures


def equilibre(ecritures: list[Ecriture]) -> tuple[Decimal, Decimal]:
    """Total des débits et des crédits ; ils doivent être égaux."""
    return (sou(sum((e.debit for e in ecritures), ZERO)),
            sou(sum((e.credit for e in ecritures), ZERO)))


# --- récapitulatif de TVA -------------------------------------------------


@dataclass
class LigneTVAPeriode:
    taux: float
    base_ht: Decimal
    tva: Decimal


def recapitulatif_tva(depot: RegistreVentes, periode: Periode) -> list[LigneTVAPeriode]:
    """Base et TVA collectée par taux, pour remplir la déclaration."""
    bases: dict[float, Decimal] = {}
    taxes: dict[float, Decimal] = {}
    for facture in factures_de_la_periode(depot, periode):
        for ligne in calculer_totaux(facture).tva:
            bases[ligne.taux] = bases.get(ligne.taux, ZERO) + ligne.base_ht
            taxes[ligne.taux] = taxes.get(ligne.taux, ZERO) + ligne.montant
    return [LigneTVAPeriode(taux, sou(bases[taux]), sou(taxes[taux]))
            for taux in sorted(bases, reverse=True)]
