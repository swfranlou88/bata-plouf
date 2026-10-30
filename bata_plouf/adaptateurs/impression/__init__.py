"""Mise en page, impression et export PDF des devis et des factures.

    gabarit.py (hors paquet)  les réglages choisis par l'utilisateur
    styles.py                 couleurs dérivées, mesures, échappement
    blocs.py                  un bloc du document = une fonction
    document.py               l'ordre des blocs
    rendu.py                  pagination, pied de page, PDF, impression
"""

from .blocs import Contexte
from .document import corps_html, html_document
from .rendu import RenduDocument

__all__ = ["Contexte", "RenduDocument", "corps_html", "html_document"]
