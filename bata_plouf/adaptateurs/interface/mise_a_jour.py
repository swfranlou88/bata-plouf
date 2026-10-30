"""Écran de mise à jour : chercher, télécharger, installer."""

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout,
)

from ... import __version__
from ..mise_a_jour import (
    ErreurMiseAJour, VersionDistante, application_installee, chercher, extraire,
    installer, telecharger,
)
from .commun import barre, bouton, discret, informer, titre


class Chercheur(QThread):
    """Interroge GitHub sans figer la fenêtre."""

    trouve = Signal(object)   # VersionDistante, ou None si déjà à jour
    echoue = Signal(str)

    def __init__(self, depot: str, parent=None):
        super().__init__(parent)
        self.depot = depot

    def run(self) -> None:
        try:
            self.trouve.emit(chercher(self.depot))
        except ErreurMiseAJour as erreur:
            self.echoue.emit(str(erreur))
        except Exception as erreur:  # noqa: BLE001 — sans cela, aucun signal
            self.echoue.emit(f"Recherche impossible : {erreur}")


class Telechargeur(QThread):
    avance = Signal(int)
    prete = Signal(object)    # Path du bundle extrait
    echoue = Signal(str)

    def __init__(self, version: VersionDistante, parent=None):
        super().__init__(parent)
        self.version = version

    def run(self) -> None:
        try:
            archive = telecharger(self.version, self.avance.emit)
            self.prete.emit(extraire(archive))
        except ErreurMiseAJour as erreur:
            self.echoue.emit(str(erreur))
        except Exception as erreur:  # noqa: BLE001 — sans cela, aucun signal
            self.echoue.emit(f"Téléchargement impossible : {erreur}")


class DialogueMiseAJour(QDialog):
    """Quatre états : recherche, verdict, téléchargement, installation."""

    def __init__(self, parent, depot: str, version: VersionDistante | None = None,
                 automatique: bool = False):
        super().__init__(parent)
        self.depot = depot
        self._deja_trouvee = version
        # En mode automatique, rien n'est demandé : on télécharge et on
        # installe dès l'ouverture. Le bouton « Plus tard » reste là pour que
        # l'utilisateur ne soit jamais prisonnier de la fenêtre.
        self.automatique = automatique
        self.version: VersionDistante | None = None
        self.nouvelle: Path | None = None
        self.chercheur: Chercheur | None = None
        self.telechargeur: Telechargeur | None = None

        self.setWindowTitle("Mise à jour automatique" if automatique
                            else "Mise à jour")
        self.setMinimumWidth(520)

        self.etat = QLabel("Recherche d'une nouvelle version…")
        self.etat.setWordWrap(True)
        self.detail = discret(f"Version installée : {__version__}")
        self.detail.setWordWrap(True)

        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMaximumHeight(140)
        self.notes.setVisible(False)

        self.jauge = QProgressBar()
        self.jauge.setVisible(False)

        self.bouton_action = bouton("Installer et redémarrer", self.installer,
                                    principal=True)
        self.bouton_action.setEnabled(False)
        boutons = QDialogButtonBox()
        boutons.addButton(self.bouton_action, QDialogButtonBox.ButtonRole.AcceptRole)
        fermer = boutons.addButton("Plus tard" if automatique else "Fermer",
                                   QDialogButtonBox.ButtonRole.RejectRole)
        fermer.clicked.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.setSpacing(10)
        disposition.addWidget(titre("Mise à jour", 15))
        disposition.addWidget(self.etat)
        disposition.addWidget(self.detail)
        disposition.addWidget(self.notes)
        disposition.addWidget(self.jauge)
        disposition.addWidget(boutons)

        # Au lancement, la version est déjà connue : inutile de redemander
        # à GitHub, on passe directement au verdict.
        if self._deja_trouvee is not None:
            self._verdict(self._deja_trouvee)
        else:
            self._chercher()

    # --- fin de vie ------------------------------------------------------

    def _attendre_les_fils(self) -> None:
        """Laisse les fils d'exécution se terminer avant de disparaître.

        Détruire un QThread encore en cours fait avorter le processus. La
        requête réseau ayant son propre délai d'expiration, l'attente est
        toujours brève.
        """
        for fil in (self.chercheur, self.telechargeur):
            if fil is not None and fil.isRunning():
                fil.requestInterruption()
                fil.wait(12000)

    def done(self, resultat: int) -> None:
        # done() couvre accept(), reject() et la croix de fermeture
        self._attendre_les_fils()
        super().done(resultat)

    # --- recherche -------------------------------------------------------

    def _chercher(self) -> None:
        if not self.depot:
            self.etat.setText(
                "Aucun dépôt renseigné. Indiquez-le dans les Paramètres, à la "
                "rubrique Mises à jour, sous la forme « compte/nom ».")
            return
        self.chercheur = Chercheur(self.depot, self)
        self.chercheur.trouve.connect(self._verdict)
        self.chercheur.echoue.connect(self._probleme)
        self.chercheur.start()

    def _verdict(self, version) -> None:
        if version is None:
            self.etat.setText("Le logiciel est à jour.")
            return
        self.version = version
        self.etat.setText(
            f"<b>Version {version.etiquette} disponible</b> "
            f"({version.taille_lisible})")
        publiee = f", publiée le {version.publiee_le}" if version.publiee_le else ""
        self.detail.setText(f"Vous utilisez la version {__version__}{publiee}.")
        if version.notes:
            self.notes.setPlainText(version.notes)
            self.notes.setVisible(True)

        if application_installee() is None:
            if self.automatique:
                self.reject()
                return
            self.etat.setText(
                f"Version {version.etiquette} disponible, mais le logiciel tourne "
                "depuis le code source : mettez-le à jour avec git, puis "
                "reconstruisez-le.")
            return
        self.bouton_action.setEnabled(True)
        if self.automatique:
            # Le temps que la fenêtre s'affiche, puis on enchaîne tout seul
            QTimer.singleShot(0, self.installer)

    def _probleme(self, message: str) -> None:
        if self.automatique:
            # Une mise à jour qui échoue ne doit pas barrer la route : on
            # referme sans rien dire, le bandeau de l'accueil reste là pour
            # réessayer plus tard.
            self.reject()
            return
        self.etat.setText(message)
        self.jauge.setVisible(False)
        self.bouton_action.setEnabled(True)

    # --- téléchargement et installation ----------------------------------

    def installer(self) -> None:
        if self.version is None:
            return
        if self.nouvelle is not None:
            self._remplacer()
            return

        self.bouton_action.setEnabled(False)
        self.etat.setText("Téléchargement en cours…")
        self.jauge.setValue(0)
        self.jauge.setVisible(True)
        self.telechargeur = Telechargeur(self.version, self)
        self.telechargeur.avance.connect(self.jauge.setValue)
        self.telechargeur.prete.connect(self._telechargee)
        self.telechargeur.echoue.connect(self._probleme)
        self.telechargeur.start()

    def _telechargee(self, bundle) -> None:
        self.nouvelle = Path(bundle)
        self.jauge.setVisible(False)
        self.etat.setText(
            f"Version {self.version.etiquette} prête à être installée.")
        self.detail.setText(
            "Le logiciel va se fermer, se remplacer, puis se rouvrir tout seul. "
            "Vos données ne sont pas touchées : elles vivent en dehors de "
            "l'application.")
        self.bouton_action.setEnabled(True)
        self._remplacer()

    def _remplacer(self) -> None:
        ancienne = application_installee()
        if ancienne is None or self.nouvelle is None:
            return
        try:
            installer(self.nouvelle, ancienne)
        except Exception as erreur:  # noqa: BLE001 — y compris les erreurs disque
            self._probleme(str(erreur))
            return
        # Le script détaché attend que ce processus se termine pour échanger
        # les deux applications : il faut donc quitter maintenant.
        from PySide6.QtWidgets import QApplication
        self.accept()
        QApplication.quit()
