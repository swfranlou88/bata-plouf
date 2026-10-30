"""Compile l'installateur en une petite application double-cliquable.

    uv run python outils/construire_installateur.py [compte/depot]

Le résultat pèse une centaine de kilo-octets : c'est lui qu'on donne à
l'utilisateur la première fois, ou le jour où l'application ne démarre plus.
Il va chercher la dernière version publiée et l'installe.
"""

import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

NOM = "Installer Bata-plouf"
IDENTIFIANT = "fr.bataplouf.installateur"


def depot_choisi() -> str:
    from bata_plouf import DEPOT_GITHUB

    depot = (sys.argv[1] if len(sys.argv) > 1 else DEPOT_GITHUB).strip().strip("/")
    if "/" not in depot:
        raise SystemExit(
            "Indiquez le dépôt GitHub, au format « compte/nom » :\n"
            "    uv run python outils/construire_installateur.py compte/bata-plouf\n"
            "ou renseignez DEPOT_GITHUB dans bata_plouf/__init__.py.")
    return depot


def compiler(depot: str) -> Path:
    source = (RACINE / "outils" / "installateur.applescript").read_text(encoding="utf-8")
    source = source.replace("__DEPOT__", depot)

    cible = RACINE / "dist" / f"{NOM}.app"
    shutil.rmtree(cible, ignore_errors=True)
    cible.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".applescript", encoding="utf-8",
                                     delete=False) as fichier:
        fichier.write(source)
        temporaire = Path(fichier.name)
    try:
        subprocess.run(["osacompile", "-o", str(cible), str(temporaire)], check=True)
    finally:
        temporaire.unlink(missing_ok=True)
    return cible


def habiller(app: Path) -> None:
    """Donne à l'installateur l'icône et le nom du logiciel."""
    icone = RACINE / "ressources" / "bata-plouf.icns"
    if icone.exists():
        shutil.copy(icone, app / "Contents" / "Resources" / "applet.icns")

    chemin = app / "Contents" / "Info.plist"
    with open(chemin, "rb") as f:
        plist = plistlib.load(f)
    plist.update({
        "CFBundleName": NOM,
        "CFBundleDisplayName": NOM,
        "CFBundleIdentifier": IDENTIFIANT,
        "CFBundleShortVersionString": "1.0",
        "NSHumanReadableCopyright": "Installe la dernière version de Bata-plouf.",
        "LSMinimumSystemVersion": "11.0",
    })
    with open(chemin, "wb") as f:
        plistlib.dump(plist, f)


def signer(app: Path) -> None:
    subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none",
                    str(app)], check=True, capture_output=True)


def main() -> None:
    depot = depot_choisi()
    app = compiler(depot)
    habiller(app)
    signer(app)
    poids = sum(f.stat().st_size for f in app.rglob("*")
                if f.is_file() and not f.is_symlink())
    print(f"{app}")
    print(f"dépôt visé : {depot}")
    print(f"taille : {poids / 1024:.0f} Ko")


if __name__ == "__main__":
    main()
