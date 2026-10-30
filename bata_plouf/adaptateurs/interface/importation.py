"""Écran de reprise des données de l'ancien logiciel."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..import_batappli import (
    CHAMPS, ENCODAGES, Importateur, LIBELLES_CIBLES, Sondage,
    appliquer_reglages, deviner_correspondance, sonder,
)
from .commun import alerter, barre, bouton, discret, informer, titre

SEPARATEURS_LISIBLES = [
    ("Point-virgule  ;", ";"),
    ("Tabulation", "\t"),
    ("Barre verticale  |", "|"),
    ("Virgule  ,", ","),
    ("Aucun (largeur fixe)", ""),
]


class DialogueImport(QDialog):
    """Lit un fichier de l'ancien logiciel et le verse dans la base.

    Rien n'est écrit tant que la simulation n'a pas été relue : c'est le
    garde-fou qui permet de tâtonner sans abîmer les données déjà saisies.
    """

    def __init__(self, parent, depot):
        super().__init__(parent)
        self.depot = depot
        self.sondage: Sondage | None = None
        self.listes_champs: dict[str, QComboBox] = {}

        self.setWindowTitle("Reprise des données de l'ancien logiciel")
        self.resize(980, 760)

        self.fichier = QLabel("Aucun fichier choisi")
        self.fichier.setStyleSheet("font-weight: bold;")

        self.encodage = QComboBox()
        self.encodage.addItems(ENCODAGES)
        self.separateur = QComboBox()
        for libelle, valeur in SEPARATEURS_LISIBLES:
            self.separateur.addItem(libelle, valeur)
        self.entete = QCheckBox("La première ligne contient les noms de colonnes")
        self.cible = QComboBox()
        for cle, libelle in LIBELLES_CIBLES.items():
            self.cible.addItem(libelle, cle)

        self.infos = QLabel("")
        self.infos.setWordWrap(True)

        self.apercu = QTableWidget()
        self.apercu.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.apercu.setAlternatingRowColors(True)
        self.apercu.verticalHeader().setVisible(False)
        self.apercu.setMinimumHeight(170)

        self.zone_champs = QWidget()
        self.disposition_champs = QFormLayout(self.zone_champs)
        defilement = QScrollArea()
        defilement.setWidget(self.zone_champs)
        defilement.setWidgetResizable(True)
        defilement.setMinimumHeight(210)

        self.rapport = QPlainTextEdit()
        self.rapport.setReadOnly(True)
        self.rapport.setMaximumHeight(150)
        self.rapport.setPlaceholderText(
            "Le résultat de la simulation s'affichera ici avant tout import réel."
        )

        self.bouton_simuler = bouton("Simuler", self.simuler)
        self.bouton_importer = bouton("Importer pour de bon", self.importer, principal=True)
        self.bouton_simuler.setEnabled(False)
        self.bouton_importer.setEnabled(False)

        groupe_reglages = QGroupBox("Lecture du fichier")
        reglages = QFormLayout(groupe_reglages)
        reglages.addRow("Fichier", barre(self.fichier, "-",
                                         bouton("Choisir un fichier…", self.choisir)))
        reglages.addRow("Encodage", self.encodage)
        reglages.addRow("Séparateur", self.separateur)
        reglages.addRow("", self.entete)
        reglages.addRow("Importer vers", self.cible)
        reglages.addRow("", self.infos)

        groupe_colonnes = QGroupBox("Correspondance des colonnes")
        colonnes = QVBoxLayout(groupe_colonnes)
        colonnes.addWidget(discret(
            "Chaque champ du logiciel reçoit une colonne du fichier. Ce qui est deviné "
            "d'après les noms de colonnes est pré-rempli — vérifiez, corrigez, "
            "laissez « ignorer » pour ce qui ne vous sert pas."))
        colonnes.addWidget(defilement)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(16, 14, 16, 14)
        disposition.addWidget(titre("Reprise des données"))
        disposition.addWidget(groupe_reglages)
        disposition.addWidget(QLabel("Aperçu du fichier"))
        disposition.addWidget(self.apercu)
        disposition.addWidget(groupe_colonnes, 1)
        disposition.addWidget(QLabel("Rapport"))
        disposition.addWidget(self.rapport)
        disposition.addWidget(barre(
            discret("Une sauvegarde complète est créée avant tout import réel."), "-",
            self.bouton_simuler, self.bouton_importer,
            bouton("Fermer", self.accept)))

        self.encodage.currentTextChanged.connect(self._relire)
        self.separateur.currentIndexChanged.connect(self._relire)
        self.entete.toggled.connect(self._relire)
        self.cible.currentIndexChanged.connect(self._construire_champs)

    # --- fichier ---------------------------------------------------------

    def choisir(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir un fichier de l'ancien logiciel", str(Path.home()),
            "Fichiers texte (*.txt *.csv *.asc *.dat *.prn);;Tous les fichiers (*)")
        if not chemin:
            return
        try:
            self.sondage = sonder(chemin)
        except OSError as erreur:
            alerter(self, "Lecture impossible", str(erreur))
            return

        self.fichier.setText(Path(chemin).name)
        for widget in (self.encodage, self.separateur, self.entete):
            widget.blockSignals(True)
        self.encodage.setCurrentText(self.sondage.encodage)
        index = self.separateur.findData(self.sondage.separateur)
        self.separateur.setCurrentIndex(max(0, index))
        self.entete.setChecked(self.sondage.a_un_entete)
        for widget in (self.encodage, self.separateur, self.entete):
            widget.blockSignals(False)

        self._pre_selectionner_cible(Path(chemin).name)
        self._afficher()

    def _pre_selectionner_cible(self, nom_fichier: str) -> None:
        nom = nom_fichier.lower()
        for cle, mots in (("lignes", ("ligne", "detail", "corps")),
                          ("devis", ("devis", "dev")),
                          ("articles", ("article", "tarif", "prix", "biblio", "ouvrage")),
                          ("chantiers", ("chantier", "affaire")),
                          ("clients", ("client", "tiers"))):
            if any(mot in nom for mot in mots):
                index = self.cible.findData(cle)
                if index >= 0:
                    self.cible.setCurrentIndex(index)
                return

    def _relire(self) -> None:
        if self.sondage is None:
            return
        self.sondage = appliquer_reglages(
            self.sondage, self.encodage.currentText(),
            self.separateur.currentData(), self.entete.isChecked())
        self._afficher()

    def _afficher(self) -> None:
        s = self.sondage
        remarques = ("  " + "  ".join(s.remarques)) if s.remarques else ""
        self.infos.setText(
            f"{s.lignes} enregistrement(s), {s.colonnes} colonne(s), "
            f"{s.taille // 1024 or 1} Ko.{remarques}")

        self.apercu.clear()
        self.apercu.setColumnCount(len(s.entete))
        self.apercu.setHorizontalHeaderLabels(s.entete)
        self.apercu.setRowCount(len(s.apercu))
        for rang, ligne in enumerate(s.apercu):
            for colonne in range(len(s.entete)):
                valeur = ligne[colonne] if colonne < len(ligne) else ""
                self.apercu.setItem(rang, colonne, QTableWidgetItem(valeur))
        self.apercu.resizeColumnsToContents()

        self._construire_champs()
        self.bouton_simuler.setEnabled(True)
        self.bouton_importer.setEnabled(False)

    # --- correspondance --------------------------------------------------

    def _construire_champs(self) -> None:
        while self.disposition_champs.rowCount():
            self.disposition_champs.removeRow(0)
        self.listes_champs.clear()
        if self.sondage is None:
            return

        cible = self.cible.currentData()
        devine = deviner_correspondance(self.sondage.entete, cible)
        for champ in CHAMPS[cible]:
            liste = QComboBox()
            liste.addItem("— ignorer —", -1)
            for index, nom in enumerate(self.sondage.entete):
                liste.addItem(f"{index + 1}. {nom}", index)
            position = liste.findData(devine.get(champ.cle, -1))
            liste.setCurrentIndex(max(0, position))
            self.disposition_champs.addRow(champ.libelle, liste)
            self.listes_champs[champ.cle] = liste
        self.bouton_importer.setEnabled(False)

    def _correspondance(self) -> dict[str, int]:
        return {cle: liste.currentData()
                for cle, liste in self.listes_champs.items()
                if liste.currentData() is not None and liste.currentData() >= 0}

    # --- exécution -------------------------------------------------------

    def simuler(self) -> None:
        if self.sondage is None:
            return
        rapport = Importateur(self.depot).executer(
            self.sondage, self.cible.currentData(), self._correspondance(), simulation=True)
        self.rapport.setPlainText(rapport.resume())
        self.bouton_importer.setEnabled(rapport.crees + rapport.mis_a_jour > 0)

    def importer(self) -> None:
        if self.sondage is None:
            return
        self.depot.creer_sauvegarde()
        rapport = Importateur(self.depot).executer(
            self.sondage, self.cible.currentData(), self._correspondance(), simulation=False)
        self.rapport.setPlainText(rapport.resume())
        self.bouton_importer.setEnabled(False)
        informer(self, "Reprise terminée",
                 f"{rapport.crees} création(s) et {rapport.mis_a_jour} mise(s) à jour.\n\n"
                 "Une sauvegarde de l'état précédent a été déposée dans le "
                 "sous-dossier « sauvegardes ».")
