"""Écran d'accueil : les six catégories, et l'essentiel en un coup d'œil."""

from PySide6.QtCore import QDate, QLocale, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ...domaine import euros
from .commun import barre, bouton, discret

# L'ordre voulu par l'utilisateur, et le seul endroit où il est décidé.
RUBRIQUES_ACCUEIL = [
    ("clients", "Clients", "Particuliers et professionnels"),
    ("devis", "Devis", "Chiffrage et propositions"),
    ("catalogue", "Articles", "Fournitures et prix d'achat"),
    ("ouvrages", "Ouvrages", "Ouvrages posés, prix de vente"),
    ("factures", "Factures", "Acomptes, situations, soldes"),
    ("chantiers", "Chantiers", "Heures et fournitures à prévoir"),
]

STYLE_CARTE = """
QPushButton {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 10px;
    text-align: left;
    padding: 0px;
}
QPushButton:hover   { background: palette(alternate-base);
                      border: 1px solid palette(highlight); }
QPushButton:pressed { background: palette(midlight); }
"""


class Carte(QPushButton):
    """Une catégorie : son nom, ce qu'elle contient, et combien de fiches."""

    def __init__(self, cle: str, intitule: str, description: str, parent=None):
        super().__init__(parent)
        self.cle = cle
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(240, 118)
        self.setMaximumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet(STYLE_CARTE)

        self.nombre = QLabel("—")
        police = self.nombre.font()
        police.setPointSize(30)
        police.setBold(True)
        self.nombre.setFont(police)

        etiquette = QLabel(intitule)
        police_titre = etiquette.font()
        police_titre.setPointSize(14)
        police_titre.setBold(True)
        etiquette.setFont(police_titre)

        self.detail = discret(description)
        self.detail.setWordWrap(True)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(18, 14, 18, 14)
        disposition.setSpacing(2)
        disposition.addWidget(self.nombre)
        disposition.addWidget(etiquette)
        disposition.addWidget(self.detail)
        disposition.addStretch(1)

    def definir(self, nombre: int, detail: str = "") -> None:
        self.nombre.setText(str(nombre))
        if detail:
            self.detail.setText(detail)


class Chiffre(QFrame):
    """Un indicateur du bandeau du haut."""

    def __init__(self, intitule: str, parent=None):
        super().__init__(parent)
        self.valeur = QLabel("—")
        police = self.valeur.font()
        police.setPointSize(15)
        police.setBold(True)
        self.valeur.setFont(police)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 24, 0)
        disposition.setSpacing(0)
        disposition.addWidget(self.valeur)
        disposition.addWidget(discret(intitule))

    def definir(self, texte: str) -> None:
        self.valeur.setText(texte)


class VueAccueil(QWidget):
    ouvrir_rubrique = Signal(str)
    mise_a_jour_demandee = Signal()
    nouveau_devis = Signal()
    nouveau_client = Signal()
    nouvelle_facture = Signal()

    nom = "Accueil"

    def __init__(self, depot, parent=None):
        super().__init__(parent)
        self.depot = depot
        self.cartes: dict[str, Carte] = {}

        self.societe = QLabel()
        police = self.societe.font()
        police.setPointSize(21)
        police.setBold(True)
        self.societe.setFont(police)
        self.jour = discret("")

        self.chiffre_attente = Chiffre("en attente de réponse")
        self.chiffre_facture = Chiffre("facturé cette année")
        self.chiffre_impaye = Chiffre("restant à encaisser")
        self.chiffre_retard = Chiffre("en retard de paiement")

        self.bandeau_maj = QWidget()
        self.libelle_maj = QLabel()
        ligne_maj = QHBoxLayout(self.bandeau_maj)
        ligne_maj.setContentsMargins(10, 8, 10, 8)
        ligne_maj.addWidget(self.libelle_maj)
        ligne_maj.addStretch(1)
        ligne_maj.addWidget(bouton("Mettre à jour", self.mise_a_jour_demandee.emit,
                                   principal=True))
        self.bandeau_maj.setStyleSheet(
            "background: palette(highlight); border-radius: 6px;")
        self.libelle_maj.setStyleSheet("color: palette(highlighted-text);")
        self.bandeau_maj.setVisible(False)

        self.avertissement = QLabel()
        self.avertissement.setWordWrap(True)
        self.avertissement.setStyleSheet(
            "background: palette(alternate-base); padding: 10px; border-radius: 6px;")
        self.avertissement.setVisible(False)

        self._construire()
        self.rafraichir()

    def _construire(self) -> None:
        entete = QWidget()
        ligne_entete = QHBoxLayout(entete)
        ligne_entete.setContentsMargins(0, 0, 0, 0)
        titres = QVBoxLayout()
        titres.setSpacing(0)
        titres.addWidget(self.societe)
        titres.addWidget(self.jour)
        boite_titres = QWidget()
        boite_titres.setLayout(titres)
        ligne_entete.addWidget(boite_titres)
        ligne_entete.addStretch(1)

        bandeau = QFrame()
        bandeau.setFrameShape(QFrame.Shape.StyledPanel)
        ligne_chiffres = QHBoxLayout(bandeau)
        ligne_chiffres.setContentsMargins(18, 12, 18, 12)
        for chiffre in (self.chiffre_attente, self.chiffre_facture,
                        self.chiffre_impaye, self.chiffre_retard):
            ligne_chiffres.addWidget(chiffre)
        ligne_chiffres.addStretch(1)

        grille = QGridLayout()
        grille.setSpacing(14)
        for index, (cle, intitule, description) in enumerate(RUBRIQUES_ACCUEIL):
            carte = Carte(cle, intitule, description)
            carte.clicked.connect(lambda _=False, c=cle: self.ouvrir_rubrique.emit(c))
            self.cartes[cle] = carte
            grille.addWidget(carte, index // 3, index % 3)
        # Les raccourcis prennent la case libre qui suit les catégories,
        # plutôt que de laisser un trou au bout de la dernière rangée.
        raccourcis = QFrame()
        raccourcis.setMaximumHeight(150)
        raccourcis.setFrameShape(QFrame.Shape.StyledPanel)
        colonne = QVBoxLayout(raccourcis)
        colonne.setContentsMargins(18, 14, 18, 14)
        colonne.setSpacing(8)
        colonne.addWidget(discret("Raccourcis"))
        boutons = [
            bouton("Nouveau devis", self.nouveau_devis.emit, principal=True),
            bouton("Nouveau client", self.nouveau_client.emit),
            bouton("Nouvelle facture", self.nouvelle_facture.emit),
        ]
        apres = len(RUBRIQUES_ACCUEIL)
        largeur = 3 - apres % 3
        if largeur > 1:
            # Le bloc finit la rangée : les boutons s'y rangent côte à côte
            # plutôt que de laisser une grande case aux trois quarts vide.
            rangee = QHBoxLayout()
            for b in boutons:
                rangee.addWidget(b)
            rangee.addStretch(1)
            colonne.addLayout(rangee)
        else:
            for b in boutons:
                colonne.addWidget(b)
        colonne.addStretch(1)
        grille.addWidget(raccourcis, apres // 3, apres % 3, 1, largeur)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(22, 18, 22, 18)
        disposition.setSpacing(16)
        disposition.addWidget(entete)
        disposition.addWidget(self.bandeau_maj)
        disposition.addWidget(self.avertissement)
        disposition.addWidget(bandeau)
        disposition.addLayout(grille)
        disposition.addStretch(1)

    def annoncer_mise_a_jour(self, etiquette: str) -> None:
        """Signale discrètement qu'une version plus récente existe."""
        self.libelle_maj.setText(
            f"Une nouvelle version du logiciel est disponible ({etiquette}).")
        self.bandeau_maj.setVisible(True)

    # --- mise à jour -----------------------------------------------------

    def rafraichir(self) -> None:
        societe = self.depot.societe
        self.societe.setText(societe.nom or "Votre entreprise")
        francais = QLocale(QLocale.Language.French, QLocale.Country.France)
        self.jour.setText(
            francais.toString(QDate.currentDate(), "dddd d MMMM yyyy").capitalize())

        stats = self.depot.statistiques()
        self.chiffre_attente.definir(euros(stats["ht_en_attente"]) + " HT")
        self.chiffre_facture.definir(euros(stats["ht_facture"]) + " HT")
        self.chiffre_impaye.definir(euros(stats["ttc_impaye"]) + " TTC")
        self.chiffre_retard.definir(euros(stats["ttc_en_retard"]) + " TTC")

        devis_attente = len(self.depot.devis(statut="envoyé"))
        # Un chantier, c'est un devis vu du côté de l'atelier : ceux qui
        # attendent une réponse ou qui sont acceptés sont du travail en vue.
        chantiers_ouverts = len([d for d in self.depot.devis()
                                 if d.statut in ("envoyé", "accepté")])
        factures_dues = len([f for f in self.depot.factures(statut="émise")])

        self.cartes["clients"].definir(stats["clients"])
        self.cartes["devis"].definir(
            stats["devis"],
            f"{devis_attente} en attente de réponse" if devis_attente
            else "Chiffrage et propositions")
        self.cartes["catalogue"].definir(stats["articles"])
        self.cartes["ouvrages"].definir(stats["ouvrages"])
        self.cartes["factures"].definir(
            stats["factures"],
            f"{factures_dues} à encaisser" if factures_dues
            else "Acomptes, situations, soldes")
        self.cartes["chantiers"].definir(
            stats["devis"],
            f"{chantiers_ouverts} en vue" if chantiers_ouverts
            else "Heures et fournitures à prévoir")

        messages = []
        if not societe.nom or not societe.siret:
            messages.append(
                "Renseignez les Paramètres : sans SIRET ni assurance décennale, "
                "vos devis ne sont pas conformes.")
        if stats["corbeille"]:
            messages.append(
                f"{stats['corbeille']} fiche(s) dans la corbeille — la case "
                "« Corbeille » de chaque liste permet de les restaurer.")
        self.avertissement.setText("  ·  ".join(messages))
        self.avertissement.setVisible(bool(messages))
