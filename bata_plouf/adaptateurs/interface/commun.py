"""Briques d'interface réutilisées par tous les écrans."""

import unicodedata

from PySide6.QtCore import (
    QAbstractTableModel, QDate, QEasingCurve, QEvent, QItemSelectionModel,
    QModelIndex, QObject, QPropertyAnimation, QSortFilterProxyModel, QTimer,
    Qt,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPalette, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication, QCalendarWidget, QComboBox, QCompleter, QDateEdit,
    QDoubleSpinBox, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QStyle, QStyledItemDelegate,
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
        # arbitraire — devis du plus récent, articles par famille — donc on
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
    quelconque — les devis arrivent du plus récent, les articles par
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


def morceau(texte: str, cherche: str) -> tuple[int, int]:
    """Où la recherche tombe dans le texte : position et longueur.

    (0, 0) si elle n'y est pas. À la différence d'amorce, elle est cherchée
    n'importe où : les listes de clients, de devis et de factures cherchent
    ainsi — on tape « ame » pour trouver SAINT-AMÉ.
    """
    voulu, _ = plier(cherche)
    if not voulu:
        return (0, 0)
    trouve, positions = plier(texte)
    ou = trouve.find(voulu)
    if ou < 0:
        return (0, 0)
    debut = positions[ou]
    fin = positions[ou + len(voulu) - 1] + 1
    return (debut, fin - debut)


class DelegueAmorce(QStyledItemDelegate):
    """Surligne, dans la cellule, la part qui a répondu à la recherche.

    Sans cela, une liste filtrée ne dit pas pourquoi telle fiche s'y trouve
    et telle autre non.

    Deux façons de mordre, selon la liste : la bibliothèque cherche par le
    début d'un nom — quatre mille fiches se consultent comme un index —, les
    autres listes n'importe où dans le texte. Le surlignage suit la règle de
    sa liste, sinon il montrerait autre chose que ce qui a filtré.
    """

    def __init__(self, parent=None, depuis_le_debut: bool = True):
        super().__init__(parent)
        self.cherche = ""
        self.depuis_le_debut = depuis_le_debut

    def chercher(self, texte: str) -> None:
        self.cherche = texte or ""

    def _part(self, texte: str) -> tuple[int, int]:
        if self.depuis_le_debut:
            return (0, amorce(texte, self.cherche))
        return morceau(texte, self.cherche)

    def paint(self, peintre, option, index) -> None:
        reglage = QStyleOptionViewItem(option)
        self.initStyleOption(reglage, index)
        debut, longueur = self._part(reglage.text)
        if longueur:
            cadre = (reglage.widget.style() if reglage.widget
                     else QApplication.style()).subElementRect(
                QStyle.SubElement.SE_ItemViewItemText, reglage, reglage.widget)
            mesure = QFontMetrics(reglage.font)
            avant = mesure.horizontalAdvance(reglage.text[:debut])
            largeur = mesure.horizontalAdvance(
                reglage.text[debut:debut + longueur])
            teinte = QColor(option.palette.highlight().color())
            teinte.setAlpha(80 if reglage.state & QStyle.StateFlag.State_Selected
                            else 110)
            peintre.save()
            peintre.fillRect(cadre.left() + avant, cadre.top(), largeur + 2,
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
        # D'abord la liste : une recherche abandonnée la fois d'avant ne doit
        # pas restreindre encore celle qu'on vient de rouvrir. Et rétablir le
        # filtre après coup déferait la sélection qui suit.
        filtre = getattr(self.boite, "_filtre", None)
        if filtre is not None:
            filtre.chercher("")
        if self.boite.currentData() == "":
            ligne.clear()
        else:
            ligne.selectAll()


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
    # Sur les deux : au clic, c'est la liste déroulante qui reçoit l'entrée
    # dans le champ, et au clavier c'est la ligne de saisie.
    boite.installEventFilter(boite._selection)
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


def liste_deroulante(valeurs, selection="", formateur=str) -> QComboBox:
    """Les valeurs restent en donnée, « formateur » décide de l'affichage.

    Un taux de TVA se lit « 20 % » et se calcule en 20.0 : séparer les deux
    évite de reconvertir du texte au moment de s'en servir.
    """
    boite = QComboBox()
    for valeur in valeurs:
        boite.addItem(formateur(valeur), valeur)
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


# Le gris de « palette(mid) » est fait pour les bordures, pas pour du texte :
# sur fond sombre il se noie, et les notes deviennent illisibles. On prend un
# bleu-vert sourd — assez clair sur fond sombre, assez foncé sur fond clair —
# qui se distingue du texte courant sans crier comme une couleur d'accent.
TEINTE_DISCRETE_SOMBRE = "#79c6d8"
TEINTE_DISCRETE_CLAIRE = "#4d6f79"


def teinte_discrete(palette=None) -> str:
    """La couleur des textes de second plan, selon le thème en cours."""
    if palette is None:
        palette = QApplication.palette()
    fond = palette.color(QPalette.ColorRole.Window)
    return (TEINTE_DISCRETE_SOMBRE if fond.lightness() < 128
            else TEINTE_DISCRETE_CLAIRE)


# L'orange des champs qu'on vient de modifier : assez chaud pour sauter aux
# yeux parmi des intitulés gris, assez sourd pour ne pas crier comme une
# erreur. Deux valeurs, comme pour les textes discrets : sur fond sombre il
# faut l'éclaircir, sinon il se confond avec le brun du décor.
TEINTE_MODIFIEE_SOMBRE = "#f0a44f"
TEINTE_MODIFIEE_CLAIRE = "#b35f10"


def teinte_modifiee(palette=None) -> str:
    """La couleur qui marque un champ modifié, selon le thème en cours."""
    if palette is None:
        palette = QApplication.palette()
    fond = palette.color(QPalette.ColorRole.Window)
    return (TEINTE_MODIFIEE_SOMBRE if fond.lightness() < 128
            else TEINTE_MODIFIEE_CLAIRE)


# Le vert d'un champ qui attend d'être rempli, et le rouge d'un geste qui
# défait. Deux nuances chacun : sur fond sombre il faut les éclaircir.
TEINTE_ATTENTE_SOMBRE, TEINTE_ATTENTE_CLAIRE = "#4caf7d", "#1e7a4c"
TEINTE_DEFAIRE_SOMBRE, TEINTE_DEFAIRE_CLAIRE = "#e8705f", "#b3382a"


def _sombre(palette=None) -> bool:
    """Le thème en cours est-il sombre ?

    Sans palette donnée, c'est celle de l'application qui tranche, et c'est
    presque toujours ce qu'on veut : poser une feuille de style sur un
    widget y fige une palette, qui ne suit plus le thème ensuite. Demander
    la sienne à un widget déjà teinté, c'est relire la couleur d'hier.
    """
    if palette is None:
        palette = QApplication.palette()
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def teinte_attente(palette=None) -> str:
    """Le vert d'un champ qu'il reste à remplir pour aboutir."""
    return (TEINTE_ATTENTE_SOMBRE if _sombre(palette)
            else TEINTE_ATTENTE_CLAIRE)


def teinte_defaire(palette=None) -> str:
    """Le rouge d'un bouton qui annule plutôt qu'il n'avance."""
    return (TEINTE_DEFAIRE_SOMBRE if _sombre(palette)
            else TEINTE_DEFAIRE_CLAIRE)


def suivre_le_theme(widget, methode) -> None:
    """Rappelle « methode » quand le système passe du clair au sombre.

    Un widget qui porte une feuille de style ne reçoit plus les changements
    de palette : Qt tient sa couleur pour fixée à la main et cesse de le
    prévenir. On écoute donc le système lui-même. La méthode doit être celle
    d'un QObject : Qt la débranche alors toute seule quand le widget meurt.
    """
    application = QApplication.instance()
    if application is None:
        return
    application.styleHints().colorSchemeChanged.connect(methode)


class Discret(QLabel):
    """Un texte de second plan, lisible en thème clair comme en sombre.

    La couleur se recalcule quand le système bascule : sur un Mac réglé sur
    « automatique », le thème change au coucher du soleil, et le logiciel
    reste ouvert plus longtemps que cela.
    """

    def __init__(self, texte: str = "", parent=None):
        super().__init__(texte, parent)
        self._teinte = ""
        self._teinter()
        suivre_le_theme(self, self._au_theme)

    def _au_theme(self, _schema=None) -> None:
        self._teinter()

    def changeEvent(self, evenement):
        if evenement.type() in (QEvent.Type.PaletteChange,
                                QEvent.Type.ApplicationPaletteChange):
            self._teinter()
        super().changeEvent(evenement)

    def _teinter(self) -> None:
        # Poser la feuille de style change la palette du widget, qui rappelle
        # changeEvent : sans cette comparaison, on tournerait en rond jusqu'à
        # épuisement de la pile.
        voulue = teinte_discrete()
        if voulue == self._teinte:
            return
        self._teinte = voulue
        self.setStyleSheet(f"color: {voulue};")


def discret(texte: str) -> QLabel:
    return Discret(texte)


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


class BoutonRouge(QPushButton):
    """Le bouton d'un geste qui détruit : il se signale par sa couleur.

    Rouge pour tout ce qui supprime, et rien d'autre : si l'archivage, la
    copie et la mise à la corbeille se ressemblent tous, le clic de trop se
    fait un jour. La teinte se recalcule au changement de thème, comme pour
    les textes discrets.
    """

    def __init__(self, texte: str = "", parent=None):
        super().__init__(texte, parent)
        self._teinte = ""
        self._teinter()
        suivre_le_theme(self, self._au_theme)

    def _au_theme(self, _schema=None) -> None:
        self._teinter()

    def changeEvent(self, evenement):
        if evenement.type() in (QEvent.Type.PaletteChange,
                                QEvent.Type.ApplicationPaletteChange):
            self._teinter()
        super().changeEvent(evenement)

    def _teinter(self) -> None:
        # Même précaution que pour « Discret » : poser la feuille de style
        # change la palette, qui rappellerait changeEvent sans fin.
        voulue = teinte_defaire()
        if voulue == self._teinte:
            return
        self._teinte = voulue
        self.setStyleSheet(f"color: {voulue}; font-weight: bold;")


def bouton(texte: str, action=None, principal: bool = False,
           danger: bool = False) -> QPushButton:
    b = BoutonRouge(texte) if danger else QPushButton(texte)
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


class Annonce(QLabel):
    """Un mot en bas de la fenêtre, le temps d'être lu, puis plus rien.

    À ne pas confondre avec les bandeaux de l'accueil, qui restent tant que
    ce qu'ils annoncent est vrai : celle-ci passe.

    Une fenêtre modale pour annoncer « c'est enregistré » arrête le travail
    et réclame un clic pour confirmer ce qu'on voit déjà. L'annonce le dit
    sans rien interrompre : elle paraît, se lit, s'efface. Elle reste donc
    réservée à ce qui s'est bien passé — un refus ou une erreur méritent
    qu'on s'arrête, et gardent leur fenêtre.

    Il y en a une seule par fenêtre : un deuxième message remplace le
    premier au lieu de s'empiler par-dessus.
    """

    MARGE = 52          # du bas de la fenêtre : au-dessus de la barre de boutons
    PARUTION = 140      # millisecondes pour apparaître
    EFFACEMENT = 420    # et pour s'en aller
    DEDANS = (20, 11)   # ce qui sépare le texte du bord, horizontal et vertical

    def __init__(self, fenetre: QWidget):
        super().__init__(fenetre)
        self.setObjectName("annonce")
        # Elle flotte au-dessus de l'écran : elle ne doit pas prendre les
        # clics destinés à ce qu'elle recouvre.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Le gras est posé sur la police, pas dans la feuille de style : la
        # mesure du texte doit être faite avec la police qui servira à le
        # peindre, sinon la boîte est taillée trop court.
        police = self.font()
        police.setBold(True)
        self.setFont(police)
        self._voile = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._voile)
        self._fondu = QPropertyAnimation(self._voile, b"opacity", self)
        self._fondu.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fondu.finished.connect(self._fondu_fini)
        self._minuteur = QTimer(self)
        self._minuteur.setSingleShot(True)
        self._minuteur.timeout.connect(self._partir)
        fenetre.installEventFilter(self)
        self.hide()

    def montrer(self, message: str, duree: int) -> None:
        self.setText(message)
        self.setStyleSheet(self._habit())
        self._placer()
        self.show()
        self.raise_()
        self._minuteur.start(duree)
        self._glisser(1.0, self.PARUTION)

    # --- fondu ------------------------------------------------------------

    def _glisser(self, vers: float, duree: int) -> None:
        self._fondu.stop()
        self._fondu.setDuration(duree)
        self._fondu.setStartValue(self._voile.opacity())
        self._fondu.setEndValue(vers)
        self._fondu.start()

    def _partir(self) -> None:
        self._glisser(0.0, self.EFFACEMENT)

    def _fondu_fini(self) -> None:
        # Se cacher libère le dessin ; rester visible à opacité nulle coûte
        # un repeint à chaque rafraîchissement de la fenêtre.
        if self._voile.opacity() <= 0.01:
            self.hide()

    # --- place et couleurs ------------------------------------------------

    def _habit(self) -> str:
        """Clair sur sombre, sombre sur clair : un bandeau se détache."""
        sombre = _sombre()
        fond = "#eceef1" if sombre else "#2b2e33"
        encre = "#16181c" if sombre else "#f5f6f8"
        return (f"QLabel#annonce {{ background: {fond}; color: {encre};"
                " border-radius: 7px; padding: 10px 18px; font-weight: bold; }")

    def _placer(self) -> None:
        """Taillé au texte, centré en bas.

        La taille est mesurée à la main : un QLabel qui renvoie à la ligne ne
        sait pas deviner la largeur qu'on lui destine, et se replie en
        colonne étroite si on le laisse faire.
        """
        fenetre = self.parentWidget()
        if fenetre is None:
            return
        marge_h, marge_v = self.DEDANS
        dispo = max(220, fenetre.width() - 72) - 2 * marge_h
        mesure = QFontMetrics(self.font()).boundingRect(
            0, 0, dispo, 4000,
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter),
            self.text())
        self.setFixedSize(mesure.width() + 2 * marge_h + 2,
                          mesure.height() + 2 * marge_v + 2)
        self.move(max(0, (fenetre.width() - self.width()) // 2),
                  max(0, fenetre.height() - self.height() - self.MARGE))

    def eventFilter(self, objet, evenement) -> bool:
        if evenement.type() == QEvent.Type.Resize and self.isVisible():
            self._placer()
        return super().eventFilter(objet, evenement)


def annoncer(parent, message: str, duree: int = 2600) -> None:
    """Annonce en bas de la fenêtre ce qui vient d'être fait.

    Pour ce qui s'est bien passé et n'appelle aucune décision : enregistré,
    marqué payé, copié. Ce qui échoue ou demande un choix passe par
    `alerter` ou `confirmer`, qui, eux, arrêtent la main.
    """
    fenetre = parent.window() if parent is not None else None
    if fenetre is None:
        return
    annonce = fenetre.findChild(Annonce, "annonce")
    if annonce is None or annonce.parentWidget() is not fenetre:
        annonce = Annonce(fenetre)
    annonce.montrer(message, duree)


def informer(parent, titre_: str, message: str) -> None:
    QMessageBox.information(parent, titre_, message)


VIDE = QDate(1900, 1, 1)


class ChampDate(QDateEdit):
    """Champ date au format français, avec calendrier.

    Pour une date facultative, la valeur minimale sert de « case vide » :
    c'est la façon propre de représenter une absence de date avec un
    QDateEdit. Mais le calendrier s'ouvrait alors sur janvier 1900, et il
    fallait remonter plus de quinze cents mois pour arriver à aujourd'hui.
    Sur un champ vide il s'ouvre donc sur le mois en cours — sans rien
    écrire dans le champ : la date ne s'inscrit qu'au clic sur un jour, et
    refermer le calendrier laisse le champ vide comme il l'était.
    """

    def __init__(self, valeur_iso: str = "", optionnel: bool = False):
        super().__init__()
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd/MM/yyyy")
        self.setMinimumDate(VIDE)
        if optionnel:
            self.setSpecialValueText("—")
        if valeur_iso:
            self.setDate(QDate.fromString(valeur_iso[:10], "yyyy-MM-dd"))
        elif optionnel:
            self.setDate(VIDE)
        else:
            self.setDate(QDate.currentDate())
        # Qt ne crée le calendrier qu'au premier clic ; en le posant soi-même
        # on l'a tout de suite sous la main pour le surveiller.
        self.setCalendarWidget(QCalendarWidget(self))
        self.calendarWidget().installEventFilter(self)

    def eventFilter(self, objet, evenement) -> bool:
        if evenement.type() == QEvent.Type.Show:
            jour = QDate.currentDate()
            # Aujourd'hui en gras : sans sélection, rien ne distinguait le
            # bon jour des trente autres. Remis à chaque ouverture, la date
            # reste juste même si l'application passe la nuit allumée.
            objet.setDateTextFormat(QDate(), QTextCharFormat())
            gras = QTextCharFormat()
            gras.setFontWeight(QFont.Weight.Bold)
            objet.setDateTextFormat(jour, gras)
            if self.date() == VIDE:
                # Change la page affichée, pas la sélection : le champ, lui,
                # reste vide tant qu'aucun jour n'est cliqué.
                objet.setCurrentPage(jour.year(), jour.month())
        return super().eventFilter(objet, evenement)


def champ_date(valeur_iso: str = "", optionnel: bool = False) -> ChampDate:
    return ChampDate(valeur_iso, optionnel)


def valeur_date(boite) -> str:
    if boite.date() == VIDE:
        return ""
    return boite.date().toString("yyyy-MM-dd")
