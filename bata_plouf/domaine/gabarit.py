"""Réglages de présentation du devis imprimé.

Données pures, sans Qt ni HTML : le module d'impression les consomme, le
stockage les enregistre dans « modele-devis.json », et l'écran « Modèle du
devis » les modifie. Séparer ces réglages du métier permet de changer
l'apparence d'un devis sans jamais toucher aux calculs.
"""

from dataclasses import dataclass, field


@dataclass
class Gabarit:
    # --- couleur et typographie ---
    # Une seule couleur d'accent : les fonds de bloc et de section en sont
    # dérivés, et la couleur du texte posé dessus est calculée pour rester
    # lisible. L'utilisateur ne peut donc pas fabriquer un devis illisible.
    couleur: str = "#333333"
    police: str = "Helvetica"
    taille_police: float = 9.5

    # --- en-tête ---
    titre_document: str = "DEVIS"
    titre_facture: str = "FACTURE"
    logo_largeur_mm: float = 38.0
    logo_a_droite: bool = True
    afficher_bloc_chantier: bool = True

    # --- textes libres ---
    texte_introduction: str = ""
    texte_conclusion: str = ""

    # --- colonnes du tableau ---
    colonne_unite: bool = True
    colonne_tva: bool = True
    colonne_remise: bool = False
    numeroter_lignes: bool = False
    afficher_detail_lignes: bool = True
    afficher_sous_totaux_sections: bool = True

    # --- blocs de bas de page ---
    afficher_recap_tva: bool = True
    afficher_acompte: bool = True
    afficher_conditions: bool = True
    afficher_mentions: bool = True
    afficher_signature: bool = True
    # Rappel du marché en bas des factures issues d'un devis
    afficher_recapitulatif_marche: bool = True
    texte_signature: str = (
        "Date et signature du client, précédées de la mention "
        "« devis reçu avant exécution des travaux »."
    )
    hauteur_signature_mm: float = 22.0

    # --- pied de page répété sur chaque page ---
    afficher_pied: bool = True
    afficher_numero_page: bool = True
    pied_personnalise: str = ""

    # --- marges, en millimètres ---
    marge_gauche: float = 14.0
    marge_haute: float = 12.0
    marge_droite: float = 14.0
    marge_basse: float = 16.0

    def marges(self) -> tuple[float, float, float, float]:
        return (self.marge_gauche, self.marge_haute, self.marge_droite, self.marge_basse)


# --- modèles tout faits, pour démarrer sans tout régler -------------------

MODELES_PREDEFINIS: dict[str, dict] = {
    "Classique": {
        "couleur": "#333333", "police": "Helvetica", "taille_police": 9.5,
        "colonne_remise": False, "numeroter_lignes": False,
        "marge_gauche": 14.0, "marge_haute": 12.0, "marge_droite": 14.0, "marge_basse": 16.0,
    },
    "Bleu bâtiment": {
        "couleur": "#1f4e79", "police": "Helvetica", "taille_police": 9.5,
        "colonne_remise": False, "numeroter_lignes": True,
    },
    "Terre cuite": {
        "couleur": "#8a4b2a", "police": "Georgia", "taille_police": 10.0,
        "colonne_remise": False, "numeroter_lignes": True,
    },
    "Compact": {
        "couleur": "#333333", "police": "Helvetica", "taille_police": 8.5,
        "afficher_detail_lignes": False, "colonne_remise": False,
        "marge_gauche": 11.0, "marge_haute": 10.0, "marge_droite": 11.0, "marge_basse": 13.0,
    },
    "Détaillé": {
        "couleur": "#2f5d3a", "police": "Helvetica", "taille_police": 9.5,
        "colonne_remise": True, "numeroter_lignes": True,
        "afficher_detail_lignes": True, "afficher_sous_totaux_sections": True,
    },
}

# Qt substitue automatiquement la police la plus proche quand elle manque
# (Helvetica devient Arial sous Windows, une sans-serif sous Linux).
POLICES = [
    "Helvetica", "Arial", "Verdana", "Tahoma",
    "Times New Roman", "Georgia", "Courier New",
    "DejaVu Sans", "Liberation Sans",
]

COULEURS_SUGGEREES = [
    ("Gris ardoise", "#333333"),
    ("Bleu bâtiment", "#1f4e79"),
    ("Terre cuite", "#8a4b2a"),
    ("Vert chantier", "#2f5d3a"),
    ("Bordeaux", "#7b2233"),
    ("Noir", "#000000"),
]


# --- dérivation des couleurs ---------------------------------------------


def _rvb(couleur: str) -> tuple[int, int, int]:
    texte = (couleur or "#333333").lstrip("#")
    if len(texte) == 3:
        texte = "".join(c * 2 for c in texte)
    try:
        return int(texte[0:2], 16), int(texte[2:4], 16), int(texte[4:6], 16)
    except (ValueError, IndexError):
        return 51, 51, 51


def _hex(rvb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(c))) for c in rvb))


def eclaircir(couleur: str, proportion: float) -> str:
    """Mélange la couleur avec du blanc ; 0 = inchangée, 1 = blanc."""
    r, v, b = _rvb(couleur)
    melange = lambda c: c + (255 - c) * proportion  # noqa: E731
    return _hex((melange(r), melange(v), melange(b)))


def luminance(couleur: str) -> float:
    r, v, b = _rvb(couleur)
    return (0.299 * r + 0.587 * v + 0.114 * b) / 255


def texte_lisible_sur(couleur: str) -> str:
    """Noir ou blanc, selon ce qui se lit le mieux sur ce fond."""
    return "#000000" if luminance(couleur) > 0.6 else "#ffffff"
