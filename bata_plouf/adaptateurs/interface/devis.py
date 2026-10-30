"""Liste des devis et éditeur de devis."""

from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
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
    CENTRE, Colonne, DROITE, GAUCHE, ModeleListe, alerter, barre, bouton,
    champ_date, champ_entier, champ_pourcent, champ_texte, confirmer, discret,
    informer, liste_deroulante, titre, valeur_date,
)
from .vues import VueListe

COL_DESIGNATION, COL_QUANTITE, COL_UNITE, COL_PU, COL_TVA, COL_REMISE, COL_TOTAL = range(7)


# --- tableau des lignes ---------------------------------------------------


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


# --- choix dans la bibliothèque de prix -----------------------------------


class DialogueChoixArticle(QDialog):
    def __init__(self, parent, depot):
        super().__init__(parent)
        self.depot = depot
        self.setWindowTitle("Insérer depuis la bibliothèque de prix")
        self.resize(760, 460)

        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Référence, désignation, famille…")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self.rafraichir)

        self.modele = ModeleListe([
            Colonne("Réf.", lambda a: a.reference, largeur=90),
            Colonne("Désignation", lambda a: a.designation, gras=True),
            Colonne("Famille", lambda a: a.famille, largeur=130),
            Colonne("Un.", lambda a: a.unite, largeur=55, alignement=CENTRE),
            Colonne("Vente", lambda a: euros(a.prix_vente), largeur=100, alignement=DROITE),
            Colonne("TVA", lambda a: f"{nombre(a.taux_tva)} %", largeur=65, alignement=CENTRE),
        ])
        self.tableau = QTableView()
        self.tableau.setModel(self.modele)
        self.tableau.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableau.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tableau.verticalHeader().setVisible(False)
        self.tableau.setAlternatingRowColors(True)
        self.tableau.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableau.doubleClicked.connect(self.accept)

        boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Insérer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.addWidget(self.recherche)
        disposition.addWidget(self.tableau, 1)
        disposition.addWidget(discret("Astuce : sélection multiple possible avec ⌘ ou ⇧."))
        disposition.addWidget(boutons)
        self.rafraichir()

    def rafraichir(self):
        self.modele.definir(self.depot.articles(self.recherche.text().strip()))
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

    def __init__(self, depot, devis: Devis, parent=None):
        super().__init__(parent)
        self.depot = depot
        self.devis = devis

        self.client = QComboBox()
        self.chantier = QComboBox()
        self.adresse_chantier = champ_texte(
            devis.adresse_chantier,
            "adresse des travaux, si aucune fiche chantier")
        self.objet = champ_texte(devis.objet, "Construction d'un garage accolé de 32 m²")
        self.date = champ_date(devis.date_devis)
        self.validite = champ_entier(devis.validite_jours or depot.societe.validite_jours, 999)
        self.validite.setSuffix(" jours")
        self.statut = liste_deroulante(STATUTS_DEVIS, devis.statut)
        self.remise = champ_pourcent(devis.remise_globale_pct)
        self.acompte = champ_pourcent(devis.acompte_pct)
        self.numero = QLabel(devis.numero or "attribué à l'enregistrement")

        self.client.currentIndexChanged.connect(self._changer_client)
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
        entete.addRow("Chantier", self.chantier)
        entete.addRow("Adresse chantier", self.adresse_chantier)
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
            bouton("+ Prestation", self.ajouter_prestation, principal=True),
            bouton("+ Section", self.ajouter_section),
            bouton("+ Texte libre", self.ajouter_texte),
            bouton("Bibliothèque…", self.inserer_articles),
            "-",
            bouton("↑", lambda: self.deplacer(-1)),
            bouton("↓", lambda: self.deplacer(1)),
            bouton("Supprimer la ligne", self.supprimer_ligne),
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
            bouton("Enregistrer", self.enregistrer, principal=True),
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
            self.client.addItem(client.libelle, client.id)
        index = self.client.findData(self.devis.client_id)
        self.client.setCurrentIndex(max(0, index))
        self.client.blockSignals(False)
        self._changer_client()

    def _changer_client(self) -> None:
        client_id = self.client.currentData() or ""
        self.chantier.clear()
        self.chantier.addItem("— aucun —", "")
        for chantier in self.depot.chantiers(client_id=client_id):
            self.chantier.addItem(chantier.libelle, chantier.id)
        index = self.chantier.findData(self.devis.chantier_id)
        self.chantier.setCurrentIndex(max(0, index))

    # --- lignes ----------------------------------------------------------

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
        indexes = self.tableau.selectionModel().selectedRows()
        for index in sorted((i.row() for i in indexes), reverse=True):
            self.modele.retirer(index)

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
        d.chantier_id = self.chantier.currentData() or ""
        d.objet = self.objet.text().strip()
        d.adresse_chantier = self.adresse_chantier.text().strip()
        d.date_devis = valeur_date(self.date)
        d.validite_jours = self.validite.value()
        d.statut = self.statut.currentText()
        d.remise_globale_pct = self.remise.value()
        d.acompte_pct = self.acompte.value()
        d.notes_internes = self.notes.toPlainText().strip()

    def enregistrer(self) -> bool:
        self._collecter()
        if not self.devis.client_id:
            alerter(self, "Client manquant", "Choisissez le client avant d'enregistrer le devis.")
            return False
        self.depot.enregistrer_devis(self.devis)
        self.numero.setText(self.devis.numero)
        self.enregistre.emit()
        return True

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
        informer(self, "Devis enregistré", f"Le devis a été enregistré :\n{chemin}")

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
            Colonne("Numéro", lambda d: d.numero, largeur=110, gras=True),
            Colonne("Date", lambda d: date_fr(d.date_devis), largeur=95, alignement=CENTRE),
            Colonne("Client", lambda d: self.depot.nom_client(d.client_id), largeur=200),
            Colonne("Objet", lambda d: d.objet or self.depot.nom_chantier(d.chantier_id)),
            Colonne("Total HT", lambda d: euros(d.totaux().total_ht),
                    largeur=115, alignement=DROITE),
            Colonne("TTC", lambda d: euros(d.totaux().total_ttc),
                    largeur=115, alignement=DROITE),
            Colonne("Statut", lambda d: d.statut, largeur=95, alignement=CENTRE),
            Colonne("Facturé", self._facture, largeur=80, alignement=CENTRE),
        ]

    def _facture(self, devis) -> str:
        from ...domaine.facturation import avancement_facture
        if not self.depot.factures(devis_id=devis.id):
            return "—"
        return f"{nombre(avancement_facture(self.depot, devis))} %"

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
        devis = Devis(
            validite_jours=societe.validite_jours,
            acompte_pct=societe.acompte_defaut_pct,
            conditions=societe.conditions_paiement,
            mentions=societe.mentions_devis,
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


