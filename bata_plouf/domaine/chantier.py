"""Le chantier, c'est le devis lu du côté de l'atelier.

Rien ne s'enregistre ici : il n'y a pas de fiche chantier à tenir à jour en
plus du devis, qui porte déjà le client, l'adresse et le détail des travaux.
Ce module répond à deux questions qu'on se pose la veille d'attaquer, et il y
répond en recalculant tout à la demande :

  — combien d'heures ? Un ouvrage dit ce qu'il consomme par unité, main
    d'œuvre comprise : 2,93 heures pour un mètre carré de bouchage en agglos.
  — quoi emmener ? Le même ouvrage dit aussi son agglo, son sable et son
    ciment. Multipliés par les quantités du devis et additionnés d'un poste
    à l'autre, cela fait la liste de courses.

Quand la composition manque, le temps de pose se lit encore dans les notes de
la fiche — « Main d'oeuvre 2.930 », comme l'ancien logiciel l'écrivait. Et
quand on ne sait rien, on le dit : un ouvrage sans temps connu est annoncé à
part plutôt que compté pour zéro.
"""

import re
import unicodedata
from dataclasses import dataclass, field

# « Main d'oeuvre 2.930 », « Main doeuvre  0.879 » : la vieille note, écrite à
# la main, qui sert encore de repli quand la composition manque.
MOTIF_HEURES = re.compile(r"main\s*d[’']?\s*oeuvre\s*:?\s*([0-9]+(?:[.,][0-9]+)?)")
# Ce qui se compte en heures plutôt qu'en sacs ou en mètres.
UNITES_TEMPS = {"h", "hr", "heure", "heures"}
MOTIF_MAIN_OEUVRE = re.compile(r"main\s*d[’']?\s*oeuvre")
HEURES_PAR_JOUR = 7.0


def cle(texte) -> str:
    """De quoi rapprocher deux écritures d'un même ouvrage.

    Sans casse, sans accent et sans « œ » : les documents repris nomment
    leurs lignes en toutes lettres, sans garder le lien vers la fiche, et
    c'est le libellé qui doit les retrouver.
    """
    plat = unicodedata.normalize("NFD", str(texte or "").casefold())
    plat = "".join(c for c in plat if not unicodedata.combining(c))
    return " ".join(plat.replace("œ", "oe").replace("æ", "ae").split())


def est_du_temps(unite) -> bool:
    """Un composant compté en heures : de la main d'œuvre ou une machine."""
    return cle(unite) in UNITES_TEMPS


def est_main_doeuvre(designation) -> bool:
    """La main d'œuvre, par opposition aux heures de machine."""
    return bool(MOTIF_MAIN_OEUVRE.search(cle(designation)))


def heures_notees(article) -> float | None:
    """Le temps que les notes de la fiche annoncent, ou None."""
    if article is None:
        return None
    trouve = MOTIF_HEURES.search(cle(getattr(article, "notes_internes", "")))
    if not trouve:
        return None
    try:
        return float(trouve.group(1).replace(",", "."))
    except ValueError:
        return None


def heures_unitaires(article) -> float | None:
    """Les heures de main d'œuvre d'une unité d'ouvrage.

    La composition d'abord, car c'est elle qui sert à bâtir le prix ; les
    notes ensuite, pour les fiches que l'ancien logiciel n'a pas détaillées.
    """
    if article is None:
        return None
    composants = getattr(article, "composants", None) or []
    heures = sum(c.quantite for c in composants
                 if est_du_temps(c.unite) and est_main_doeuvre(c.designation))
    if heures:
        return round(heures, 4)
    return heures_notees(article)


@dataclass
class Poste:
    """Une ligne de devis et le temps de main d'œuvre qu'elle demande."""

    designation: str
    quantite: float
    unite: str
    heures_unitaires: float

    @property
    def heures(self) -> float:
        return (self.quantite or 0.0) * (self.heures_unitaires or 0.0)


@dataclass
class Fourniture:
    """Un matériau à prévoir, avec sa quantité, tous postes confondus."""

    designation: str
    quantite: float
    unite: str


@dataclass
class Machine:
    """Des heures qui ne sont pas des heures d'homme : tractopelle, nacelle."""

    designation: str
    heures: float


@dataclass
class Preparation:
    """Ce qu'il faut emmener et le temps qu'il faudra y passer."""

    postes: list[Poste] = field(default_factory=list)
    fournitures: list[Fourniture] = field(default_factory=list)
    machines: list[Machine] = field(default_factory=list)
    # Les lignes chiffrées dont on ne sait pas le temps : à dire, pas à taire.
    sans_temps: list[str] = field(default_factory=list)

    @property
    def heures(self) -> float:
        return sum(p.heures for p in self.postes)

    @property
    def journees(self) -> float:
        """Le temps en journées de sept heures."""
        return self.heures / HEURES_PAR_JOUR

    @property
    def complet(self) -> bool:
        return not self.sans_temps


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
            # Le premier gagne : la bibliothèque porte des doublons, et un
            # ouvrage rangé en tête vaut mieux qu'un tirage au sort.
            self.par_nom.setdefault(cle(article.designation), article)

    def article_de(self, ligne):
        lien = getattr(ligne, "article_id", "")
        if lien and lien in self.par_id:
            return self.par_id[lien]
        return self.par_nom.get(cle(getattr(ligne, "designation", "")))


class _Cumul:
    """Un panier qui additionne les quantités d'un même article."""

    def __init__(self):
        self.par_cle: dict[str, list] = {}

    def ajouter(self, designation: str, quantite: float, unite: str) -> None:
        # L'unité fait partie de la clé : on n'additionne pas des sacs et des
        # mètres cubes sous prétexte qu'ils portent le même nom.
        repere = (cle(designation), cle(unite))
        if repere in self.par_cle:
            self.par_cle[repere][1] += quantite
        else:
            self.par_cle[repere] = [designation, quantite, unite]

    def liste(self) -> list[tuple[str, float, str]]:
        return [(nom, round(quantite, 4), unite)
                for nom, quantite, unite in self.par_cle.values()]


def preparation(document, catalogue: Catalogue) -> Preparation:
    """Les heures et la matière d'un devis ou d'une facture, recalculées."""
    resultat = Preparation()
    fournitures, machines = _Cumul(), _Cumul()

    for ligne in getattr(document, "lignes", []):
        if not getattr(ligne, "chiffree", False):
            continue
        article = catalogue.article_de(ligne)
        quantite = float(getattr(ligne, "quantite", 0) or 0)
        unite = getattr(ligne, "unite", "") or ""
        designation = getattr(ligne, "designation", "") or ""
        composants = getattr(article, "composants", None) or []

        if composants:
            for composant in composants:
                total = (composant.quantite or 0.0) * quantite
                if not est_du_temps(composant.unite):
                    fournitures.ajouter(composant.designation, total,
                                        composant.unite)
                elif not est_main_doeuvre(composant.designation):
                    machines.ajouter(composant.designation, total, "h")

        if article is not None and getattr(article, "type", "") == "matériau":
            # Un matériau posé en ligne directe sur le devis : du sable livré,
            # un sac de ciment vendu tel quel.
            fournitures.ajouter(designation, quantite, unite)
            continue

        temps = heures_unitaires(article)
        if temps is None:
            resultat.sans_temps.append(designation)
            continue
        resultat.postes.append(Poste(designation, quantite, unite, temps))

    resultat.fournitures = [Fourniture(*f) for f in fournitures.liste()]
    resultat.machines = [Machine(nom, heures)
                         for nom, heures, _ in machines.liste()]
    return resultat
