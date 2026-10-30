"""Écran d'export comptable : choisir une période, produire les fichiers."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QLabel, QVBoxLayout,
)

from ...domaine.comptabilite import (
    Periode, annees_disponibles, ecritures_ventes, equilibre,
    factures_de_la_periode, journal_des_ventes, periode_annee, periode_mois,
    periode_trimestre, recapitulatif_tva,
)
from ...domaine.formats import euros, nombre
from ..export_csv import exporter
from ..systeme import ouvrir_dossier
from .commun import alerter, barre, bouton, confirmer, discret, informer, liste_deroulante

MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
        "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
DECOUPAGES = (["Année entière"]
              + [f"{n}ᵉ trimestre" if n > 1 else "1er trimestre" for n in range(1, 5)]
              + MOIS)


class DialogueExportComptable(QDialog):
    """Sort le journal des ventes, les écritures et le récapitulatif de TVA.

    Le contenu de la période s'affiche avant d'écrire quoi que ce soit, avec le
    contrôle d'équilibre : un export qui ne tombe pas juste ne doit pas quitter
    le logiciel.
    """

    def __init__(self, parent, depot):
        super().__init__(parent)
        self.depot = depot
        self.setWindowTitle("Export comptable")
        self.setMinimumWidth(620)

        self.annee = liste_deroulante(annees_disponibles(depot))
        self.decoupage = liste_deroulante(DECOUPAGES)
        self.annee.currentIndexChanged.connect(self._resumer)
        self.decoupage.currentIndexChanged.connect(self._resumer)

        self.resume = QLabel()
        self.resume.setTextFormat(Qt.TextFormat.RichText)
        self.controle = QLabel()
        self.controle.setWordWrap(True)

        self.journal = QCheckBox("Journal des ventes — une ligne par facture, "
                                 "lisible dans un tableur")
        self.ecritures = QCheckBox("Écritures comptables — partie double, à importer "
                                   "dans un logiciel comptable")
        self.tva = QCheckBox("Récapitulatif de TVA — base et TVA collectée par taux")
        for case in (self.journal, self.ecritures, self.tva):
            case.setChecked(True)

        periode_boite = QGroupBox("Période")
        formulaire = QFormLayout(periode_boite)
        formulaire.addRow("Année", self.annee)
        formulaire.addRow("Découpage", self.decoupage)
        formulaire.addRow("Contenu", self.resume)
        formulaire.addRow("", self.controle)

        fichiers = QGroupBox("Fichiers à produire")
        colonne = QVBoxLayout(fichiers)
        for case in (self.journal, self.ecritures, self.tva):
            colonne.addWidget(case)

        self.bouton_exporter = bouton("Exporter…", self.exporter, principal=True)
        boutons = QDialogButtonBox()
        boutons.addButton(self.bouton_exporter, QDialogButtonBox.ButtonRole.AcceptRole)
        fermer = boutons.addButton("Fermer", QDialogButtonBox.ButtonRole.RejectRole)
        fermer.clicked.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.addWidget(periode_boite)
        disposition.addWidget(fichiers)
        note = discret(
            "Les brouillons sont exclus : ils n'ont pas d'existence comptable. "
            "Les factures annulées restent incluses, avec l'avoir qui les "
            "contrepasse — sinon le journal ne serait plus équilibré.")
        note.setWordWrap(True)
        disposition.addWidget(note)
        disposition.addWidget(boutons)

        self._resumer()

    # --- période ---------------------------------------------------------

    def periode(self) -> Periode:
        annee = int(self.annee.currentData())
        rang = self.decoupage.currentIndex()
        if rang == 0:
            return periode_annee(annee)
        if rang <= 4:
            return periode_trimestre(annee, rang)
        return periode_mois(annee, rang - 4)

    def _resumer(self) -> None:
        periode = self.periode()
        factures = factures_de_la_periode(self.depot, periode)
        lignes = journal_des_ventes(self.depot, periode)
        ht = sum((l.total_ht for l in lignes), start=__import__("decimal").Decimal("0.00"))
        ttc = sum((l.total_ttc for l in lignes), start=__import__("decimal").Decimal("0.00"))

        self.resume.setText(
            f"<b>{len(factures)}</b> facture(s) · <b>{euros(ht)}</b> HT · "
            f"<b>{euros(ttc)}</b> TTC")

        debits, credits = equilibre(ecritures_ventes(self.depot, periode))
        if not factures:
            self.controle.setText("")
        elif debits == credits:
            self.controle.setText(
                f"Écritures équilibrées : {euros(debits)} au débit comme au crédit.")
        else:
            self.controle.setText(
                f"⚠ Déséquilibre de {euros(debits - credits)} entre débit et crédit. "
                "Signalez-le avant de transmettre quoi que ce soit.")
        self.bouton_exporter.setEnabled(bool(factures))

    # --- export ----------------------------------------------------------

    def exporter(self) -> None:
        periode = self.periode()
        if not any(c.isChecked() for c in (self.journal, self.ecritures, self.tva)):
            alerter(self, "Rien à produire", "Cochez au moins un fichier.")
            return

        dossier = QFileDialog.getExistingDirectory(
            self, "Où déposer les fichiers pour le comptable ?",
            str(self.depot.racine))
        if not dossier:
            return

        try:
            produits = exporter(self.depot, periode, Path(dossier),
                                journal=self.journal.isChecked(),
                                ecritures=self.ecritures.isChecked(),
                                tva=self.tva.isChecked())
        except OSError as erreur:
            alerter(self, "Écriture impossible", str(erreur))
            return

        liste = "\n".join(f"  · {chemin.name}" for chemin in produits)
        if confirmer(self, "Export terminé",
                     f"{len(produits)} fichier(s) écrits pour « {periode} » :\n\n"
                     f"{liste}\n\nOuvrir le dossier ?"):
            ouvrir_dossier(dossier)
