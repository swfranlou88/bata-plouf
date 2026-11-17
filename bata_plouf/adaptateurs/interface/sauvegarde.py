"""La fenêtre qui demande de quoi sauvegarder en ligne, et celle qui le fait.

Trois choses à réunir une fois pour toutes : le dépôt où déposer, un jeton
qui donne le droit d'y écrire, et la phrase de passe qui chiffre. Ensuite
plus rien n'est demandé — la sauvegarde part toute seule, une fois par mois.

La phrase de passe est la seule qu'on ne peut pas récupérer : ni GitHub, ni
le logiciel, ni personne ne la connaît. La fenêtre le dit, et la demande deux
fois, comme on fait pour un mot de passe qu'on ne reverra jamais.
"""

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QVBoxLayout,
)

from .. import environnement, sauvegarde_en_ligne, sauvegarde_mensuelle
from ..coffre import ErreurCoffre, dechiffrer_fichier, reproche
from ..sauvegarde_en_ligne import ErreurSauvegarde
from .commun import alerter, champ_texte, discret, informer


class DialogueSecrets(QDialog):
    """Dépôt, jeton et phrase de passe — demandés une fois."""

    def __init__(self, parent, depot):
        super().__init__(parent)
        self.depot = depot
        self.setWindowTitle("Sauvegarde mensuelle en ligne")
        self.setMinimumWidth(560)

        secrets = environnement.lire(depot.racine)
        self.depot_cible = champ_texte(
            sauvegarde_mensuelle.depot_vise(depot) or "",
            "compte/bata-plouf-sauvegardes")
        self.jeton = champ_texte(secrets[environnement.JETON], "github_pat_…")
        self.jeton.setEchoMode(QLineEdit.EchoMode.Password)
        self.phrase = champ_texte(secrets[environnement.PHRASE],
                                  "quatre mots qui tiennent debout")
        self.phrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmation = champ_texte("", "la même, pour être sûr")
        self.confirmation.setEchoMode(QLineEdit.EchoMode.Password)
        if secrets[environnement.PHRASE]:
            # Déjà réglée : on ne force pas à la retaper deux fois pour
            # changer le seul jeton.
            self.confirmation.setText(secrets[environnement.PHRASE])

        explication = QLabel(
            "Une fois par mois, au lancement, le logiciel dépose une copie "
            "chiffrée de vos données sur GitHub. Le fichier y est public : "
            "c'est la phrase de passe, et elle seule, qui le rend illisible.\n\n"
            "<b>Notez cette phrase ailleurs qu'ici.</b> Personne ne peut la "
            "retrouver — ni GitHub, ni le logiciel, ni la personne qui l'a "
            "écrit. Sans elle, les sauvegardes ne se rouvrent pas.")
        explication.setWordWrap(True)
        explication.setTextFormat(Qt.TextFormat.RichText)

        formulaire = QFormLayout()
        formulaire.addRow("Dépôt GitHub", self.depot_cible)
        formulaire.addRow("Jeton d'écriture", self.jeton)
        formulaire.addRow("Phrase de passe", self.phrase)
        formulaire.addRow("Confirmation", self.confirmation)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Enregistrer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Plus tard")
        boutons.accepted.connect(self._valider)
        boutons.rejected.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.setSpacing(10)
        disposition.addWidget(explication)
        disposition.addLayout(formulaire)
        disposition.addWidget(discret(
            "Le jeton se crée sur github.com → Settings → Developer settings "
            "→ Fine-grained tokens, limité à ce seul dépôt, avec "
            "« Contents : Read and write »."))
        disposition.addWidget(boutons)

    def _valider(self) -> None:
        cible = self.depot_cible.text().strip().strip("/")
        if "/" not in cible:
            alerter(self, "Dépôt incomplet",
                    "Le dépôt s'écrit « compte/nom », par exemple "
                    "« dupont/bata-plouf-sauvegardes ».")
            return
        if not self.jeton.text().strip():
            alerter(self, "Jeton manquant",
                    "Sans jeton, le logiciel ne peut rien déposer sur GitHub.")
            return
        faute = reproche(self.phrase.text())
        if faute:
            alerter(self, "Phrase de passe", faute)
            return
        if self.phrase.text() != self.confirmation.text():
            alerter(self, "Phrase de passe",
                    "Les deux saisies diffèrent. Retapez-les.")
            return

        environnement.ecrire(self.depot.racine, {
            environnement.DEPOT: cible,
            environnement.JETON: self.jeton.text().strip(),
            environnement.PHRASE: self.phrase.text(),
        })
        societe = self.depot.societe
        societe.depot_sauvegardes = cible
        self.depot.enregistrer_societe(societe)
        self.accept()


class Sauvegardeur(QThread):
    """La sauvegarde dans un fil à part : elle dure quelques secondes."""

    fini = Signal(str)
    echoue = Signal(str)

    def __init__(self, depot, parent=None):
        super().__init__(parent)
        self.depot = depot

    def run(self) -> None:
        try:
            self.fini.emit(sauvegarde_mensuelle.sauvegarder(self.depot))
        except ErreurSauvegarde as erreur:
            self.echoue.emit(str(erreur))
        except Exception as erreur:  # noqa: BLE001 — un fil ne doit rien laisser filer
            self.echoue.emit(f"{type(erreur).__name__} : {erreur}")


class DialogueRestaurer(QDialog):
    """Choisir une sauvegarde en ligne, la rapatrier et la déchiffrer.

    Restaurer depuis un terminal suppose Python, uv et le dossier du code
    source — trois choses qu'un Mac neuf n'a pas. Le logiciel, lui, est le
    premier à être réinstallé : c'est donc à lui de savoir rouvrir une
    sauvegarde.
    """

    def __init__(self, parent, depot):
        super().__init__(parent)
        self.depot = depot
        self.choix = None
        self.setWindowTitle("Restaurer une sauvegarde en ligne")
        self.setMinimumWidth(520)

        self.liste = QListWidget()
        self.message = discret("")
        self.message.setWordWrap(True)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Restaurer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self._choisir)
        boutons.rejected.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.setSpacing(10)
        disposition.addWidget(QLabel(
            "Ces sauvegardes remplaceront la totalité des données. "
            "L'état actuel est mis de côté avant, et reste récupérable."))
        disposition.addWidget(self.liste, 1)
        disposition.addWidget(self.message)
        disposition.addWidget(boutons)
        self._remplir()

    def _remplir(self) -> None:
        secrets = environnement.lire(self.depot.racine)
        cible = sauvegarde_mensuelle.depot_vise(self.depot)
        try:
            pieces = sauvegarde_en_ligne.liste(cible, secrets[environnement.JETON])
        except ErreurSauvegarde as erreur:
            self.message.setText(str(erreur))
            return
        for nom, taille, date in pieces:
            self.liste.addItem(f"{nom}  ·  {taille // 1024} Ko  ·  déposée le {date}")
        if not pieces:
            self.message.setText(f"Aucune sauvegarde en ligne sur {cible}.")
        else:
            self.liste.setCurrentRow(0)

    def _choisir(self) -> None:
        element = self.liste.currentItem()
        if element is None:
            return
        self.choix = element.text().split("  ·  ")[0]
        self.accept()


def rapatrier(parent, depot, nom: str) -> Path | None:
    """Télécharge et déchiffre une sauvegarde ; rend le zip en clair."""
    secrets = environnement.lire(depot.racine)
    phrase = secrets[environnement.PHRASE]
    if not phrase:
        phrase, accepte = QInputDialog.getText(
            parent, "Phrase de passe",
            "Phrase de passe de la sauvegarde :", QLineEdit.EchoMode.Password)
        if not accepte or not phrase:
            return None

    abri = Path(tempfile.mkdtemp(prefix="bata-plouf-restauration-"))
    try:
        chiffre = sauvegarde_en_ligne.telecharger(
            sauvegarde_mensuelle.depot_vise(depot),
            secrets[environnement.JETON], nom, abri / nom)
        return dechiffrer_fichier(chiffre, abri / "sauvegarde.zip", phrase)
    except (ErreurSauvegarde, ErreurCoffre) as erreur:
        shutil.rmtree(abri, ignore_errors=True)
        alerter(parent, "Restauration impossible", str(erreur))
        return None


def regler(parent, depot) -> bool:
    """Ouvre la fenêtre des secrets. Rend vrai si tout est réuni après coup."""
    DialogueSecrets(parent, depot).exec()
    return sauvegarde_mensuelle.prete(depot)


def sauvegarder_maintenant(parent, depot) -> None:
    """Sauvegarde à la demande, avec un mot à la fin — succès comme échec."""
    if not sauvegarde_mensuelle.prete(depot) and not regler(parent, depot):
        return
    parent.setEnabled(False)
    fil = Sauvegardeur(depot, parent)

    def termine(adresse: str) -> None:
        parent.setEnabled(True)
        informer(parent, "Sauvegarde déposée",
                 "La sauvegarde chiffrée de ce mois est en ligne.\n\n" + adresse)

    def rate(message: str) -> None:
        parent.setEnabled(True)
        alerter(parent, "Sauvegarde impossible", message)

    fil.fini.connect(termine)
    fil.echoue.connect(rate)
    parent._sauvegardeur = fil  # sans référence, le fil est ramassé en route
    fil.start()
