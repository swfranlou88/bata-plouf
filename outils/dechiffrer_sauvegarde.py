"""Rouvre une sauvegarde chiffrée, sans passer par le logiciel.

Une sauvegarde qui ne se rouvre qu'avec l'outil qui l'a faite n'est pas une
sauvegarde : le jour où l'on en a besoin, c'est souvent que la machine, elle,
n'est plus là. Ce script ne dépend que de Python et de la phrase de passe.

    uv run python outils/dechiffrer_sauvegarde.py bata-plouf-2026-11.zip.enc

Il rend un fichier .zip ordinaire, celui qu'on glisse dans Paramètres →
« Restaurer depuis une archive ». On peut aussi lui donner une adresse :

    uv run python outils/dechiffrer_sauvegarde.py https://github.com/.../fichier.zip.enc

La phrase de passe se tape à l'invite, jamais sur la ligne de commande : elle
y resterait dans l'historique du terminal.
"""

import getpass
import sys
import tempfile
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


def recuperer(source: str) -> tuple[Path, Path | None]:
    """Le fichier à ouvrir, et le dossier temporaire à effacer après."""
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

    source, abri = recuperer(sys.argv[1])
    try:
        if not source.is_file():
            print(f"Fichier introuvable : {source}")
            return 1
        if len(sys.argv) > 2:
            destination = Path(sys.argv[2]).expanduser()
        else:
            nom = source.name[:-4] if source.name.endswith(".enc") else source.name + ".zip"
            destination = Path.cwd() / nom

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
