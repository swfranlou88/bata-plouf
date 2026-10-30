"""Fabrication des factures à partir d'un devis — service du domaine.

Trois façons de facturer un chantier, et une pour se corriger :

  acompte    un pourcentage du marché, demandé à la commande ;
  situation  un avancement cumulé — la facture ne réclame que ce qui n'a pas
             déjà été facturé, acomptes compris ;
  solde      tout le reste, à la fin des travaux ;
  avoir      annule une facture déjà émise, qui n'est plus modifiable.

Le point délicat est la TVA. Un acompte de 30 % sur un chantier qui mélange du
20 % et du 10 % ne peut pas être facturé à un taux moyen : il faut une ligne
par taux, calculée sur la base correspondante du devis. C'est ce que fait
`_lignes_par_taux`, et c'est ce qui garantit que la somme des factures retombe
exactement sur le total du devis.
"""

from dataclasses import dataclass
from decimal import Decimal

from .calculs import sou
from .entites import Devis, Facture, Ligne, nouvel_id
from .formats import euros, nombre, taux_tva_txt
from .ports import JournalFactures

# Une facture annulée compte encore : c'est l'avoir qui la contrepasse, et
# retirer les deux déduirait son montant deux fois du reste à facturer. Le
# brouillon compte aussi, pour ne pas facturer deux fois la même chose pendant
# qu'une facture est préparée.
STATUTS_COMPTES = ("brouillon", "émise", "payée", "annulée")


# --- ce qui a déjà été facturé -------------------------------------------


def factures_du_devis(depot: JournalFactures, devis_id: str) -> list[Facture]:
    factures = [f for f in depot.factures() if f.devis_id == devis_id]
    return sorted(factures, key=lambda f: (f.date_facture, f.numero))


def _comptabilisable(facture: Facture) -> bool:
    """Une facture annulée ne compte plus ; un brouillon, si.

    Compter les brouillons évite de facturer deux fois la même chose quand une
    facture est préparée mais pas encore émise.
    """
    return facture.statut in STATUTS_COMPTES


def deja_facture_par_taux(depot: JournalFactures, devis_id: str, ignorer_id: str = "",
                          avant: Facture | None = None) -> dict[float, Decimal]:
    """Montants HT déjà facturés pour ce devis, ventilés par taux de TVA.

    Les avoirs portent des montants négatifs, ils se déduisent donc tout seuls.
    « avant » limite le calcul aux factures antérieures, pour le rappel imprimé
    en bas d'une facture.
    """
    cumul: dict[float, Decimal] = {}
    for facture in factures_du_devis(depot, devis_id):
        if facture.id == ignorer_id or not _comptabilisable(facture):
            continue
        if avant is not None:
            if (facture.date_facture, facture.numero) >= (avant.date_facture, avant.numero):
                continue
        for ligne in facture.totaux().tva:
            cumul[ligne.taux] = cumul.get(ligne.taux, Decimal("0.00")) + ligne.base_ht
    return cumul


def deja_facture_ht(depot, devis_id: str, ignorer_id: str = "",
                    avant: Facture | None = None) -> Decimal:
    return sou(sum(deja_facture_par_taux(depot, devis_id, ignorer_id, avant).values(),
                   Decimal("0.00")))


def bases_du_devis(devis: Devis) -> dict[float, Decimal]:
    """Base HT par taux de TVA, remise globale déjà déduite."""
    return {l.taux: l.base_ht for l in devis.totaux().tva}


def reste_a_facturer(depot, devis: Devis, ignorer_id: str = "") -> Decimal:
    total = sou(sum(bases_du_devis(devis).values(), Decimal("0.00")))
    return sou(total - deja_facture_ht(depot, devis.id, ignorer_id))


def avancement_facture(depot, devis: Devis, ignorer_id: str = "") -> float:
    """Pourcentage du marché déjà facturé, pour proposer l'avancement suivant."""
    total = sum(bases_du_devis(devis).values(), Decimal("0.00"))
    if not total:
        return 0.0
    return float(round(deja_facture_ht(depot, devis.id, ignorer_id) / total * 100, 2))


# --- avancement poste par poste ------------------------------------------


def coefficient_remise(devis: Devis) -> Decimal:
    return (Decimal("1")
            - Decimal(str(devis.remise_globale_pct or 0)) / Decimal("100"))


def montant_ligne(devis: Devis, ligne: Ligne) -> Decimal:
    """Montant HT d'une ligne du marché, remise globale déduite.

    Arrondi exactement comme dans le calcul des totaux, pour que la somme des
    lignes tombe au centime sur le total du devis.
    """
    return sou(ligne.total_ht * coefficient_remise(devis))


@dataclass
class EtatLigne:
    """Où en est un poste du marché."""

    ligne: Ligne
    montant: Decimal
    deja: Decimal

    @property
    def pct_deja(self) -> float:
        if not self.montant:
            return 0.0
        return float(round(self.deja / self.montant * 100, 2))

    @property
    def reste(self) -> Decimal:
        return sou(self.montant - self.deja)


def etat_avancement(depot: JournalFactures, devis: Devis,
                    ignorer_id: str = "") -> list[EtatLigne]:
    """Pour chaque poste chiffré : son montant, et ce qui en est déjà facturé.

    Seules les lignes d'avancement comptent ici : un acompte n'est pas une
    part de travaux, c'est une avance, déduite séparément.
    """
    deja: dict[str, Decimal] = {}
    for facture in factures_du_devis(depot, devis.id):
        if facture.id == ignorer_id or not _comptabilisable(facture):
            continue
        for ligne in facture.lignes:
            if ligne.ligne_origine and ligne.nature == "avancement":
                deja[ligne.ligne_origine] = (deja.get(ligne.ligne_origine, Decimal("0.00"))
                                             + ligne.total_ht)
    return [EtatLigne(ligne=ligne, montant=montant_ligne(devis, ligne),
                      deja=sou(deja.get(ligne.id, Decimal("0.00"))))
            for ligne in devis.lignes if ligne.chiffree]


def acomptes_a_absorber(depot: JournalFactures, devis: Devis,
                        ignorer_id: str = "") -> dict[float, Decimal]:
    """Acomptes versés qui n'ont pas encore été déduits d'une situation.

    La ventilation est celle de l'acompte lui-même, ce qui garde la TVA juste
    sans avoir à répartir quoi que ce soit au prorata.
    """
    restant: dict[float, Decimal] = {}
    for facture in factures_du_devis(depot, devis.id):
        if facture.id == ignorer_id or not _comptabilisable(facture):
            continue
        if facture.type == "acompte":
            for part in facture.totaux().tva:
                restant[part.taux] = restant.get(part.taux, Decimal("0.00")) + part.base_ht
        for ligne in facture.lignes:
            if ligne.nature == "deduction_acompte":
                restant[ligne.taux_tva] = (restant.get(ligne.taux_tva, Decimal("0.00"))
                                           + ligne.total_ht)  # négatif
    return {taux: sou(montant) for taux, montant in restant.items() if montant > 0}


def prochain_numero_situation(depot, devis_id: str) -> int:
    situations = [f for f in factures_du_devis(depot, devis_id)
                  if f.type == "situation" and _comptabilisable(f)]
    return len(situations) + 1


# --- fabrication des lignes ----------------------------------------------


def _lignes_par_taux(montants: dict[float, Decimal], designation: str,
                     detail: str = "") -> list[Ligne]:
    """Une ligne forfaitaire par taux de TVA, dans l'ordre décroissant."""
    lignes = []
    for taux in sorted(montants, reverse=True):
        montant = sou(montants[taux])
        if not montant:
            continue
        complement = f"Base soumise au taux de {taux_tva_txt(taux)}"
        lignes.append(Ligne(
            id=nouvel_id(),
            designation=designation,
            detail=" — ".join(x for x in [detail, complement] if x),
            quantite=1.0,
            unite="forfait",
            prix_unitaire=float(montant),
            taux_tva=taux,
        ))
    return lignes


def _nouvelle_facture(depot, devis: Devis, type_: str) -> Facture:
    societe = depot.societe
    return Facture(
        type=type_,
        devis_id=devis.id,
        client_id=devis.client_id,
        chantier_id=devis.chantier_id,
        objet=devis.objet,
        adresse_chantier=devis.adresse_chantier,
        echeance_jours=societe.delai_paiement_jours,
        conditions=societe.conditions_paiement,
        mentions=societe.mentions_facture,
    )


# --- les quatre générateurs ----------------------------------------------


def generer_facture_totale(depot: JournalFactures, devis: Devis) -> Facture:
    """Transforme un devis accepté en facture, en reprenant ses lignes.

    C'est le cas courant du petit chantier : un devis, une facture. La facture
    garde le détail poste par poste, contrairement aux acomptes et situations
    qui sont forfaitaires par taux de TVA.
    """
    facture = _nouvelle_facture(depot, devis, "totale")
    facture.pourcentage = 100.0
    facture.remise_globale_pct = devis.remise_globale_pct
    for ligne in devis.lignes:
        facture.lignes.append(Ligne(
            id=nouvel_id(),
            type=ligne.type,
            designation=ligne.designation,
            detail=ligne.detail,
            quantite=ligne.quantite,
            unite=ligne.unite,
            prix_unitaire=ligne.prix_unitaire,
            taux_tva=ligne.taux_tva,
            remise_pct=ligne.remise_pct,
            article_id=ligne.article_id,
        ))
    return facture


def generer_acompte(depot: JournalFactures, devis: Devis, pourcentage: float) -> Facture:
    """Un acompte se calcule sur le marché entier, pas sur ce qui reste.

    Deux acomptes de 30 % font donc bien 60 % du marché.
    """
    facture = _nouvelle_facture(depot, devis, "acompte")
    facture.pourcentage = pourcentage
    part = Decimal(str(pourcentage)) / Decimal("100")
    montants = {taux: sou(base * part) for taux, base in bases_du_devis(devis).items()}
    facture.lignes = _lignes_par_taux(
        montants,
        f"Acompte de {nombre(pourcentage)} % sur le devis {devis.numero}",
        devis.objet,
    )
    return facture


def generer_situation(depot: JournalFactures, devis: Devis,
                      avancements: float | dict[str, float]) -> Facture:
    """Facture l'avancement de chaque poste depuis la situation précédente.

    « avancements » est soit un pourcentage unique appliqué à tout le marché,
    soit un pourcentage par ligne du devis — c'est le cas réel d'un chantier,
    où le terrassement est fini quand les enduits n'ont pas commencé.

    L'acompte déjà versé, s'il en reste à absorber, vient en déduction au bas
    de la situation : c'est une avance sur le marché, pas une part de travaux,
    et le client ne doit pas la payer deux fois.
    """
    facture = _nouvelle_facture(depot, devis, "situation")
    facture.numero_situation = prochain_numero_situation(depot, devis.id)

    etats = {etat.ligne.id: etat for etat in etat_avancement(depot, devis)}
    if isinstance(avancements, dict):
        demande = {cle: float(valeur) for cle, valeur in avancements.items()}
    else:
        demande = {cle: float(avancements) for cle in etats}

    # Avancement d'ensemble, pour l'en-tête du document
    marche = sum((e.montant for e in etats.values()), Decimal("0.00"))
    vise = sum((sou(e.montant * Decimal(str(demande.get(cle, e.pct_deja))) / Decimal("100"))
                for cle, e in etats.items()), Decimal("0.00"))
    facture.pourcentage = float(round(vise / marche * 100, 2)) if marche else 0.0

    brut_par_taux: dict[float, Decimal] = {}
    section_en_attente: Ligne | None = None
    for ligne in devis.lignes:
        if ligne.type == "section":
            section_en_attente = ligne
            continue
        if not ligne.chiffree:
            continue
        etat = etats[ligne.id]
        pct = demande.get(ligne.id, etat.pct_deja)
        cible = sou(etat.montant * Decimal(str(pct)) / Decimal("100"))
        a_facturer = sou(cible - etat.deja)
        if a_facturer <= 0:
            continue

        if section_en_attente is not None:
            facture.lignes.append(Ligne(id=nouvel_id(), type="section",
                                        designation=section_en_attente.designation))
            section_en_attente = None

        detail = (f"Marché {euros(etat.montant)} · avancement {nombre(pct)} %"
                  + (f" · déjà facturé {euros(etat.deja)}" if etat.deja else ""))
        facture.lignes.append(Ligne(
            id=nouvel_id(),
            designation=ligne.designation,
            detail=detail,
            quantite=1.0,
            unite="forfait",
            prix_unitaire=float(a_facturer),
            taux_tva=ligne.taux_tva,
            ligne_origine=ligne.id,
            avancement_pct=pct,
            nature="avancement",
        ))
        brut_par_taux[ligne.taux_tva] = (brut_par_taux.get(ligne.taux_tva, Decimal("0.00"))
                                         + a_facturer)

    # Déduction de l'acompte, sans jamais rendre la situation négative
    restant = acomptes_a_absorber(depot, devis)
    deductions = {taux: min(restant.get(taux, Decimal("0.00")), brut)
                  for taux, brut in brut_par_taux.items()}
    deductions = {taux: montant for taux, montant in deductions.items() if montant > 0}
    if deductions:
        # Sa propre section, pour ne pas fausser le sous-total du dernier lot
        facture.lignes.append(Ligne(id=nouvel_id(), type="section",
                                    designation="Déduction de l'acompte"))
    for taux in sorted(deductions, reverse=True):
        deduction = deductions[taux]
        facture.lignes.append(Ligne(
            id=nouvel_id(),
            designation=f"Acompte déjà versé — déduction ({taux_tva_txt(taux)})",
            detail=f"Devis {devis.numero}",
            quantite=1.0,
            unite="forfait",
            prix_unitaire=float(-deduction),
            taux_tva=taux,
            nature="deduction_acompte",
        ))

    return facture


def generer_solde(depot: JournalFactures, devis: Devis) -> Facture:
    """Tout ce qui n'a pas encore été facturé sur ce devis."""
    facture = _nouvelle_facture(depot, devis, "solde")
    facture.pourcentage = 100.0

    deja = deja_facture_par_taux(depot, devis.id)
    montants = {}
    for taux, base in bases_du_devis(devis).items():
        reste = base - deja.get(taux, Decimal("0.00"))
        if reste > 0:
            montants[taux] = sou(reste)

    facture.lignes = _lignes_par_taux(
        montants,
        f"Solde des travaux — devis {devis.numero}",
        devis.objet,
    )
    return facture


def generer_avoir(depot, source: Facture) -> Facture:
    """Annule une facture émise en reprenant ses lignes au négatif."""
    avoir = Facture(
        type="avoir",
        devis_id=source.devis_id,
        client_id=source.client_id,
        chantier_id=source.chantier_id,
        objet=f"Annulation de la facture {source.numero}",
        echeance_jours=0,
        remise_globale_pct=source.remise_globale_pct,
        facture_source_id=source.id,
        mentions=depot.societe.mentions_facture,
    )
    for ligne in source.lignes:
        copie = Ligne(
            id=nouvel_id(),
            type=ligne.type,
            designation=ligne.designation,
            detail=ligne.detail,
            quantite=ligne.quantite,
            unite=ligne.unite,
            prix_unitaire=-abs(ligne.prix_unitaire),
            taux_tva=ligne.taux_tva,
            remise_pct=ligne.remise_pct,
        )
        avoir.lignes.append(copie)
    return avoir


def generer_facture_directe(depot, client_id: str = "") -> Facture:
    """Une facture sans devis, pour un petit dépannage."""
    societe = depot.societe
    return Facture(
        type="directe",
        client_id=client_id,
        echeance_jours=societe.delai_paiement_jours,
        conditions=societe.conditions_paiement,
        mentions=societe.mentions_facture,
    )


# --- rappel imprimé en bas de facture ------------------------------------


def recapitulatif_marche(depot: JournalFactures, facture: Facture) -> dict | None:
    """Situation du marché à la date de cette facture, pour l'imprimé.

    Rien à rappeler pour une facture sans devis.
    """
    if not facture.devis_id:
        return None
    devis = depot.un_devis(facture.devis_id)
    if devis is None:
        return None

    marche = devis.totaux()
    anterieur = deja_facture_ht(depot, devis.id, ignorer_id=facture.id, avant=facture)
    courant = facture.totaux().total_ht
    return {
        "devis": devis,
        "marche_ht": marche.total_ht,
        "marche_ttc": marche.total_ttc,
        "anterieur_ht": anterieur,
        "courant_ht": courant,
        "reste_ht": sou(marche.total_ht - anterieur - courant),
    }
