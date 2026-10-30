"""Écran « Modèle du devis » : réglages de présentation et aperçu en direct."""

import tempfile
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ...domaine.gabarit import (
    COULEURS_SUGGEREES, Gabarit, MODELES_PREDEFINIS, POLICES,
)
from ..impression import RenduDocument
from ...domaine import Client, Devis, Ligne, Societe, depuis_dict, en_dict
from .commun import barre, bouton, confirmer, discret, informer, liste_deroulante, titre


class ApercuDepot:
    """Fait voir au moteur de rendu un gabarit différent de celui enregistré.

    Permet de prévisualiser des réglages sans les appliquer à la base.
    """

    def __init__(self, depot, gabarit: Gabarit):
        self._depot = depot
        self.gabarit = gabarit

    def __getattr__(self, nom):
        return getattr(self._depot, nom)


def devis_exemple(depot) -> tuple[object, Devis]:
    """Un devis réel si possible, sinon un exemple complet pour l'aperçu."""
    for devis in depot.devis():
        if len(devis.lignes) >= 3 and depot.client(devis.client_id):
            return depot, devis

    class _Faux:
        """Dépôt minimal, le temps de montrer à quoi ressemblera un vrai devis."""

        def __init__(self, vrai):
            self.societe = vrai.societe if vrai.societe.nom else Societe(
                nom="Votre entreprise", adresse="12 route des Carrières",
                cp="81000", ville="Albi", telephone="05 63 00 00 00",
                siret="123 456 789 00012", assurance_nom="Votre assureur",
                assurance_contrat="0000000")
            self._client = Client(civilite="M. et Mme", nom="Durand", prenom="Paul",
                                  adresse="8 chemin du Verger", cp="81990", ville="Cambon")

        def client(self, _=None):
            return self._client

        def chantier(self, _=None):
            return None

        def nom_client(self, _=None):
            return self._client.libelle

    exemple = Devis(
        numero="D2026-0001", objet="Construction d'un garage accolé de 32 m²",
        acompte_pct=30,
        lignes=[
            Ligne(type="section", designation="Terrassement et fondations"),
            Ligne(designation="Décapage et mise à niveau du terrain",
                  detail="Évacuation des terres comprise",
                  quantite=32, unite="m²", prix_unitaire=18.5, taux_tva=20),
            Ligne(designation="Béton de propreté et semelles armées",
                  quantite=7.2, unite="m³", prix_unitaire=185, taux_tva=20),
            Ligne(type="section", designation="Maçonnerie"),
            Ligne(designation="Mur en parpaing creux 20x20x50",
                  detail="Y compris chaînages verticaux et horizontaux",
                  quantite=68, unite="m²", prix_unitaire=62, taux_tva=20,
                  remise_pct=5),
            Ligne(type="texte",
                  designation="Les réservations pour gaines électriques sont incluses."),
            Ligne(designation="Enduit monocouche gratté",
                  quantite=68, unite="m²", prix_unitaire=38, taux_tva=10),
            Ligne(designation="Main d'œuvre maçon qualifié",
                  quantite=96, unite="h", prix_unitaire=42, taux_tva=10),
        ])
    return _Faux(depot), exemple


class BoutonCouleur(QPushButton):
    couleur_changee = Signal(str)

    def __init__(self, couleur: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(64, 24))
        self._couleur = couleur
        self._peindre()
        self.clicked.connect(self._choisir)

    def _peindre(self) -> None:
        self.setStyleSheet(
            f"background-color: {self._couleur}; border: 1px solid palette(mid);"
            " border-radius: 3px;")
        self.setToolTip(self._couleur)

    def couleur(self) -> str:
        return self._couleur

    def definir(self, couleur: str) -> None:
        self._couleur = couleur
        self._peindre()

    def _choisir(self) -> None:
        choisie = QColorDialog.getColor(QColor(self._couleur), self,
                                        "Couleur du devis")
        if choisie.isValid():
            self.definir(choisie.name())
            self.couleur_changee.emit(self._couleur)


class VueGabarit(QWidget):
    """Réglages à gauche, aperçu de la première page à droite."""

    donnees_modifiees = Signal()

    nom = "Modèle du devis"

    def __init__(self, depot, parent=None):
        super().__init__(parent)
        self.depot = depot
        self.widgets: dict[str, QWidget] = {}
        self._page = 0
        self._total_pages = 1
        self._dossier = Path(tempfile.mkdtemp(prefix="apercu-devis-"))

        self._minuteur = QTimer(self)
        self._minuteur.setSingleShot(True)
        self._minuteur.setInterval(280)
        self._minuteur.timeout.connect(self.rafraichir_apercu)

        self.apercu = QLabel("Aperçu en préparation…")
        self.apercu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.apercu.setStyleSheet("background: #8a8a8a; padding: 14px;")
        self.etat_pages = discret("")

        self._construire()
        self._charger(depot.gabarit)
        QTimer.singleShot(60, self.rafraichir_apercu)

    # --- construction ----------------------------------------------------

    def _suivre(self, cle: str, widget: QWidget) -> QWidget:
        """Enregistre un widget et déclenche l'aperçu quand il change."""
        self.widgets[cle] = widget
        for signal in ("valueChanged", "toggled", "currentTextChanged", "textChanged",
                       "couleur_changee"):
            if hasattr(widget, signal):
                getattr(widget, signal).connect(self._planifier)
                break
        return widget

    def _case(self, cle: str, libelle: str) -> QCheckBox:
        return self._suivre(cle, QCheckBox(libelle))

    def _mesure(self, cle: str, maximum: float, suffixe: str, pas: float = 1.0,
                minimum: float = 0.0) -> QDoubleSpinBox:
        boite = QDoubleSpinBox()
        boite.setRange(minimum, maximum)
        boite.setSingleStep(pas)
        boite.setDecimals(1)
        boite.setSuffix(suffixe)
        return self._suivre(cle, boite)

    def _groupe(self, titre_: str, rangs) -> QGroupBox:
        groupe = QGroupBox(titre_)
        formulaire = QFormLayout(groupe)
        formulaire.setContentsMargins(10, 8, 10, 8)
        for rang in rangs:
            if isinstance(rang, tuple):
                formulaire.addRow(rang[0], rang[1])
            else:
                formulaire.addRow(rang)
        return groupe

    def _construire(self) -> None:
        self.modele_predefini = liste_deroulante(list(MODELES_PREDEFINIS))
        self.couleur = self._suivre("couleur", BoutonCouleur("#333333"))
        self.couleurs_suggerees = liste_deroulante(
            ["Couleurs suggérées…"] + [n for n, _ in COULEURS_SUGGEREES])
        self.couleurs_suggerees.currentIndexChanged.connect(self._couleur_suggeree)

        reglages = QWidget()
        pile = QVBoxLayout(reglages)
        pile.setSpacing(10)
        pile.setContentsMargins(0, 0, 8, 0)

        pile.addWidget(self._groupe("Modèle de départ", [
            ("Modèle", barre(self.modele_predefini,
                             bouton("Appliquer", self._appliquer_modele))),
        ]))

        pile.addWidget(self._groupe("Couleur et texte", [
            ("Couleur d'accent", barre(self.couleur, self.couleurs_suggerees)),
            ("Police", self._suivre("police", liste_deroulante(POLICES))),
            ("Taille du texte", self._mesure("taille_police", 16, " pt", 0.5, 6)),
            ("Titre du document", self._suivre("titre_document", QLineEdit())),
        ]))

        pile.addWidget(self._groupe("En-tête", [
            ("Largeur du logo", self._mesure("logo_largeur_mm", 90, " mm", 2)),
            self._case("logo_a_droite", "Logo à droite (sinon à gauche)"),
            self._case("afficher_bloc_chantier", "Rappeler l'adresse du chantier"),
        ]))

        pile.addWidget(self._groupe("Colonnes du tableau", [
            self._case("numeroter_lignes", "Numéroter les lignes (1, 1.1, 1.2…)"),
            self._case("colonne_unite", "Colonne Unité"),
            self._case("colonne_tva", "Colonne TVA"),
            self._case("colonne_remise", "Colonne Remise"),
            self._case("afficher_detail_lignes", "Afficher le détail sous chaque ligne"),
            self._case("afficher_sous_totaux_sections", "Sous-total par section"),
        ]))

        self.introduction = self._suivre("texte_introduction", QPlainTextEdit())
        self.introduction.setMaximumHeight(60)
        self.introduction.setPlaceholderText(
            "Phrase d'accroche imprimée avant le tableau (facultatif)")
        self.conclusion = self._suivre("texte_conclusion", QPlainTextEdit())
        self.conclusion.setMaximumHeight(60)
        self.conclusion.setPlaceholderText("Texte imprimé après le tableau (facultatif)")
        pile.addWidget(self._groupe("Textes personnels", [
            ("Avant le tableau", self.introduction),
            ("Après le tableau", self.conclusion),
        ]))

        self.texte_signature = self._suivre("texte_signature", QPlainTextEdit())
        self.texte_signature.setMaximumHeight(60)
        pile.addWidget(self._groupe("Bas du devis", [
            self._case("afficher_recap_tva", "Détailler la TVA par taux"),
            self._case("afficher_acompte", "Afficher l'acompte et le solde"),
            self._case("afficher_conditions", "Conditions de règlement"),
            self._case("afficher_mentions", "Mentions"),
            self._case("afficher_signature", "Cadre « Bon pour accord »"),
            ("Texte de signature", self.texte_signature),
            ("Hauteur du cadre", self._mesure("hauteur_signature_mm", 60, " mm", 2)),
        ]))

        self.pied = self._suivre("pied_personnalise", QPlainTextEdit())
        self.pied.setMaximumHeight(60)
        self.pied.setPlaceholderText(
            "Vide = SIRET, APE, TVA et assurance décennale repris des Paramètres")
        pile.addWidget(self._groupe("Pied de page", [
            self._case("afficher_pied", "Afficher le pied de page"),
            self._case("afficher_numero_page", "Numéro de page"),
            ("Texte personnalisé", self.pied),
        ]))

        pile.addWidget(self._groupe("Marges", [
            ("Gauche", self._mesure("marge_gauche", 50, " mm")),
            ("Haut", self._mesure("marge_haute", 50, " mm")),
            ("Droite", self._mesure("marge_droite", 50, " mm")),
            ("Bas", self._mesure("marge_basse", 50, " mm")),
        ]))
        pile.addStretch(1)

        defilement_reglages = QScrollArea()
        defilement_reglages.setWidget(reglages)
        defilement_reglages.setWidgetResizable(True)
        defilement_reglages.setFixedWidth(430)
        defilement_reglages.setFrameShape(QScrollArea.Shape.NoFrame)

        self.defilement_apercu = QScrollArea()
        self.defilement_apercu.setWidget(self.apercu)
        self.defilement_apercu.setWidgetResizable(True)
        self.defilement_apercu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.defilement_apercu.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.bouton_precedent = bouton("‹", lambda: self._changer_page(-1))
        self.bouton_suivant = bouton("›", lambda: self._changer_page(1))
        for b in (self.bouton_precedent, self.bouton_suivant):
            b.setFixedWidth(34)

        colonne_apercu = QVBoxLayout()
        colonne_apercu.setSpacing(8)
        colonne_apercu.addWidget(barre(
            QLabel("Aperçu"), "-", self.bouton_precedent, self.etat_pages,
            self.bouton_suivant))
        colonne_apercu.addWidget(self.defilement_apercu, 1)

        cadre_apercu = QWidget()
        cadre_apercu.setLayout(colonne_apercu)

        centre = QHBoxLayout()
        centre.setSpacing(14)
        centre.addWidget(defilement_reglages)
        centre.addWidget(cadre_apercu, 1)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(16, 14, 16, 14)
        disposition.setSpacing(10)
        disposition.addWidget(titre("Modèle du devis"))
        disposition.addWidget(discret(
            "Ces réglages s'appliquent à tous les devis imprimés. "
            "L'aperçu se met à jour à chaque modification."))
        disposition.addLayout(centre, 1)
        disposition.addWidget(barre(
            bouton("Revenir au modèle par défaut", self._reinitialiser), "-",
            bouton("Enregistrer le modèle", self.enregistrer, principal=True)))

    # --- lecture et écriture des réglages --------------------------------

    def _charger(self, gabarit: Gabarit) -> None:
        for champ in fields(Gabarit):
            widget = self.widgets.get(champ.name)
            if widget is None:
                continue
            valeur = getattr(gabarit, champ.name)
            widget.blockSignals(True)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(valeur))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(valeur))
            elif isinstance(widget, BoutonCouleur):
                widget.definir(str(valeur))
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(str(valeur))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(valeur))
            else:  # liste déroulante
                widget.setCurrentText(str(valeur))
            widget.blockSignals(False)

    def gabarit_courant(self) -> Gabarit:
        valeurs = {}
        for champ in fields(Gabarit):
            widget = self.widgets.get(champ.name)
            if widget is None:
                continue
            if isinstance(widget, QCheckBox):
                valeurs[champ.name] = widget.isChecked()
            elif isinstance(widget, QDoubleSpinBox):
                valeurs[champ.name] = widget.value()
            elif isinstance(widget, BoutonCouleur):
                valeurs[champ.name] = widget.couleur()
            elif isinstance(widget, QPlainTextEdit):
                valeurs[champ.name] = widget.toPlainText().strip()
            elif isinstance(widget, QLineEdit):
                valeurs[champ.name] = widget.text().strip()
            else:
                valeurs[champ.name] = widget.currentText()
        return Gabarit(**valeurs)

    # --- actions ---------------------------------------------------------

    def _couleur_suggeree(self) -> None:
        nom = self.couleurs_suggerees.currentText()
        for libelle, code in COULEURS_SUGGEREES:
            if libelle == nom:
                self.couleur.definir(code)
                self.couleurs_suggerees.blockSignals(True)
                self.couleurs_suggerees.setCurrentIndex(0)
                self.couleurs_suggerees.blockSignals(False)
                self._planifier()
                return

    def _appliquer_modele(self) -> None:
        reglages = MODELES_PREDEFINIS.get(self.modele_predefini.currentText())
        if not reglages:
            return
        courant = en_dict(self.gabarit_courant())
        courant.update(reglages)
        self._charger(depuis_dict(Gabarit, courant))
        self.rafraichir_apercu()

    def _reinitialiser(self) -> None:
        if confirmer(self, "Modèle par défaut",
                     "Revenir au modèle d'origine ? Vos réglages de présentation "
                     "seront perdus (les devis, eux, ne changent pas)."):
            self._charger(Gabarit())
            self.rafraichir_apercu()

    def enregistrer(self) -> None:
        self.depot.enregistrer_gabarit(self.gabarit_courant())
        self.donnees_modifiees.emit()
        informer(self, "Modèle enregistré",
                 "Tous les devis imprimés désormais reprendront cette présentation.")

    # --- aperçu ----------------------------------------------------------

    def _planifier(self, *_) -> None:
        self._minuteur.start()

    def _changer_page(self, pas: int) -> None:
        self._page = max(0, min(self._total_pages - 1, self._page + pas))
        self.rafraichir_apercu()

    def rafraichir_apercu(self) -> None:
        depot, devis = devis_exemple(self.depot)
        rendu = RenduDocument(ApercuDepot(depot, self.gabarit_courant()), devis)
        chemin = self._dossier / "apercu.pdf"
        try:
            rendu.vers_pdf(chemin, haute_qualite=False)
            document = QPdfDocument()
            document.load(str(chemin))
            self._total_pages = max(1, document.pageCount())
            self._page = min(self._page, self._total_pages - 1)
            image = document.render(self._page, self._taille_apercu())
        except Exception as erreur:  # un réglage incohérent ne doit pas tout bloquer
            self.apercu.setText(f"Aperçu indisponible : {erreur}")
            return
        self.apercu.setPixmap(QPixmap.fromImage(image))
        self.etat_pages.setText(f"page {self._page + 1} / {self._total_pages}")
        self.bouton_precedent.setEnabled(self._page > 0)
        self.bouton_suivant.setEnabled(self._page < self._total_pages - 1)

    def _taille_apercu(self) -> QSize:
        """Une page A4 à la largeur réellement disponible, sans déborder."""
        disponible = self.defilement_apercu.viewport().width() - 34
        largeur = max(360, min(1100, disponible))
        return QSize(int(largeur), int(largeur * 297 / 210))

    def resizeEvent(self, evenement):
        super().resizeEvent(evenement)
        self._planifier()

    def rafraichir(self) -> None:
        self._charger(self.depot.gabarit)
        self.rafraichir_apercu()
