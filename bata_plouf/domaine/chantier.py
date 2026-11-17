"""Le chantier, c'est le devis lu du côté de l'atelier.

Rien ne s'enregistre ici : il n'y a pas de fiche chantier à tenir à jour en
plus du devis, qui porte déjà le client, l'adresse et le détail des travaux.
Ce module répond à deux questions qu'on se pose la veille d'attaquer, et il y
répond en recalculant tout à la demande :

  — combien d'heures ? La composition d'un ouvrage dit son temps à l'unité,
    « Main d'oeuvre 2.930 » pour un mètre carré ; multiplié par la quantité
    du devis, cela fait les heures du poste.
  — quelle matière ? Les matériaux posés en ligne directe sur le devis, avec
    leurs quantités.

Ce que la reprise de l'ancien logiciel ne donne pas, on ne l'invente pas : un
ouvrage dont la composition ne porte pas de temps est annoncé comme tel,
plutôt que compté pour zéro.
"""

import re
import unicodedata
from dataclasses import dataclass, field

# « Main d'oeuvre 2.930 », « Main doeuvre  0.879 » : l'ancien logiciel écrivait
# la composition à la main, avec ou sans apostrophe, en heures décimales.
MOTIF_HEURES = re.compile(r"main\s*d[’']?\s*oeuvre\s*:?\s*([0-9]+(?:[.,][0-9]+)?)")


def cle(texte) -> str:
    """De quoi rapprocher deux écritures d'un même ouvrage.

    Sans casse, sans accent et sans « œ » : les documents repris nomment
    leurs lignes en toutes lettres, sans garder le lien vers la fiche, et
    c'est le libellé qui doit les retrouver.
    """
    plat = unicodedata.normalize("NFD", str(texte or "").casefold())
    plat = "".join(c for c in plat if not unicodedata.combining(c))
    return " ".join(plat.replace("œ", "oe").replace("æ", "ae").split())


def heures_unitaires(article) -> float | None:
    """Le temps que demande une unité d'ouvrage, ou None s'il est inconnu."""
    if article is None:
        return None
    trouve = MOTIF_HEURES.search(cle(getattr(article, "notes_internes", "")))
    if not trouve:
        return None
    try:
        return float(trouve.group(1).replace(",", "."))
    except ValueError:
        return None


@dataclass
class Poste:
    """Une ligne de devis et le temps qu'elle demande."""

    designation: str
    quantite: float
    unite: str
    heures_unitaires: float

    @property
    def heures(self) -> float:
        return (self.quantite or 0.0) * (self.heures_unitaires or 0.0)


@dataclass
class Fourniture:
    """Un matériau à prévoir, avec sa quantité."""

    designation: str
    quantite: float
    unite: str


@dataclass
class Preparation:
    """Ce qu'il faut emmener et le temps qu'il faudra y passer."""

    postes: list[Poste] = field(default_factory=list)
    fournitures: list[Fourniture] = field(default_factory=list)
    # Les lignes chiffrées dont on ne sait pas le temps : à dire, pas à taire.
    sans_temps: list[str] = field(default_factory=list)

    @property
    def heures(self) -> float:
        return sum(p.heures for p in self.postes)

    @property
    def journees(self) -> float:
        """Le temps en journées de sept heures, comme on le compte au devis."""
        return self.heures / HEURES_PAR_JOUR

    @property
    def complet(self) -> bool:
        return not self.sans_temps


HEURES_PAR_JOUR = 7.0


class Catalogue:
    """Les articles rangés pour retrouver l'ouvrage derrière une ligne.

    Par identifiant d'abord, c'est le lien sûr ; par libellé ensuite, car les
    documents repris de l'ancien logiciel n'ont pas ce lien et ne nous
    laissent que le nom écrit sur la ligne.
    """

    def __init__(self, articles):
        self.par_id = {}
        self.par_nom = {}
        for article in articles:
            self.par_id[article.id] = article
            nom = cle(article.designation)
            # Le premier gagne : la bibliothèque porte des doublons, et un
            # ouvrage rangé en tête vaut mieux qu'un tirage au sort.
            self.par_nom.setdefault(nom, article)

    def article_de(self, ligne):
        lien = getattr(ligne, "article_id", "")
        if lien and lien in self.par_id:
            return self.par_id[lien]
        return self.par_nom.get(cle(getattr(ligne, "designation", "")))


def preparation(document, catalogue: Catalogue) -> Preparation:
    """Les heures et la matière d'un devis ou d'une facture, recalculées."""
    resultat = Preparation()
    for ligne in getattr(document, "lignes", []):
        if not getattr(ligne, "chiffree", False):
            continue
        article = catalogue.article_de(ligne)
        quantite = float(getattr(ligne, "quantite", 0) or 0)
        unite = getattr(ligne, "unite", "") or ""
        designation = getattr(ligne, "designation", "") or ""

        if article is not None and getattr(article, "type", "") == "matériau":
            resultat.fournitures.append(Fourniture(designation, quantite, unite))
            continue

        temps = heures_unitaires(article)
        if temps is None:
            resultat.sans_temps.append(designation)
            continue
        resultat.postes.append(Poste(designation, quantite, unite, temps))
    return resultat
