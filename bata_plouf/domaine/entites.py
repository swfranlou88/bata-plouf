"""Les entités du métier : clients, chantiers, articles, devis, factures.

Ce module est le cœur de l'hexagone : il ne connaît ni Qt, ni les fichiers, ni
le format de l'ancien logiciel. Les montants y sont stockés en float parce que
les fichiers JSON doivent rester lisibles à l'œil, mais tout calcul passe par
Decimal (voir calculs.py).
"""

import uuid
from dataclasses import dataclass, field, asdict, fields
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from .calculs import Totaux, calculer_totaux, sou

# --- vocabulaire métier ---------------------------------------------------

UNITES = ["u", "ml", "m²", "m³", "kg", "t", "h", "j", "forfait", "ens"]

# 20 % neuf · 10 % rénovation de logement de plus de 2 ans
# 5,5 % rénovation énergétique · 0 % autoliquidation (sous-traitance)
TAUX_TVA = [20.0, 10.0, 5.5, 0.0]

STATUTS_DEVIS = ["brouillon", "envoyé", "accepté", "refusé", "expiré", "annulé"]
STATUTS_FACTURE = ["brouillon", "émise", "payée", "annulée"]

# Les quatre façons de facturer un chantier, plus l'avoir qui corrige une
# facture déjà émise — une facture émise ne se modifie pas, elle s'annule.
TYPES_FACTURE = ["totale", "acompte", "situation", "solde", "directe", "avoir"]
LIBELLES_FACTURE = {
    "totale": "Facture",
    "acompte": "Facture d'acompte",
    "situation": "Situation de travaux",
    "solde": "Facture de solde",
    "directe": "Facture",
    "avoir": "Avoir",
}
MODES_PAIEMENT = ["", "Virement", "Chèque", "Espèces", "Carte bancaire", "Prélèvement"]
STATUTS_CHANTIER = ["prévu", "en cours", "terminé", "annulé"]
TYPES_ARTICLE = ["matériau", "main d'œuvre", "ouvrage"]
FAMILLES = [
    "Gros œuvre", "Maçonnerie", "Fondations", "Dallage", "Enduits",
    "Couverture", "Démolition", "Terrassement", "Carrelage", "Divers",
]


def nouvel_id() -> str:
    return uuid.uuid4().hex[:12]


def maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Archivable:
    """Socle des fiches qui se suppriment en douceur.

    Rien n'est jamais effacé d'un geste : « supprimer » horodate le champ
    supprime_le, l'élément sort des listes et reste récupérable. La
    suppression définitive existe, mais seulement depuis la corbeille et
    seulement si plus rien ne pointe vers la fiche.
    """

    supprime_le: str

    @property
    def supprime(self) -> bool:
        return bool(self.supprime_le)

# --- entités --------------------------------------------------------------


@dataclass
class Societe:
    """Les paramètres de l'entreprise, repris sur chaque devis imprimé."""

    nom: str = ""
    forme_juridique: str = ""
    adresse: str = ""
    cp: str = ""
    ville: str = ""
    telephone: str = ""
    email: str = ""
    siret: str = ""
    code_ape: str = ""
    tva_intracom: str = ""
    capital: str = ""
    rcs: str = ""
    logo: str = ""  # chemin vers une image

    # Mentions légales obligatoires sur un devis de bâtiment
    assurance_nom: str = ""
    assurance_contrat: str = ""
    assurance_couverture: str = "France métropolitaine"
    qualifications: str = ""  # RGE, Qualibat…

    iban: str = ""
    bic: str = ""

    validite_jours: int = 90
    delai_paiement_jours: int = 30
    taux_tva_defaut: float = 10.0
    acompte_defaut_pct: float = 30.0
    conditions_paiement: str = (
        "Acompte à la commande, solde à la fin des travaux. "
        "Paiement par chèque ou virement à réception de facture."
    )
    mentions_devis: str = (
        "Devis gratuit, valable pour la durée indiquée ci-dessus. "
        "Tout travail supplémentaire fera l'objet d'un avenant accepté par le client."
    )
    # Mentions obligatoires sur une facture (art. L441-10 et D441-5 du code de commerce)
    mentions_facture: str = (
        "En cas de retard de paiement, une pénalité égale à trois fois le taux "
        "d'intérêt légal sera appliquée, ainsi qu'une indemnité forfaitaire pour "
        "frais de recouvrement de 40 €. Pas d'escompte pour paiement anticipé."
    )

    # Dépôt GitHub où l'application va chercher ses mises à jour, au format
    # « compte/nom ». Vide : la recherche est désactivée.
    depot_mises_a_jour: str = ""
    # "auto" installe au lancement sans rien demander · "demander" pose la
    # question une fois par jour · "jamais" coupe tout accès au réseau.
    mises_a_jour: str = "auto"

    # --- comptabilité ---
    # Comptes du plan comptable général, modifiables : chaque cabinet a ses
    # habitudes, et un export qui ne tombe pas sur les bons comptes oblige le
    # comptable à tout ressaisir.
    journal_ventes: str = "VE"
    compte_client: str = "411000"
    compte_ventes: str = "704000"
    comptes_tva: dict = field(default_factory=lambda: {
        "20.0": "445710",
        "10.0": "445711",
        "5.5": "445712",
        "0.0": "",
    })

    def compte_tva(self, taux: float) -> str:
        """Compte de TVA collectée pour ce taux, vide si autoliquidation."""
        return (self.comptes_tva or {}).get(str(float(taux)), "")

    @property
    def ligne_adresse(self) -> str:
        return " · ".join(p for p in [self.adresse, f"{self.cp} {self.ville}".strip()] if p)


@dataclass
class Client(Archivable):
    id: str = field(default_factory=nouvel_id)
    # Identifiant lisible, attribué à l'enregistrement : c'est celui qu'on se
    # dit au téléphone. L'id ci-dessus ne sort jamais de la machine.
    numero: str = ""
    type: str = "particulier"  # particulier | professionnel
    civilite: str = ""
    nom: str = ""
    prenom: str = ""
    societe: str = ""
    siret: str = ""
    adresse: str = ""
    cp: str = ""
    ville: str = ""
    telephone: str = ""
    mobile: str = ""
    email: str = ""
    notes: str = ""
    # Trace de la reprise de l'ancien logiciel, pour pouvoir retrouver l'origine
    ref_externe: str = ""
    supprime_le: str = ""
    cree_le: str = field(default_factory=maintenant)
    modifie_le: str = field(default_factory=maintenant)

    @property
    def libelle(self) -> str:
        if self.type == "professionnel" and self.societe:
            return self.societe
        nom = " ".join(p for p in [self.civilite, self.prenom, self.nom] if p)
        return nom or self.societe or "(sans nom)"

    @property
    def adresse_complete(self) -> str:
        return "\n".join(p for p in [self.adresse, f"{self.cp} {self.ville}".strip()] if p)

    def correspond(self, texte: str) -> bool:
        t = texte.lower()
        cibles = [self.numero, self.nom, self.prenom, self.societe, self.ville,
                  self.cp, self.telephone, self.mobile, self.email, self.ref_externe]
        return any(t in (c or "").lower() for c in cibles)


@dataclass
class Chantier(Archivable):
    id: str = field(default_factory=nouvel_id)
    client_id: str = ""
    libelle: str = ""
    adresse: str = ""
    cp: str = ""
    ville: str = ""
    date_debut: str = ""
    date_fin: str = ""
    statut: str = "prévu"
    notes: str = ""
    ref_externe: str = ""
    supprime_le: str = ""
    cree_le: str = field(default_factory=maintenant)
    modifie_le: str = field(default_factory=maintenant)

    @property
    def adresse_complete(self) -> str:
        return "\n".join(p for p in [self.adresse, f"{self.cp} {self.ville}".strip()] if p)


@dataclass
class Article(Archivable):
    """Une ligne de la bibliothèque de prix : matériau, main d'œuvre ou ouvrage."""

    id: str = field(default_factory=nouvel_id)
    reference: str = ""
    designation: str = ""
    detail: str = ""
    type: str = "matériau"
    fournisseur: str = ""
    famille: str = "Maçonnerie"
    unite: str = "u"
    prix_achat: float = 0.0
    prix_vente: float = 0.0
    taux_tva: float = 10.0
    ref_externe: str = ""
    supprime_le: str = ""
    cree_le: str = field(default_factory=maintenant)
    modifie_le: str = field(default_factory=maintenant)

    @property
    def benefice(self) -> float:
        """Ce que rapporte une unité vendue."""
        return round((self.prix_vente or 0) - (self.prix_achat or 0), 2)

    @property
    def marge_pct(self) -> float:
        if not self.prix_achat:
            return 0.0
        return round((self.prix_vente - self.prix_achat) / self.prix_achat * 100, 1)

    def correspond(self, texte: str) -> bool:
        t = texte.lower()
        return any(t in (c or "").lower()
                   for c in [self.reference, self.designation, self.detail,
                             self.famille, self.fournisseur])


@dataclass
class Ligne:
    """Une ligne de devis.

    type == "section"   : un titre de lot (Gros œuvre, Enduits…), sous-total calculé
    type == "prestation": une ligne chiffrée
    type == "texte"     : un commentaire libre, non chiffré
    """

    id: str = field(default_factory=nouvel_id)
    type: str = "prestation"
    designation: str = ""
    detail: str = ""
    quantite: float = 1.0
    unite: str = "u"
    prix_unitaire: float = 0.0
    taux_tva: float = 10.0
    remise_pct: float = 0.0
    article_id: str = ""

    # --- situations de travaux ---
    # Sur une facture de situation, chaque ligne dit quelle ligne du devis
    # elle fait avancer et jusqu'où. C'est ce qui permet de facturer poste
    # par poste sans jamais perdre le compte de ce qui reste.
    ligne_origine: str = ""
    avancement_pct: float = 0.0
    # "" ordinaire · "avancement" part de travaux · "deduction_acompte"
    nature: str = ""

    @property
    def chiffree(self) -> bool:
        return self.type == "prestation"

    @property
    def total_ht(self) -> Decimal:
        if not self.chiffree:
            return Decimal("0.00")
        brut = Decimal(str(self.quantite or 0)) * Decimal(str(self.prix_unitaire or 0))
        net = brut * (Decimal("1") - Decimal(str(self.remise_pct or 0)) / Decimal("100"))
        return sou(net)


@dataclass
class Devis(Archivable):
    id: str = field(default_factory=nouvel_id)
    numero: str = ""
    client_id: str = ""
    chantier_id: str = ""
    objet: str = ""
    # Adresse des travaux saisie directement, pour un petit chantier
    # qui ne mérite pas sa fiche. La fiche chantier, si elle existe,
    # a la priorité.
    adresse_chantier: str = ""
    date_devis: str = field(default_factory=lambda: date.today().isoformat())
    validite_jours: int = 90
    statut: str = "brouillon"
    lignes: list[Ligne] = field(default_factory=list)
    remise_globale_pct: float = 0.0
    acompte_pct: float = 30.0
    conditions: str = ""
    mentions: str = ""
    notes_internes: str = ""
    date_reponse: str = ""
    ref_externe: str = ""
    supprime_le: str = ""
    cree_le: str = field(default_factory=maintenant)
    modifie_le: str = field(default_factory=maintenant)

    @property
    def date_document(self) -> str:
        return self.date_devis

    @property
    def date_validite(self) -> str:
        """Date limite de validité, au format ISO."""
        try:
            d = date.fromisoformat(self.date_devis)
        except ValueError:
            return ""
        from datetime import timedelta
        return (d + timedelta(days=self.validite_jours or 0)).isoformat()

    def totaux(self) -> "Totaux":
        return calculer_totaux(self)


@dataclass
class Facture(Archivable):
    """Une facture. Même forme qu'un devis, avec ce qui lui est propre.

    Une facture passée à « émise » n'est plus modifiable : c'est une obligation
    comptable, et la seule façon de la corriger est d'émettre un avoir.
    """

    id: str = field(default_factory=nouvel_id)
    numero: str = ""
    type: str = "directe"
    devis_id: str = ""
    client_id: str = ""
    chantier_id: str = ""
    objet: str = ""
    # Adresse des travaux saisie directement, pour un petit chantier
    # qui ne mérite pas sa fiche. La fiche chantier, si elle existe,
    # a la priorité.
    adresse_chantier: str = ""
    date_facture: str = field(default_factory=lambda: date.today().isoformat())
    echeance_jours: int = 30
    statut: str = "brouillon"
    lignes: list[Ligne] = field(default_factory=list)
    remise_globale_pct: float = 0.0
    # Toujours nul sur une facture : un acompte y est une ligne, pas un calcul
    acompte_pct: float = 0.0
    # Pourcentage d'acompte, ou avancement cumulé pour une situation
    pourcentage: float = 0.0
    numero_situation: int = 0
    conditions: str = ""
    mentions: str = ""
    notes_internes: str = ""
    mode_paiement: str = ""
    date_emission: str = ""
    date_paiement: str = ""
    # Pour un avoir : la facture qu'il annule
    facture_source_id: str = ""
    ref_externe: str = ""
    supprime_le: str = ""
    cree_le: str = field(default_factory=maintenant)
    modifie_le: str = field(default_factory=maintenant)

    @property
    def date_document(self) -> str:
        return self.date_facture

    @property
    def date_echeance(self) -> str:
        try:
            d = date.fromisoformat(self.date_facture)
        except ValueError:
            return ""
        from datetime import timedelta
        return (d + timedelta(days=self.echeance_jours or 0)).isoformat()

    @property
    def modifiable(self) -> bool:
        return self.statut == "brouillon"

    @property
    def libelle_type(self) -> str:
        if self.type == "situation" and self.numero_situation:
            return f"Situation de travaux n° {self.numero_situation}"
        return LIBELLES_FACTURE.get(self.type, "Facture")

    @property
    def en_retard(self) -> bool:
        if self.statut != "émise" or not self.date_echeance:
            return False
        return date.fromisoformat(self.date_echeance) < date.today()

    def totaux(self) -> "Totaux":
        return calculer_totaux(self)

# --- (dé)sérialisation ----------------------------------------------------


def en_dict(objet) -> dict:
    return asdict(objet)


def depuis_dict(classe, donnees: dict):
    """Construit une entité en ignorant les champs inconnus.

    Indispensable pour qu'un fichier écrit par une version plus récente du
    logiciel reste lisible, et pour absorber les champs en trop d'un import.
    """
    if donnees is None:
        return classe()
    connus = {f.name for f in fields(classe)}
    filtre = {k: v for k, v in donnees.items() if k in connus}
    if classe in (Devis, Facture) and "lignes" in donnees:
        filtre["lignes"] = [depuis_dict(Ligne, l) for l in donnees.get("lignes") or []]
    return classe(**filtre)
