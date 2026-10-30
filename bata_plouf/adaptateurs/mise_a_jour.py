"""Mise à jour de l'application depuis les publications GitHub.

Le code source vit dans le dépôt ; l'application construite, elle, est déposée
en pièce jointe d'une « release ». L'API de GitHub donne l'adresse de la
dernière en une requête, ce qui permet à l'application de se mettre à jour
toute seule — sans que l'utilisateur ait à connaître git, ni même à ouvrir un
navigateur.

C'est le seul endroit du logiciel qui accède au réseau, et seulement quand on
le lui demande.

Deux détails qui font que cela fonctionne vraiment sur macOS :

  - un fichier téléchargé par l'application n'est pas mis en quarantaine,
    contrairement à un téléchargement par un navigateur : la nouvelle version
    démarre donc sans avertissement ;
  - l'archive est dézippée avec « ditto » et non avec le module zipfile, qui
    perdrait les liens symboliques et le bit exécutable, et laisserait un
    bundle incapable de démarrer.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .. import __version__

URL_API = "https://api.github.com/repos/{depot}/releases/latest"
DELAI = 10  # secondes
ENTETES = {
    "User-Agent": f"Bata-plouf/{__version__}",
    "Accept": "application/vnd.github+json",
}


class ErreurMiseAJour(Exception):
    """Toute raison pour laquelle la mise à jour ne peut pas aboutir."""


@dataclass
class VersionDistante:
    etiquette: str
    numero: tuple
    url: str
    taille: int
    notes: str
    publiee_le: str

    @property
    def taille_lisible(self) -> str:
        return f"{self.taille / 1024 / 1024:.0f} Mo" if self.taille else "taille inconnue"


# --- comparaison de versions ----------------------------------------------


def en_numero(texte: str) -> tuple:
    """« v1.2.3 » -> (1, 2, 3). Ce qui n'est pas un nombre est ignoré."""
    morceaux = re.findall(r"\d+", texte or "")
    return tuple(int(m) for m in morceaux[:4]) or (0,)


def version_installee() -> tuple:
    return en_numero(__version__)


def plus_recente(distante: tuple, locale: tuple) -> bool:
    """Compare en complétant la plus courte par des zéros."""
    longueur = max(len(distante), len(locale))
    gauche = distante + (0,) * (longueur - len(distante))
    droite = locale + (0,) * (longueur - len(locale))
    return gauche > droite


# --- où tourne-t-on ? -----------------------------------------------------


def application_installee() -> Path | None:
    """Le bundle .app en cours d'exécution, ou None si on tourne depuis les sources.

    Mettre à jour n'a de sens que pour une application construite : depuis le
    code source, c'est git qui fait le travail.
    """
    if not getattr(sys, "frozen", False):
        return None
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix == ".app":
            return parent
    return None


def suffixe_attendu() -> str:
    """Le bout de nom qui identifie l'archive faite pour cette machine."""
    systemes = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}
    machines = {"arm64": "arm64", "aarch64": "arm64",
                "x86_64": "x86_64", "AMD64": "x86_64"}
    systeme = systemes.get(platform.system(), platform.system().lower())
    machine = machines.get(platform.machine(), platform.machine().lower())
    return f"{systeme}-{machine}"


# --- interrogation de GitHub ---------------------------------------------


def chercher(depot: str) -> VersionDistante | None:
    """Renvoie la dernière version publiée si elle est plus récente, sinon None.

    « depot » s'écrit « compte/nom », comme dans l'adresse GitHub.
    """
    depot = (depot or "").strip().strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", depot):
        raise ErreurMiseAJour(
            "Le dépôt doit s'écrire « compte/nom », par exemple « dupont/bata-plouf ».")

    requete = urllib.request.Request(URL_API.format(depot=depot), headers=ENTETES)
    try:
        with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
            publication = json.load(reponse)
    except urllib.error.HTTPError as erreur:
        if erreur.code == 404:
            raise ErreurMiseAJour(
                "Aucune version publiée sur ce dépôt, ou dépôt introuvable.") from erreur
        raise ErreurMiseAJour(f"GitHub a répondu : {erreur.code}") from erreur
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erreur:
        raise ErreurMiseAJour(f"Connexion impossible : {erreur}") from erreur

    etiquette = publication.get("tag_name") or publication.get("name") or ""
    numero = en_numero(etiquette)
    if not plus_recente(numero, version_installee()):
        return None

    attendu = suffixe_attendu()
    pieces = publication.get("assets") or []
    choisie = next((p for p in pieces
                    if attendu in p.get("name", "").lower()
                    and p.get("name", "").endswith(".zip")), None)
    if choisie is None:
        raise ErreurMiseAJour(
            f"La version {etiquette} existe, mais aucune archive ne correspond à "
            f"cette machine ({attendu}).")

    return VersionDistante(
        etiquette=etiquette,
        numero=numero,
        url=choisie.get("browser_download_url", ""),
        taille=int(choisie.get("size") or 0),
        notes=(publication.get("body") or "").strip(),
        publiee_le=(publication.get("published_at") or "")[:10],
    )


# --- téléchargement -------------------------------------------------------


def telecharger(version: VersionDistante, progression=None) -> Path:
    """Rapatrie l'archive dans un dossier temporaire.

    « progression » est appelée avec un pourcentage entier, pour l'affichage.
    """
    dossier = Path(tempfile.mkdtemp(prefix="bata-plouf-maj-"))
    archive = dossier / "mise-a-jour.zip"
    requete = urllib.request.Request(version.url, headers=ENTETES)
    try:
        with urllib.request.urlopen(requete, timeout=DELAI) as reponse, \
                open(archive, "wb") as sortie:
            total = int(reponse.headers.get("Content-Length") or version.taille or 0)
            recu = 0
            while True:
                morceau = reponse.read(262144)
                if not morceau:
                    break
                sortie.write(morceau)
                recu += len(morceau)
                if progression and total:
                    progression(min(100, int(recu * 100 / total)))
    except (urllib.error.URLError, TimeoutError, OSError) as erreur:
        shutil.rmtree(dossier, ignore_errors=True)
        raise ErreurMiseAJour(f"Téléchargement interrompu : {erreur}") from erreur
    return archive


def extraire(archive: Path) -> Path:
    """Dézippe et renvoie le bundle .app trouvé dans l'archive."""
    destination = archive.parent / "contenu"
    destination.mkdir(exist_ok=True)
    if platform.system() == "Darwin":
        # ditto préserve les liens symboliques et les droits ; zipfile non.
        resultat = subprocess.run(
            ["ditto", "-x", "-k", str(archive), str(destination)],
            capture_output=True, text=True)
        if resultat.returncode != 0:
            raise ErreurMiseAJour(f"Archive illisible : {resultat.stderr.strip()}")
    else:
        shutil.unpack_archive(str(archive), str(destination))

    bundles = [c for c in destination.rglob("*.app") if c.is_dir()]
    if not bundles:
        raise ErreurMiseAJour("L'archive ne contient aucune application.")
    return min(bundles, key=lambda c: len(c.parts))


# --- installation ---------------------------------------------------------

SCRIPT_REMPLACEMENT = """#!/bin/sh
# Attend que l'application ait quitté, la remplace, puis la relance.
while kill -0 {pid} 2>/dev/null; do sleep 0.3; done
sleep 0.5
rm -rf "{ancienne}.remplacee" 2>/dev/null
mv "{ancienne}" "{ancienne}.remplacee" 2>/dev/null || exit 1
if ! mv "{nouvelle}" "{ancienne}"; then
    mv "{ancienne}.remplacee" "{ancienne}"   # on remet tout en place
    exit 1
fi
rm -rf "{ancienne}.remplacee"
xattr -dr com.apple.quarantine "{ancienne}" 2>/dev/null
open "{ancienne}"
"""


def installer(nouvelle: Path, ancienne: Path) -> None:
    """Lance le remplacement et rend la main : à l'appelant de quitter.

    Une application ne peut pas s'écraser elle-même pendant qu'elle tourne. Un
    petit script détaché attend donc sa fin, échange les deux bundles et
    relance. S'il échoue, il remet l'ancienne version en place plutôt que de
    laisser l'utilisateur sans rien.
    """
    if not os.access(ancienne.parent, os.W_OK):
        raise ErreurMiseAJour(
            f"Pas le droit d'écrire dans {ancienne.parent}. Déplacez l'application "
            "dans votre dossier Applications personnel, ou remplacez-la à la main.")

    script = nouvelle.parent / "remplacer.sh"
    script.write_text(SCRIPT_REMPLACEMENT.format(
        pid=os.getpid(), ancienne=str(ancienne), nouvelle=str(nouvelle)),
        encoding="utf-8")
    script.chmod(0o755)
    subprocess.Popen(["/bin/sh", str(script)], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
