"""Briques d'interface réutilisées par tous les écrans."""

import unicodedata

from PySide6.QtCore import (
    QAbstractTableModel, QItemSelectionModel, QModelIndex, Qt,
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ...domaine import euros

GAUCHE = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
DROITE = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
CENTRE = int(Qt.AlignmentFlag.AlignCenter)


def cle_texte(valeur) -> str:
    """Clé de tri d'un texte : sans casse ni accent.

    Sans cela « Évier » se rangerait après « Zinc », et « ABEL » loin de
    « Abel ». On décompose les caractères accentués puis on retire les
    signes, ce qui met « Émile » à sa place, entre « Eloi » et « Fabre ».
    """
    decompose = unicodedata.normalize("NFD", str(valeur or "").casefold())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def cle_numero(valeur) -> tuple:
    """Clé de tri d'un numéro écrit en texte.

    Les numéros de client et de facture repris de l'ancien logiciel sont des
    entiers écrits en texte : triés comme du texte, « 9 » tomberait après
    « 1450 ». Ceux qui ne sont pas des chiffres se rangent à la fin.
    """
    texte = str(valeur or "").strip()
    if texte.isdigit():
        return (0, int(texte), "")
    return (1, 0, cle_texte(texte))


class Colonne:
    """Description d'une colonne de tableau en lecture seule."""

    def __init__(self, titre, extracteur, largeur=None, alignement=GAUCHE,
                 gras=False, cle=None):
        self.titre = titre
        self.extracteur = extracteur
        self.largeur = largeur
        self.alignement = alignement
        self.gras = gras
        # Sur quoi trier quand on clique sur l'en-tête. Le texte affiché ne
        # peut pas servir dès qu'il est mis en forme : « 1 234,56 € » se
        # rangerait avant « 9,00 € », et « 02/01/2019 » avant « 15/11/2018 ».
        # Les colonnes chiffrées et les dates donnent donc leur clé ; les
        # autres se trient sur leur texte, sans casse ni accent.
        self.cle = cle


class ModeleListe(QAbstractTableModel):
    """Affiche une liste d'entités d'après une description de colonnes."""

    def __init__(self, colonnes: list[Colonne], elements=None):
        super().__init__()
        self.colonnes = colonnes
        self.elements: list = list(elements or [])
        # L'ordre dans lequel le dépôt a fourni les éléments. Il n'est pas
        # arbitraire — devis du plus récent, matériaux par famille — donc on
        # le garde pour pouvoir y revenir, et pour que le tri s'applique
        # toujours dessus : à valeurs égales, cet ordre-là tranche.
        self._naturel: list = list(self.elements)
        # (colonne, sens) du tri demandé, ou None si aucun.
        self.tri: tuple | None = None

    def definir(self, elements) -> None:
        self.beginResetModel()
        self._naturel = list(elements)
        self.elements = list(elements)
        self.endResetModel()
        if self.tri is not None:
            # Un rafraîchissement ne doit pas défaire le tri choisi.
            self.sort(*self.tri)

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

    # --- tri -------------------------------------------------------------

    def sort(self, colonne: int, ordre=Qt.SortOrder.AscendingOrder) -> None:
        if not 0 <= colonne < len(self.colonnes):
            return
        description = self.colonnes[colonne]
        cle = description.cle or (lambda e: cle_texte(description.extracteur(e)))
        descendant = ordre == Qt.SortOrder.DescendingOrder
        self.beginResetModel()
        try:
            self.elements = sorted(self._naturel, key=cle, reverse=descendant)
        except TypeError:
            # Une colonne qui mêle des valeurs non comparables entre elles
            # (un montant et un tiret, par exemple) : on se rabat sur leur
            # écriture, pour trier quand même au lieu de planter.
            self.elements = sorted(self._naturel, key=lambda e: str(cle(e)),
                                   reverse=descendant)
        self.endResetModel()
        self.tri = (colonne, ordre)

    def annuler_le_tri(self) -> None:
        """Revient à l'ordre dans lequel le dépôt a fourni les éléments."""
        self.beginResetModel()
        self.elements = list(self._naturel)
        self.endResetModel()
        self.tri = None


def activer_le_tri(tableau, modele):
    """Branche le tri au clic sur les en-têtes d'un tableau.

    Trois états se succèdent sur une même colonne : croissant, décroissant,
    puis l'ordre d'origine. Le troisième compte, car cet ordre n'est pas
    quelconque — les devis arrivent du plus récent, les matériaux par
    famille — et sans lui on ne pourrait plus y revenir sans changer d'écran.

    On ne passe pas par setSortingEnabled de Qt, qui trierait d'office sur la
    première colonne dès l'ouverture et effacerait justement cet ordre.

    Rend la fonction de tri, pour pouvoir la déclencher sans la souris.
    """
    entetes = tableau.horizontalHeader()
    entetes.setSectionsClickable(True)
    entetes.setSortIndicatorShown(True)
    entetes.setToolTip("Cliquez sur un en-tête pour trier ; au troisième "
                       "clic, la liste revient à son ordre d'origine")

    def trier(colonne: int) -> None:
        etat = modele.tri
        if etat is None or etat[0] != colonne:
            suivant = (colonne, Qt.SortOrder.AscendingOrder)
        elif etat[1] == Qt.SortOrder.AscendingOrder:
            suivant = (colonne, Qt.SortOrder.DescendingOrder)
        else:
            suivant = None

        # Ce sont les fiches sélectionnées qui doivent le rester, pas les
        # lignes : on les repère avant de réordonner, puisque réinitialiser
        # le modèle vide la sélection.
        choisies = {id(modele.element(index.row()))
                    for index in tableau.selectionModel().selectedRows()}

        if suivant is None:
            modele.annuler_le_tri()
            entetes.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        else:
            modele.sort(*suivant)
            entetes.setSortIndicator(*suivant)

        if not choisies:
            return
        selection = tableau.selectionModel()
        selection.clearSelection()
        drapeau = (QItemSelectionModel.SelectionFlag.Select
                   | QItemSelectionModel.SelectionFlag.Rows)
        premiere = None
        for ligne, element in enumerate(modele.elements):
            if id(element) in choisies:
                selection.select(modele.index(ligne, 0), drapeau)
                premiere = ligne if premiere is None else premiere
        if premiere is not None:
            tableau.scrollTo(modele.index(premiere, 0))

    entetes.sectionClicked.connect(trier)
    return trier


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
