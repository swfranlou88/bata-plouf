"""Adaptateur système : ce qui diffère entre macOS, Windows et Linux.

Tout ce qui dépend du système passe par ici, pour que le reste du logiciel
l'ignore. C'est le seul fichier à relire le jour où l'on vise une autre
plateforme.
"""

import os
import platform
import subprocess
from pathlib import Path

NOMS = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}


def systeme() -> str:
    """« macOS », « Windows » ou « Linux »."""
    return NOMS.get(platform.system(), platform.system())


def ouvrir_dossier(chemin: Path | str) -> bool:
    """Ouvre un dossier dans l'explorateur de fichiers du système."""
    chemin = str(chemin)
    courant = platform.system()
    try:
        if courant == "Darwin":
            subprocess.run(["open", chemin], check=False)
        elif courant == "Windows":
            os.startfile(chemin)  # noqa: S606 — l'API Windows pour cela
        else:
            subprocess.run(["xdg-open", chemin], check=False)
    except (OSError, AttributeError):
        return False
    return True


def dossier_documents() -> Path:
    """Le dossier Documents de l'utilisateur, quel que soit le système.

    Sur Windows le nom du dossier suit la langue de l'interface ; on retombe
    sur le dossier personnel si « Documents » n'existe pas.
    """
    maison = Path.home()
    for nom in ("Documents", "Documenti", "Dokumente", "Documentos"):
        candidat = maison / nom
        if candidat.is_dir():
            return candidat
    return maison
