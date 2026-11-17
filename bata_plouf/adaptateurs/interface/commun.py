"""Briques d'interface réutilisées par tous les écrans."""

import unicodedata

from PySide6.QtCore import (
    QAbstractTableModel, QEvent, QItemSelectionModel, QModelIndex, QObject,
    QSortFilterProxyModel, QTimer, Qt,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QComboBox, QCompleter, QDoubleSpinBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QToolTip, QVBoxLayout, QWidget,
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


# Traits d'union, apostrophes et points valent espace : l'ancien logiciel
# écrivait « SAINT-AMÉ » et « SAINT AME » dans la même base, et personne ne
# devrait avoir à deviner laquelle des deux a été saisie ce jour-là.
_SEPARATEURS = str.maketrans("-–—'’./", " " * 7)


def plier(texte: str) -> tuple[str, list[int]]:
    """Le texte sans casse ni accent, et d'où vient chaque caractère.

    Replier « é » en « e » change la longueur de la chaîne : sans garder la
    position d'origine de chaque caractère, on ne saurait plus dire quelle
    part du texte affiché a répondu à la recherche, ni jusqu'où surligner.
    """
    plie, positions = [], []
    for rang, caractere in enumerate(texte or ""):
        decompose = unicodedata.normalize("NFD", caractere.casefold())
        for lettre in decompose:
            if not unicodedata.combining(lettre):
                plie.append(lettre)
                positions.append(rang)
    return "".join(plie), positions


def amorce(texte: str, cherche: str) -> int:
    """Combien de caractères de « texte » la recherche couvre, depuis le début.

    Zéro si le texte ne commence pas par ce qu'on cherche. La recherche se
    fait depuis le début du nom, pas n'importe où dedans : une liste de
    quatre mille lignes se consulte comme un index, et on doit pouvoir dire
    d'un coup d'œil pourquoi une fiche est restée.
    """
    voulu, _ = plier(cherche)
    if not voulu:
        return 0
    trouve, positions = plier(texte)
    if not trouve.startswith(voulu):
        return 0
    return positions[len(voulu) - 1] + 1


class DelegueAmorce(QStyledItemDelegate):
    """Surligne, dans la cellule, la part qui a répondu à la recherche.

    Sans cela, une liste filtrée ne dit pas pourquoi telle fiche s'y trouve
    et telle autre non.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cherche = ""

    def chercher(self, texte: str) -> None:
        self.cherche = texte or ""

    def paint(self, peintre, option, index) -> None:
        reglage = QStyleOptionViewItem(option)
        self.initStyleOption(reglage, index)
        longueur = amorce(reglage.text, self.cherche)
        if longueur:
            cadre = (reglage.widget.style() if reglage.widget
                     else QApplication.style()).subElementRect(
                QStyle.SubElement.SE_ItemViewItemText, reglage, reglage.widget)
            largeur = QFontMetrics(reglage.font).horizontalAdvance(
                reglage.text[:longueur])
            teinte = QColor(option.palette.highlight().color())
            teinte.setAlpha(80 if reglage.state & QStyle.StateFlag.State_Selected
                            else 110)
            peintre.save()
            peintre.fillRect(cadre.left(), cadre.top(), largeur + 2,
                             cadre.height(), teinte)
            peintre.restore()
        super().paint(peintre, option, index)


class _InfobulleAuSurvol(QObject):
    """Rend au survol le texte entier d'une cellule que sa colonne rogne.

    Une désignation de la bibliothèque fait couramment soixante caractères et
    la colonne n'en montre que la moitié ; l'élargir assez reviendrait à
    chasser les prix de l'écran. On donne donc le texte complet au survol —
    mais seulement s'il est rogné, sinon l'infobulle recopierait ce qui se lit
    déjà, et finirait par gêner partout.
    """

    def __init__(self, tableau):
        super().__init__(tableau)
        self.tableau = tableau

    def eventFilter(self, objet, evenement):
        if evenement.type() != QEvent.Type.ToolTip:
            return False
        index = self.tableau.indexAt(evenement.pos())
        texte, impose = "", None
        if index.isValid():
            # Une cellule qui porte sa propre infobulle garde la main ; sinon
            # on rend son texte, et seulement s'il déborde.
            impose = index.data(Qt.ItemDataRole.ToolTipRole)
            texte = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if impose:
            QToolTip.showText(evenement.globalPos(), str(impose), self.tableau,
                              self.tableau.visualRect(index))
        elif texte and self.rogne(index, texte):
            QToolTip.showText(evenement.globalPos(), texte, self.tableau,
                              self.tableau.visualRect(index))
        else:
            # Sans cela l'infobulle de la cellule voisine resterait affichée.
            QToolTip.hideText()
        return True

    def rogne(self, index, texte: str) -> bool:
        """Le texte déborde-t-il de la place que le style lui laisse ?"""
        reglage = QStyleOptionViewItem()
        reglage.initFrom(self.tableau)
        reglage.rect = self.tableau.visualRect(index)
        police = index.data(Qt.ItemDataRole.FontRole)
        if police is not None:
            reglage.font = police
        cadre = (self.tableau.style() or QApplication.style()).subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, reglage, self.tableau)
        mesure = QFontMetrics(reglage.font)
        # Une ligne de devis écrit son détail sous sa désignation : c'est la
        # plus large de ces lignes qui déborde, pas leur somme.
        return any(mesure.horizontalAdvance(morceau) > cadre.width()
                   for morceau in texte.split("\n"))


def infobulles_si_tronque(tableau):
    """Fait rendre à un tableau le texte entier de ses cellules rognées."""
    tableau._infobulle = _InfobulleAuSurvol(tableau)
    tableau.viewport().installEventFilter(tableau._infobulle)
    return tableau


def cle_recherche(valeur) -> str:
    """Clé de comparaison d'une recherche : sans casse, accent ni ponctuation."""
    return " ".join(cle_texte(valeur).translate(_SEPARATEURS).split())


class _ContientSansAccent(QSortFilterProxyModel):
    """Ne garde que les lignes où le texte cherché apparaît, accents ignorés.

    Qt sait filtrer par début de mot ; ici on cherche n'importe où, et
    « ame » doit trouver « SAINT-AMÉ » comme « SAINT AME » — l'ancien
    logiciel saisissait les villes tantôt avec accent, tantôt sans.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cherche = ""

    def chercher(self, texte: str) -> None:
        self._cherche = cle_recherche(texte)
        self.invalidateFilter()

    def filterAcceptsRow(self, rang: int, parent) -> bool:
        if not self._cherche:
            return True
        source = self.sourceModel()
        if source is None:
            return True
        return self._cherche in cle_recherche(
            source.index(rang, 0, parent).data())


class _SelectionAuFocus(QObject):
    """Entrer dans le champ met de côté ce qui s'y trouve.

    Sans cela, les lettres tapées s'ajouteraient au nom déjà présent et la
    recherche ne trouverait rien. Le choix est différé d'un tour de boucle :
    au moment du clic, Qt n'a pas encore posé le curseur.

    Sur « — aucun — », il n'y a rien à garder : la mention dit seulement
    qu'on n'a rien choisi, et la laisser obligerait à l'effacer à la main
    avant de taper. Le champ se vide alors tout seul, et l'invite prend la
    place. Une liste qui ne propose pas ce choix-là n'est pas concernée :
    c'est le repère vide de l'entrée qui la désigne, pas son libellé.
    """

    def __init__(self, boite):
        super().__init__(boite)
        self.boite = boite

    def eventFilter(self, objet, evenement):
        if evenement.type() == QEvent.Type.FocusIn:
            QTimer.singleShot(0, self.entrer)
        return False

    def entrer(self) -> None:
        ligne = self.boite.lineEdit()
        if ligne is None:
            return
        if self.boite.currentData() == "":
            ligne.clear()
        else:
            ligne.selectAll()
        # Une recherche abandonnée la fois d'avant ne doit pas restreindre
        # encore la liste qu'on vient de rouvrir.
        filtre = getattr(self.boite, "_filtre", None)
        if filtre is not None:
            filtre.chercher("")


def rendre_cherchable(boite: QComboBox, invite: str = "Taper pour filtrer…") -> QComboBox:
    """Rend une liste déroulante filtrable au clavier.

    Huit cents clients ne se parcourent pas à la molette : on tape trois
    lettres et la liste se réduit. Le texte saisi ne crée jamais d'entrée —
    il ne sert qu'à chercher, et ce qu'on retient reste une fiche de la
    liste ; une recherche abandonnée remet le nom de la fiche en place.
    """
    boite.setEditable(True)
    boite.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    boite.lineEdit().setPlaceholderText(invite)
    boite._selection = _SelectionAuFocus(boite)
    boite.lineEdit().installEventFilter(boite._selection)

    filtre = _ContientSansAccent(boite)
    filtre.setSourceModel(boite.model())
    boite._filtre = filtre

    completeur = QCompleter(filtre, boite)
    # C'est notre filtre qui trie les lignes ; celui de Qt ne doit pas
    # repasser derrière avec sa correspondance par le début.
    completeur.setCompletionMode(
        QCompleter.CompletionMode.UnfilteredPopupCompletion)
    completeur.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    boite.setCompleter(completeur)

    def choisir(index) -> None:
        # Deux fiches peuvent porter le même nom : on remonte jusqu'à la
        # ligne d'origine plutôt que de rechercher le texte dans la liste.
        rang = filtre.mapToSource(
            completeur.completionModel().mapToSource(index)).row()
        if rang >= 0:
            boite.setCurrentIndex(rang)

    completeur.activated[QModelIndex].connect(choisir)
    boite.lineEdit().textEdited.connect(filtre.chercher)
    boite.lineEdit().editingFinished.connect(
        lambda: boite.setEditText(boite.itemText(boite.currentIndex())))
    return boite


def etiquette_client(client) -> str:
    """« M. Léo MOUGEL — SAINT-AMÉ ».

    La ville ne tient pas de la décoration : sur huit cents fiches, deux
    homonymes ne se distinguent que par elle, et c'est aussi sur elle qu'on
    retrouve un client dont on a oublié le nom.
    """
    ville = (getattr(client, "ville", "") or "").strip()
    return f"{client.libelle} — {ville}" if ville else client.libelle


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


def adresse_en_ligne(fiche) -> str:
    """L'adresse d'une fiche sur une seule ligne, comme on la dicterait."""
    morceaux = str(getattr(fiche, "adresse_complete", "") or "").split("\n")
    return ", ".join(m.strip() for m in morceaux if m.strip())


def bouton_copier_adresse(champ, fiche_courante, libelle="Celle du client"):
    """Un bouton qui recopie dans « champ » l'adresse de la fiche courante.

    Le chantier est presque toujours chez le client : retaper son adresse est
    une corvée, et une occasion de se tromper sur le code postal. Le champ
    reste modifiable après coup — on travaille aussi chez la fille du client,
    ou sur un terrain qui n'a pas encore de numéro de rue.
    """

    def copier() -> None:
        fiche = fiche_courante()
        adresse = adresse_en_ligne(fiche) if fiche else ""
        if not adresse:
            alerter(champ.window(), "Pas d'adresse à recopier",
                    "Ce client n'a pas d'adresse dans sa fiche."
                    if fiche else "Choisissez d'abord un client.")
            return
        ancienne = champ.text().strip()
        # Ce qui a été tapé à la main ne s'efface pas sur un clic malheureux.
        if ancienne and ancienne != adresse and not confirmer(
                champ.window(), "Remplacer l'adresse",
                f"Remplacer « {ancienne} »\npar « {adresse} » ?"):
            return
        champ.setText(adresse)
        champ.setFocus()

    copieur = bouton(libelle, copier)
    copieur.setToolTip("Recopie l'adresse de la fiche client ; elle reste "
                       "modifiable")
    return copieur


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
