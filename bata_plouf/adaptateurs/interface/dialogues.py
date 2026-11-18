"""Fiches de saisie : client, chantier, article de la bibliothèque de prix."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QTableView, QVBoxLayout, QWidget,
)

from ...domaine import (
    Article, Chantier, Client, Composant, STATUTS_CHANTIER,
    TAUX_TVA, TYPES_ARTICLE, UNITES, euros, nombre,
)
from ...domaine.chantier import est_du_temps
from ..impression.styles import echapper
from .commun import (
    CENTRE, DROITE, GAUCHE, barre, bouton, champ_date, champ_euros,
    champ_texte, confirmer, discret, etiquette_client, infobulles_si_tronque,
    liste_deroulante, rendre_cherchable, teinte_modifiee, valeur_date,
)

# La marge de la maison, appliquée au prix d'achat pour proposer le prix de
# vente. Vingt-cinq pour cent du prix d'achat, comme l'affiche la fiche.
MARGE_PAR_DEFAUT = 0.25


class ModeleComposants(QAbstractTableModel):
    """La composition d'un ouvrage, quantités modifiables.

    Seule la quantité se tape : le nom et l'unité viennent de la fiche du
    article, et les retoucher ici ferait diverger deux écritures du même
    article.
    """

    EN_TETES = ["Pour une unité", "Quantité", "Un."]

    def __init__(self, lignes=None):
        super().__init__()
        self.lignes: list = list(lignes or [])

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.lignes)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (orientation == Qt.Orientation.Horizontal
                and role == Qt.ItemDataRole.DisplayRole):
            return self.EN_TETES[section]
        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 1:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        composant = self.lignes[index.row()]
        if role == Qt.ItemDataRole.EditRole and index.column() == 1:
            return composant.quantite
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return composant.designation
            if index.column() == 1:
                return nombre(composant.quantite, 3)
            return composant.unite
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() == 1:
                return DROITE
            return CENTRE if index.column() == 2 else GAUCHE
        return None

    def setData(self, index, valeur, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != 1:
            return False
        try:
            self.lignes[index.row()].quantite = round(float(valeur), 4)
        except (TypeError, ValueError):
            return False
        self.dataChanged.emit(index, index)
        return True

    def ajouter(self, composant) -> None:
        rang = len(self.lignes)
        self.beginInsertRows(QModelIndex(), rang, rang)
        self.lignes.append(composant)
        self.endInsertRows()

    def retirer(self, rangs) -> None:
        if not rangs:
            return
        self.beginResetModel()
        self.lignes = [c for rang, c in enumerate(self.lignes)
                       if rang not in set(rangs)]
        self.endResetModel()


class DialogueBase(QDialog):
    """Socle des fiches : le formulaire, les boutons, et la sortie surveillée.

    Deux règles pour une fiche qu'on remplit au clavier :

      — **Entrée ne valide pas.** On tape un prix, on fait Entrée pour
        confirmer le champ, et la fenêtre se fermait : c'est la touche la
        plus naturelle qui faisait le geste le plus brutal. Aucun bouton
        n'est donc « par défaut ».
      — **Sortir sans enregistrer se demande.** Fermer une fiche modifiée
        par Annuler, par Échap ou par la croix fait apparaître ce qui serait
        perdu, et laisse le choix entre enregistrer, abandonner, ou revenir.
    """

    def __init__(self, parent, titre_: str):
        super().__init__(parent)
        self.setWindowTitle(titre_)
        self.setMinimumWidth(520)
        self.formulaire = QFormLayout()
        self.formulaire.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        enregistrer = self.boutons.button(QDialogButtonBox.StandardButton.Save)
        enregistrer.setText("Enregistrer")
        annuler = self.boutons.button(QDialogButtonBox.StandardButton.Cancel)
        annuler.setText("Annuler")
        # Sans bouton par défaut, Entrée dans un champ ne ferme plus la fiche.
        for bouton_ in (enregistrer, annuler):
            bouton_.setAutoDefault(False)
            bouton_.setDefault(False)
        self.boutons.accepted.connect(self.accept)
        self.boutons.rejected.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.addLayout(self.formulaire)
        disposition.addWidget(self.boutons)
        self._depart: dict | None = None

    def ajouter(self, etiquette: str, widget):
        self.formulaire.addRow(etiquette, widget)
        return widget

    def ajouter_paire(self, etiquette: str, gauche, droite):
        boite = QWidget()
        ligne = QHBoxLayout(boite)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.addWidget(gauche)
        ligne.addWidget(droite, 1)
        self.formulaire.addRow(etiquette, boite)

    # --- ce que la fiche montre, et ce qui y a changé --------------------

    def _valeur(self, widget) -> str:
        """Ce qu'affiche un champ, quel qu'il soit, en une chaîne."""
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText().strip()
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        if isinstance(widget, QAbstractSpinBox):
            return widget.text().strip()
        if isinstance(widget, QCheckBox):
            return "oui" if widget.isChecked() else "non"
        if isinstance(widget, QTableView) and widget.model() is not None:
            modele = widget.model()
            return " · ".join(
                str(modele.index(rang, colonne).data() or "")
                for rang in range(modele.rowCount())
                for colonne in range(modele.columnCount()))
        if isinstance(widget, QWidget) and not isinstance(widget, QLabel):
            # Les paires et les cadres : on lit ce qu'ils contiennent, mais
            # sans descendre dans les champs eux-mêmes — la ligne de saisie
            # d'un compteur appartient au compteur, et le lire deux fois
            # donnerait « 40,00 / 40,00 ».
            dedans = [self._valeur(enfant)
                      for enfant in widget.findChildren(
                          QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
                      if isinstance(enfant, (QLineEdit, QComboBox, QCheckBox,
                                             QPlainTextEdit, QAbstractSpinBox,
                                             QTableView))]
            return " / ".join(v for v in dedans if v)
        return ""

    def champs(self) -> dict:
        """Les champs de la fiche, par leur intitulé, tels qu'ils sont là.

        On lit les widgets, pas l'entité : calculer l'état courant en
        appelant resultat() écrirait dans la fiche du dépôt, et ce serait
        précisément ce qu'on cherche à éviter quand on sort sans enregistrer.
        """
        lus = {}
        for rang in range(self.formulaire.rowCount()):
            intitule = self.formulaire.itemAt(rang, QFormLayout.ItemRole.LabelRole)
            champ = self.formulaire.itemAt(rang, QFormLayout.ItemRole.FieldRole)
            if champ is None or champ.widget() is None:
                continue
            nom = ""
            if intitule is not None and isinstance(intitule.widget(), QLabel):
                nom = intitule.widget().text().strip()
            valeur = self._valeur(champ.widget())
            if nom:
                lus[nom] = valeur
        return lus

    def retenir_depart(self) -> None:
        """À appeler une fois la fiche remplie : l'état à comparer plus tard."""
        self._depart = self.champs()
        self._veiller()

    # --- marquer ce qui a changé -----------------------------------------

    def _veiller(self) -> None:
        """Écoute tout ce qui peut changer dans le formulaire."""
        for rang in range(self.formulaire.rowCount()):
            champ = self.formulaire.itemAt(rang, QFormLayout.ItemRole.FieldRole)
            if champ is not None and champ.widget() is not None:
                self._ecouter(champ.widget())

    def _ecouter(self, widget) -> None:
        # Chaque sorte de champ annonce ses changements à sa façon : on
        # branche ce qui existe plutôt que de tenir une liste par type.
        for nom in ("textChanged", "currentTextChanged", "valueChanged",
                    "toggled"):
            signal = getattr(widget, nom, None)
            if signal is not None and hasattr(signal, "connect"):
                signal.connect(lambda *_: self._marquer())
        modele = getattr(widget, "model", None)
        modele = modele() if callable(modele) else None
        if modele is not None:
            for nom in ("dataChanged", "modelReset", "rowsInserted",
                        "rowsRemoved"):
                signal = getattr(modele, nom, None)
                if signal is not None:
                    signal.connect(lambda *_: self._marquer())
        if isinstance(widget, QWidget) and not isinstance(widget, QLabel):
            for enfant in widget.findChildren(
                    QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if not isinstance(enfant, QLabel):
                    self._ecouter(enfant)

    def _marquer(self) -> None:
        """Met en orange l'intitulé des champs qui ne sont plus d'origine."""
        if self._depart is None:
            return
        maintenant = self.champs()
        teinte = teinte_modifiee()
        for rang in range(self.formulaire.rowCount()):
            intitule = self.formulaire.itemAt(rang, QFormLayout.ItemRole.LabelRole)
            if intitule is None or not isinstance(intitule.widget(), QLabel):
                continue
            etiquette = intitule.widget()
            nom = etiquette.text().strip()
            if not nom:
                continue
            change = maintenant.get(nom, "") != self._depart.get(nom, "")
            etiquette.setStyleSheet(
                f"color: {teinte}; font-weight: bold;" if change else "")

    def showEvent(self, evenement) -> None:
        # Au premier affichage, et pas dans le constructeur : chaque fiche
        # ajoute ses champs à sa façon, et aucune n'aurait à penser à le
        # dire. À l'écran, tout est en place.
        super().showEvent(evenement)
        # Qt réattribue un bouton « par défaut » à l'affichage : on le lui
        # retire après coup, sinon Entrée refermerait la fiche malgré tout.
        for bouton_ in self.boutons.buttons():
            bouton_.setAutoDefault(False)
            bouton_.setDefault(False)
        if self._depart is None:
            self.retenir_depart()

    def differences(self) -> list[tuple[str, str, str]]:
        if self._depart is None:
            return []
        maintenant = self.champs()
        return [(nom, self._depart.get(nom, ""), valeur)
                for nom, valeur in maintenant.items()
                if valeur != self._depart.get(nom, "")]

    # --- sortie surveillée ------------------------------------------------

    def _decider_sortie(self) -> str:
        """« enregistrer », « quitter » ou « rester », selon ce qu'on répond."""
        ecarts = self.differences()
        if not ecarts:
            return "quitter"

        def court(valeur: str) -> str:
            # Une désignation d'ouvrage fait cent caractères : on en montre
            # assez pour reconnaître ce qui change, pas la ligne entière.
            valeur = valeur or "(vide)"
            return valeur if len(valeur) <= 58 else valeur[:55] + "…"

        # Une ligne vide entre chaque écart : collés, ils se lisent comme un
        # paragraphe, et l'œil ne retrouve plus où commence le suivant.
        lignes = "".join(
            f"<tr><td style='padding-right:10px; padding-bottom:9px;'>"
            f"<b>{echapper(nom)}</b></td>"
            f"<td style='padding-bottom:9px;'>{echapper(court(avant))} &rarr; "
            f"<b>{echapper(court(apres))}</b></td></tr>"
            for nom, avant, apres in ecarts[:10])
        reste = ("" if len(ecarts) <= 10 else
                 f"<p>… et {len(ecarts) - 10} autre(s).</p>")

        boite = QMessageBox(self)
        boite.setWindowTitle("Modifications non enregistrées")
        boite.setIcon(QMessageBox.Icon.Warning)
        boite.setTextFormat(Qt.TextFormat.RichText)
        boite.setText("Les éléments suivants ont été modifiés :")
        boite.setInformativeText(f"<table cellspacing='0'>{lignes}</table>{reste}")
        garder = boite.addButton("Enregistrer et quitter",
                                 QMessageBox.ButtonRole.AcceptRole)
        jeter = boite.addButton("Quitter sans enregistrer",
                                QMessageBox.ButtonRole.DestructiveRole)
        rester = boite.addButton("Rester sur la fiche",
                                 QMessageBox.ButtonRole.RejectRole)
        # Revenir à la fiche est le choix le moins coûteux : c'est lui qu'on
        # propose par défaut, et celui qu'Échap déclenche.
        boite.setDefaultButton(rester)
        boite.setEscapeButton(rester)
        boite.exec()
        clique = boite.clickedButton()
        if clique is garder:
            return "enregistrer"
        if clique is jeter:
            return "quitter"
        return "rester"

    def reject(self) -> None:
        choix = self._decider_sortie()
        if choix == "rester":
            return
        if choix == "enregistrer":
            self.accept()
            return
        super().reject()

    def closeEvent(self, evenement) -> None:
        choix = self._decider_sortie()
        if choix == "rester":
            evenement.ignore()
            return
        if choix == "enregistrer":
            evenement.accept()
            self.accept()
            return
        evenement.accept()
        super().closeEvent(evenement)


class DialogueClient(DialogueBase):
    def __init__(self, parent, client: Client | None = None):
        super().__init__(parent, "Fiche client")
        self.client = client or Client()
        c = self.client

        self.numero = QLabel(c.numero or "attribué à l'enregistrement")
        self.ajouter("Numéro client", self.numero)
        self.type = self.ajouter("Type", liste_deroulante(["particulier", "professionnel"], c.type))
        self.societe = self.ajouter("Raison sociale", champ_texte(c.societe))
        self.siret = self.ajouter("SIRET", champ_texte(c.siret, "14 chiffres"))
        self.civilite = liste_deroulante(["", "M.", "Mme", "M. et Mme", "Société"], c.civilite)
        self.civilite.setEditable(True)
        self.civilite.setMaximumWidth(120)
        self.nom = champ_texte(c.nom)
        self.ajouter_paire("Nom", self.civilite, self.nom)
        self.prenom = self.ajouter("Prénom", champ_texte(c.prenom))
        self.adresse = self.ajouter("Adresse", champ_texte(c.adresse))
        self.cp = champ_texte(c.cp, "81000")
        self.cp.setMaximumWidth(120)
        self.ville = champ_texte(c.ville)
        self.ajouter_paire("Code postal / Ville", self.cp, self.ville)
        self.telephone = self.ajouter("Téléphone 1", champ_texte(c.telephone, "fixe"))
        self.mobile = self.ajouter("Téléphone 2", champ_texte(c.mobile, "mobile"))
        self.email = self.ajouter("Courriel", champ_texte(c.email))
        self.notes = QPlainTextEdit(c.notes)
        self.notes.setMaximumHeight(90)
        self.ajouter("Description", self.notes)

        self.type.currentTextChanged.connect(self._basculer)
        self._basculer(self.type.currentText())

    def _basculer(self, type_: str) -> None:
        pro = type_ == "professionnel"
        for widget in (self.societe, self.siret):
            widget.setVisible(pro)
            etiquette = self.formulaire.labelForField(widget)
            if etiquette:
                etiquette.setVisible(pro)

    def resultat(self) -> Client:
        c = self.client
        c.type = self.type.currentText()
        c.societe = self.societe.text().strip()
        c.siret = self.siret.text().strip()
        c.civilite = self.civilite.currentText().strip()
        c.nom = self.nom.text().strip()
        c.prenom = self.prenom.text().strip()
        c.adresse = self.adresse.text().strip()
        c.cp = self.cp.text().strip()
        c.ville = self.ville.text().strip()
        c.telephone = self.telephone.text().strip()
        c.mobile = self.mobile.text().strip()
        c.email = self.email.text().strip()
        c.notes = self.notes.toPlainText().strip()
        return c


class DialogueChantier(DialogueBase):
    def __init__(self, parent, depot, chantier: Chantier | None = None, client_id: str = ""):
        super().__init__(parent, "Fiche chantier")
        self.depot = depot
        self.chantier = chantier or Chantier(client_id=client_id)
        ch = self.chantier

        self.client = rendre_cherchable(liste_deroulante([], None),
                                        "Nom, société ou ville…")
        for cl in depot.clients():
            self.client.addItem(etiquette_client(cl), cl.id)
        index = self.client.findData(ch.client_id)
        if index >= 0:
            self.client.setCurrentIndex(index)
        self.ajouter("Client", self.client)

        self.libelle = self.ajouter("Libellé", champ_texte(ch.libelle, "Extension garage"))
        self.adresse = champ_texte(ch.adresse)
        self.ajouter_paire("Adresse", bouton("Reprendre celle du client", self._copier_adresse),
                           self.adresse)
        self.cp = champ_texte(ch.cp)
        self.cp.setMaximumWidth(120)
        self.ville = champ_texte(ch.ville)
        self.ajouter_paire("Code postal / Ville", self.cp, self.ville)
        self.debut = self.ajouter("Début", champ_date(ch.date_debut, optionnel=True))
        self.fin = self.ajouter("Fin", champ_date(ch.date_fin, optionnel=True))
        self.statut = self.ajouter("Statut", liste_deroulante(STATUTS_CHANTIER, ch.statut))
        self.notes = QPlainTextEdit(ch.notes)
        self.notes.setMaximumHeight(90)
        self.ajouter("Notes", self.notes)

    def _copier_adresse(self) -> None:
        client = self.depot.client(self.client.currentData())
        if client:
            self.adresse.setText(client.adresse)
            self.cp.setText(client.cp)
            self.ville.setText(client.ville)

    def resultat(self) -> Chantier:
        ch = self.chantier
        ch.client_id = self.client.currentData() or ""
        ch.libelle = self.libelle.text().strip()
        ch.adresse = self.adresse.text().strip()
        ch.cp = self.cp.text().strip()
        ch.ville = self.ville.text().strip()
        ch.date_debut = valeur_date(self.debut)
        ch.date_fin = valeur_date(self.fin)
        ch.statut = self.statut.currentText()
        ch.notes = self.notes.toPlainText().strip()
        return ch


class DialogueArticle(DialogueBase):
    def __init__(self, parent, depot, article: Article | None = None):
        super().__init__(parent, "Fiche article")
        self.depot = depot
        self.article = article or Article(taux_tva=depot.societe.taux_tva_defaut)
        a = self.article

        self.reference = self.ajouter("Référence fournisseur",
                                      champ_texte(a.reference, "PAR20"))
        self.fournisseur = self.ajouter("Fournisseur",
                                        champ_texte(a.fournisseur, "Point P, Gedimat…"))
        self.designation = self.ajouter("Nom", champ_texte(a.designation))
        self.detail = QPlainTextEdit(a.detail)
        self.detail.setMaximumHeight(70)
        self.detail.setPlaceholderText(
            "Précision imprimée sous la désignation, sur le devis du client")
        self.ajouter("Détail imprimé", self.detail)
        self.type = self.ajouter("Type", liste_deroulante(TYPES_ARTICLE, a.type))
        self.unite = self.ajouter("Unité", liste_deroulante(UNITES, a.unite))
        self.prix_achat = champ_euros(a.prix_achat)
        self.prix_vente = champ_euros(a.prix_vente)
        # Sans le « € » collé au nombre : on saisit des prix à la chaîne, et
        # le symbole se met en travers du curseur. L'intitulé le porte.
        for champ in (self.prix_achat, self.prix_vente):
            champ.setSuffix("")
        self.ajouter_paire("Prix d'achat / de vente (€)",
                           self.prix_achat, self.prix_vente)
        self.marge = QLabel()
        self.ajouter("Bénéfice", self.marge)
        self.tva = self.ajouter("TVA", liste_deroulante(TAUX_TVA, a.taux_tva))
        self.notes = QPlainTextEdit(a.notes_internes)
        self.notes.setMaximumHeight(70)
        self.notes.setPlaceholderText(
            "Temps de main d'œuvre, consommations, dates de tarif — "
            "jamais imprimé")
        self.ajouter("Notes internes", self.notes)

        if a.type == "ouvrage" or a.composants:
            self.ajouter("Composition", self._composition(a))

        self.prix_achat.valueChanged.connect(self._suivre_achat)
        self.prix_achat.valueChanged.connect(self._marge)
        self.prix_vente.valueChanged.connect(self._marge)
        self._marge()

    def _composition(self, article):
        """Ce dont l'ouvrage est fait, par unité : matière et heures.

        C'est la table qui bâtit le prix de vente et qui fait, sur un
        chantier, la liste de ce qu'il faut emmener. Elle se modifie ici :
        une quantité se tape dans la colonne, un article s'ajoute depuis la
        bibliothèque.
        """
        cadre = QWidget()
        dedans = QVBoxLayout(cadre)
        dedans.setContentsMargins(0, 0, 0, 0)
        dedans.setSpacing(4)

        self.composants = ModeleComposants(list(article.composants))
        self.table_composants = QTableView()
        self.table_composants.setModel(self.composants)
        self.table_composants.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows)
        self.table_composants.verticalHeader().setVisible(False)
        self.table_composants.verticalHeader().setDefaultSectionSize(22)
        self.table_composants.setAlternatingRowColors(True)
        self.table_composants.setMinimumHeight(120)
        self.table_composants.setMaximumHeight(170)
        entetes = self.table_composants.horizontalHeader()
        entetes.setStretchLastSection(False)
        for rang, largeur in ((0, None), (1, 85), (2, 50)):
            if largeur:
                entetes.setSectionResizeMode(rang, QHeaderView.ResizeMode.Fixed)
                self.table_composants.setColumnWidth(rang, largeur)
            else:
                entetes.setSectionResizeMode(rang, QHeaderView.ResizeMode.Stretch)
        infobulles_si_tronque(self.table_composants)
        dedans.addWidget(self.table_composants)

        self.resume_composition = discret("")
        dedans.addWidget(barre(
            bouton("Ajouter…", self._ajouter_composant),
            bouton("Retirer", self._retirer_composant, danger=True),
            "-", self.resume_composition))
        self.composants.dataChanged.connect(lambda *_: self._resumer())
        self.composants.modelReset.connect(self._resumer)
        self._resumer()
        # Sans ce ressort, le formulaire étire la composition sur toute la
        # hauteur restante et le résumé se retrouve loin du tableau.
        dedans.addStretch(1)
        return cadre

    def _ajouter_composant(self) -> None:
        """Prendre dans la bibliothèque de quoi composer l'ouvrage."""
        # Importé ici : l'écran des devis connaît déjà cette fiche, et le
        # chemin inverse ferait un cercle.
        from .devis import DialogueChoixArticle

        dialogue = DialogueChoixArticle(self, self.depot, "Articles")
        if dialogue.exec() != QDialog.DialogCode.Accepted:
            return
        for article in dialogue.articles():
            if article.id == self.article.id:
                continue  # un ouvrage ne se compose pas de lui-même
            self.composants.ajouter(Composant(
                article_id=article.id, quantite=1.0,
                designation=article.designation, unite=article.unite))
        self._resumer()

    def _retirer_composant(self) -> None:
        rangs = {i.row() for i in
                 self.table_composants.selectionModel().selectedRows()}
        if not rangs:
            return
        noms = [(self.composants.lignes[r].designation or "").strip()
                for r in sorted(rangs) if r < len(self.composants.lignes)]
        quoi = (f"« {noms[0]} »" if len(noms) == 1
                else "\n\n" + "\n".join(f"• {n}" for n in noms[:6]))
        if not confirmer(self, "Retirer de la composition",
                         f"Retirer {quoi} de la composition de cet ouvrage ?"
                         "\n\nL'article reste au catalogue ; seul son emploi "
                         "dans cet ouvrage disparaît."):
            return
        self.composants.retirer(rangs)
        self._resumer()

    def _resumer(self) -> None:
        """Ce que la composition dit du prix, à côté de ce qui est saisi."""
        heures = sum(c.quantite for c in self.composants.lignes
                     if est_du_temps(c.unite))
        matiere = sum(1 for c in self.composants.lignes
                      if not est_du_temps(c.unite))
        total = 0.0
        for composant in self.composants.lignes:
            fiche = self.depot.article(composant.article_id)
            if fiche is not None:
                total += (composant.quantite or 0.0) * (fiche.prix_vente or 0.0)
        unite = self.unite.currentText() or "unité"
        # Court : la fiche n'est pas large, et ce résumé se lit d'un coup
        # d'œil pour comparer au prix de vente saisi juste au-dessus.
        self.resume_composition.setText(
            f"{nombre(heures, 3)} h · {matiere} articles · "
            f"{euros(total)} / {unite}")

    def _suivre_achat(self, achat: float) -> None:
        """Le prix de vente suit l'achat, à la marge de la maison.

        Un prix d'achat qu'on corrige, c'est un tarif fournisseur qui a bougé :
        sans cela la marge fondrait sans qu'on le voie, fiche après fiche. Le
        prix de vente reste modifiable ensuite — une affaire se négocie.
        """
        self.prix_vente.setValue(round(achat * (1 + MARGE_PAR_DEFAUT), 2))

    def _marge(self) -> None:
        achat = self.prix_achat.value()
        vente = self.prix_vente.value()
        benefice = euros(vente - achat)
        if not achat:
            self.marge.setText(f"{benefice} par unité")
            return
        self.marge.setText(
            f"{benefice} par unité, soit "
            f"{nombre((vente - achat) / achat * 100, 1)} % de marge")

    def resultat(self) -> Article:
        a = self.article
        a.reference = self.reference.text().strip()
        a.designation = self.designation.text().strip()
        a.detail = self.detail.toPlainText().strip()
        a.notes_internes = self.notes.toPlainText().strip()
        a.type = self.type.currentText()
        a.fournisseur = self.fournisseur.text().strip()
        a.unite = self.unite.currentText()
        a.prix_achat = self.prix_achat.value()
        a.prix_vente = self.prix_vente.value()
        a.taux_tva = float(self.tva.currentData())
        if hasattr(self, "composants"):
            a.composants = list(self.composants.lignes)
        return a
