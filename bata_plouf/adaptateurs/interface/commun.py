"""Briques d'interface réutilisées par tous les écrans."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ...domaine import euros

GAUCHE = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
DROITE = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
CENTRE = int(Qt.AlignmentFlag.AlignCenter)


class Colonne:
    """Description d'une colonne de tableau en lecture seule."""

    def __init__(self, titre, extracteur, largeur=None, alignement=GAUCHE, gras=False):
        self.titre = titre
        self.extracteur = extracteur
        self.largeur = largeur
        self.alignement = alignement
        self.gras = gras


class ModeleListe(QAbstractTableModel):
    """Affiche une liste d'entités d'après une description de colonnes."""

    def __init__(self, colonnes: list[Colonne], elements=None):
        super().__init__()
        self.colonnes = colonnes
        self.elements: list = list(elements or [])

    def definir(self, elements) -> None:
        self.beginResetModel()
        self.elements = list(elements)
        self.endResetModel()

    def element(self, ligne: int):
        if 0 <= ligne < len(self.elements):
            return self.elements[ligne]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.elements)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.colonnes)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        colonne = self.colonnes[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return colonne.extracteur(self.elements[index.row()])
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return colonne.alignement
        if role == Qt.ItemDataRole.FontRole and colonne.gras:
            police = QFont()
            police.setBold(True)
            return police
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.colonnes[section].titre
        return None


def champ_texte(valeur: str = "", indication: str = "") -> QLineEdit:
    ligne = QLineEdit(valeur or "")
    if indication:
        ligne.setPlaceholderText(indication)
    return ligne


def champ_euros(valeur: float = 0.0, maximum: float = 9_999_999.0) -> QDoubleSpinBox:
    boite = QDoubleSpinBox()
    boite.setDecimals(2)
    boite.setRange(-maximum, maximum)
    boite.setSuffix(" €")
    boite.setGroupSeparatorShown(True)
    boite.setValue(float(valeur or 0))
    return boite


def champ_pourcent(valeur: float = 0.0) -> QDoubleSpinBox:
    boite = QDoubleSpinBox()
    boite.setDecimals(2)
    boite.setRange(0, 100)
    boite.setSuffix(" %")
    boite.setValue(float(valeur or 0))
    return boite


def champ_quantite(valeur: float = 1.0) -> QDoubleSpinBox:
    boite = QDoubleSpinBox()
    boite.setDecimals(3)
    boite.setRange(-999999, 999999)
    boite.setValue(float(valeur or 0))
    return boite


def champ_entier(valeur: int = 0, maximum: int = 9999) -> QSpinBox:
    boite = QSpinBox()
    boite.setRange(0, maximum)
    boite.setValue(int(valeur or 0))
    return boite


def liste_deroulante(valeurs, selection="") -> QComboBox:
    boite = QComboBox()
    for valeur in valeurs:
        boite.addItem(str(valeur), valeur)
    if selection is not None:
        index = boite.findData(selection)
        if index < 0:
            index = boite.findText(str(selection))
        if index >= 0:
            boite.setCurrentIndex(index)
    return boite


def titre(texte: str, taille: int = 16) -> QLabel:
    etiquette = QLabel(texte)
    police = etiquette.font()
    police.setPointSize(taille)
    police.setBold(True)
    etiquette.setFont(police)
    return etiquette


def discret(texte: str) -> QLabel:
    etiquette = QLabel(texte)
    etiquette.setStyleSheet("color: palette(mid);")
    return etiquette


def barre(*widgets) -> QWidget:
    """Range des widgets sur une ligne ; la chaîne '-' insère un ressort."""
    boite = QWidget()
    disposition = QHBoxLayout(boite)
    disposition.setContentsMargins(0, 0, 0, 0)
    disposition.setSpacing(8)
    for widget in widgets:
        if widget == "-":
            disposition.addStretch(1)
        elif isinstance(widget, str):
            disposition.addWidget(QLabel(widget))
        else:
            disposition.addWidget(widget)
    return boite


def colonne(*widgets, marges=(0, 0, 0, 0), espacement=8) -> QWidget:
    boite = QWidget()
    disposition = QVBoxLayout(boite)
    disposition.setContentsMargins(*marges)
    disposition.setSpacing(espacement)
    for widget in widgets:
        if widget == "-":
            disposition.addStretch(1)
        else:
            disposition.addWidget(widget)
    return boite


def bouton(texte: str, action=None, principal: bool = False) -> QPushButton:
    b = QPushButton(texte)
    if action:
        b.clicked.connect(action)
    if principal:
        b.setDefault(True)
    return b


def confirmer(parent, titre_: str, question: str) -> bool:
    reponse = QMessageBox.question(
        parent, titre_, question,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reponse == QMessageBox.StandardButton.Yes


def alerter(parent, titre_: str, message: str) -> None:
    QMessageBox.warning(parent, titre_, message)


def informer(parent, titre_: str, message: str) -> None:
    QMessageBox.information(parent, titre_, message)


def champ_date(valeur_iso: str = "", optionnel: bool = False):
    """Champ date au format français, avec calendrier.

    Pour une date facultative, la valeur minimale sert de « case vide » : c'est
    la façon propre de représenter une absence de date avec un QDateEdit.
    """
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QDateEdit

    boite = QDateEdit()
    boite.setCalendarPopup(True)
    boite.setDisplayFormat("dd/MM/yyyy")
    vide = QDate(1900, 1, 1)
    boite.setMinimumDate(vide)
    if optionnel:
        boite.setSpecialValueText("—")
    if valeur_iso:
        boite.setDate(QDate.fromString(valeur_iso[:10], "yyyy-MM-dd"))
    elif optionnel:
        boite.setDate(vide)
    else:
        boite.setDate(QDate.currentDate())
    return boite


def valeur_date(boite) -> str:
    from PySide6.QtCore import QDate

    if boite.date() == QDate(1900, 1, 1):
        return ""
    return boite.date().toString("yyyy-MM-dd")
