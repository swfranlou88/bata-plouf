"""L'écran Chantiers : les devis vus du côté de l'atelier.

Un chantier n'est pas une fiche de plus. Le devis porte déjà le client,
l'adresse et le détail des travaux ; ce qui manque la veille d'attaquer, ce
sont les heures et la matière — et cela se calcule, à la demande, à partir de
la composition des ouvrages. Rien n'est enregistré ici, donc rien ne peut s'y
démoder.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QLabel, QTableView, QVBoxLayout,
    QWidget,
)

from ...domaine import STATUTS_DEVIS, date_fr, euros, nombre
from ...domaine.chantier import Catalogue, preparation
from ...domaine.facturation import avancement_facture
from .commun import (
    CENTRE, Colonne, DROITE, ModeleListe, activer_le_tri, barre, bouton,
    cle_numero, discret, infobulles_si_tronque, liste_deroulante, titre,
)
from .vues import VueListe


def _lieu(devis) -> str:
    """Où l'on va : l'objet des travaux, à défaut l'adresse."""
    return devis.objet or devis.adresse_chantier or "—"


class VueChantiers(VueListe):
    """La liste des chantiers, c'est-à-dire la liste des devis."""

    nom = "Chantiers"
    mot_element = "chantier"
    libelle_modifier = "Ouvrir le chantier"
    indication_recherche = "Client, objet, ville, numéro de devis…"

    ouvrir_chantier = Signal(object)

    def __init__(self, depot, parent=None):
        self.statut = liste_deroulante(["Tous les statuts"] + STATUTS_DEVIS)
        super().__init__(depot, parent)
        # Un chantier ne se crée pas et ne se jette pas : il naît avec son
        # devis et meurt avec lui.
        for widget in (self.bouton_nouveau, self.bouton_supprimer,
                       self.corbeille):
            widget.setVisible(False)
        self.tableau.doubleClicked.connect(lambda _: self.modifier())

    # --- contenu ---------------------------------------------------------

    def filtres(self):
        return [self.statut]

    def charger(self):
        choisi = self.statut.currentText()
        devis = self.depot.devis(
            recherche=self.recherche.text().strip(),
            statut="" if choisi.startswith("Tous") else choisi)
        # Le catalogue coûte cher à bâtir et sert à toutes les lignes : une
        # fois par rafraîchissement, pas une fois par devis.
        self._catalogue = Catalogue(self.depot.articles())
        self._travaux = {d.id: preparation(d, self._catalogue) for d in devis}
        return devis

    def _preparation(self, devis):
        prevu = self._travaux.get(devis.id)
        if prevu is None:
            prevu = preparation(devis, self._catalogue or
                                Catalogue(self.depot.articles()))
            self._travaux[devis.id] = prevu
        return prevu

    def colonnes(self):
        return [
            Colonne("Devis", lambda d: d.numero, largeur=105, gras=True,
                    cle=lambda d: cle_numero(d.numero)),
            Colonne("Client", lambda d: self.depot.nom_client(d.client_id),
                    largeur=190),
            Colonne("Chantier", lambda d: _lieu(d)),
            Colonne("Date", lambda d: date_fr(d.date_devis), largeur=95,
                    alignement=CENTRE, cle=lambda d: d.date_devis or ""),
            Colonne("Heures", self._heures, largeur=85, alignement=DROITE,
                    cle=lambda d: self._preparation(d).heures),
            Colonne("Fournitures", self._fournitures, largeur=95,
                    alignement=CENTRE,
                    cle=lambda d: len(self._preparation(d).fournitures)),
            Colonne("Facturé", self._facture, largeur=80, alignement=CENTRE,
                    cle=self._cle_facture),
            Colonne("Statut", lambda d: d.statut, largeur=95,
                    alignement=CENTRE),
        ]

    def _heures(self, devis) -> str:
        prevu = self._preparation(devis)
        if not prevu.postes:
            return "—"
        return f"{nombre(prevu.heures, 1)} h" + ("" if prevu.complet else " ?")

    def _fournitures(self, devis) -> str:
        compte = len(self._preparation(devis).fournitures)
        return str(compte) if compte else "—"

    def _facture(self, devis) -> str:
        if not self.depot.factures(devis_id=devis.id):
            return "—"
        return f"{nombre(avancement_facture(self.depot, devis))} %"

    def _cle_facture(self, devis) -> tuple:
        if not self.depot.factures(devis_id=devis.id):
            return (0, 0.0)
        return (1, avancement_facture(self.depot, devis))

    # --- actions ---------------------------------------------------------

    def libelle(self, devis) -> str:
        return f"le chantier du devis {devis.numero}"

    def modifier(self) -> None:
        devis = self.selection()
        if devis is not None:
            self.ouvrir_chantier.emit(devis)


class FicheChantier(QWidget):
    """Ce qu'il faut emmener et le temps qu'il faudra y passer."""

    ferme = Signal()
    devis_demande = Signal(object)

    def __init__(self, depot, devis, parent=None):
        super().__init__(parent)
        self.depot = depot
        self.devis = devis
        prevu = preparation(devis, Catalogue(depot.articles()))

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(16, 14, 16, 14)
        disposition.setSpacing(10)
        disposition.addWidget(titre(f"Chantier — {_lieu(devis)}"))
        disposition.addWidget(self._entete(prevu))

        colonnes = QHBoxLayout()
        colonnes.setSpacing(14)
        colonnes.addWidget(self._main_doeuvre(prevu), 3)
        colonnes.addWidget(self._fournitures(prevu), 2)
        cadre = QWidget()
        cadre.setLayout(colonnes)
        disposition.addWidget(cadre, 1)

        disposition.addWidget(barre(
            bouton("← Retour à la liste", self.ferme.emit),
            "-",
            bouton("Ouvrir le devis",
                   lambda: self.devis_demande.emit(self.devis),
                   principal=True),
        ))

    # --- blocs -----------------------------------------------------------

    def _entete(self, prevu) -> QWidget:
        depot, devis = self.depot, self.devis
        gauche = QLabel(self._table([
            ("Client", depot.nom_client(devis.client_id)),
            ("Adresse", devis.adresse_chantier or "—"),
            ("Devis", f"{devis.numero} du {date_fr(devis.date_devis)}"),
            ("Statut", devis.statut),
        ]))
        gauche.setTextFormat(Qt.TextFormat.RichText)

        factures = depot.factures(devis_id=devis.id)
        avancement = (f"{nombre(avancement_facture(depot, devis))} %"
                      if factures else "pas encore facturé")
        droite = QLabel(self._table([
            ("Main d'œuvre", f"{nombre(prevu.heures, 1)} h, soit "
                             f"{nombre(prevu.journees, 1)} journées de sept heures"),
            ("Fournitures", f"{len(prevu.fournitures)} ligne(s)"),
            ("Montant des travaux", euros(devis.totaux().total_ht) + " HT"),
            ("Facturé", avancement),
        ]))
        droite.setTextFormat(Qt.TextFormat.RichText)

        boite = QHBoxLayout()
        boite.setSpacing(14)
        boite.addWidget(gauche, 1)
        boite.addWidget(droite, 1)
        cadre = QWidget()
        cadre.setLayout(boite)
        return cadre

    def _main_doeuvre(self, prevu) -> QGroupBox:
        boite = QGroupBox("Main d'œuvre")
        dedans = QVBoxLayout(boite)
        modele = ModeleListe([
            Colonne("Poste", lambda p: p.designation),
            Colonne("Quantité", lambda p: nombre(p.quantite, 2), largeur=90,
                    alignement=DROITE, cle=lambda p: p.quantite),
            Colonne("Un.", lambda p: p.unite, largeur=55, alignement=CENTRE),
            Colonne("H / unité", lambda p: nombre(p.heures_unitaires, 3),
                    largeur=85, alignement=DROITE,
                    cle=lambda p: p.heures_unitaires),
            Colonne("Heures", lambda p: nombre(p.heures, 2), largeur=85,
                    alignement=DROITE, gras=True, cle=lambda p: p.heures),
        ], prevu.postes)
        tableau = self._tableau(modele)
        dedans.addWidget(tableau, 1)
        dedans.addWidget(QLabel(
            f"<b>{nombre(prevu.heures, 1)} heures</b> au total, "
            f"soit {nombre(prevu.journees, 1)} journées de sept heures."))
        if prevu.sans_temps:
            # Un ouvrage sans temps connu ne vaut pas zéro heure : le dire,
            # c'est la seule façon de ne pas se fier à un total trop bas.
            dedans.addWidget(discret(
                f"{len(prevu.sans_temps)} ligne(s) sans temps connu, non "
                "comptées : " + ", ".join(prevu.sans_temps[:3])
                + ("…" if len(prevu.sans_temps) > 3 else "")))
        return boite

    def _fournitures(self, prevu) -> QGroupBox:
        boite = QGroupBox("Fournitures à prévoir")
        dedans = QVBoxLayout(boite)
        modele = ModeleListe([
            Colonne("Matériau", lambda f: f.designation),
            Colonne("Quantité", lambda f: nombre(f.quantite, 2), largeur=90,
                    alignement=DROITE, cle=lambda f: f.quantite),
            Colonne("Un.", lambda f: f.unite, largeur=55, alignement=CENTRE),
        ], prevu.fournitures)
        dedans.addWidget(self._tableau(modele), 1)
        dedans.addWidget(discret(
            "Les matériaux compris dans un ouvrage n'y figurent pas : "
            "l'ancien logiciel n'en gardait que le temps de pose."))
        return boite

    @staticmethod
    def _tableau(modele) -> QTableView:
        tableau = QTableView()
        tableau.setModel(modele)
        tableau.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tableau.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tableau.setAlternatingRowColors(True)
        tableau.verticalHeader().setVisible(False)
        tableau.verticalHeader().setDefaultSectionSize(24)
        for rang, colonne in enumerate(modele.colonnes):
            if colonne.largeur:
                tableau.setColumnWidth(rang, colonne.largeur)
        tableau.horizontalHeader().setStretchLastSection(False)
        activer_le_tri(tableau, modele)
        infobulles_si_tronque(tableau)
        return tableau

    @staticmethod
    def _table(rangs) -> str:
        return "<table cellpadding='2'>" + "".join(
            f"<tr><td style='color:palette(mid);'>{libelle}&nbsp;&nbsp;</td>"
            f"<td>{valeur}</td></tr>" for libelle, valeur in rangs) + "</table>"
