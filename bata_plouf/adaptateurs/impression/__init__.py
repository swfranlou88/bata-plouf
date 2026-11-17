"""Mise en page, impression et export PDF des devis et des factures.

    gabarit.py (hors paquet)  les réglages choisis par l'utilisateur
    styles.py                 couleurs dérivées, mesures, échappement
    blocs.py                  un bloc du document = une fonction
    blocs_classique.py        les mêmes, en devis d'artisan
    document.py               l'ordre des blocs, et le choix entre les deux
    rendu.py                  pagination, pied de page, PDF, impression
    feuille_chantier.py       la liste de fournitures qu'on emporte
"""

from .blocs import Contexte
from .document import corps_html, html_document
from .feuille_chantier import html_feuille
from .rendu import RenduDocument

__all__ = ["Contexte", "RenduDocument", "corps_html", "html_document",
           "html_feuille"]
