"""Archive d'échange : toute la base dans un seul fichier zip.

Sert à porter les données d'un poste à l'autre, à les confier au comptable,
ou à les remettre en place après un incident. L'archive ne contient que du
JSON — ce que le logiciel sait relire — et laisse de côté les PDF déjà
imprimés, qui se regénèrent, ainsi que les sauvegardes, qui sont propres au
poste.

L'import est l'opération la plus lourde de conséquences du logiciel : il
remplace la base entière. Trois précautions l'encadrent donc :

  - on n'extrait que les fichiers qu'on attend, et on reconstruit soi-même
    leur destination : une archive peut contenir « ../../ailleurs » ;
  - on vérifie que chaque fichier se relit avant de toucher à quoi que ce
    soit, et on déplie dans un dossier provisoire ;
  - on sauvegarde l'existant d'abord, et on dit où.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import __version__

# Carte d'identité de l'archive, pour ne pas déplier n'importe quel zip.
MANIFESTE = "bata-plouf.json"
SIGNATURE = "Bata-plouf"

# Les fichiers de données, à la racine du dossier.
FICHIERS_RACINE = ("parametres.json", "modele-devis.json", "clients.json",
                   "chantiers.json", "articles.json", "compteurs.json")
# Et les dossiers à un fichier par pièce.
DOSSIERS = ("devis", "factures")

# Sans ces deux-là, il n'y a pas de base à reprendre.
INDISPENSABLES = ("clients.json",)

# Le logo n'est pas du JSON, mais sans lui l'en-tête des devis arriverait nu
# sur le nouveau poste. C'est la seule image acceptée, et c'est nous qui la
# nommons : le nom inscrit dans l'archive ne sert jamais de chemin.
EXTENSIONS_LOGO = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
NOMS_LOGO = tuple("logo" + extension for extension in EXTENSIONS_LOGO)

# Une archive de données reste petite : la base réelle de l'entreprise, neuf
# ans d'historique, pèse moins de cinq mégaoctets de JSON. Au-delà de cette
# borne, on refuse plutôt que de remplir le disque en dépliant.
TAILLE_MAXIMALE = 500 * 1024 * 1024


class ErreurArchive(Exception):
    """L'archive n'est pas exploitable, et rien n'a été modifié."""


@dataclass
class Inventaire:
    """Ce qu'une archive annonce, lu sans rien extraire."""

    chemin: Path
    version: str = ""
    cree_le: str = ""
    comptes: dict = field(default_factory=dict)
    retenus: int = 0
    logo: bool = False
    ecartes: list[str] = field(default_factory=list)
    problemes: list[str] = field(default_factory=list)

    @property
    def exploitable(self) -> bool:
        return not self.problemes

    def resume(self) -> str:
        if not self.comptes:
            return "archive vide"
        ordre = ("clients", "chantiers", "articles", "devis", "factures")
        return " · ".join(f"{self.comptes[c]} {c}" for c in ordre
                          if self.comptes.get(c))


@dataclass
class Rapport:
    """Ce que l'import a fait."""

    sauvegarde: Path | None
    comptes: dict
    logo: bool = False
    ecartes: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)


def nom_propose() -> str:
    return f"Bata-plouf-{datetime.now():%Y-%m-%d_%Hh%M}.zip"


def _logo_de(depot) -> Path | None:
    """Le fichier du logo, s'il y en a un et qu'il est d'un format connu."""
    chemin = Path(getattr(depot.societe, "logo", "") or "")
    if chemin.is_file() and chemin.suffix.lower() in EXTENSIONS_LOGO:
        return chemin
    return None


def _comptes(depot) -> dict:
    """Ce que contient la base, corbeille comprise."""
    return {
        "clients": len(depot.clients()) + len(depot.clients(supprimes=True)),
        "chantiers": len(depot.chantiers()) + len(depot.chantiers(supprimes=True)),
        "articles": len(depot.articles()) + len(depot.articles(supprimes=True)),
        "devis": len(depot.devis()) + len(depot.devis(supprimes=True)),
        "factures": len(depot.factures()) + len(depot.factures(supprimes=True)),
    }


# --- écriture -------------------------------------------------------------

def ecrire(depot, destination: Path | str) -> Path:
    """Écrit toute la base dans une archive zip, et rend son chemin."""
    destination = Path(destination)
    if destination.is_dir():
        destination = destination / nom_propose()
    if destination.suffix.lower() != ".zip":
        destination = destination.with_suffix(".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)

    manifeste = {
        "logiciel": SIGNATURE,
        "version": __version__,
        "cree_le": datetime.now().isoformat(timespec="seconds"),
        "contenu": _comptes(depot),
    }

    # On écrit à côté puis on renomme : une archive interrompue en route ne
    # doit pas se faire passer pour une archive complète.
    provisoire = destination.with_name(destination.name + ".tmp")
    try:
        with zipfile.ZipFile(provisoire, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=9) as archive:
            archive.writestr(MANIFESTE,
                             json.dumps(manifeste, ensure_ascii=False, indent=2))
            for nom in FICHIERS_RACINE:
                fichier = depot.racine / nom
                if fichier.is_file():
                    archive.write(fichier, nom)
            for dossier in DOSSIERS:
                for fichier in sorted((depot.racine / dossier).glob("*.json")):
                    archive.write(fichier, f"{dossier}/{fichier.name}")
            logo = _logo_de(depot)
            if logo is not None:
                archive.write(logo, "logo" + logo.suffix.lower())
        os.replace(provisoire, destination)
    except OSError:
        Path(provisoire).unlink(missing_ok=True)
        raise
    return destination


# --- lecture --------------------------------------------------------------

def _membres_acceptes(archive: zipfile.ZipFile) -> tuple[dict, list[str]]:
    """Trie les membres de l'archive : ceux qu'on extrait, ceux qu'on laisse.

    Le nom inscrit dans un zip ne sert jamais à construire un chemin : il
    peut valoir « ../../ailleurs » ou un chemin absolu, et viser hors du
    dossier de données. On ne retient donc que les noms attendus, et la
    destination est reconstruite à partir d'eux.
    """
    retenus: dict[str, zipfile.ZipInfo] = {}
    ecartes: list[str] = []
    for membre in archive.infolist():
        if membre.is_dir():
            continue
        nom = membre.filename.replace("\\", "/")
        morceaux = [m for m in nom.split("/") if m not in ("", ".")]
        if nom.startswith("/") or ".." in morceaux:
            ecartes.append(nom)
        elif len(morceaux) == 1 and morceaux[0] in FICHIERS_RACINE + NOMS_LOGO:
            retenus[morceaux[0]] = membre
        elif (len(morceaux) == 2 and morceaux[0] in DOSSIERS
              and morceaux[1].endswith(".json")):
            retenus[f"{morceaux[0]}/{morceaux[1]}"] = membre
        elif morceaux != [MANIFESTE]:
            ecartes.append(nom)
    return retenus, ecartes


def inspecter(chemin: Path | str) -> Inventaire:
    """Dit ce que contient une archive, sans rien extraire ni modifier."""
    chemin = Path(chemin)
    inventaire = Inventaire(chemin=chemin)
    if not chemin.is_file():
        inventaire.problemes.append("Ce fichier n'existe pas.")
        return inventaire

    try:
        with zipfile.ZipFile(chemin) as archive:
            abime = archive.testzip()
            if abime is not None:
                inventaire.problemes.append(f"Archive abîmée : « {abime} ».")
                return inventaire

            retenus, ecartes = _membres_acceptes(archive)
            inventaire.retenus, inventaire.ecartes = len(retenus), ecartes

            total = sum(m.file_size for m in retenus.values())
            if total > TAILLE_MAXIMALE:
                inventaire.problemes.append(
                    f"Archive démesurée pour des données de devis "
                    f"({total / 1024 / 1024:.0f} Mo dépliés).")
                return inventaire

            if MANIFESTE in archive.namelist():
                try:
                    manifeste = json.loads(archive.read(MANIFESTE))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    manifeste = {}
                if manifeste.get("logiciel") == SIGNATURE:
                    inventaire.version = str(manifeste.get("version", ""))
                    inventaire.cree_le = str(manifeste.get("cree_le", ""))

            manquants = [n for n in INDISPENSABLES if n not in retenus]
            if manquants:
                inventaire.problemes.append(
                    "Ce zip ne ressemble pas à des données Bata-plouf : "
                    + ", ".join(manquants) + " n'y figure pas.")
                return inventaire

            # Un JSON illisible découvert après remplacement serait une perte
            # de données : on relit tout maintenant.
            comptes = {"devis": 0, "factures": 0}
            for cle, membre in sorted(retenus.items()):
                if cle in NOMS_LOGO:
                    inventaire.logo = True
                    continue
                try:
                    contenu = json.loads(archive.read(membre))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    inventaire.problemes.append(f"Fichier illisible : « {cle} ».")
                    continue
                if "/" in cle:
                    comptes[cle.split("/")[0]] += 1
                elif isinstance(contenu, list):
                    comptes[cle.removesuffix(".json")] = len(contenu)
            inventaire.comptes = comptes
    except (zipfile.BadZipFile, OSError) as erreur:
        inventaire.problemes.append(f"Fichier illisible comme archive : {erreur}")
    return inventaire


def restaurer(depot, chemin: Path | str) -> Rapport:
    """Remplace la base par le contenu de l'archive.

    Sauvegarde l'existant avant toute chose, déplie dans un dossier
    provisoire, et ne touche à la base que si tout s'est bien passé.
    """
    chemin = Path(chemin)
    inventaire = inspecter(chemin)
    if not inventaire.exploitable:
        raise ErreurArchive("\n".join(inventaire.problemes))

    sauvegarde = depot.creer_sauvegarde()
    abri = Path(tempfile.mkdtemp(prefix="bata-plouf-import-",
                                 dir=depot.racine.parent))
    try:
        with zipfile.ZipFile(chemin) as archive:
            retenus, _ = _membres_acceptes(archive)
            for cle, membre in retenus.items():
                cible = abri / cle
                cible.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(membre) as source, open(cible, "wb") as sortie:
                    shutil.copyfileobj(source, sortie)

        # Tout est déplié et relu : on peut remplacer.
        for dossier in DOSSIERS:
            shutil.rmtree(depot.racine / dossier, ignore_errors=True)
            (depot.racine / dossier).mkdir(parents=True, exist_ok=True)
        for nom in FICHIERS_RACINE + NOMS_LOGO:
            (depot.racine / nom).unlink(missing_ok=True)
        for cle in retenus:
            shutil.copy2(abri / cle, depot.racine / cle)
    finally:
        shutil.rmtree(abri, ignore_errors=True)

    depot.charger()
    # Le chemin du logo inscrit dans les paramètres est celui de l'ancien
    # poste, où il ne mène plus nulle part : on le fait pointer sur la copie
    # que l'archive vient de déposer.
    repris = next((c for c in retenus if c in NOMS_LOGO), None)
    if repris:
        societe = depot.societe
        societe.logo = str(depot.racine / repris)
        depot.enregistrer_societe(societe)

    return Rapport(sauvegarde=sauvegarde, comptes=_comptes(depot),
                   logo=bool(repris), ecartes=inventaire.ecartes,
                   anomalies=list(depot.anomalies))
