"""Pagination, pied de page répété, export PDF et impression."""

import math
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt, QUrl
from PySide6.QtGui import (
    QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QTextDocument,
)
from PySide6.QtPrintSupport import QPrinter

from ...domaine.gabarit import Gabarit
from .blocs import Contexte
from .document import corps_html
from .styles import mm_en_px, palette

NOIR = QColor("#000000")
HAUTEUR_PIED_MM = 13.0
# De quoi ne pas frôler le bas de page en étirant le tableau : une page qui
# déborde d'un millimètre en fait naître une seconde, vide.
RESPIRATION_MM = 6.0


class RenduDocument:
    """Dessine un devis ou une facture sur une imprimante ou dans un PDF.

    Le corps est du HTML mis en page par Qt ; l'en-tête de page et le pied sont
    peints à la main, ce qui est la seule façon de répéter les mentions légales
    et le numéro de page sur chaque feuille.
    """

    def __init__(self, depot, document):
        self.depot = depot
        self.document = document
        self.gabarit: Gabarit = getattr(depot, "gabarit", None) or Gabarit()

    # --- préparation -----------------------------------------------------

    def _preparer(self, printer: QPrinter) -> tuple[QTextDocument, QRectF, QRectF]:
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageMargins(QMarginsF(*self.gabarit.marges()),
                               QPageLayout.Unit.Millimeter)

        dpi = printer.resolution()
        # La zone imprimable, ramenée à son coin : sur une imprimante comme
        # dans un PDF, Qt place déjà l'origine du peintre à l'intérieur des
        # marges. Peindre à paintRect.left() les compterait une seconde fois —
        # le document glissait vers la droite d'autant que la marge gauche, et
        # il ne restait rien à droite.
        imprimable = QRectF(printer.pageLayout().paintRectPixels(dpi))
        zone = QRectF(0, 0, imprimable.width(), imprimable.height())
        pied = mm_en_px(HAUTEUR_PIED_MM, dpi) if self.gabarit.afficher_pied else 0
        corps = QRectF(0, 0, zone.width(), zone.height() - pied)

        doc = QTextDocument()
        doc.documentLayout().setPaintDevice(printer)
        police = QFont(self.gabarit.police or "Helvetica")
        police.setPointSizeF(self.gabarit.taille_police)
        doc.setDefaultFont(police)
        # Un devis s'imprime en noir sur blanc, même si le système est en
        # thème sombre : sans cette règle Qt écrirait en blanc sur blanc.
        doc.setDefaultStyleSheet("body, p, div, span, td, th, li { color: #000000; }")

        logo = self.depot.societe.logo
        if logo and Path(logo).exists():
            image = QImage(logo)
            if not image.isNull():
                doc.addResource(QTextDocument.ResourceType.ImageResource,
                                QUrl("logo"), image)

        def html(remplissage: int = 0) -> str:
            return corps_html(Contexte(
                depot=self.depot, document=self.document, gabarit=self.gabarit,
                dpi=dpi, remplissage_px=remplissage))

        doc.setHtml(html())
        self._etirer_tableau(doc, corps, dpi, html)
        doc.setPageSize(QSizeF(corps.width(), corps.height()))
        return doc, zone, corps

    def _etirer_tableau(self, doc: QTextDocument, corps: QRectF, dpi: int,
                        html) -> None:
        """Fait descendre le cadre du tableau jusqu'au bas de la page.

        Qt rend exactement la hauteur demandée en remplissage : une mesure de
        la hauteur naturelle suffit donc à calculer ce qui manque, et la
        seconde mise en page tombe juste. On vérifie quand même qu'aucune page
        n'est née de l'opération, et on renonce si c'est le cas — un devis
        correct vaut mieux qu'un beau cadre suivi d'une page blanche.
        """
        if not (self.gabarit.classique and self.gabarit.tableau_pleine_hauteur):
            return
        page = corps.height()
        if page <= 0:
            return

        doc.setTextWidth(corps.width())
        hauteur = doc.size().height()
        pages = max(1, math.ceil((hauteur - 1) / page))
        manque = pages * page - mm_en_px(RESPIRATION_MM, dpi) - hauteur
        if manque < 4:
            return

        # Le « px » des feuilles de style vaut toujours 1/96 de pouce, quelle
        # que soit la définition de l'imprimante : sur une sortie à 1200 ppp,
        # demander la hauteur en points de l'appareil la multiplierait par
        # douze et demi, et ferait naître une dizaine de pages vides.
        doc.setHtml(html(int(manque * 96.0 / dpi)))
        doc.setPageSize(QSizeF(corps.width(), page))
        if doc.pageCount() > pages:
            doc.setHtml(html())

    # --- pied de page ----------------------------------------------------

    def _lignes_pied(self) -> list[str]:
        if self.gabarit.pied_personnalise:
            return self.gabarit.pied_personnalise.split("\n")[:3]

        s = self.depot.societe
        premiere = " · ".join(filter(None, [
            f"SIRET {s.siret}" if s.siret else "",
            f"APE {s.code_ape}" if s.code_ape else "",
            f"TVA {s.tva_intracom}" if s.tva_intracom else "",
            f"RCS {s.rcs}" if s.rcs else "",
        ]))
        contrat = f" n° {s.assurance_contrat}" if s.assurance_contrat else ""
        seconde = " · ".join(filter(None, [
            f"Assurance décennale : {s.assurance_nom}{contrat}" if s.assurance_nom else "",
            f"Couverture : {s.assurance_couverture}" if s.assurance_couverture else "",
            s.qualifications,
        ]))
        return [l for l in (premiere, seconde) if l]

    def _peindre_pied(self, peintre: QPainter, zone: QRectF, page: int, total: int) -> None:
        if not self.gabarit.afficher_pied:
            return
        couleurs = palette(self.gabarit)
        dpi = peintre.device().logicalDpiY()
        haut = zone.bottom() - mm_en_px(HAUTEUR_PIED_MM, dpi) + 2

        peintre.save()
        peintre.setPen(QColor(couleurs.accent))
        peintre.drawLine(int(zone.left()), int(haut), int(zone.right()), int(haut))

        police = QFont(self.gabarit.police or "Helvetica")
        police.setPointSizeF(max(6.0, self.gabarit.taille_police - 2.5))
        peintre.setFont(police)
        peintre.setPen(QColor(couleurs.gris_clair))

        haut_gauche = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        hauteur_ligne = peintre.fontMetrics().height()
        for index, texte in enumerate(self._lignes_pied()):
            rect = QRectF(zone.left(), haut + 4 + index * hauteur_ligne, zone.width(), 200)
            peintre.drawText(rect, haut_gauche, texte)

        if self.gabarit.afficher_numero_page:
            rect = QRectF(zone.left(), haut + 4, zone.width(), 200)
            peintre.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop),
                             f"Page {page}/{total}")
        peintre.restore()

    # --- rendu -----------------------------------------------------------

    def peindre(self, printer: QPrinter) -> int:
        doc, zone, corps = self._preparer(printer)
        total = max(1, doc.pageCount())

        peintre = QPainter()
        if not peintre.begin(printer):
            raise RuntimeError("Impossible d'ouvrir le périphérique d'impression.")
        try:
            for index in range(total):
                if index:
                    printer.newPage()
                peintre.save()
                peintre.setPen(NOIR)
                peintre.setClipRect(QRectF(0, 0, corps.width(), corps.height()))
                peintre.translate(0, -index * corps.height())
                doc.drawContents(peintre)
                peintre.restore()
                self._peindre_pied(peintre, zone, index + 1, total)
        finally:
            peintre.end()
        return total

    def vers_pdf(self, chemin: Path, haute_qualite: bool = True) -> Path:
        """Écrit le devis en PDF.

        « haute_qualite » est inutilement lent pour un aperçu à l'écran, qui se
        contente de la résolution écran et se régénère à chaque réglage.
        """
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution if haute_qualite
                           else QPrinter.PrinterMode.ScreenResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(chemin))
        printer.setDocName(self.intitule())
        self.peindre(printer)
        return chemin

    def intitule(self) -> str:
        """« Devis D2026-0001 » ou « Facture d'acompte F2026-0003 »."""
        libelle = getattr(self.document, "libelle_type", None) or self.gabarit.titre_document
        return f"{libelle} {self.document.numero}".strip()

    def nom_fichier(self) -> str:
        client = self.depot.nom_client(self.document.client_id)
        bout = "".join(c for c in client if c.isalnum() or c in " -_").strip().replace(" ", "-")
        defaut = "facture" if hasattr(self.document, "date_facture") else "devis"
        numero = self.document.numero or defaut
        return f"{numero}{('-' + bout) if bout else ''}.pdf"
