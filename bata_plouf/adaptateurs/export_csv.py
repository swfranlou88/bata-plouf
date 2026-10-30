"""Écriture des fichiers remis au comptable.

Trois choix de format, tous dictés par ce qui s'ouvre sans bagarre chez un
comptable français :

  séparateur point-virgule   le séparateur attendu par Excel en français ;
  encodage UTF-8 avec BOM    sans lui, Excel abîme les accents ;
  virgule décimale           sinon les montants arrivent comme du texte.

Les montants sont écrits sans symbole ni séparateur de milliers : c'est un
fichier de travail, pas un document à lire.
"""

import csv
from decimal import Decimal
from pathlib import Path

from ..domaine.comptabilite import (
    Ecriture, LigneJournal, LigneTVAPeriode, Periode, ecritures_ventes, equilibre,
    journal_des_ventes, recapitulatif_tva, taux_rencontres,
)
from ..domaine.formats import date_fr, nombre
from ..domaine.ports import RegistreVentes

SEPARATEUR = ";"
ENCODAGE = "utf-8-sig"


def _montant(valeur: Decimal) -> str:
    """1234.56 -> « 1234,56 », tel qu'un tableur français l'attend."""
    return f"{valeur:.2f}".replace(".", ",")


def _ecrire(chemin: Path, entetes: list[str], rangs) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding=ENCODAGE, newline="") as fichier:
        graveur = csv.writer(fichier, delimiter=SEPARATEUR, quoting=csv.QUOTE_MINIMAL)
        graveur.writerow(entetes)
        graveur.writerows(rangs)
    return chemin


def _suffixe(periode: Periode) -> str:
    """« Année 2026 » -> « annee-2026 ».

    Sans accent ni espace : le fichier voyagera par courriel, par clé USB et
    sur le poste du comptable, qui n'est pas forcément un Mac.
    """
    import unicodedata
    texte = unicodedata.normalize("NFD", str(periode))
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return "".join(c if c.isalnum() else "-" for c in texte.lower()).strip("-")


# --- journal des ventes ---------------------------------------------------


def ecrire_journal_ventes(dossier: Path, lignes: list[LigneJournal],
                          periode: Periode) -> Path:
    taux = taux_rencontres(lignes)
    entetes = ["Date", "Numéro", "Type", "Client", "Objet"]
    for t in taux:
        entetes += [f"Base {nombre(t)} %", f"TVA {nombre(t)} %"]
    entetes += ["Total HT", "Total TVA", "Total TTC", "Statut", "Règlement", "Payée le"]

    rangs = []
    for ligne in lignes:
        rang = [date_fr(ligne.date_facture), ligne.numero, ligne.type,
                ligne.client, ligne.objet]
        for t in taux:
            rang += [_montant(ligne.bases.get(t, Decimal("0.00"))),
                     _montant(ligne.tva.get(t, Decimal("0.00")))]
        rang += [_montant(ligne.total_ht), _montant(ligne.total_tva),
                 _montant(ligne.total_ttc), ligne.statut, ligne.mode_paiement,
                 date_fr(ligne.date_paiement)]
        rangs.append(rang)

    # Une ligne de total, pour que le comptable vérifie d'un coup d'œil
    if lignes:
        total = ["", "", "", "", "TOTAL"]
        for t in taux:
            total += [_montant(sum((l.bases.get(t, Decimal("0.00")) for l in lignes),
                                   Decimal("0.00"))),
                      _montant(sum((l.tva.get(t, Decimal("0.00")) for l in lignes),
                                   Decimal("0.00")))]
        total += [_montant(sum((l.total_ht for l in lignes), Decimal("0.00"))),
                  _montant(sum((l.total_tva for l in lignes), Decimal("0.00"))),
                  _montant(sum((l.total_ttc for l in lignes), Decimal("0.00"))),
                  "", "", ""]
        rangs.append(total)

    return _ecrire(dossier / f"journal-des-ventes-{_suffixe(periode)}.csv",
                   entetes, rangs)


# --- écritures comptables -------------------------------------------------


def ecrire_ecritures(dossier: Path, ecritures: list[Ecriture],
                     periode: Periode) -> Path:
    rangs = [[date_fr(e.date_ecriture), e.journal, e.compte, e.piece, e.libelle,
              _montant(e.debit) if e.debit else "",
              _montant(e.credit) if e.credit else ""]
             for e in ecritures]
    debits, credits = equilibre(ecritures)
    rangs.append(["", "", "", "", "TOTAL", _montant(debits), _montant(credits)])
    return _ecrire(dossier / f"ecritures-ventes-{_suffixe(periode)}.csv",
                   ["Date", "Journal", "Compte", "Pièce", "Libellé", "Débit", "Crédit"],
                   rangs)


# --- récapitulatif de TVA -------------------------------------------------


def ecrire_recapitulatif_tva(dossier: Path, lignes: list[LigneTVAPeriode],
                             periode: Periode) -> Path:
    rangs = [[f"{nombre(l.taux)} %", _montant(l.base_ht), _montant(l.tva)]
             for l in lignes]
    rangs.append(["TOTAL",
                  _montant(sum((l.base_ht for l in lignes), Decimal("0.00"))),
                  _montant(sum((l.tva for l in lignes), Decimal("0.00")))])
    return _ecrire(dossier / f"recapitulatif-tva-{_suffixe(periode)}.csv",
                   ["Taux", "Base HT", "TVA collectée"], rangs)


# --- tout d'un coup -------------------------------------------------------


def exporter(depot: RegistreVentes, periode: Periode, dossier: Path,
             journal: bool = True, ecritures: bool = True,
             tva: bool = True) -> list[Path]:
    """Écrit les fichiers demandés et renvoie leurs chemins."""
    dossier = Path(dossier)
    produits = []
    lignes = journal_des_ventes(depot, periode)
    if journal:
        produits.append(ecrire_journal_ventes(dossier, lignes, periode))
    if ecritures:
        produits.append(ecrire_ecritures(dossier, ecritures_ventes(depot, periode),
                                         periode))
    if tva:
        produits.append(ecrire_recapitulatif_tva(dossier,
                                                 recapitulatif_tva(depot, periode),
                                                 periode))
    return produits
