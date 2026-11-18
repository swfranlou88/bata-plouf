"""Écrans de facturation : liste, éditeur, et passage du devis à la facture."""

from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QPlainTextEdit, QTableView, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog

from ...domaine.calculs import (
    conditions_par_defaut, mentions_par_defaut, taux_reduit,
)
from ...domaine.facturation import (
    avancement_facture, etat_avancement, generer_acompte, generer_avoir,
    generer_facture_directe, generer_facture_totale, generer_solde,
    generer_situation, prochain_numero_situation, recapitulatif_marche,
    reste_a_facturer,
)
from ..impression import RenduDocument
from ...domaine import (
    Facture, LIBELLES_FACTURE, MODES_PAIEMENT, STATUTS_FACTURE, TAUX_TVA, UNITES,
    date_fr, euros, nombre, taux_tva_txt,
)
from ..depot_fichiers import ErreurReference
from .commun import (
    CENTRE, Colonne, DROITE, alerter, annoncer, barre, bouton,
    bouton_copier_adresse,
    champ_date, champ_entier, champ_texte, cle_numero, confirmer, discret,
    informer, etiquette_client, infobulles_si_tronque, liste_deroulante,
    rendre_cherchable, teinte_attente, teinte_defaire, titre, valeur_date,
)
from .devis import (
    COL_DESIGNATION, COL_PU, COL_QUANTITE, COL_REMISE, COL_TOTAL, COL_TVA,
    COL_UNITE, DelegueChoix, DelegueNombre, ModeleLignes, question_lignes,
    ouvrir_fiche_de_la_ligne,
)
from .vues import VueListe


# --- choix du type de facture --------------------------------------------


class DialogueFacturer(QDialog):
    """Demande quoi facturer sur un devis, et montre le montant avant de valider."""

    def __init__(self, parent, depot, devis):
        super().__init__(parent)
        self.depot = depot
        self.devis = devis
        self.setWindowTitle(f"Facturer le devis {devis.numero}")
        self.setMinimumWidth(560)

        marche = devis.totaux()
        self.deja_pct = avancement_facture(depot, devis)
        reste = reste_a_facturer(depot, devis)

        # L'ordre compte : le cas le plus courant d'abord, un devis = une facture.
        self.type = liste_deroulante(
            ["Facture complète", "Acompte", "Situation de travaux",
             "Solde des travaux"])
        self.type.currentIndexChanged.connect(self._basculer)

        self.pourcentage = liste_deroulante([])  # remplacé juste après
        from .commun import champ_pourcent
        self.pourcentage = champ_pourcent(depot.societe.acompte_defaut_pct)
        self.pourcentage.valueChanged.connect(self._estimer)

        self.bouton_appliquer = bouton("Appliquer à tous", self._appliquer_a_tous)
        self.explication = QLabel()
        self.explication.setWordWrap(True)

        # Un poste par ligne chiffrée du devis, avec son avancement à saisir
        self.avancements: dict[str, QDoubleSpinBox] = {}
        self.tableau_avancement = QTableWidget()
        self.tableau_avancement.setColumnCount(4)
        self.tableau_avancement.setHorizontalHeaderLabels(
            ["Poste", "Marché", "Déjà facturé", "Avancement"])
        self.tableau_avancement.verticalHeader().setVisible(False)
        self.tableau_avancement.setAlternatingRowColors(True)
        self.tableau_avancement.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableau_avancement.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.tableau_avancement.setMinimumHeight(190)
        self._remplir_avancement()
        self.montant = QLabel()
        self.montant.setTextFormat(Qt.TextFormat.RichText)

        rappel = QGroupBox("Où en est ce chantier")
        formulaire_rappel = QFormLayout(rappel)
        formulaire_rappel.addRow("Marché", QLabel(
            f"{euros(marche.total_ht)} HT · {euros(marche.total_ttc)} TTC"))
        formulaire_rappel.addRow("Déjà facturé", QLabel(
            f"{euros(marche.total_ht - reste)} HT ({nombre(self.deja_pct)} %)"))
        formulaire_rappel.addRow("Reste à facturer", QLabel(f"{euros(reste)} HT"))

        choix = QGroupBox("Facture à établir")
        formulaire = QFormLayout(choix)
        formulaire.addRow("Type", self.type)
        self.etiquette_pct = QLabel("Pourcentage")
        formulaire.addRow(self.etiquette_pct,
                          barre(self.pourcentage, self.bouton_appliquer, "-"))
        formulaire.addRow("", self.explication)
        formulaire.addRow("Montant", self.montant)

        self.boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Créer la facture")
        self.boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        self.boutons.accepted.connect(self.accept)
        self.boutons.rejected.connect(self.reject)

        self.groupe_avancement = QGroupBox("Avancement poste par poste")
        colonne_avancement = QVBoxLayout(self.groupe_avancement)
        colonne_avancement.addWidget(discret(
            "Indiquez où en est chaque poste. Seule la part qui n'a pas encore "
            "été facturée sera réclamée."))
        colonne_avancement.addWidget(self.tableau_avancement)

        disposition = QVBoxLayout(self)
        disposition.addWidget(rappel)
        disposition.addWidget(choix)
        disposition.addWidget(self.groupe_avancement)
        if devis.statut != "accepté":
            disposition.addWidget(discret(
                f"Ce devis est au statut « {devis.statut} ». Rien ne l'interdit, "
                "mais on facture normalement un devis accepté."))
        disposition.addWidget(self.boutons)

        self._basculer()

    # --- avancement poste par poste --------------------------------------

    def _remplir_avancement(self) -> None:
        """Un poste par ligne chiffrée du devis, avec son avancement à saisir.

        Chaque poste rappelle son montant au marché et ce qui en est déjà
        facturé ; le minimum du compteur est l'avancement déjà atteint, pour
        qu'on ne puisse pas revenir en arrière par mégarde.
        """
        etats = etat_avancement(self.depot, self.devis)
        sections, courante = {}, ""
        for ligne in self.devis.lignes:
            if ligne.type == "section":
                courante = ligne.designation
            elif ligne.chiffree:
                sections[ligne.id] = courante

        self.tableau_avancement.setRowCount(len(etats))
        for rang, etat in enumerate(etats):
            intitule = etat.ligne.designation
            if sections.get(etat.ligne.id):
                intitule = f"{sections[etat.ligne.id]} · {intitule}"
            cellule_poste = QTableWidgetItem(intitule)
            cellule_poste.setToolTip(intitule)  # le libellé complet, s'il est tronqué
            self.tableau_avancement.setItem(rang, 0, cellule_poste)
            for colonne, texte in ((1, euros(etat.montant)), (2, euros(etat.deja))):
                cellule = QTableWidgetItem(texte)
                cellule.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                         | Qt.AlignmentFlag.AlignVCenter)
                self.tableau_avancement.setItem(rang, colonne, cellule)

            boite = QDoubleSpinBox()
            boite.setDecimals(0)
            boite.setRange(etat.pct_deja, 100)
            boite.setSuffix(" %")
            boite.setValue(min(100.0, etat.pct_deja + 25))
            boite.valueChanged.connect(self._estimer)
            self.tableau_avancement.setCellWidget(rang, 3, boite)
            self.avancements[etat.ligne.id] = boite

        entetes = self.tableau_avancement.horizontalHeader()
        entetes.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for colonne, largeur in ((1, 110), (2, 115), (3, 90)):
            entetes.setSectionResizeMode(colonne, QHeaderView.ResizeMode.Fixed)
            self.tableau_avancement.setColumnWidth(colonne, largeur)

    def _appliquer_a_tous(self) -> None:
        """Met tous les postes au même avancement, pour aller vite."""
        valeur = self.pourcentage.value()
        for boite in self.avancements.values():
            boite.setValue(max(boite.minimum(), min(valeur, 100.0)))
        self._estimer()

    def _basculer(self) -> None:
        choix = self.type.currentText()
        self.doublon = False
        if choix == "Facture complète":
            self.etiquette_pct.setText("Pourcentage")
            self.pourcentage.setEnabled(False)
            self.pourcentage.setValue(100.0)
            if self.deja_pct:
                self.doublon = True
                self.explication.setText(
                    f"⚠ {nombre(self.deja_pct)} % du marché sont déjà facturés : "
                    "une facture complète ferait double emploi. Établissez plutôt "
                    "une situation ou le solde.")
            else:
                self.explication.setText(
                    "La facture reprend toutes les lignes du devis, poste par "
                    "poste, avec le même détail.")
        elif choix == "Acompte":
            self.etiquette_pct.setText("Pourcentage")
            self.pourcentage.setEnabled(True)
            self.pourcentage.setValue(self.depot.societe.acompte_defaut_pct)
            self.explication.setText(
                "L'acompte se calcule sur le montant total du marché.")
        elif choix == "Situation de travaux":
            numero = prochain_numero_situation(self.depot, self.devis.id)
            self.etiquette_pct.setText("Tout à")
            self.pourcentage.setEnabled(True)
            self.pourcentage.setValue(min(100.0, max(self.deja_pct + 25, self.deja_pct)))
            self.explication.setText(
                f"Situation n° {numero}. L'acompte déjà versé viendra en "
                "déduction au bas de la facture.")
        else:
            self.etiquette_pct.setText("Pourcentage")
            self.pourcentage.setEnabled(False)
            self.pourcentage.setValue(100.0)
            self.explication.setText(
                "Le solde reprend tout ce qui n'a pas encore été facturé, "
                "acomptes et situations déduits.")
        self.groupe_avancement.setVisible(choix == "Situation de travaux")
        self.bouton_appliquer.setVisible(choix == "Situation de travaux")
        self.adjustSize()
        self._estimer()

    def _projet(self) -> Facture:
        choix = self.type.currentText()
        if choix == "Facture complète":
            return generer_facture_totale(self.depot, self.devis)
        if choix == "Acompte":
            return generer_acompte(self.depot, self.devis, self.pourcentage.value())
        if choix == "Situation de travaux":
            return generer_situation(
                self.depot, self.devis,
                {cle: boite.value() for cle, boite in self.avancements.items()})
        return generer_solde(self.depot, self.devis)

    def _estimer(self) -> None:
        facture = self._projet()
        t = facture.totaux()
        valide = t.total_ht > 0 and not getattr(self, "doublon", False)
        self.montant.setText(
            f"<b>{euros(t.total_ht)} HT</b> · {euros(t.total_ttc)} TTC" if valide
            else "<i>Rien à facturer avec ces valeurs</i>")
        self.boutons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valide)

    def facture(self) -> Facture:
        return self._projet()


# --- éditeur de facture ---------------------------------------------------


class EditeurFacture(QWidget):
    ferme = Signal()
    enregistre = Signal()

    def __init__(self, depot, facture: Facture, parent=None):
        super().__init__(parent)
        self.depot = depot
        self.facture = facture

        self.numero = QLabel(facture.numero or "attribué à l'enregistrement")
        self.type = QLabel(facture.libelle_type)
        self.origine = QLabel("—")
        # Huit cents fiches : on tape trois lettres plutôt que de dérouler.
        self.client = rendre_cherchable(QComboBox(), "Nom, société ou ville…")
        self.adresse_chantier = champ_texte(
            facture.adresse_chantier, "adresse des travaux")
        self.copier_adresse = bouton_copier_adresse(
            self.adresse_chantier, self._client_courant)
        self.objet = champ_texte(facture.objet)
        self.date = champ_date(facture.date_facture)
        self.echeance = champ_entier(facture.echeance_jours, 365)
        self.echeance.setSuffix(" jours")
        self.statut = QLabel(facture.statut)
        self.mode_paiement = liste_deroulante(MODES_PAIEMENT, facture.mode_paiement)
        self.date_paiement = champ_date(facture.date_paiement, optionnel=True)
        self.bouton_payee = bouton("Marquer payée", self.basculer_paiement)
        # L'un renseigné appelle l'autre : on le dit en vert plutôt que de
        # laisser un règlement à moitié saisi.
        self.mode_paiement.currentIndexChanged.connect(self._eclairer_reglement)
        self.date_paiement.dateChanged.connect(self._eclairer_reglement)

        for widget in (self.echeance,):
            widget.valueChanged.connect(self._recalculer)
        self.date.dateChanged.connect(self._recalculer)

        self.modele = ModeleLignes(facture)
        for signal in (self.modele.dataChanged, self.modele.rowsInserted,
                       self.modele.rowsRemoved):
            signal.connect(lambda *_: self._recalculer())
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
        self.tableau.doubleClicked.connect(self._double_clic)
        entetes = self.tableau.horizontalHeader()
        entetes.setSectionResizeMode(COL_DESIGNATION, QHeaderView.ResizeMode.Stretch)
        for colonne, largeur in ((COL_QUANTITE, 90), (COL_UNITE, 80), (COL_PU, 110),
                                 (COL_TVA, 85), (COL_REMISE, 90), (6, 125)):
            entetes.setSectionResizeMode(colonne, QHeaderView.ResizeMode.Fixed)
            self.tableau.setColumnWidth(colonne, largeur)
        self.tableau.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        # Une ligne sans détail ne doit pas être écrasée
        self.tableau.verticalHeader().setMinimumSectionSize(27)
        infobulles_si_tronque(self.tableau)

        self.totaux = QLabel()
        self.totaux.setTextFormat(Qt.TextFormat.RichText)
        self.totaux.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.marche = QLabel()
        self.marche.setTextFormat(Qt.TextFormat.RichText)
        self.marche.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.notes = QPlainTextEdit(facture.notes_internes)
        self.notes.setPlaceholderText("Notes internes — ne figurent pas sur la facture")
        self.notes.setMaximumHeight(60)

        self.avertissement = QLabel()
        self.avertissement.setWordWrap(True)
        self.avertissement.setStyleSheet(
            "background: palette(alternate-base); padding: 7px; border-radius: 4px;")

        self._construire()
        self._remplir_clients()
        self._appliquer_verrou()
        self._recalculer()

    # --- montage ---------------------------------------------------------

    def _construire(self) -> None:
        gauche = QFormLayout()
        gauche.addRow("Numéro", self.numero)
        gauche.addRow("Type", self.type)
        gauche.addRow("Devis d'origine", self.origine)
        gauche.addRow("Client", self.client)
        gauche.addRow("Adresse chantier",
                      barre(self.adresse_chantier, self.copier_adresse))
        gauche.addRow("Objet", self.objet)

        droite = QFormLayout()
        droite.addRow("Date", self.date)
        droite.addRow("Paiement sous", self.echeance)
        droite.addRow("Statut", self.statut)
        droite.addRow("Mode de règlement", self.mode_paiement)
        droite.addRow("Payée le", self.date_paiement)

        cadre = QWidget()
        colonnes = QHBoxLayout(cadre)
        colonnes.setContentsMargins(0, 0, 0, 0)
        for formulaire, poids in ((gauche, 3), (droite, 2)):
            boite = QWidget()
            boite.setLayout(formulaire)
            colonnes.addWidget(boite, poids)

        self.outils = barre(
            bouton("+ Ligne", self.ajouter_ligne),
            bouton("Bibliothèque…", self.inserer_articles),
            bouton("Supprimer la ligne", self.supprimer_ligne, danger=True),
            "-",
            bouton("Émettre la facture", self.emettre, principal=True),
            self.bouton_payee,
            bouton("Créer un avoir", self.creer_avoir),
        )

        bas = QWidget()
        disposition_bas = QHBoxLayout(bas)
        disposition_bas.setContentsMargins(0, 0, 0, 0)
        groupe_notes = QGroupBox("Notes internes")
        QVBoxLayout(groupe_notes).addWidget(self.notes)
        self.groupe_marche = QGroupBox("Rappel du marché")
        QVBoxLayout(self.groupe_marche).addWidget(self.marche)
        self.groupe_marche.setMinimumWidth(300)
        groupe_totaux = QGroupBox("Récapitulatif")
        QVBoxLayout(groupe_totaux).addWidget(self.totaux)
        groupe_totaux.setMinimumWidth(300)
        disposition_bas.addWidget(groupe_notes, 1)
        disposition_bas.addWidget(self.groupe_marche)
        disposition_bas.addWidget(groupe_totaux)

        actions = barre(
            bouton("← Retour à la liste", self._retour), "-",
            bouton("Aperçu avant impression", self.apercu),
            bouton("Enregistrer en PDF", self.exporter_pdf),
            bouton("Imprimer…", self.imprimer),
            bouton("Enregistrer", self._enregistrer_et_confirmer,
                   principal=True),
        )

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(16, 14, 16, 14)
        disposition.setSpacing(10)
        disposition.addWidget(titre("Facture"))
        disposition.addWidget(self.avertissement)
        disposition.addWidget(cadre)
        disposition.addWidget(self.outils)
        disposition.addWidget(self.tableau, 1)
        disposition.addWidget(bas)
        disposition.addWidget(actions)

    def _remplir_clients(self) -> None:
        self.client.blockSignals(True)
        self.client.clear()
        self.client.addItem("— aucun —", "")
        for client in self.depot.clients():
            self.client.addItem(etiquette_client(client), client.id)
        self.client.setCurrentIndex(max(0, self.client.findData(self.facture.client_id)))
        self.client.blockSignals(False)

        if self.facture.devis_id:
            devis = self.depot.un_devis(self.facture.devis_id)
            self.origine.setText(
                f"{devis.numero} du {date_fr(devis.date_devis)}" if devis
                else "devis introuvable")

    def _double_clic(self, index) -> None:
        """Le double-clic sur la désignation d'un ouvrage ouvre son ouvrage."""
        if index.column() == COL_DESIGNATION:
            QTimer.singleShot(0, lambda: self._fiche_de_la_ligne(index.row()))

    def _fiche_de_la_ligne(self, rang: int) -> None:
        ligne = self.modele.ligne(rang)
        if ligne is None:
            return
        if ouvrir_fiche_de_la_ligne(self, self.depot, ligne, self.facture.modifiable):
            self.modele.dataChanged.emit(self.modele.index(rang, 0),
                                         self.modele.index(rang, COL_TOTAL))

    def _client_courant(self):
        return self.depot.client(self.client.currentData() or "")

    # --- règlement --------------------------------------------------------

    def _reglement_renseigne(self) -> tuple[bool, bool]:
        """Le mode et la date sont-ils renseignés ?"""
        return (bool(self.mode_paiement.currentText().strip()),
                bool(valeur_date(self.date_paiement)))

    def _eclairer_reglement(self) -> None:
        """Vert sur celui qui manque, vert sur le bouton quand les deux sont là.

        Un règlement à moitié saisi ne se voit pas : la date est là, le mode
        ne l'est pas, et la facture reste impayée sans qu'on sache pourquoi.
        """
        mode, date = self._reglement_renseigne()
        vert = teinte_attente()
        attente = f"border: 1px solid {vert}; border-radius: 3px;"
        # Chacun s'allume quand l'autre est rempli et que lui ne l'est pas.
        self.mode_paiement.setStyleSheet("" if mode or not date else attente)
        self.date_paiement.setStyleSheet("" if date or not mode else attente)

        if self.facture.statut == "payée":
            self.bouton_payee.setText("Enlever le paiement de la facture")
            rouge = teinte_defaire()
            self.bouton_payee.setStyleSheet(
                f"color: {rouge}; font-weight: bold;")
        else:
            self.bouton_payee.setText("Marquer payée")
            # Seule une facture émise attend un règlement : un brouillon
            # s'émet d'abord, une facture annulée ne se paie plus. Le bouton
            # ne se met pas en vert pour un geste qu'il refusera.
            pret = mode and date and self.facture.statut == "émise"
            self.bouton_payee.setStyleSheet(
                f"color: {vert}; font-weight: bold;" if pret else "")

    def basculer_paiement(self) -> None:
        """Marquer payée, ou défaire ce règlement — avec confirmation."""
        if self.facture.statut == "payée":
            self._defaire_paiement()
            return
        self.marquer_payee()

    def _defaire_paiement(self) -> None:
        regle = date_fr(self.facture.date_paiement)
        if not confirmer(
                self, "Enlever le paiement",
                f"La facture {self.facture.numero} ne sera plus marquée payée"
                + (f" (réglée le {regle})" if regle else "") + ".\n\n"
                "Le mode de règlement et la date seront effacés, et la "
                "facture repassera en attente de paiement. Continuer ?"):
            return
        self.facture.statut = "émise"
        self.facture.date_paiement = ""
        self.facture.mode_paiement = ""
        self.mode_paiement.setCurrentIndex(0)
        self.date_paiement.setDate(self.date_paiement.minimumDate())
        self.depot.enregistrer_facture(self.facture)
        self._appliquer_verrou()
        self.enregistre.emit()
        annoncer(self, f"Facture {self.facture.numero} de nouveau en attente "
                 "de règlement")

    # --- verrou comptable ------------------------------------------------

    def _appliquer_verrou(self) -> None:
        """Une facture émise ne se modifie plus.

        Les champs se figent et seuls le règlement et l'impression restent
        accessibles ; la correction passe par un avoir.
        """
        modifiable = self.facture.modifiable
        # L'adresse du chantier se fige avec le reste : elle est imprimée sur
        # la facture émise, et la corriger après coup la ferait mentir.
        for widget in (self.client, self.adresse_chantier,
                       self.copier_adresse, self.objet, self.date,
                       self.echeance, self.notes):
            widget.setEnabled(modifiable)
        self.tableau.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            if modifiable else QAbstractItemView.EditTrigger.NoEditTriggers)
        self.statut.setText(self.facture.statut
                            + (" — en retard" if self.facture.en_retard else ""))
        self.groupe_marche.setVisible(bool(self.facture.devis_id))
        self._eclairer_reglement()

        if self.facture.type == "avoir":
            self.avertissement.setText(
                "Avoir : les montants sont négatifs et viennent en déduction de ce "
                "qui a été facturé.")
            self.avertissement.setVisible(True)
        elif modifiable:
            self.avertissement.setText(
                "Brouillon : la facture est encore modifiable et n'a pas de valeur "
                "comptable. Le numéro est déjà réservé.")
            self.avertissement.setVisible(True)
        else:
            self.avertissement.setText(
                "Facture émise : elle ne peut plus être modifiée ni supprimée. "
                "Pour la corriger, créez un avoir.")
            self.avertissement.setVisible(True)

    # --- lignes ----------------------------------------------------------

    def ajouter_ligne(self) -> None:
        if not self.facture.modifiable:
            return
        from ...domaine import Ligne
        rang = self.modele.inserer(Ligne(taux_tva=self.depot.societe.taux_tva_defaut))
        index = self.modele.index(rang, COL_DESIGNATION)
        self.tableau.setCurrentIndex(index)
        self.tableau.edit(index)

    def inserer_articles(self) -> None:
        """Reprendre des ouvrages de la bibliothèque, comme sur un devis.

        Une facture directe se compose comme un devis : elle n'a pas de
        marché derrière elle, et ses lignes sortent du même catalogue.
        """
        if not self.facture.modifiable:
            return
        from ...domaine import Ligne
        from .devis import DialogueChoixArticle
        dialogue = DialogueChoixArticle(self, self.depot)
        if dialogue.exec() != QDialog.DialogCode.Accepted:
            return
        rang = None
        for article in dialogue.articles():
            rang = self.modele.inserer(Ligne(
                designation=article.designation, detail=article.detail,
                unite=article.unite, prix_unitaire=article.prix_vente,
                taux_tva=article.taux_tva, article_id=article.id,
                quantite=1.0), rang) + 1

    def supprimer_ligne(self) -> None:
        if not self.facture.modifiable:
            return
        rangs = [i.row() for i in self.tableau.selectionModel().selectedRows()]
        if not rangs:
            return
        if not confirmer(self, "Supprimer de la facture",
                         question_lignes(self.modele, rangs, "facture")):
            return
        for rang in sorted(rangs, reverse=True):
            self.modele.retirer(rang)

    # --- totaux ----------------------------------------------------------

    def _recalculer(self) -> None:
        self._collecter()
        t = self.facture.totaux()
        rangs = [("Total HT", euros(t.total_ht), True)]
        for l in t.tva:
            rangs.append((f"TVA {taux_tva_txt(l.taux)}", euros(l.montant), False))
        rangs.append(("Net à payer TTC", euros(t.total_ttc), True))
        rangs.append(("Échéance", date_fr(self.facture.date_echeance), False))
        self.totaux.setText(self._table(rangs))

        infos = recapitulatif_marche(self.depot, self.facture)
        if infos:
            self.marche.setText(self._table([
                (f"Devis {infos['devis'].numero}", euros(infos["marche_ht"]), False),
                ("Déjà facturé", euros(infos["anterieur_ht"]), False),
                ("Présente facture", euros(infos["courant_ht"]), True),
                ("Reste à facturer", euros(infos["reste_ht"]), False),
            ]))

    @staticmethod
    def _table(rangs) -> str:
        corps = "".join(
            f"<tr><td style='padding:2px 6px;'>{'<b>' if fort else ''}{libelle}"
            f"{'</b>' if fort else ''}</td>"
            f"<td align='right' style='padding:2px 6px;'>{'<b>' if fort else ''}{valeur}"
            f"{'</b>' if fort else ''}</td></tr>"
            for libelle, valeur, fort in rangs)
        return f"<table width='100%'>{corps}</table>"

    # --- enregistrement --------------------------------------------------

    def _collecter(self) -> None:
        if not self.facture.modifiable:
            self.facture.mode_paiement = self.mode_paiement.currentText()
            self.facture.date_paiement = valeur_date(self.date_paiement)
            return
        f = self.facture
        f.client_id = self.client.currentData() or ""
        f.objet = self.objet.text().strip()
        f.adresse_chantier = self.adresse_chantier.text().strip()
        f.date_facture = valeur_date(self.date)
        f.echeance_jours = self.echeance.value()
        f.notes_internes = self.notes.toPlainText().strip()
        f.mode_paiement = self.mode_paiement.currentText()
        f.date_paiement = valeur_date(self.date_paiement)

    def _enregistrer_et_confirmer(self) -> None:
        """Le bouton confirme ; l'enregistrement d'avant une impression, non.

        Sans un mot, on ne sait pas si la facture est partie dans le dossier
        ou si un champ manquant a tout retenu — et on réenregistre à tout
        hasard.
        """
        if self.enregistrer():
            annoncer(self, f"Facture {self.facture.numero} enregistrée")

    def enregistrer(self) -> bool:
        self._collecter()
        if not self.facture.client_id:
            alerter(self, "Client manquant", "Choisissez le client avant d'enregistrer.")
            return False
        if not self.facture.lignes:
            alerter(self, "Facture vide", "Ajoutez au moins une ligne.")
            return False
        self.depot.enregistrer_facture(self.facture)
        self.numero.setText(self.facture.numero)
        self.enregistre.emit()
        return True

    def emettre(self) -> None:
        if not self.facture.modifiable:
            informer(self, "Déjà émise", "Cette facture a déjà été émise.")
            return
        if not self.enregistrer():
            return
        if not confirmer(self, "Émettre la facture",
                         f"Émettre définitivement la facture {self.facture.numero} ?\n\n"
                         "Elle ne pourra plus être modifiée ni supprimée : c'est une "
                         "obligation comptable. La seule correction possible sera un avoir."):
            return
        from datetime import date as _date
        # Le bas de page se fige ici, et ici seulement : tant que la facture
        # est un brouillon elle suit les Paramètres, mais ce qui est parti
        # chez le client doit se réimprimer à l'identique dans dix ans, même
        # si les textes ont changé entre-temps.
        societe = self.depot.societe
        if not self.facture.conditions:
            self.facture.conditions = conditions_par_defaut(
                societe, True, taux_reduit(self.facture))
        if not self.facture.mentions:
            self.facture.mentions = mentions_par_defaut(societe, True)
        self.facture.statut = "émise"
        self.facture.date_emission = _date.today().isoformat()
        self.depot.enregistrer_facture(self.facture)
        self._appliquer_verrou()
        self.enregistre.emit()

    def marquer_payee(self) -> None:
        if self.facture.statut == "brouillon":
            alerter(self, "Facture en brouillon",
                    "Émettez d'abord la facture avant de la marquer payée.")
            return
        if self.facture.statut == "annulée":
            alerter(self, "Facture annulée",
                    "Cette facture a été annulée par un avoir : elle n'attend "
                    "plus de règlement.")
            return
        from datetime import date as _date
        # Le mode et la date viennent des champs : sans cette reprise, le
        # règlement affiché à l'écran serait perdu au moment même où on le
        # valide, et la facture porterait la date du jour à sa place.
        self._collecter()
        self.facture.statut = "payée"
        if not self.facture.date_paiement:
            from PySide6.QtCore import QDate
            self.facture.date_paiement = _date.today().isoformat()
            self.date_paiement.setDate(QDate.currentDate())
        self.depot.enregistrer_facture(self.facture)
        self._appliquer_verrou()
        self.enregistre.emit()
        annoncer(self, f"Facture {self.facture.numero} marquée payée")

    def creer_avoir(self) -> None:
        if self.facture.statut == "brouillon":
            alerter(self, "Facture en brouillon",
                    "Un brouillon se modifie ou se supprime ; l'avoir sert à annuler "
                    "une facture déjà émise.")
            return
        if self.facture.type == "avoir":
            alerter(self, "Déjà un avoir", "On n'établit pas un avoir sur un avoir.")
            return
        if not confirmer(self, "Créer un avoir",
                         f"Établir un avoir annulant la facture {self.facture.numero} ?"):
            return
        avoir = self.depot.enregistrer_facture(generer_avoir(self.depot, self.facture))
        self.facture.statut = "annulée"
        self.depot.enregistrer_facture(self.facture)
        self.enregistre.emit()
        informer(self, "Avoir créé",
                 f"L'avoir {avoir.numero} a été créé et la facture "
                 f"{self.facture.numero} passe en « annulée ».")
        self.ferme.emit()

    def _retour(self) -> None:
        if self.facture.modifiable:
            self.enregistrer()
        self.ferme.emit()

    # --- impression ------------------------------------------------------

    def _rendu(self) -> RenduDocument | None:
        if self.facture.modifiable and not self.enregistrer():
            return None
        return RenduDocument(self.depot, self.facture)

    def apercu(self) -> None:
        rendu = self._rendu()
        if rendu is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogue = QPrintPreviewDialog(printer, self)
        dialogue.setWindowTitle(f"Aperçu — {rendu.intitule()}")
        dialogue.resize(900, 1000)
        dialogue.paintRequested.connect(rendu.peindre)
        dialogue.exec()

    def exporter_pdf(self) -> None:
        rendu = self._rendu()
        if rendu is None:
            return
        defaut = str(self.depot.d_pdf / rendu.nom_fichier())
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer la facture en PDF",
                                                defaut, "Document PDF (*.pdf)")
        if chemin:
            rendu.vers_pdf(Path(chemin))
            annoncer(self, f"Facture enregistrée en PDF : {Path(chemin).name}")

    def imprimer(self) -> None:
        rendu = self._rendu()
        if rendu is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogue = QPrintDialog(printer, self)
        dialogue.setWindowTitle(f"Imprimer — {rendu.intitule()}")
        if dialogue.exec() == QDialog.DialogCode.Accepted:
            rendu.peindre(printer)


# --- liste des factures ---------------------------------------------------


class VueFactures(VueListe):
    nom = "Factures"
    mot_element = "facture"
    libelle_nouveau = "Facture directe"
    libelle_modifier = "Ouvrir"
    indication_recherche = "Numéro, client, objet…"

    ouvrir_demande = Signal(object)

    def __init__(self, depot, parent=None):
        self.statut = liste_deroulante(
            ["Tous les statuts"] + STATUTS_FACTURE + ["en retard"])
        super().__init__(depot, parent)
        self.statut.currentIndexChanged.connect(self.rafraichir)

    def filtres(self):
        return [self.statut]

    def libelle(self, facture):
        return f"la facture {facture.numero}"

    def archiver(self, facture, definitif):
        self.depot.supprimer_facture(facture.id, definitif=definitif)

    def desarchiver(self, facture):
        self.depot.restaurer_facture(facture.id)

    def colonnes(self):
        return [
            Colonne("Numéro", lambda f: f.numero, largeur=110, gras=True,
                    cle=lambda f: cle_numero(f.numero)),
            Colonne("Date", lambda f: date_fr(f.date_facture), largeur=92,
                    alignement=CENTRE, cle=lambda f: f.date_facture or ""),
            Colonne("Type", lambda f: LIBELLES_FACTURE.get(f.type, f.type), largeur=145),
            Colonne("Client", lambda f: self.depot.nom_client(f.client_id), largeur=175),
            Colonne("Objet", lambda f: f.objet),
            Colonne("Total HT", lambda f: euros(f.totaux().total_ht), largeur=110,
                    alignement=DROITE, cle=lambda f: f.totaux().total_ht),
            Colonne("TTC", lambda f: euros(f.totaux().total_ttc), largeur=110,
                    alignement=DROITE, cle=lambda f: f.totaux().total_ttc),
            Colonne("Échéance", lambda f: date_fr(f.date_echeance), largeur=92,
                    alignement=CENTRE, cle=lambda f: f.date_echeance or ""),
            Colonne("Statut", lambda f: ("en retard" if f.en_retard else f.statut),
                    largeur=90, alignement=CENTRE),
        ]

    def charger(self):
        statut = self.statut.currentText()
        return self.depot.factures(
            recherche=self.recherche.text().strip(),
            statut="" if statut.startswith("Tous") else statut,
            supprimes=self.archives)

    def nouveau(self):
        if not self.depot.clients():
            alerter(self, "Aucun client", "Créez d'abord un client.")
            return
        self.ouvrir_demande.emit(generer_facture_directe(self.depot))

    def modifier(self):
        facture = self.selection()
        if facture is not None:
            self.ouvrir_demande.emit(facture)


