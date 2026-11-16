"""Écrans de liste : clients, chantiers, matériaux.

Toutes les listes partagent le même socle : une recherche, des filtres propres
à la catégorie, un tableau, et un jeu de boutons qui bascule selon qu'on
regarde les fiches actives ou la corbeille.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHeaderView, QLineEdit, QTableView,
    QVBoxLayout, QWidget,
)

from ...domaine import FAMILLES, TYPES_ARTICLE, date_fr, euros, nombre
from ..depot_fichiers import ErreurReference
from .commun import (
    CENTRE, Colonne, DROITE, DelegueAmorce, ModeleListe, activer_le_tri,
    alerter, amorce, barre, bouton, cle_numero, confirmer, discret,
    liste_deroulante, titre,
)
from .dialogues import DialogueArticle, DialogueChantier, DialogueClient


class VueListe(QWidget):
    """Socle commun : recherche, filtres, tableau, corbeille."""

    donnees_modifiees = Signal()

    nom = "Liste"
    indication_recherche = "Rechercher…"
    mot_element = "élément"
    libelle_nouveau = "Nouveau"
    libelle_modifier = "Modifier"

    def __init__(self, depot, parent=None):
        super().__init__(parent)
        self.depot = depot

        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText(self.indication_recherche)
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self.rafraichir)

        self.corbeille = QCheckBox("Corbeille")
        self.corbeille.setToolTip(
            "Afficher les fiches supprimées, pour les restaurer ou les effacer "
            "définitivement")
        self.corbeille.toggled.connect(self._basculer)

        self.compteur = discret("")
        self.modele = ModeleListe(self.colonnes())

        self.tableau = QTableView()
        self.tableau.setModel(self.modele)
        self.tableau.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableau.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tableau.setAlternatingRowColors(True)
        self.tableau.verticalHeader().setVisible(False)
        self.tableau.horizontalHeader().setStretchLastSection(False)
        self.tableau.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableau.doubleClicked.connect(lambda _: self.modifier())
        self.tableau.verticalHeader().setDefaultSectionSize(26)

        self._trier_par = activer_le_tri(self.tableau, self.modele)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(16, 14, 16, 14)
        disposition.setSpacing(10)
        disposition.addWidget(titre(self.nom))
        disposition.addWidget(self._barre_outils())
        disposition.addWidget(self.tableau, 1)
        disposition.addWidget(self.compteur)

        self._basculer(False)

    # --- à préciser dans les sous-classes --------------------------------

    def colonnes(self) -> list[Colonne]:
        raise NotImplementedError

    def charger(self) -> list:
        raise NotImplementedError

    def filtres(self) -> list:
        """Listes déroulantes propres à la catégorie, après la recherche."""
        return []

    def actions(self) -> list:
        """Boutons supplémentaires, entre « Modifier » et « Supprimer »."""
        return []

    def nouveau(self) -> None:
        raise NotImplementedError

    def modifier(self) -> None:
        raise NotImplementedError

    def archiver(self, element, definitif: bool) -> None:
        raise NotImplementedError

    def desarchiver(self, element) -> None:
        raise NotImplementedError

    def libelle(self, element) -> str:
        raise NotImplementedError

    # --- barre d'outils --------------------------------------------------

    def _barre_outils(self) -> QWidget:
        self.bouton_nouveau = bouton(self.libelle_nouveau, self.nouveau, principal=True)
        self.bouton_modifier = bouton(self.libelle_modifier, self.modifier)
        self.bouton_supprimer = bouton("Supprimer", self.supprimer)
        self.bouton_restaurer = bouton("Restaurer", self.restaurer)
        self.bouton_effacer = bouton("Effacer définitivement", self.effacer)

        self.actions_propres = self.actions()
        self.groupe_actif = ([self.bouton_nouveau, self.bouton_modifier]
                             + self.actions_propres + [self.bouton_supprimer])
        self.groupe_corbeille = [self.bouton_restaurer, self.bouton_effacer]

        return barre(self.recherche, *self.filtres(), self.corbeille, "-",
                     *self.groupe_actif, *self.groupe_corbeille)

    def _basculer(self, dans_la_corbeille: bool) -> None:
        for widget in self.groupe_actif:
            widget.setVisible(not dans_la_corbeille)
        for widget in self.groupe_corbeille:
            widget.setVisible(dans_la_corbeille)
        self.rafraichir()

    @property
    def archives(self) -> bool:
        return self.corbeille.isChecked()

    # --- actions communes ------------------------------------------------

    def selection(self):
        indexes = self.tableau.selectionModel().selectedRows()
        return self.modele.element(indexes[0].row()) if indexes else None

    def supprimer(self) -> None:
        element = self.selection()
        if element is None:
            return
        if not confirmer(self, f"Supprimer {self.mot_element}",
                         f"Déplacer « {self.libelle(element)} » dans la corbeille ?\n\n"
                         "Rien n'est effacé : la fiche sort des listes et reste "
                         "récupérable depuis la corbeille."):
            return
        try:
            self.archiver(element, definitif=False)
        except ErreurReference as erreur:
            alerter(self, "Suppression impossible", str(erreur))
            return
        self._signaler()

    def restaurer(self) -> None:
        element = self.selection()
        if element is None:
            return
        self.desarchiver(element)
        self._signaler()

    def effacer(self) -> None:
        element = self.selection()
        if element is None:
            return
        if not confirmer(self, "Effacer définitivement",
                         f"Effacer « {self.libelle(element)} » pour de bon ?\n\n"
                         "Cette fois la fiche disparaît du logiciel."):
            return
        try:
            self.archiver(element, definitif=True)
        except ErreurReference as erreur:
            alerter(self, "Suppression impossible", str(erreur))
            return
        self._signaler()

    def rafraichir(self) -> None:
        elements = self.charger()
        self.modele.definir(elements)
        quoi = "dans la corbeille" if self.archives else "au total"
        self.compteur.setText(f"{len(elements)} {self.mot_element}(s) {quoi}")
        for index, colonne in enumerate(self.modele.colonnes):
            if colonne.largeur:
                self.tableau.setColumnWidth(index, colonne.largeur)
            else:
                self.tableau.horizontalHeader().setSectionResizeMode(
                    index, QHeaderView.ResizeMode.Stretch)

    def _signaler(self) -> None:
        self.rafraichir()
        self.donnees_modifiees.emit()


class VueClients(VueListe):
    nom = "Clients"
    mot_element = "client"
    libelle_nouveau = "Nouveau client"
    indication_recherche = "Nom, ville, téléphone, courriel…"

    def colonnes(self):
        return [
            Colonne("N°", lambda c: c.numero, largeur=70,
                    cle=lambda c: cle_numero(c.numero)),
            Colonne("Client", lambda c: c.libelle, gras=True),
            Colonne("Ville", lambda c: f"{c.cp} {c.ville}".strip(), largeur=170),
            Colonne("Téléphone", lambda c: c.mobile or c.telephone, largeur=130),
            Colonne("Courriel", lambda c: c.email, largeur=210),
            Colonne("Devis", lambda c: str(len(self.depot.devis(client_id=c.id))),
                    largeur=60, alignement=CENTRE,
                    cle=lambda c: len(self.depot.devis(client_id=c.id))),
        ]

    def charger(self):
        return self.depot.clients(self.recherche.text().strip(),
                                  supprimes=self.archives)

    def libelle(self, client):
        return client.libelle

    def archiver(self, client, definitif):
        self.depot.supprimer_client(client.id, definitif=definitif)

    def desarchiver(self, client):
        self.depot.restaurer_client(client.id)

    def nouveau(self):
        dialogue = DialogueClient(self)
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            self.depot.enregistrer_client(dialogue.resultat())
            self._signaler()

    def modifier(self):
        client = self.selection()
        if client is None:
            return
        dialogue = DialogueClient(self, client)
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            self.depot.enregistrer_client(dialogue.resultat())
            self._signaler()


class VueChantiers(VueListe):
    nom = "Chantiers"
    mot_element = "chantier"
    libelle_nouveau = "Nouveau chantier"
    indication_recherche = "Libellé, ville, client…"

    def colonnes(self):
        return [
            Colonne("Chantier", lambda c: c.libelle, gras=True),
            Colonne("Client", lambda c: self.depot.nom_client(c.client_id), largeur=200),
            Colonne("Ville", lambda c: f"{c.cp} {c.ville}".strip(), largeur=160),
            # La date au format ISO se trie toute seule, dans le bon ordre.
            Colonne("Début", lambda c: date_fr(c.date_debut), largeur=95,
                    alignement=CENTRE, cle=lambda c: c.date_debut or ""),
            Colonne("Statut", lambda c: c.statut, largeur=95, alignement=CENTRE),
            Colonne("Devis", lambda c: str(sum(1 for d in self.depot.devis()
                                               if d.chantier_id == c.id)),
                    largeur=60, alignement=CENTRE,
                    cle=lambda c: sum(1 for d in self.depot.devis()
                                      if d.chantier_id == c.id)),
        ]

    def charger(self):
        return self.depot.chantiers(recherche=self.recherche.text().strip(),
                                    supprimes=self.archives)

    def libelle(self, chantier):
        return chantier.libelle

    def archiver(self, chantier, definitif):
        self.depot.supprimer_chantier(chantier.id, definitif=definitif)

    def desarchiver(self, chantier):
        self.depot.restaurer_chantier(chantier.id)

    def nouveau(self):
        if not self.depot.clients():
            alerter(self, "Aucun client",
                    "Créez d'abord un client : un chantier est toujours rattaché "
                    "à un client.")
            return
        dialogue = DialogueChantier(self, self.depot)
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            self.depot.enregistrer_chantier(dialogue.resultat())
            self._signaler()

    def modifier(self):
        chantier = self.selection()
        if chantier is None:
            return
        dialogue = DialogueChantier(self, self.depot, chantier)
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            self.depot.enregistrer_chantier(dialogue.resultat())
            self._signaler()


class VueCatalogue(VueListe):
    """Les fournitures : ce qui s'achète chez le fournisseur et se revend."""

    nom = "Matériaux"
    mot_element = "article"
    libelle_nouveau = "Nouvel article"
    indication_recherche = "Nom ou référence fournisseur…"
    # Ce que cette liste montre. Ici tout sauf les ouvrages, pour qu'une
    # fiche d'un type inattendu reste visible quelque part plutôt que de
    # disparaître des deux écrans.
    type_cree = "matériau"
    types_filtrables = ["matériau", "main d'œuvre"]
    # Ce sur quoi porte le champ de recherche, et rien d'autre. La famille
    # en est exclue : elle a sa propre liste déroulante juste à côté, et
    # presque toute la bibliothèque porte « Maçonnerie » — taper les trois
    # premières lettres rendait les mille deux cents fiches.
    champs_recherche = ("designation", "reference")

    def retient(self, article) -> bool:
        return article.type != "ouvrage"

    # Les colonnes où la recherche peut mordre, et donc où la surbrillance
    # a quelque chose à montrer : le code et le nom.
    colonnes_cherchees = (0, 1)

    def __init__(self, depot, parent=None):
        self.famille = liste_deroulante(["Toutes les familles"] + FAMILLES)
        self.type = liste_deroulante(["Tous les types"] + self.types_filtrables)
        # Avant le socle : il rafraîchit la liste dès sa construction, et
        # cherche alors déjà la surbrillance.
        self.surbrillance = DelegueAmorce()
        super().__init__(depot, parent)
        self.famille.currentIndexChanged.connect(self.rafraichir)
        self.type.currentIndexChanged.connect(self.rafraichir)
        for colonne in self.colonnes_cherchees:
            self.tableau.setItemDelegateForColumn(colonne, self.surbrillance)

    def filtres(self):
        # Un seul type possible : la liste déroulante n'aurait rien à offrir.
        if len(self.types_filtrables) < 2:
            return [self.famille]
        return [self.famille, self.type]

    def actions(self):
        return [bouton("Dupliquer", self.dupliquer)]

    def colonnes(self):
        return [
            Colonne("Réf. fourn.", lambda a: a.reference, largeur=100),
            Colonne("Nom", lambda a: a.designation, gras=True),
            Colonne("Fournisseur", lambda a: a.fournisseur, largeur=120),
            Colonne("Famille", lambda a: a.famille, largeur=120),
            Colonne("Un.", lambda a: a.unite, largeur=55, alignement=CENTRE),
            Colonne("Achat", lambda a: euros(a.prix_achat), largeur=95,
                    alignement=DROITE, cle=lambda a: a.prix_achat or 0.0),
            Colonne("Vente", lambda a: euros(a.prix_vente), largeur=95,
                    alignement=DROITE, cle=lambda a: a.prix_vente or 0.0),
            Colonne("Bénéfice", lambda a: euros(a.benefice), largeur=95,
                    alignement=DROITE, cle=lambda a: a.benefice),
            # Le tiret des articles sans prix d'achat ne se compare pas à un
            # pourcentage : on les range à part, avant les marges connues.
            Colonne("Marge", lambda a: f"{nombre(a.marge_pct, 1)} %" if a.prix_achat
                    else "—", largeur=70, alignement=DROITE,
                    cle=lambda a: (1, a.marge_pct) if a.prix_achat else (0, 0.0)),
            Colonne("TVA", lambda a: f"{nombre(a.taux_tva)} %", largeur=65,
                    alignement=CENTRE, cle=lambda a: a.taux_tva or 0.0),
        ]

    def charger(self):
        famille = self.famille.currentText()
        type_ = self.type.currentText()
        articles = self.depot.articles(
            famille="" if famille.startswith("Toutes") else famille,
            type_=("" if type_.startswith("Tous") or len(self.types_filtrables) < 2
                   else type_),
            supprimes=self.archives,
        )
        articles = [a for a in articles if self.retient(a)]
        return [a for a in articles if self.correspond(a)]

    def correspond(self, article) -> bool:
        """La recherche du bandeau : le début d'un nom ou d'un code.

        Pas n'importe où dans le texte : quatre mille fiches se consultent
        comme un index, et une liste filtrée doit pouvoir dire pourquoi
        chacune est restée.
        """
        cherche = self.recherche.text().strip()
        if not cherche:
            return True
        return any(amorce(getattr(article, champ, ""), cherche)
                   for champ in self.champs_recherche)

    def libelle(self, article):
        return article.designation

    def archiver(self, article, definitif):
        self.depot.supprimer_article(article.id, definitif=definitif)

    def desarchiver(self, article):
        self.depot.restaurer_article(article.id)

    def rafraichir(self):
        self.surbrillance.chercher(self.recherche.text().strip())
        familles = sorted(set(FAMILLES) | set(self.depot.familles()))
        courante = self.famille.currentText()
        if [self.famille.itemText(i) for i in range(1, self.famille.count())] != familles:
            self.famille.blockSignals(True)
            self.famille.clear()
            self.famille.addItems(["Toutes les familles"] + familles)
            self.famille.setCurrentIndex(max(0, self.famille.findText(courante)))
            self.famille.blockSignals(False)
        super().rafraichir()

    def nouveau(self):
        from ...domaine import Article
        neuf = Article(type=self.type_cree,
                       taux_tva=self.depot.societe.taux_tva_defaut)
        dialogue = DialogueArticle(self, self.depot, neuf)
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            self.depot.enregistrer_article(dialogue.resultat())
            self._signaler()

    def modifier(self):
        article = self.selection()
        if article is None:
            return
        dialogue = DialogueArticle(self, self.depot, article)
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            self.depot.enregistrer_article(dialogue.resultat())
            self._signaler()

    def dupliquer(self):
        from ...domaine import Article, depuis_dict, en_dict, nouvel_id
        article = self.selection()
        if article is None:
            return
        copie = depuis_dict(Article, en_dict(article))
        copie.id = nouvel_id()
        copie.designation += " (copie)"
        dialogue = DialogueArticle(self, self.depot, copie)
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            self.depot.enregistrer_article(dialogue.resultat())
            self._signaler()


class VueOuvrages(VueCatalogue):
    """Les ouvrages : une prestation posée, prix de vente tout compris.

    Même bibliothèque que les matériaux, même fiche, mais deux écrans :
    chercher un sac de ciment et chercher un prix de carrelage posé ne sont
    pas le même geste, et mêler les deux fait mille cinq cents lignes.
    """

    nom = "Ouvrages"
    mot_element = "ouvrage"
    libelle_nouveau = "Nouvel ouvrage"
    indication_recherche = "Nom ou code de l'ouvrage…"
    type_cree = "ouvrage"
    types_filtrables = ["ouvrage"]

    def retient(self, article) -> bool:
        return article.type == "ouvrage"

    def colonnes(self):
        # Un ouvrage ne s'achète chez personne : la colonne du fournisseur
        # resterait vide, et sa référence est le code que lui donnait
        # l'ancien logiciel, pas une référence de catalogue.
        gardees = [c for c in super().colonnes() if c.titre != "Fournisseur"]
        gardees[0].titre = "Code"
        return gardees
