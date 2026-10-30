"""Fenêtre principale : navigation à gauche, écran courant à droite."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QStackedWidget, QWidget,
)

from ...domaine import euros
from datetime import date

from .accueil import VueAccueil
from .mise_a_jour import Chercheur, DialogueMiseAJour
from .devis import EditeurDevis, VueDevis
from .factures import DialogueFacturer, EditeurFacture, VueFactures
from .gabarit import VueGabarit
from .parametres import VueParametres
from .vues import VueCatalogue, VueChantiers, VueClients

# L'ordre de la barre latérale reprend celui des catégories de l'accueil.
RUBRIQUES = [
    ("Accueil", "accueil"),
    ("Clients", "clients"),
    ("Devis", "devis"),
    ("Matériaux", "catalogue"),
    ("Factures", "factures"),
    ("Chantiers", "chantiers"),
    ("Modèle du devis", "gabarit"),
    ("Paramètres", "parametres"),
]


class FenetrePrincipale(QMainWindow):
    def __init__(self, depot):
        super().__init__()
        self.depot = depot
        self.editeur: EditeurDevis | None = None

        self.setWindowTitle("Bata-plouf")
        self.resize(1280, 820)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(210)
        self.navigation.setSpacing(2)
        for libelle, _ in RUBRIQUES:
            element = QListWidgetItem(libelle)
            element.setSizeHint(QSize(0, 34))
            self.navigation.addItem(element)
        self.navigation.currentRowChanged.connect(self._changer_rubrique)

        self.vue_accueil = VueAccueil(depot)
        self.vue_devis = VueDevis(depot)
        self.vue_factures = VueFactures(depot)
        self.vue_clients = VueClients(depot)
        self.vue_chantiers = VueChantiers(depot)
        self.vue_catalogue = VueCatalogue(depot)
        self.vue_gabarit = VueGabarit(depot)
        self.vue_parametres = VueParametres(depot)

        self.pages = QStackedWidget()
        for vue in self.vues():
            self.pages.addWidget(vue)
            if hasattr(vue, "donnees_modifiees"):
                vue.donnees_modifiees.connect(self.tout_rafraichir)

        self.vue_accueil.ouvrir_rubrique.connect(
            lambda cle: self.navigation.setCurrentRow(self.rubrique(cle)))
        self.vue_accueil.nouveau_devis.connect(self.vue_devis.nouveau)
        self.vue_accueil.nouveau_client.connect(self.vue_clients.nouveau)
        self.vue_accueil.nouvelle_facture.connect(self.vue_factures.nouveau)
        self.vue_accueil.mise_a_jour_demandee.connect(self.chercher_mise_a_jour)

        self.vue_devis.ouvrir_demande.connect(self.ouvrir_devis)
        self.vue_devis.facturer_demande.connect(self.facturer_devis)
        self.vue_factures.ouvrir_demande.connect(self.ouvrir_facture)

        centre = QWidget()
        disposition = QHBoxLayout(centre)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addWidget(self.navigation)
        disposition.addWidget(self.pages, 1)
        self.setCentralWidget(centre)

        self._menus()
        self.navigation.setCurrentRow(self.rubrique("accueil"))
        self.tout_rafraichir()

    # --- menus -----------------------------------------------------------

    def _menus(self) -> None:
        fichier = self.menuBar().addMenu("Fichier")
        fichier.addAction("Accueil", "Ctrl+0",
                          lambda: self.navigation.setCurrentRow(self.rubrique("accueil")))
        fichier.addSeparator()
        fichier.addAction("Nouveau devis", "Ctrl+N", self.vue_devis.nouveau)
        fichier.addAction("Nouvelle facture", "Ctrl+Shift+N", self.vue_factures.nouveau)
        fichier.addSeparator()
        fichier.addAction("Reprendre les données de l'ancien logiciel…",
                          self.vue_parametres._importer)
        fichier.addSeparator()
        fichier.addAction("Personnaliser le modèle de devis…",
                          lambda: self.navigation.setCurrentRow(self.rubrique("gabarit")))
        fichier.addSeparator()
        fichier.addAction("Export comptable…", "Ctrl+E",
                          self.vue_parametres._exporter_comptable)
        fichier.addAction("Créer une sauvegarde", self.vue_parametres._sauvegarder)
        fichier.addAction("Exporter une copie…", self.vue_parametres._exporter)
        fichier.addAction("Ouvrir le dossier de données", self.vue_parametres._ouvrir_dossier)

        aide = self.menuBar().addMenu("Aide")
        aide.addAction("Rechercher une mise à jour…", self.chercher_mise_a_jour)
        aide.addAction("À propos", self._a_propos)

    # --- mises à jour ----------------------------------------------------

    def depot_github(self) -> str:
        """Le réglage de l'utilisateur, ou le dépôt inscrit dans le code."""
        from ... import DEPOT_GITHUB
        return (self.depot.societe.depot_mises_a_jour or DEPOT_GITHUB or "").strip()

    def chercher_mise_a_jour(self, version=None, automatique: bool = False) -> None:
        DialogueMiseAJour(self, self.depot_github(), version, automatique).exec()

    def mode_mise_a_jour(self) -> str:
        return (self.depot.societe.mises_a_jour or "auto").strip()

    def verifier_en_arriere_plan(self) -> None:
        """Interroge GitHub au lancement, dans un fil séparé.

        La requête ne part pas si aucun dépôt n'est inscrit, ni si
        l'utilisateur a choisi « jamais » : l'accès au réseau reste son
        choix. Elle pèse deux kilo-octets, donc à chaque lancement.
        """
        depot = self.depot_github()
        if not depot or self.mode_mise_a_jour() == "jamais":
            return

        self._chercheur = Chercheur(depot, self)
        self._chercheur.trouve.connect(self._annoncer)
        self._chercheur.echoue.connect(lambda _: None)  # un échec reste silencieux
        self._chercheur.start()

    def _annoncer(self, version) -> None:
        """Signale la nouvelle version, et propose de l'installer tout de suite.

        Le lancement est le seul moment où redémarrer ne coûte rien : personne
        n'est au milieu d'un devis. Passé ce moment, le bandeau de l'accueil
        prend le relais sans plus rien interrompre.
        """
        if version is None:
            return
        self.vue_accueil.annoncer_mise_a_jour(version.etiquette)
        mode = self.mode_mise_a_jour()

        if mode == "auto":
            # Rien à demander : l'application se met à jour et redémarre.
            self.chercher_mise_a_jour(version, automatique=True)
            return

        # Mode « me demander » : une seule fois par jour, pour ne pas lasser
        aujourdhui = date.today().isoformat()
        if self.depot.compteurs.get("question_maj") == aujourdhui:
            return
        self.depot.compteurs["question_maj"] = aujourdhui
        self.depot.enregistrer_compteurs()

        question = QMessageBox(self)
        question.setWindowTitle("Mise à jour disponible")
        question.setIcon(QMessageBox.Icon.Question)
        question.setText(f"Bata-plouf {version.etiquette} est disponible "
                         f"({version.taille_lisible}).")
        question.setInformativeText(
            "L'installer maintenant ? Le logiciel se fermera et se rouvrira "
            "tout seul.\n\nVos devis, factures et clients ne sont pas touchés.")
        maintenant = question.addButton("Installer maintenant",
                                        QMessageBox.ButtonRole.AcceptRole)
        question.addButton("Plus tard", QMessageBox.ButtonRole.RejectRole)
        question.setDefaultButton(maintenant)
        question.exec()
        if question.clickedButton() is maintenant:
            self.chercher_mise_a_jour(version)

    def closeEvent(self, evenement) -> None:
        """Ne pas quitter pendant qu'une recherche de mise à jour tourne."""
        chercheur = getattr(self, "_chercheur", None)
        if chercheur is not None and chercheur.isRunning():
            chercheur.requestInterruption()
            chercheur.wait(12000)
        super().closeEvent(evenement)

    def _a_propos(self) -> None:
        QMessageBox.about(
            self, "À propos de Bata-plouf",
            "<b>Bata-plouf</b><br><br>"
            "Logiciel de devis pour le bâtiment, fonctionnant entièrement sur ce Mac, "
            "sans connexion internet et sans base de données.<br><br>"
            f"Vos données sont dans :<br><code>{self.depot.racine}</code>")

    # --- navigation ------------------------------------------------------

    def _changer_rubrique(self, rang: int) -> None:
        if self.editeur is not None:
            self._fermer_editeur()
        if 0 <= rang < self.pages.count():
            self.pages.setCurrentIndex(rang)
            vue = self.pages.widget(rang)
            if hasattr(vue, "rafraichir"):
                vue.rafraichir()

    def ouvrir_devis(self, devis) -> None:
        self._ouvrir(EditeurDevis(self.depot, devis), "devis")

    def ouvrir_facture(self, facture) -> None:
        self._ouvrir(EditeurFacture(self.depot, facture), "factures")

    def facturer_devis(self, devis) -> None:
        """Du devis à la facture : on demande quoi facturer, puis on l'ouvre."""
        dialogue = DialogueFacturer(self, self.depot, devis)
        if dialogue.exec() != QDialog.DialogCode.Accepted:
            return
        facture = self.depot.enregistrer_facture(dialogue.facture())
        self.tout_rafraichir()
        self.ouvrir_facture(facture)

    def _ouvrir(self, editeur, retour: str) -> None:
        self._fermer_editeur()
        self.editeur = editeur
        self._retour_vers = retour
        editeur.ferme.connect(self._retour_liste)
        editeur.enregistre.connect(self.tout_rafraichir)
        self.pages.addWidget(editeur)
        self.pages.setCurrentWidget(editeur)

    def _retour_liste(self) -> None:
        rang = self.rubrique(getattr(self, "_retour_vers", "accueil"))
        self._fermer_editeur()
        self.navigation.setCurrentRow(rang)
        self.pages.setCurrentIndex(rang)
        self.pages.widget(rang).rafraichir()

    def _fermer_editeur(self) -> None:
        if self.editeur is None:
            return
        editeur, self.editeur = self.editeur, None
        self.pages.removeWidget(editeur)
        editeur.deleteLater()

    # --- rafraîchissement ------------------------------------------------

    def vues(self) -> tuple:
        """Les écrans, dans l'ordre de la barre de navigation."""
        return (self.vue_accueil, self.vue_clients, self.vue_devis,
                self.vue_catalogue, self.vue_factures, self.vue_chantiers,
                self.vue_gabarit, self.vue_parametres)

    @staticmethod
    def rubrique(cle: str) -> int:
        """Indice d'une rubrique, pour ne pas écrire de numéro en dur."""
        return [c for _, c in RUBRIQUES].index(cle)

    def tout_rafraichir(self) -> None:
        for vue in self.vues():
            if vue is not self.vue_gabarit:  # son aperçu se régénère tout seul
                vue.rafraichir()
        stats = self.depot.statistiques()
        self.statusBar().showMessage(
            f"{stats['devis']} devis · {stats['factures']} factures · "
            f"{stats['clients']} clients · "
            f"{euros(stats['ht_en_attente'])} HT en attente de réponse · "
            f"{euros(stats['ht_facture'])} HT facturé · "
            f"{euros(stats['ttc_impaye'])} TTC restant à encaisser"
        )
