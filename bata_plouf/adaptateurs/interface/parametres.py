"""Paramètres de l'entreprise et gestion du dossier de données."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QLabel, QPlainTextEdit,
    QScrollArea, QVBoxLayout, QWidget,
)

from ...domaine import TAUX_TVA, Societe
from .commun import (
    alerter, barre, bouton, champ_entier, champ_pourcent, champ_texte, discret,
    informer, liste_deroulante, titre,
)
from ...adaptateurs.systeme import ouvrir_dossier
from .comptabilite import DialogueExportComptable
from .mise_a_jour import DialogueMiseAJour
from .importation import DialogueImport


class VueParametres(QWidget):
    donnees_modifiees = Signal()

    def __init__(self, depot, parent=None):
        super().__init__(parent)
        self.depot = depot
        s = depot.societe

        self.nom = champ_texte(s.nom, "Maçonnerie Dupont")
        self.forme = champ_texte(s.forme_juridique, "EURL au capital de 10 000 €")
        self.adresse = champ_texte(s.adresse)
        self.cp = champ_texte(s.cp)
        self.ville = champ_texte(s.ville)
        self.telephone = champ_texte(s.telephone)
        self.email = champ_texte(s.email)
        self.logo = champ_texte(s.logo)
        self.logo.setReadOnly(True)
        self.logo.setPlaceholderText("Aucun logo")

        self.siret = champ_texte(s.siret, "14 chiffres")
        self.ape = champ_texte(s.code_ape, "4399C")
        self.tva_intra = champ_texte(s.tva_intracom, "FR12345678901")
        self.rcs = champ_texte(s.rcs)
        self.capital = champ_texte(s.capital)

        self.assurance = champ_texte(s.assurance_nom, "Nom de l'assureur")
        self.contrat = champ_texte(s.assurance_contrat, "N° de contrat")
        self.couverture = champ_texte(s.assurance_couverture)
        self.qualifications = champ_texte(s.qualifications, "RGE, Qualibat…")

        self.iban = champ_texte(s.iban)
        self.bic = champ_texte(s.bic)

        self.validite = champ_entier(s.validite_jours, 999)
        self.validite.setSuffix(" jours")
        self.tva_defaut = liste_deroulante(TAUX_TVA, s.taux_tva_defaut)
        self.acompte = champ_pourcent(s.acompte_defaut_pct)
        self.conditions = QPlainTextEdit(s.conditions_paiement)
        self.conditions.setMaximumHeight(70)
        self.mentions = QPlainTextEdit(s.mentions_devis)
        self.mentions.setMaximumHeight(70)

        self.journal_ventes = champ_texte(s.journal_ventes, "VE")
        self.compte_client = champ_texte(s.compte_client, "411000")
        self.compte_ventes = champ_texte(s.compte_ventes, "704000")
        comptes = s.comptes_tva or {}
        self.compte_tva_20 = champ_texte(comptes.get("20.0", ""), "445710")
        self.compte_tva_10 = champ_texte(comptes.get("10.0", ""), "445711")
        self.compte_tva_55 = champ_texte(comptes.get("5.5", ""), "445712")

        self.depot_maj = champ_texte(s.depot_mises_a_jour, "compte/bata-plouf")
        self.mode_maj = liste_deroulante(
            ["auto", "demander", "jamais"], s.mises_a_jour or "auto")
        for rang, texte in enumerate((
                "Automatiques — installées au lancement",
                "Me demander avant d'installer",
                "Jamais — aucun accès au réseau")):
            self.mode_maj.setItemText(rang, texte)

        self.dossier = QLabel(str(depot.racine))
        self.dossier.setWordWrap(True)

        self._construire()

    def _groupe(self, titre_: str, champs: list[tuple[str, object]]) -> QGroupBox:
        groupe = QGroupBox(titre_)
        formulaire = QFormLayout(groupe)
        for etiquette, widget in champs:
            formulaire.addRow(etiquette, widget)
        return groupe

    def _construire(self) -> None:
        contenu = QWidget()
        disposition = QVBoxLayout(contenu)
        disposition.setSpacing(12)

        disposition.addWidget(self._groupe("Identité", [
            ("Raison sociale", self.nom),
            ("Forme juridique", self.forme),
            ("Adresse", self.adresse),
            ("Code postal", self.cp),
            ("Ville", self.ville),
            ("Téléphone", self.telephone),
            ("Courriel", self.email),
            ("Logo", barre(self.logo, bouton("Choisir…", self._choisir_logo),
                           bouton("Retirer", self._retirer_logo))),
        ]))
        disposition.addWidget(self._groupe("Mentions légales", [
            ("SIRET", self.siret),
            ("Code APE", self.ape),
            ("TVA intracommunautaire", self.tva_intra),
            ("RCS", self.rcs),
            ("Capital", self.capital),
        ]))
        disposition.addWidget(self._groupe("Assurance et qualifications", [
            ("Assurance décennale", self.assurance),
            ("N° de contrat", self.contrat),
            ("Zone de couverture", self.couverture),
            ("Qualifications", self.qualifications),
        ]))
        disposition.addWidget(self._groupe("Coordonnées bancaires", [
            ("IBAN", self.iban),
            ("BIC", self.bic),
        ]))
        disposition.addWidget(self._groupe("Valeurs par défaut des devis", [
            ("Durée de validité", self.validite),
            ("Taux de TVA", self.tva_defaut),
            ("Acompte", self.acompte),
            ("Conditions de règlement", self.conditions),
            ("Mentions", self.mentions),
        ]))
        disposition.addWidget(self._groupe("Comptabilité", [
            ("Journal des ventes", self.journal_ventes),
            ("Compte clients", self.compte_client),
            ("Compte de ventes", self.compte_ventes),
            ("TVA collectée 20 %", self.compte_tva_20),
            ("TVA collectée 10 %", self.compte_tva_10),
            ("TVA collectée 5,5 %", self.compte_tva_55),
            ("", barre(bouton("Export comptable…", self._exporter_comptable), "-")),
        ]))
        disposition.addWidget(self._groupe("Mises à jour", [
            ("Dépôt GitHub", self.depot_maj),
            ("Mises à jour", self.mode_maj),
            ("", barre(bouton("Rechercher une mise à jour", self._chercher_maj), "-")),
        ]))
        disposition.addWidget(self._groupe("Données", [
            ("Dossier", self.dossier),
            ("", barre(bouton("Ouvrir le dossier", self._ouvrir_dossier),
                       bouton("Sauvegarder maintenant", self._sauvegarder),
                       bouton("Exporter une copie…", self._exporter), "-")),
            ("Ancien logiciel", barre(
                bouton("Reprendre les données de Batappli…", self._importer), "-")),
        ]))
        disposition.addStretch(1)

        defilement = QScrollArea()
        defilement.setWidget(contenu)
        defilement.setWidgetResizable(True)

        principale = QVBoxLayout(self)
        principale.setContentsMargins(16, 14, 16, 14)
        principale.setSpacing(10)
        principale.addWidget(titre("Paramètres"))
        # ESSAI DE MISE À JOUR — ce rouge n'a pas d'autre raison d'être que
        # de vérifier qu'une nouvelle version arrive bien jusqu'au poste de
        # l'utilisateur. À remettre en gris une fois le test concluant.
        avertissement = discret(
            "Ces informations figurent sur chaque devis imprimé. Le SIRET et "
            "l'assurance décennale sont des mentions obligatoires.")
        avertissement.setStyleSheet("color: #c0392b; font-weight: bold;")
        principale.addWidget(avertissement)
        principale.addWidget(defilement, 1)
        principale.addWidget(barre("-", bouton("Enregistrer", self.enregistrer, principal=True)))

    # --- actions ---------------------------------------------------------

    def _choisir_logo(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir le logo", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.gif *.bmp)")
        if chemin:
            self.logo.setText(chemin)

    def _retirer_logo(self) -> None:
        self.logo.setText("")

    def _ouvrir_dossier(self) -> None:
        if not ouvrir_dossier(self.depot.racine):
            alerter(self, "Ouverture impossible",
                    f"Le dossier se trouve ici :\n{self.depot.racine}")

    def _sauvegarder(self) -> None:
        cible = self.depot.creer_sauvegarde()
        if cible is None:
            informer(self, "Rien à sauvegarder", "Le dossier de données est encore vide.")
        else:
            informer(self, "Sauvegarde créée", f"Instantané enregistré dans :\n{cible}")

    def _exporter(self) -> None:
        dossier = QFileDialog.getExistingDirectory(
            self, "Où déposer la copie ? (clé USB, disque externe, iCloud…)", str(Path.home()))
        if not dossier:
            return
        try:
            cible = self.depot.exporter_vers(Path(dossier))
        except OSError as erreur:
            alerter(self, "Export impossible", str(erreur))
            return
        informer(self, "Copie effectuée", f"Vos données ont été copiées dans :\n{cible}")

    def _chercher_maj(self) -> None:
        DialogueMiseAJour(self, self.depot_maj.text().strip()).exec()

    def _exporter_comptable(self) -> None:
        DialogueExportComptable(self, self.depot).exec()

    def _importer(self) -> None:
        dialogue = DialogueImport(self, self.depot)
        dialogue.exec()
        self.donnees_modifiees.emit()

    def enregistrer(self) -> None:
        societe = Societe(
            nom=self.nom.text().strip(),
            forme_juridique=self.forme.text().strip(),
            adresse=self.adresse.text().strip(),
            cp=self.cp.text().strip(),
            ville=self.ville.text().strip(),
            telephone=self.telephone.text().strip(),
            email=self.email.text().strip(),
            logo=self.logo.text().strip(),
            siret=self.siret.text().strip(),
            code_ape=self.ape.text().strip(),
            tva_intracom=self.tva_intra.text().strip(),
            rcs=self.rcs.text().strip(),
            capital=self.capital.text().strip(),
            assurance_nom=self.assurance.text().strip(),
            assurance_contrat=self.contrat.text().strip(),
            assurance_couverture=self.couverture.text().strip(),
            qualifications=self.qualifications.text().strip(),
            iban=self.iban.text().strip(),
            bic=self.bic.text().strip(),
            validite_jours=self.validite.value(),
            taux_tva_defaut=float(self.tva_defaut.currentData()),
            acompte_defaut_pct=self.acompte.value(),
            conditions_paiement=self.conditions.toPlainText().strip(),
            mentions_devis=self.mentions.toPlainText().strip(),
            mentions_facture=self.depot.societe.mentions_facture,
            delai_paiement_jours=self.depot.societe.delai_paiement_jours,
            depot_mises_a_jour=self.depot_maj.text().strip(),
            mises_a_jour=self.mode_maj.currentData() or "auto",
            journal_ventes=self.journal_ventes.text().strip() or "VE",
            compte_client=self.compte_client.text().strip(),
            compte_ventes=self.compte_ventes.text().strip(),
            comptes_tva={
                "20.0": self.compte_tva_20.text().strip(),
                "10.0": self.compte_tva_10.text().strip(),
                "5.5": self.compte_tva_55.text().strip(),
                "0.0": "",
            },
        )
        self.depot.enregistrer_societe(societe)
        self.donnees_modifiees.emit()
        informer(self, "Paramètres enregistrés",
                 "Les prochains devis imprimés reprendront ces informations.")

    def rafraichir(self) -> None:
        self.dossier.setText(str(self.depot.racine))
