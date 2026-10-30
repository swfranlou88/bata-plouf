"""Fiches de saisie : client, chantier, article de la bibliothèque de prix."""

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QVBoxLayout, QWidget,
)

from ...domaine import (
    Article, Chantier, Client, FAMILLES, STATUTS_CHANTIER, TAUX_TVA,
    TYPES_ARTICLE, UNITES, euros,
)
from .commun import (
    bouton, champ_date, champ_euros, champ_texte, liste_deroulante,
    valeur_date,
)


class DialogueBase(QDialog):
    def __init__(self, parent, titre_: str):
        super().__init__(parent)
        self.setWindowTitle(titre_)
        self.setMinimumWidth(520)
        self.formulaire = QFormLayout()
        self.formulaire.setLabelAlignment(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AlignmentFlag.AlignRight
        )
        self.boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.boutons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        self.boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        self.boutons.accepted.connect(self.accept)
        self.boutons.rejected.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.addLayout(self.formulaire)
        disposition.addWidget(self.boutons)

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

        self.client = liste_deroulante([], None)
        for cl in depot.clients():
            self.client.addItem(cl.libelle, cl.id)
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
        self.ajouter("Libellé", self.detail)
        self.type = self.ajouter("Type", liste_deroulante(TYPES_ARTICLE, a.type))
        familles = sorted(set(FAMILLES) | set(depot.familles()))
        self.famille = liste_deroulante(familles, a.famille)
        self.famille.setEditable(True)
        self.ajouter("Famille", self.famille)
        self.unite = self.ajouter("Unité", liste_deroulante(UNITES, a.unite))
        self.prix_achat = champ_euros(a.prix_achat)
        self.prix_vente = champ_euros(a.prix_vente)
        self.ajouter_paire("Prix d'achat / de vente", self.prix_achat, self.prix_vente)
        self.marge = QLabel()
        self.ajouter("Bénéfice", self.marge)
        self.tva = self.ajouter("TVA", liste_deroulante(TAUX_TVA, a.taux_tva))

        self.prix_achat.valueChanged.connect(self._marge)
        self.prix_vente.valueChanged.connect(self._marge)
        self._marge()

    def _marge(self) -> None:
        achat = self.prix_achat.value()
        vente = self.prix_vente.value()
        benefice = euros(vente - achat)
        if not achat:
            self.marge.setText(f"{benefice} par unité")
            return
        self.marge.setText(
            f"{benefice} par unité, soit {round((vente - achat) / achat * 100, 1)} % "
            "de marge")

    def resultat(self) -> Article:
        a = self.article
        a.reference = self.reference.text().strip()
        a.designation = self.designation.text().strip()
        a.detail = self.detail.toPlainText().strip()
        a.type = self.type.currentText()
        a.fournisseur = self.fournisseur.text().strip()
        a.famille = self.famille.currentText().strip()
        a.unite = self.unite.currentText()
        a.prix_achat = self.prix_achat.value()
        a.prix_vente = self.prix_vente.value()
        a.taux_tva = float(self.tva.currentData())
        return a
