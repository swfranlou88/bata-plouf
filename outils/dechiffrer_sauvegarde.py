"""Rouvre une sauvegarde chiffrée, sans passer par le logiciel.

Une sauvegarde qui ne se rouvre qu'avec l'outil qui l'a faite n'est pas une
sauvegarde : le jour où l'on en a besoin, c'est souvent que la machine, elle,
n'est plus là. Ce script ne dépend que de Python et de la phrase de passe.

    uv run python outils/dechiffrer_sauvegarde.py bata-plouf-2026-11.zip.enc

Il rend un fichier .zip ordinaire, celui qu'on glisse dans Paramètres →
« Importer un zip ». Trois façons de lui désigner la sauvegarde :

    … dechiffrer_sauvegarde.py bata-plouf-2026-11.zip.enc      un fichier local
    … dechiffrer_sauvegarde.py https://…/fichier.zip.enc       une adresse
    … dechiffrer_sauvegarde.py compte/depot bata-plouf-2026-11.zip.enc

La troisième va chercher la pièce dans la release « sauvegardes » du dépôt,
privé compris. Il faut alors un jeton de lecture, dans la variable
JETON_GITHUB ou dans le sauvegarde.env du dossier de données :

    JETON_GITHUB=github_pat_… uv run python outils/dechiffrer_sauvegarde.py \
        compte/bata-plouf-sauvegardes bata-plouf-2026-11.zip.enc

Phrase de passe et jeton ne se tapent jamais sur la ligne de commande : ils
resteraient dans l'historique du terminal.
"""

import getpass
import sys
import tempfile
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


def jeton_connu() -> str:
    """Le jeton, pris dans l'environnement ou dans le dossier de données."""
    import os

    from bata_plouf.adaptateurs import environnement
    from bata_plouf.adaptateurs.depot_fichiers import DOSSIER_DEFAUT

    return (os.environ.get(environnement.JETON)
            or environnement.lire(DOSSIER_DEFAUT).get(environnement.JETON, ""))


def recuperer(arguments: list[str]) -> tuple[Path, Path | None]:
    """Le fichier à ouvrir, et le dossier temporaire à effacer après."""
    from bata_plouf.adaptateurs.sauvegarde_en_ligne import (
        ErreurSauvegarde, telecharger,
    )

    source = arguments[0]
    if "/" in source and not source.startswith(("http://", "https://")) \
            and not Path(source).expanduser().exists():
        # « compte/depot nom-du-fichier » : on passe par l'API, seule voie
        # vers un dépôt privé.
        if len(arguments) < 2:
            raise SystemExit("Indiquez aussi le nom du fichier à rapatrier.")
        jeton = jeton_connu()
        if not jeton:
            raise SystemExit(
                "Aucun jeton : renseignez JETON_GITHUB, ou lancez cet outil "
                "sur la machine où le logiciel est installé.")
        abri = Path(tempfile.mkdtemp(prefix="bata-plouf-sauvegarde-"))
        print(f"Téléchargement de {arguments[1]} depuis {source}…")
        try:
            return telecharger(source, jeton, arguments[1],
                               abri / arguments[1]), abri
        except ErreurSauvegarde as erreur:
            raise SystemExit(str(erreur)) from erreur

    if not source.startswith(("http://", "https://")):
        return Path(source).expanduser(), None
    abri = Path(tempfile.mkdtemp(prefix="bata-plouf-sauvegarde-"))
    cible = abri / source.rstrip("/").split("/")[-1]
    print(f"Téléchargement de {source}…")
    urllib.request.urlretrieve(source, cible)
    return cible, abri


def main() -> int:
    import shutil

    from bata_plouf.adaptateurs.coffre import ErreurCoffre, dechiffrer

    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    source, abri = recuperer(sys.argv[1:])
    try:
        if not source.is_file():
            print(f"Fichier introuvable : {source}")
            return 1
        nom = (source.name[:-4] if source.name.endswith(".enc")
               else source.name + ".zip")
        destination = Path.cwd() / nom

        if not source.read_bytes()[:8] == b"BPLOUF1\n":
            # Une sauvegarde déposée sans phrase de passe : c'est déjà un zip.
            if destination.resolve() != source.resolve():
                destination.write_bytes(source.read_bytes())
            print(f"{destination} — {destination.stat().st_size // 1024} Ko")
            print("Cette sauvegarde n'est pas chiffrée : c'est une archive "
                  "ordinaire, à reprendre depuis Paramètres → « Importer un "
                  "zip ».")
            return 0

        phrase = getpass.getpass("Phrase de passe : ")
        print("Déchiffrement… (une seconde, la dérivation de la clé est lente "
              "par construction)")
        try:
            clair = dechiffrer(source.read_bytes(), phrase)
        except ErreurCoffre as erreur:
            print(erreur)
            return 1
        destination.write_bytes(clair)
    finally:
        if abri is not None:
            shutil.rmtree(abri, ignore_errors=True)

    print(f"{destination} — {destination.stat().st_size // 1024} Ko")
    print("À restaurer depuis Paramètres → « Restaurer depuis une archive ».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
