"""Paramètres de l'entreprise et gestion du dossier de données."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QLabel,
    QPlainTextEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ...domaine import TAUX_TVA, Societe
from .commun import (
    alerter, barre, bouton, champ_entier, champ_pourcent, champ_texte, confirmer,
    discret, informer, liste_deroulante, titre,
)
from ...adaptateurs import archive, sauvegarde_mensuelle
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
        self.conditions_reduit = QPlainTextEdit(s.conditions_devis_reduit)
        self.conditions_reduit.setMaximumHeight(70)
        self.conditions_reduit.setPlaceholderText(
            "Pour les travaux à 10 % ou 5,5 % — vide = le texte ci-dessus")
        self.mentions = QPlainTextEdit(s.mentions_devis)
        self.mentions.setMaximumHeight(70)
        self.conditions_f = QPlainTextEdit(s.conditions_facture)
        self.conditions_f.setMaximumHeight(70)
        self.conditions_f.setPlaceholderText(
            "Vide = les mêmes conditions que sur le devis")
        self.mentions_f = QPlainTextEdit(s.mentions_facture)
        self.mentions_f.setMaximumHeight(70)

        self.journal_ventes = champ_texte(s.journal_ventes, "VE")
        self.compte_client = champ_texte(s.compte_client, "411000")
        self.compte_ventes = champ_texte(s.compte_ventes, "704000")
        comptes = s.comptes_tva or {}
        self.compte_tva_20 = champ_texte(comptes.get("20.0", ""), "445710")
        self.compte_tva_10 = champ_texte(comptes.get("10.0", ""), "445711")
        self.compte_tva_55 = champ_texte(comptes.get("5.5", ""), "445712")

        self.etat_sauvegarde = discret(sauvegarde_mensuelle.etat(depot))
        self.etat_sauvegarde.setWordWrap(True)
        # Sans cela, une étiquette qui passe à la ligne garde la hauteur d'une
        # seule et se fait couper par la rangée du formulaire.
        self.etat_sauvegarde.setSizePolicy(QSizePolicy.Policy.Preferred,
                                           QSizePolicy.Policy.MinimumExpanding)
        self.etat_sauvegarde.setMinimumHeight(
            self.etat_sauvegarde.fontMetrics().height() * 2)
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
            ("Conditions — taux normal", self.conditions),
            ("Conditions — taux réduit", self.conditions_reduit),
            ("Mentions", self.mentions),
        ]))
        disposition.addWidget(self._groupe("Valeurs par défaut des factures", [
            ("Conditions de règlement", self.conditions_f),
            ("Mentions", self.mentions_f),
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
        disposition.addWidget(self._groupe("Sauvegarde mensuelle en ligne", [
            ("État", self.etat_sauvegarde),
            ("", barre(bouton("Réglages…", self._regler_sauvegarde),
                       bouton("Sauvegarder en ligne maintenant",
                              self._sauvegarder_en_ligne),
                       bouton("Restaurer depuis le dépôt…",
                              self._restaurer_en_ligne), "-")),
        ]))
        disposition.addWidget(self._groupe("Données", [
            ("Dossier", self.dossier),
            ("", barre(bouton("Ouvrir le dossier", self._ouvrir_dossier),
                       bouton("Sauvegarder maintenant", self._sauvegarder),
                       bouton("Exporter une copie…", self._exporter), "-")),
            ("Archive zip", barre(
                bouton("Exporter en zip…", self._exporter_zip),
                bouton("Importer un zip…", self._importer_zip), "-")),
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
        principale.addWidget(discret(
            "Ces informations figurent sur chaque devis imprimé. Le SIRET et "
            "l'assurance décennale sont des mentions obligatoires."))
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
        if cible is not None:
            informer(self, "Sauvegarde créée", f"Instantané enregistré dans :\n{cible}")
            return
        derniere = self.depot.derniere_sauvegarde()
        if derniere is None:
            informer(self, "Rien à sauvegarder",
                     "Le dossier de données est encore vide.")
            return
        # Une copie identique de plus chasserait un vrai état antérieur de
        # la liste : on le dit plutôt que de faire semblant.
        informer(self, "Rien n'a changé",
                 "Les données n'ont pas bougé depuis la dernière sauvegarde :"
                 f"\n{derniere.name}")

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

    def _exporter_zip(self) -> None:
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer l'archive des données",
            str(Path.home() / archive.nom_propose()), "Archive zip (*.zip)")
        if not chemin:
            return
        try:
            cible = archive.ecrire(self.depot, Path(chemin))
        except OSError as erreur:
            alerter(self, "Export impossible", str(erreur))
            return
        poids = cible.stat().st_size / 1024
        informer(self, "Archive créée",
                 f"Toutes vos données tiennent dans :\n{cible}\n\n"
                 f"{poids:.0f} Ko. Les devis imprimés en PDF n'y sont pas : "
                 "le logiciel sait les refaire à partir des données.")

    def _importer_zip(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Quelle archive reprendre ?", str(Path.home()),
            "Archive zip (*.zip)")
        if not chemin:
            return
        self._reprendre_archive(Path(chemin))

    def _reprendre_archive(self, chemin: Path) -> None:
        # On regarde ce que contient l'archive avant de proposer quoi que ce
        # soit : l'import remplace toute la base, et l'utilisateur doit
        # savoir ce qu'il met à la place.
        inventaire = archive.inspecter(Path(chemin))
        if not inventaire.exploitable:
            alerter(self, "Archive inutilisable",
                    "\n".join(inventaire.problemes)
                    + "\n\nVos données n'ont pas été touchées.")
            return

        venue = (f" du {inventaire.cree_le[:10]}" if inventaire.cree_le else "")
        avec_logo = "\net le logo de l'en-tête" if inventaire.logo else ""
        if not confirmer(
                self, "Remplacer toutes les données",
                f"L'archive{venue} contient :\n{inventaire.resume()}"
                f"{avec_logo}\n\n"
                "Elle remplacera la totalité de vos clients, chantiers, "
                "matériaux, devis et factures.\n\n"
                "Une sauvegarde de l'état actuel est faite juste avant, et "
                "reste récupérable depuis le dossier de données. Continuer ?"):
            return

        try:
            rapport = archive.restaurer(self.depot, Path(chemin))
        except (archive.ErreurArchive, OSError) as erreur:
            alerter(self, "Import interrompu",
                    f"{erreur}\n\nVos données n'ont pas été remplacées.")
            return

        details = [f"{rapport.comptes[c]} {c}" for c in
                   ("clients", "chantiers", "articles", "devis", "factures")]
        message = "Données reprises :\n" + " · ".join(details)
        if rapport.logo:
            message += "\nLe logo de l'en-tête a été repris lui aussi."
        if rapport.sauvegarde:
            message += f"\n\nL'état précédent est conservé dans :\n{rapport.sauvegarde}"
        if rapport.ecartes:
            message += (f"\n\n{len(rapport.ecartes)} fichier(s) de l'archive "
                        "ont été laissés de côté : ils ne font pas partie des "
                        "données du logiciel.")
        if rapport.anomalies:
            message += "\n\nÀ vérifier :\n" + "\n".join(
                f"· {a}" for a in rapport.anomalies[:8])
        informer(self, "Import terminé", message)
        self.rafraichir()
        self.donnees_modifiees.emit()

    def _regler_sauvegarde(self) -> None:
        from .sauvegarde import regler

        regler(self, self.depot)
        self.etat_sauvegarde.setText(sauvegarde_mensuelle.etat(self.depot))

    def _sauvegarder_en_ligne(self) -> None:
        from .sauvegarde import sauvegarder_maintenant

        sauvegarder_maintenant(self, self.depot)
        self.etat_sauvegarde.setText(sauvegarde_mensuelle.etat(self.depot))

    def _restaurer_en_ligne(self) -> None:
        """Rapatrier une sauvegarde chiffrée et la remettre en place."""
        from .sauvegarde import DialogueRestaurer, rapatrier

        if not sauvegarde_mensuelle.depot_vise(self.depot):
            alerter(self, "Aucun dépôt",
                    "Réglez d'abord le dépôt des sauvegardes.")
            return
        dialogue = DialogueRestaurer(self, self.depot)
        if dialogue.exec() != QDialog.DialogCode.Accepted or not dialogue.choix:
            return
        clair = rapatrier(self, self.depot, dialogue.choix)
        if clair is not None:
            # Le reste du chemin est celui d'une archive ordinaire : même
            # inspection, même confirmation, même sauvegarde de l'état actuel.
            self._reprendre_archive(Path(clair))

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
            conditions_devis_reduit=self.conditions_reduit.toPlainText().strip(),
            mentions_devis=self.mentions.toPlainText().strip(),
            conditions_facture=self.conditions_f.toPlainText().strip(),
            mentions_facture=self.mentions_f.toPlainText().strip(),
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
