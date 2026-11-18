"""Liste des devis et éditeur de devis."""

from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPlainTextEdit, QStyledItemDelegate, QTableView, QVBoxLayout, QWidget,
)

from ...domaine import (
    Devis, Ligne, STATUTS_DEVIS, TAUX_TVA, UNITES, date_fr, euros, nombre,
    nouvel_id, sous_totaux_sections, taux_tva_txt,
)
from ..impression import RenduDocument
from .commun import (
    CENTRE, Colonne, DROITE, GAUCHE, DelegueAmorce, ModeleListe,
    activer_le_tri, alerter, amorce, barre, bouton, bouton_copier_adresse,
    champ_date, champ_entier, champ_pourcent, champ_texte, cle_numero,
    annoncer, confirmer, discret, etiquette_client, infobulles_si_tronque,
    liste_deroulante, rendre_cherchable, titre, valeur_date,
)
from .dialogues import DialogueArticle
from .vues import VueListe

COL_DESIGNATION, COL_QUANTITE, COL_UNITE, COL_PU, COL_TVA, COL_REMISE, COL_TOTAL = range(7)


# --- tableau des lignes ---------------------------------------------------


def question_lignes(modele, rangs, mot: str) -> str:
    """Ce qu'on s'apprête à retirer, nommé plutôt que compté.

    « Supprimer 3 lignes ? » ne dit pas lesquelles : on relit la sélection
    dans la question, parce que c'est elle qu'on vient de cliquer à la
    souris et qu'une ligne de trop se voit mal dans un tableau.
    """
    noms = []
    for rang in sorted(rangs):
        ligne = modele.ligne(rang)
        nom = (getattr(ligne, "designation", "") or "").strip()
        if len(nom) > 70:
            nom = nom[:70] + "…"
        noms.append(nom or "(sans désignation)")

    article, seul = (("du", "seul le devis") if mot == "devis"
                     else ("de la", "seule la facture"))
    fin = f"\n\nLa bibliothèque n'est pas touchée : {seul} change."
    if len(noms) == 1:
        return f"Retirer « {noms[0]} » {article} {mot} ?" + fin
    liste = "\n".join(f"• {nom}" for nom in noms[:6])
    if len(noms) > 6:
        liste += f"\n• … et {len(noms) - 6} autre(s)"
    return f"Retirer ces {len(noms)} lignes {article} {mot} ?\n\n{liste}" + fin


class ModeleLignes(QAbstractTableModel):
    """Les lignes d'un devis ou d'une facture, éditables dans le tableau."""

    EN_TETES = ["Désignation", "Qté", "Unité", "P.U. HT", "TVA", "Remise", "Total HT"]

    def __init__(self, document):
        super().__init__()
        self.document = document

    def definir(self, document) -> None:
        self.beginResetModel()
        self.document = document
        self.endResetModel()

    def ligne(self, rang: int) -> Ligne | None:
        if 0 <= rang < len(self.document.lignes):
            return self.document.lignes[rang]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.document.lignes)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else 7

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.EN_TETES[section]
        if orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        ligne = self.ligne(index.row())
        if ligne is None:
            return base
        if index.column() == COL_DESIGNATION:
            # Celle d'un ouvrage n'est pas un texte libre : elle se corrige
            # dans la fiche de la bibliothèque, au double-clic.
            if ligne.article_id:
                return base
            return base | Qt.ItemFlag.ItemIsEditable
        if index.column() == COL_TOTAL:
            return base
        if ligne.chiffree:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        ligne = self.ligne(index.row())
        if ligne is None:
            return None
        colonne = index.column()

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            brut = role == Qt.ItemDataRole.EditRole
            if colonne == COL_DESIGNATION:
                if ligne.detail and not brut:
                    return f"{ligne.designation}\n{ligne.detail}"
                return ligne.designation
            if colonne == COL_TOTAL:
                if ligne.type == "section":
                    total = sous_totaux_sections(self.document).get(ligne.id, Decimal("0.00"))
                    return euros(total)
                return euros(ligne.total_ht) if ligne.chiffree else ""
            if not ligne.chiffree:
                return None
            if colonne == COL_QUANTITE:
                return ligne.quantite if brut else nombre(ligne.quantite, 3)
            if colonne == COL_UNITE:
                return ligne.unite
            if colonne == COL_PU:
                return ligne.prix_unitaire if brut else euros(ligne.prix_unitaire)
            if colonne == COL_TVA:
                return ligne.taux_tva if brut else taux_tva_txt(ligne.taux_tva)
            if colonne == COL_REMISE:
                if brut:
                    return ligne.remise_pct
                return f"{nombre(ligne.remise_pct)} %" if ligne.remise_pct else ""

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if colonne in (COL_QUANTITE, COL_PU, COL_TOTAL, COL_REMISE):
                return DROITE
            if colonne in (COL_UNITE, COL_TVA):
                return CENTRE
            return GAUCHE

        if role == Qt.ItemDataRole.FontRole and ligne.type == "section":
            police = QFont()
            police.setBold(True)
            return police

        if role == Qt.ItemDataRole.BackgroundRole and ligne.type == "section":
            return QBrush(QColor(0, 0, 0, 28))

        if role == Qt.ItemDataRole.ForegroundRole and ligne.type == "texte":
            return QBrush(QColor(128, 128, 128))

        return None

    def setData(self, index, valeur, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole:
            return False
        ligne = self.ligne(index.row())
        if ligne is None:
            return False
        colonne = index.column()
        try:
            if colonne == COL_DESIGNATION:
                ligne.designation = str(valeur).strip()
            elif colonne == COL_QUANTITE:
                ligne.quantite = float(valeur)
            elif colonne == COL_UNITE:
                ligne.unite = str(valeur)
            elif colonne == COL_PU:
                ligne.prix_unitaire = float(valeur)
            elif colonne == COL_TVA:
                ligne.taux_tva = float(valeur)
            elif colonne == COL_REMISE:
                ligne.remise_pct = float(valeur)
            else:
                return False
        except (TypeError, ValueError):
            return False
        # Le total de la ligne et le sous-total de sa section bougent aussi
        self.dataChanged.emit(self.index(0, COL_TOTAL),
                              self.index(self.rowCount() - 1, COL_TOTAL))
        self.dataChanged.emit(index, index)
        return True

    # --- manipulations ---------------------------------------------------

    def inserer(self, ligne: Ligne, position: int | None = None) -> int:
        if position is None or position < 0:
            position = len(self.document.lignes)
        self.beginInsertRows(QModelIndex(), position, position)
        self.document.lignes.insert(position, ligne)
        self.endInsertRows()
        return position

    def retirer(self, rang: int) -> None:
        if not 0 <= rang < len(self.document.lignes):
            return
        self.beginRemoveRows(QModelIndex(), rang, rang)
        del self.document.lignes[rang]
        self.endRemoveRows()

    def deplacer(self, rang: int, pas: int) -> int:
        cible = rang + pas
        if not (0 <= rang < len(self.document.lignes) and 0 <= cible < len(self.document.lignes)):
            return rang
        self.beginResetModel()
        lignes = self.document.lignes
        lignes[rang], lignes[cible] = lignes[cible], lignes[rang]
        self.endResetModel()
        return cible


class DelegueNombre(QStyledItemDelegate):
    """Le délégué par défaut plafonne à 99,99 : ici on fixe nos propres bornes."""

    def __init__(self, parent=None, decimales=2, maximum=9_999_999.0, suffixe=""):
        super().__init__(parent)
        self.decimales = decimales
        self.maximum = maximum
        self.suffixe = suffixe

    def createEditor(self, parent, option, index):
        boite = QDoubleSpinBox(parent)
        boite.setDecimals(self.decimales)
        boite.setRange(-self.maximum, self.maximum)
        boite.setSuffix(self.suffixe)
        return boite


class DelegueChoix(QStyledItemDelegate):
    def __init__(self, valeurs, parent=None, formateur=str):
        super().__init__(parent)
        self.valeurs = valeurs
        self.formateur = formateur

    def createEditor(self, parent, option, index):
        boite = QComboBox(parent)
        for valeur in self.valeurs:
            boite.addItem(self.formateur(valeur), valeur)
        return boite

    def setEditorData(self, editeur, index):
        valeur = index.data(Qt.ItemDataRole.EditRole)
        position = editeur.findData(valeur)
        editeur.setCurrentIndex(max(0, position))

    def setModelData(self, editeur, modele, index):
        modele.setData(index, editeur.currentData(), Qt.ItemDataRole.EditRole)


# --- la fiche derrière une ligne ------------------------------------------


# Ce que la fiche de bibliothèque dicte à la ligne qui en vient : le champ
# de la ligne, et celui de la fiche quand il ne porte pas le même nom.
REPORTS = [
    ("designation", None),
    ("detail", None),
    ("unite", None),
    ("prix_unitaire", "prix_vente"),
    ("taux_tva", None),
]


def ouvrir_fiche_de_la_ligne(parent, depot, ligne, reportable: bool) -> bool:
    """Ouvre la fiche de bibliothèque dont vient une ligne.

    Ce qu'on corrige dans la fiche descend sur la ligne du document ouvert :
    c'est bien celle-là qu'on avait sous les yeux en double-cliquant.

    Seulement ce qu'on vient de changer, cependant. Une ligne porte souvent
    un prix négocié pour ce chantier-là ; ouvrir la fiche pour y lire le
    tarif, puis sortir par OK, ne doit pas écraser ce prix par celui de la
    bibliothèque. On compare donc la fiche à elle-même, avant et après.

    Sur une facture émise, rien ne descend : le verrou comptable tient.

    Rend vrai si la ligne a changé.
    """
    article = depot.article(ligne.article_id) if ligne.article_id else None
    if article is None:
        # Sa fiche a disparu de la bibliothèque : sans cela la ligne resterait
        # prisonnière d'un lien mort, ni modifiable ici ni ouvrable là-bas.
        if ligne.article_id and confirmer(
                parent, "Fiche introuvable",
                "L'ouvrage de cette ligne n'est plus dans la bibliothèque.\n\n"
                "Modifier le texte de la ligne à la place ?"):
            ligne.article_id = ""
            return True
        return False

    avant = {champ: getattr(article, source or champ) for champ, source in REPORTS}
    dialogue = DialogueArticle(parent, depot, article)
    if dialogue.exec() != QDialog.DialogCode.Accepted:
        return False
    fiche = depot.enregistrer_article(dialogue.resultat())
    if not reportable:
        return False

    change = False
    for champ, source in REPORTS:
        valeur = getattr(fiche, source or champ)
        if valeur != avant[champ] and getattr(ligne, champ) != valeur:
            setattr(ligne, champ, valeur)
            change = True
    return change


# --- choix dans la bibliothèque de prix -----------------------------------


# Ce qu'une ligne de devis vend. Les ouvrages d'abord : sur les 1316 lignes
# chiffrées reprises de l'ancien logiciel qu'on retrouve en bibliothèque,
# 1234 sont des ouvrages — une prestation posée, au prix de vente. Les
# matériaux restent à portée, pour le sable et le ciment qu'on livre.
FAMILLES_BIBLIOTHEQUE = ["Ouvrages", "Matériaux", "Tout"]


class DialogueChoixArticle(QDialog):
    def __init__(self, parent, depot, genre: str = ""):
        super().__init__(parent)
        self.depot = depot
        self.setWindowTitle("Insérer depuis la bibliothèque de prix")
        self.resize(760, 460)

        # Sur quoi la bibliothèque s'ouvre : les ouvrages pour un devis, les
        # matériaux pour composer un ouvrage.
        self.genre = liste_deroulante(FAMILLES_BIBLIOTHEQUE,
                                      genre if genre in FAMILLES_BIBLIOTHEQUE
                                      else FAMILLES_BIBLIOTHEQUE[0])
        self.genre.currentIndexChanged.connect(self.rafraichir)
        self.compte = discret("")

        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Nom ou code…")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self.rafraichir)

        self.modele = ModeleListe([
            Colonne("Réf.", lambda a: a.reference, largeur=90),
            Colonne("Désignation", lambda a: a.designation, gras=True),
            Colonne("Famille", lambda a: a.famille, largeur=130),
            Colonne("Un.", lambda a: a.unite, largeur=55, alignement=CENTRE),
            Colonne("Vente", lambda a: euros(a.prix_vente), largeur=100,
                    alignement=DROITE, cle=lambda a: a.prix_vente or 0.0),
            Colonne("TVA", lambda a: f"{nombre(a.taux_tva)} %", largeur=65,
                    alignement=CENTRE, cle=lambda a: a.taux_tva or 0.0),
        ])
        self.tableau = QTableView()
        self.tableau.setModel(self.modele)
        self.tableau.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableau.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tableau.verticalHeader().setVisible(False)
        self.tableau.setAlternatingRowColors(True)
        self.tableau.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableau.doubleClicked.connect(self.accept)
        # Le même tri que sur les listings : le maçon qui cherche un article
        # veut pouvoir classer la bibliothèque par prix ou par famille.
        activer_le_tri(self.tableau, self.modele)
        self.surbrillance = DelegueAmorce(self.tableau)
        for colonne in (0, 1):  # la référence et la désignation
            self.tableau.setItemDelegateForColumn(colonne, self.surbrillance)
        infobulles_si_tronque(self.tableau)

        boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Insérer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.addWidget(barre(self.genre, self.recherche))
        disposition.addWidget(self.tableau, 1)
        disposition.addWidget(barre(
            discret("Astuce : sélection multiple possible avec ⌘ ou ⇧."),
            "-", self.compte))
        disposition.addWidget(boutons)
        self.rafraichir()

    def _retenus(self):
        """Ce que la bibliothèque propose : le genre choisi, puis la recherche."""
        genre = self.genre.currentText()
        articles = [a for a in self.depot.articles()
                    if genre == "Tout"
                    or (a.type == "ouvrage") == (genre == "Ouvrages")]
        # Comme sur les écrans de la bibliothèque : le début du nom ou du
        # code, pas la famille que presque toutes les fiches ont en commun.
        cherche = self.recherche.text().strip()
        if cherche:
            articles = [a for a in articles
                        if amorce(a.designation, cherche)
                        or amorce(a.reference, cherche)]
        return articles

    def rafraichir(self):
        self.surbrillance.chercher(self.recherche.text().strip())
        retenus = self._retenus()
        self.modele.definir(retenus)
        self.compte.setText(f"{len(retenus)} fiche(s)")
        for index, colonne in enumerate(self.modele.colonnes):
            if colonne.largeur:
                self.tableau.setColumnWidth(index, colonne.largeur)
            else:
                self.tableau.horizontalHeader().setSectionResizeMode(
                    index, QHeaderView.ResizeMode.Stretch)

    def articles(self):
        rangs = sorted({i.row() for i in self.tableau.selectionModel().selectedRows()})
        return [self.modele.element(r) for r in rangs]


# --- éditeur --------------------------------------------------------------


class EditeurDevis(QWidget):
    ferme = Signal()
    enregistre = Signal()
    # Le devis dont on veut voir le chantier : heures et fournitures.
    chantier_demande = Signal(object)
    # Le devis à facturer : la fenêtre principale ouvre la suite, comme
    # lorsque la demande vient de la liste.
    facturer_demande = Signal(object)

    def __init__(self, depot, devis: Devis, parent=None):
        super().__init__(parent)
        self.depot = depot
        self.devis = devis

        # Huit cents fiches : on tape trois lettres plutôt que de dérouler.
        self.client = rendre_cherchable(QComboBox(), "Nom, société ou ville…")
        self.adresse_chantier = champ_texte(
            devis.adresse_chantier, "adresse des travaux")
        self.copier_adresse = bouton_copier_adresse(
            self.adresse_chantier, self._client_courant)
        self.objet = champ_texte(devis.objet, "Construction d'un garage accolé de 32 m²")
        self.date = champ_date(devis.date_devis)
        self.validite = champ_entier(devis.validite_jours or depot.societe.validite_jours, 999)
        self.validite.setSuffix(" jours")
        self.statut = liste_deroulante(STATUTS_DEVIS, devis.statut)
        self.remise = champ_pourcent(devis.remise_globale_pct)
        self.acompte = champ_pourcent(devis.acompte_pct)
        self.numero = QLabel(devis.numero or "attribué à l'enregistrement")

        for widget in (self.remise, self.acompte):
            widget.valueChanged.connect(self._recalculer)
        self.validite.valueChanged.connect(self._recalculer)
        self.date.dateChanged.connect(self._recalculer)

        self.modele = ModeleLignes(devis)
        self.modele.dataChanged.connect(lambda *_: self._recalculer())
        self.modele.rowsInserted.connect(lambda *_: self._recalculer())
        self.modele.rowsRemoved.connect(lambda *_: self._recalculer())
        self.modele.modelReset.connect(self._recalculer)

        self.tableau = QTableView()
        self.tableau.setModel(self.modele)
        self.tableau.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableau.setAlternatingRowColors(True)
        self.tableau.setWordWrap(False)
        self.tableau.setItemDelegateForColumn(
            COL_QUANTITE, DelegueNombre(self, decimales=3, maximum=999_999))
        self.tableau.setItemDelegateForColumn(
            COL_PU, DelegueNombre(self, decimales=2, suffixe=" €"))
        self.tableau.setItemDelegateForColumn(
            COL_REMISE, DelegueNombre(self, decimales=2, maximum=100, suffixe=" %"))
        self.tableau.setItemDelegateForColumn(COL_UNITE, DelegueChoix(UNITES, self))
        self.tableau.setItemDelegateForColumn(
            COL_TVA, DelegueChoix(TAUX_TVA, self, formateur=taux_tva_txt))
        # La désignation d'un ouvrage ouvre sa fiche au lieu de s'éditer.
        self.tableau.doubleClicked.connect(self._double_clic)

        # La désignation prend toute la place restante, les colonnes chiffrées
        # gardent une largeur fixe pour rester lisibles.
        entetes = self.tableau.horizontalHeader()
        entetes.setSectionResizeMode(COL_DESIGNATION, QHeaderView.ResizeMode.Stretch)
        for colonne, largeur in ((COL_QUANTITE, 90), (COL_UNITE, 80), (COL_PU, 110),
                                 (COL_TVA, 85), (COL_REMISE, 90), (COL_TOTAL, 125)):
            entetes.setSectionResizeMode(colonne, QHeaderView.ResizeMode.Fixed)
            self.tableau.setColumnWidth(colonne, largeur)
        # Hauteur variable : le détail d'une ligne s'affiche sous sa désignation.
        self.tableau.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        # Une ligne sans détail ne doit pas être écrasée
        self.tableau.verticalHeader().setMinimumSectionSize(27)
        # Une désignation plus large que sa colonne se lit au survol.
        infobulles_si_tronque(self.tableau)

        self.totaux = QLabel()
        self.totaux.setTextFormat(Qt.TextFormat.RichText)
        self.totaux.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.notes = QPlainTextEdit(devis.notes_internes)
        self.notes.setPlaceholderText("Notes internes — ne figurent pas sur le devis imprimé")
        self.notes.setMaximumHeight(70)

        self._construire()
        self._remplir_clients()
        self._recalculer()

    # --- montage ---------------------------------------------------------

    def _construire(self) -> None:
        entete = QFormLayout()
        entete.addRow("Numéro", self.numero)
        entete.addRow("Client", self.client)
        entete.addRow("Adresse chantier",
                      barre(self.adresse_chantier, self.copier_adresse))
        entete.addRow("Objet", self.objet)

        droite = QFormLayout()
        droite.addRow("Date", self.date)
        droite.addRow("Validité", self.validite)
        droite.addRow("Statut", self.statut)
        droite.addRow("Remise globale", self.remise)
        droite.addRow("Acompte", self.acompte)

        cadre = QWidget()
        colonnes = QHBoxLayout(cadre)
        colonnes.setContentsMargins(0, 0, 0, 0)
        gauche = QWidget()
        gauche.setLayout(entete)
        fin = QWidget()
        fin.setLayout(droite)
        colonnes.addWidget(gauche, 3)
        colonnes.addWidget(fin, 2)

        outils = barre(
            bouton("+ Prestation", self.ajouter_prestation),
            bouton("+ Section", self.ajouter_section),
            bouton("+ Texte libre", self.ajouter_texte),
            # Le geste courant, mis en avant : sur les lignes chiffrées des
            # documents repris, la bibliothèque en fournit quinze sur seize.
            bouton("Bibliothèque…", self.inserer_articles, principal=True),
            "-",
            bouton("↑", lambda: self.deplacer(-1)),
            bouton("↓", lambda: self.deplacer(1)),
            bouton("Supprimer la ligne", self.supprimer_ligne, danger=True),
        )

        bas = QWidget()
        disposition_bas = QHBoxLayout(bas)
        disposition_bas.setContentsMargins(0, 0, 0, 0)
        groupe_notes = QGroupBox("Notes internes")
        notes_layout = QVBoxLayout(groupe_notes)
        notes_layout.addWidget(self.notes)
        groupe_totaux = QGroupBox("Récapitulatif")
        totaux_layout = QVBoxLayout(groupe_totaux)
        totaux_layout.addWidget(self.totaux)
        groupe_totaux.setMinimumWidth(330)
        disposition_bas.addWidget(groupe_notes, 1)
        disposition_bas.addWidget(groupe_totaux)

        actions = barre(
            bouton("← Retour à la liste", self._retour),
            "-",
            bouton("Aperçu avant impression", self.apercu),
            bouton("Enregistrer en PDF", self.exporter_pdf),
            bouton("Imprimer…", self.imprimer),
            bouton("Chantier", self.chantier),
            bouton("Facturer…", self.facturer),
            bouton("Enregistrer", self._enregistrer_et_confirmer,
                   principal=True),
        )

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(16, 14, 16, 14)
        disposition.setSpacing(10)
        disposition.addWidget(titre("Devis"))
        disposition.addWidget(cadre)
        disposition.addWidget(outils)
        disposition.addWidget(self.tableau, 1)
        disposition.addWidget(bas)
        disposition.addWidget(actions)

    def _remplir_clients(self) -> None:
        self.client.blockSignals(True)
        self.client.clear()
        self.client.addItem("— aucun —", "")
        for client in self.depot.clients():
            self.client.addItem(etiquette_client(client), client.id)
        index = self.client.findData(self.devis.client_id)
        self.client.setCurrentIndex(max(0, index))
        self.client.blockSignals(False)

    def _client_courant(self):
        return self.depot.client(self.client.currentData() or "")

    # --- lignes ----------------------------------------------------------

    def _double_clic(self, index) -> None:
        """Le double-clic sur la désignation d'un ouvrage ouvre son ouvrage."""
        if index.column() == COL_DESIGNATION:
            # La fiche attend la fin du double-clic pour s'ouvrir.
            QTimer.singleShot(0, lambda: self._fiche_de_la_ligne(index.row()))

    def _fiche_de_la_ligne(self, rang: int) -> None:
        ligne = self.modele.ligne(rang)
        if ligne is None:
            return
        if ouvrir_fiche_de_la_ligne(self, self.depot, ligne, True):
            self.modele.dataChanged.emit(self.modele.index(rang, 0),
                                         self.modele.index(rang, COL_TOTAL))

    def _position_insertion(self) -> int | None:
        indexes = self.tableau.selectionModel().selectedRows()
        return indexes[0].row() + 1 if indexes else None

    def _ajouter(self, ligne: Ligne) -> None:
        rang = self.modele.inserer(ligne, self._position_insertion())
        index = self.modele.index(rang, COL_DESIGNATION)
        self.tableau.setCurrentIndex(index)
        self.tableau.edit(index)

    def ajouter_prestation(self) -> None:
        self._ajouter(Ligne(taux_tva=self.depot.societe.taux_tva_defaut))

    def ajouter_section(self) -> None:
        self._ajouter(Ligne(type="section", designation="Nouvelle section"))

    def ajouter_texte(self) -> None:
        self._ajouter(Ligne(type="texte", designation="Texte libre"))

    def inserer_articles(self) -> None:
        dialogue = DialogueChoixArticle(self, self.depot)
        if dialogue.exec() != QDialog.DialogCode.Accepted:
            return
        position = self._position_insertion()
        for article in dialogue.articles():
            ligne = Ligne(
                designation=article.designation, detail=article.detail,
                unite=article.unite, prix_unitaire=article.prix_vente,
                taux_tva=article.taux_tva, article_id=article.id, quantite=1.0,
            )
            position = self.modele.inserer(ligne, position)
            position += 1

    def supprimer_ligne(self) -> None:
        rangs = [i.row() for i in self.tableau.selectionModel().selectedRows()]
        if not rangs:
            return
        if not confirmer(self, "Supprimer du devis",
                         question_lignes(self.modele, rangs, "devis")):
            return
        for rang in sorted(rangs, reverse=True):
            self.modele.retirer(rang)

    def deplacer(self, pas: int) -> None:
        indexes = self.tableau.selectionModel().selectedRows()
        if not indexes:
            return
        nouveau = self.modele.deplacer(indexes[0].row(), pas)
        self.tableau.selectRow(nouveau)

    # --- totaux ----------------------------------------------------------

    def _recalculer(self) -> None:
        self._collecter(sans_numero=True)
        t = self.devis.totaux()
        lignes = []
        if t.remise:
            lignes.append(("Total brut HT", euros(t.brut_ht), False))
            lignes.append((f"Remise {nombre(self.devis.remise_globale_pct)} %",
                           "− " + euros(t.remise), False))
        lignes.append(("Total HT", euros(t.total_ht), True))
        for l in t.tva:
            lignes.append((f"TVA {taux_tva_txt(l.taux)}", euros(l.montant), False))
        lignes.append(("Total TTC", euros(t.total_ttc), True))
        if self.devis.acompte_pct:
            lignes.append((f"Acompte {nombre(self.devis.acompte_pct)} %", euros(t.acompte), False))
            lignes.append(("Solde", euros(t.solde), False))

        corps = "".join(
            f"<tr><td style='padding:2px 6px;'>{'<b>' if fort else ''}{libelle}"
            f"{'</b>' if fort else ''}</td>"
            f"<td align='right' style='padding:2px 6px;'>{'<b>' if fort else ''}{valeur}"
            f"{'</b>' if fort else ''}</td></tr>"
            for libelle, valeur, fort in lignes
        )
        self.totaux.setText(f"<table width='100%'>{corps}</table>")
        self.numero.setText(self.devis.numero or "attribué à l'enregistrement")

    # --- enregistrement --------------------------------------------------

    def _collecter(self, sans_numero: bool = False) -> None:
        d = self.devis
        d.client_id = self.client.currentData() or ""
        d.objet = self.objet.text().strip()
        d.adresse_chantier = self.adresse_chantier.text().strip()
        d.date_devis = valeur_date(self.date)
        d.validite_jours = self.validite.value()
        d.statut = self.statut.currentText()
        d.remise_globale_pct = self.remise.value()
        d.acompte_pct = self.acompte.value()
        d.notes_internes = self.notes.toPlainText().strip()

    def _enregistrer_et_confirmer(self) -> None:
        """Le bouton confirme ; l'enregistrement d'avant une impression, non.

        Sans un mot, on ne sait pas si le devis est parti dans le dossier ou
        si un champ manquant a tout retenu — et on réenregistre à tout
        hasard.
        """
        if self.enregistrer():
            annoncer(self, f"Devis {self.devis.numero} enregistré")

    def enregistrer(self) -> bool:
        self._collecter()
        if not self.devis.client_id:
            alerter(self, "Client manquant", "Choisissez le client avant d'enregistrer le devis.")
            return False
        self.depot.enregistrer_devis(self.devis)
        self.numero.setText(self.devis.numero)
        self.enregistre.emit()
        return True

    def chantier(self) -> None:
        """Le même travail, vu du côté de l'atelier.

        Ce qui est à l'écran est d'abord rangé dans le devis : les heures se
        comptent sur les lignes qu'on vient d'ajouter, pas sur celles d'hier.
        """
        self._collecter()
        if self.devis.client_id:
            self.enregistrer()
        self.chantier_demande.emit(self.devis)

    def facturer(self) -> None:
        """Du devis à sa facture, sans repasser par la liste.

        Le devis est enregistré d'abord : c'est ce qui est à l'écran qu'on
        veut facturer, pas ce qui dormait dans le dossier.
        """
        if not self.enregistrer():
            return
        if not self.devis.lignes:
            alerter(self, "Devis vide", "Ce devis n'a aucune ligne à facturer.")
            return
        self.facturer_demande.emit(self.devis)

    def _retour(self) -> None:
        self.enregistrer()
        self.ferme.emit()

    # --- impression ------------------------------------------------------

    def _rendu(self) -> RenduDocument | None:
        if not self.enregistrer():
            return None
        return RenduDocument(self.depot, self.devis)

    def apercu(self) -> None:
        rendu = self._rendu()
        if rendu is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogue = QPrintPreviewDialog(printer, self)
        dialogue.setWindowTitle(f"Aperçu — devis {self.devis.numero}")
        dialogue.resize(900, 1000)
        dialogue.paintRequested.connect(rendu.peindre)
        dialogue.exec()

    def exporter_pdf(self) -> None:
        rendu = self._rendu()
        if rendu is None:
            return
        defaut = str(self.depot.d_pdf / rendu.nom_fichier())
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le devis en PDF",
                                                defaut, "Document PDF (*.pdf)")
        if not chemin:
            return
        rendu.vers_pdf(Path(chemin))
        annoncer(self, f"Devis enregistré en PDF : {Path(chemin).name}")

    def imprimer(self) -> None:
        rendu = self._rendu()
        if rendu is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogue = QPrintDialog(printer, self)
        dialogue.setWindowTitle(f"Imprimer le devis {self.devis.numero}")
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            rendu.peindre(printer)


# --- liste des devis ------------------------------------------------------


class VueDevis(VueListe):
    nom = "Devis"
    mot_element = "devis"
    libelle_nouveau = "Nouveau devis"
    libelle_modifier = "Ouvrir"
    indication_recherche = "Numéro, client, objet…"

    ouvrir_demande = Signal(object)
    facturer_demande = Signal(object)

    def __init__(self, depot, parent=None):
        self.statut = liste_deroulante(["Tous les statuts"] + STATUTS_DEVIS)
        super().__init__(depot, parent)
        self.statut.currentIndexChanged.connect(self.rafraichir)

    def filtres(self):
        return [self.statut]

    def actions(self):
        return [bouton("Dupliquer", self.dupliquer),
                bouton("Facturer…", self.facturer)]

    def libelle(self, devis):
        return f"le devis {devis.numero}"

    def archiver(self, devis, definitif):
        self.depot.supprimer_devis(devis.id, definitif=definitif)

    def desarchiver(self, devis):
        self.depot.restaurer_devis(devis.id)

    def colonnes(self):
        return [
            Colonne("Numéro", lambda d: d.numero, largeur=110, gras=True,
                    cle=lambda d: cle_numero(d.numero)),
            Colonne("Date", lambda d: date_fr(d.date_devis), largeur=95,
                    alignement=CENTRE, cle=lambda d: d.date_devis or ""),
            Colonne("Client", lambda d: self.depot.nom_client(d.client_id), largeur=200),
            Colonne("Objet", lambda d: d.objet or self.depot.nom_chantier(d.chantier_id)),
            Colonne("Total HT", lambda d: euros(d.totaux().total_ht),
                    largeur=115, alignement=DROITE,
                    cle=lambda d: d.totaux().total_ht),
            Colonne("TTC", lambda d: euros(d.totaux().total_ttc),
                    largeur=115, alignement=DROITE,
                    cle=lambda d: d.totaux().total_ttc),
            Colonne("Statut", lambda d: d.statut, largeur=95, alignement=CENTRE),
            # Les devis sans facture affichent un tiret : on les groupe avant
            # ceux qui sont entamés, plutôt que de comparer « — » à un taux.
            Colonne("Facturé", self._facture, largeur=80, alignement=CENTRE,
                    cle=self._cle_facture),
        ]

    def _facture(self, devis) -> str:
        from ...domaine.facturation import avancement_facture
        if not self.depot.factures(devis_id=devis.id):
            return "—"
        return f"{nombre(avancement_facture(self.depot, devis))} %"

    def _cle_facture(self, devis) -> tuple:
        from ...domaine.facturation import avancement_facture
        if not self.depot.factures(devis_id=devis.id):
            return (0, 0.0)
        return (1, float(avancement_facture(self.depot, devis)))

    def charger(self):
        statut = self.statut.currentText()
        return self.depot.devis(
            recherche=self.recherche.text().strip(),
            statut="" if statut.startswith("Tous") else statut,
            supprimes=self.archives,
        )

    def nouveau(self):
        if not self.depot.clients():
            alerter(self, "Aucun client",
                    "Créez d'abord un client : un devis est toujours adressé à quelqu'un.")
            return
        societe = self.depot.societe
        # Ni conditions ni mentions recopiées ici : laissées vides, elles
        # se choisissent à l'impression d'après le type du document et son
        # taux de TVA. Les y figer rendait sourd aux Paramètres tout devis
        # déjà créé — et donnait au devis à 10 % le bas de page du 20 %.
        devis = Devis(
            validite_jours=societe.validite_jours,
            acompte_pct=societe.acompte_defaut_pct,
        )
        self.ouvrir_demande.emit(devis)

    def modifier(self):
        devis = self.selection()
        if devis is not None:
            self.ouvrir_demande.emit(devis)

    def facturer(self):
        devis = self.selection()
        if devis is None:
            return
        if not devis.lignes:
            alerter(self, "Devis vide", "Ce devis n'a aucune ligne à facturer.")
            return
        self.facturer_demande.emit(devis)

    def dupliquer(self):
        devis = self.selection()
        if devis is None:
            return
        copie = self.depot.dupliquer_devis(devis.id)
        self._signaler()
        if copie is not None:
            self.ouvrir_demande.emit(copie)


