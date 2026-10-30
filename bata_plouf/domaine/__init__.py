"""Le cœur de l'hexagone : le métier du maçon, et rien d'autre.

Aucun module de ce paquet n'importe Qt, ne lit un fichier ni ne connaît
l'ancien logiciel. Il peut tourner et se tester seul.

    entites.py      les fiches : client, chantier, article, devis, facture
    calculs.py      totaux, ventilation de la TVA, sous-totaux de section
    formats.py      montants, nombres et dates à la française
    gabarit.py      les réglages de présentation des documents
    facturation.py  acompte, situation, solde, avoir
    ports.py        ce que le domaine attend de l'extérieur
"""

from .calculs import LigneTVA, Totaux, calculer_totaux, sous_totaux_sections, sou
from .entites import (
    Archivable, Article, Chantier, Client, Devis, FAMILLES, Facture,
    LIBELLES_FACTURE, Ligne, MODES_PAIEMENT, STATUTS_CHANTIER, STATUTS_DEVIS,
    STATUTS_FACTURE, Societe, TAUX_TVA, TYPES_ARTICLE, TYPES_FACTURE, UNITES,
    depuis_dict, en_dict, maintenant, nouvel_id,
)
from .formats import date_fr, date_iso, euros, nombre, taux_tva_txt
from .gabarit import Gabarit
from .ports import Depot, JournalFactures, RegistreVentes, SourceDocuments

__all__ = [
    "Archivable", "Article", "Chantier", "Client", "Depot", "Devis", "FAMILLES",
    "Facture", "Gabarit", "JournalFactures", "RegistreVentes", "LIBELLES_FACTURE", "Ligne",
    "LigneTVA", "MODES_PAIEMENT", "STATUTS_CHANTIER", "STATUTS_DEVIS",
    "STATUTS_FACTURE", "Societe", "SourceDocuments", "TAUX_TVA", "TYPES_ARTICLE",
    "TYPES_FACTURE", "Totaux", "UNITES", "calculer_totaux", "date_fr", "date_iso",
    "depuis_dict", "en_dict", "euros", "maintenant", "nombre", "nouvel_id", "sou",
    "sous_totaux_sections", "taux_tva_txt",
]
