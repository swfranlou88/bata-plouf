"""Construit l'application autonome, pour le système sur lequel on la lance.

    uv run --with pyinstaller python outils/construire.py

  macOS    → dist/Bata-plouf.app       bundle signé, à glisser dans Applications
  Windows  → dist/Bata-plouf/…exe     dossier à copier, raccourci vers l'exe
  Linux    → dist/Bata-plouf/…        dossier + fichier .desktop

L'application embarque Python et Qt : elle n'a besoin ni d'uv, ni du dossier
du projet. PyInstaller ne sait pas construire pour un autre système que le
sien : produire la version Windows demande de lancer cette commande sur une
machine Windows.

Les modules Qt inutilisés sont écartés un par un. Sans cela PySide6 embarque
QtWebEngine, à lui seul plus lourd que tout le reste de l'application réunie.
"""

import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

SYSTEME = platform.system()
SUR_MAC = SYSTEME == "Darwin"

# Les quatre premiers octets d'un binaire Mach-O, en 64 bits et en archive grasse
ENTETES_MACHO = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe",
                 b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")
NOM = "Bata-plouf"
NOM_FICHIER = NOM  # sans accent ni espace : utilisable tel quel partout
IDENTIFIANT = "fr.bataplouf.app"

# Tout ce dont un logiciel de devis n'a aucun usage.
MODULES_ECARTES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.QtQml", "PySide6.QtQmlModels",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtSensors", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtOpcUa",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtUiTools", "PySide6.QtScxml", "PySide6.QtRemoteObjects",
    "PySide6.QtStateMachine", "PySide6.QtNetworkAuth", "PySide6.QtHttpServer",
    "PySide6.QtVirtualKeyboard",
    "tkinter", "unittest", "pydoc", "doctest",
]


def icone() -> Path:
    """Régénère l'icône, pour qu'elle ne puisse pas être périmée."""
    sys.path.insert(0, str(RACINE / "outils"))
    from icone import construire
    return construire()


def construire_bundle(icone_fichier: Path) -> Path:
    commande = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", NOM_FICHIER,
        "--icon", str(icone_fichier),
        "--paths", str(RACINE),
        "--distpath", str(RACINE / "dist"),
        "--workpath", str(RACINE / "build"),
        "--specpath", str(RACINE / "build"),
        "--log-level", "WARN",
    ]
    if SUR_MAC:
        commande += ["--osx-bundle-identifier", IDENTIFIANT]
    for module in MODULES_ECARTES:
        commande += ["--exclude-module", module]
    commande.append(str(RACINE / "lanceur.py"))

    subprocess.run(commande, check=True, cwd=RACINE)
    dossier = RACINE / "dist"
    return dossier / f"{NOM_FICHIER}.app" if SUR_MAC else dossier / NOM_FICHIER


def est_binaire(chemin: Path) -> bool:
    try:
        with open(chemin, "rb") as f:
            return f.read(4) in ENTETES_MACHO
    except OSError:
        return False


def signer(app: Path) -> None:
    """Signature ad hoc, de l'intérieur vers l'extérieur.

    Sur Apple Silicon une application non signée refuse de démarrer, et
    « codesign --deep » plante (signal 10) sur un bundle de cette taille en
    laissant derrière lui des fichiers « .cstemp » qui font échouer toutes les
    tentatives suivantes. On nettoie donc, puis on signe chaque binaire
    séparément, les plus profonds d'abord, et le bundle en dernier.
    """
    for reste in list(app.rglob("*.cstemp*")):
        reste.unlink(missing_ok=True)

    def appel(cible: Path) -> None:
        resultat = subprocess.run(
            ["codesign", "--force", "--sign", "-", "--timestamp=none", str(cible)],
            capture_output=True, text=True)
        if resultat.returncode != 0:
            raise RuntimeError(
                f"signature refusée pour {cible.name} : "
                f"{resultat.stderr.strip() or resultat.returncode}")

    binaires = [c for c in app.rglob("*") if c.is_file() and not c.is_symlink()
                and est_binaire(c)]
    for cible in sorted(binaires, key=lambda c: len(c.parts), reverse=True):
        appel(cible)

    frameworks = sorted(app.rglob("*.framework"), key=lambda c: len(c.parts),
                        reverse=True)
    for cible in frameworks:
        appel(cible)

    appel(app)
    print(f"signé : {len(binaires)} binaires, {len(frameworks)} frameworks, "
          "puis le bundle")


def verifier(app: Path) -> None:
    """Contrôle qu'une signature est bien présente.

    Sur Apple Silicon un binaire sans signature est tué au démarrage : c'est
    le seul point bloquant. Le scellé des ressources, lui, reste imparfait à
    cause des liens croisés que PyInstaller pose entre Resources et
    Frameworks — ils font tourner en rond le parcours récursif de codesign,
    jusqu'à le faire planter avec « --deep ». L'application démarre malgré
    cela ; seule une diffusion à d'autres Mac demanderait une vraie signature
    Apple, donc on signale sans arrêter la construction.
    """
    infos = subprocess.run(["codesign", "-dv", str(app)],
                           capture_output=True, text=True)
    trace = infos.stdout + infos.stderr
    if "Signature=adhoc" not in trace and "Authority=" not in trace:
        raise RuntimeError("l'application n'est pas signée, elle ne démarrera pas")

    controle = subprocess.run(["codesign", "--verify", str(app)],
                              capture_output=True, text=True)
    if controle.returncode == 0:
        print("signature vérifiée")
    else:
        print(f"signature ad hoc posée — réserve : {controle.stderr.strip()}")
        print("  (sans effet sur ce Mac ; voir le README pour la diffusion)")


def completer_plist(app: Path) -> None:
    """Renseigne ce que PyInstaller laisse vide dans Info.plist."""
    chemin = app / "Contents" / "Info.plist"
    with open(chemin, "rb") as f:
        plist = plistlib.load(f)

    from bata_plouf import __version__
    plist.update({
        "CFBundleDisplayName": NOM,
        "CFBundleName": NOM,
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "NSHumanReadableCopyright": "Logiciel de devis et de facturation pour le bâtiment.",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.business",
        # L'application ne va jamais sur le réseau ; autant que le système le sache.
        "NSSupportsAutomaticTermination": False,
    })
    with open(chemin, "wb") as f:
        plistlib.dump(plist, f)


def archiver(resultat: Path) -> Path:
    """Produit l'archive à déposer dans une publication GitHub.

    Le nom porte la version et la machine visée : c'est ce que l'application
    cherche quand elle se met à jour toute seule. Sur macOS l'archive est
    faite avec ditto, parce qu'un zip ordinaire perdrait les liens
    symboliques et le bit exécutable du bundle.
    """
    from bata_plouf import __version__
    from bata_plouf.adaptateurs.mise_a_jour import suffixe_attendu

    archive = RACINE / "dist" / f"{NOM_FICHIER}-{__version__}-{suffixe_attendu()}.zip"
    archive.unlink(missing_ok=True)
    if SUR_MAC:
        subprocess.run(["ditto", "-c", "-k", "--keepParent",
                        str(resultat), str(archive)], check=True)
    else:
        shutil.make_archive(str(archive.with_suffix("")), "zip",
                            root_dir=str(resultat.parent), base_dir=resultat.name)
    return archive


def poids(chemin: Path) -> str:
    """Taille réelle : les liens symboliques ne comptent pas deux fois."""
    octets = sum(f.stat().st_size for f in chemin.rglob("*")
                 if f.is_file() and not f.is_symlink())
    return f"{octets / 1024 / 1024:.0f} Mo"


def ecrire_raccourci_linux(dossier: Path, icone_fichier: Path) -> None:
    """Fichier .desktop, pour que l'application apparaisse dans le menu."""
    raccourci = RACINE / "dist" / f"{NOM_FICHIER}.desktop"
    raccourci.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NOM}\n"
        "Comment=Devis et factures pour le bâtiment\n"
        f"Exec={dossier / NOM_FICHIER}\n"
        f"Icon={icone_fichier}\n"
        "Categories=Office;Finance;\n"
        "Terminal=false\n", encoding="utf-8")
    raccourci.chmod(0o755)


def main() -> None:
    icone_fichier = icone()
    print(f"système : {SYSTEME}   icône : {icone_fichier.name}")
    resultat = construire_bundle(icone_fichier)

    if SUR_MAC:
        # L'Info.plist se complète avant la signature : toute modification du
        # bundle après coup invaliderait la signature.
        completer_plist(resultat)
        signer(resultat)
        verifier(resultat)
        # PyInstaller dépose aussi la version « dossier » à côté du bundle
        shutil.rmtree(RACINE / "dist" / NOM_FICHIER, ignore_errors=True)
    elif SYSTEME == "Linux":
        ecrire_raccourci_linux(resultat, icone_fichier)
        print("raccourci .desktop écrit à côté du dossier")
    else:
        print(f"lancez {NOM_FICHIER}.exe dans ce dossier, ou créez-en un raccourci")

    shutil.rmtree(RACINE / "build", ignore_errors=True)
    archive = archiver(resultat)
    print(f"\n{resultat}")
    print(f"taille : {poids(resultat)}")
    print(f"archive : {archive.name} "
          f"({archive.stat().st_size / 1024 / 1024:.0f} Mo) — à déposer dans "
          "une publication GitHub")


if __name__ == "__main__":
    main()
