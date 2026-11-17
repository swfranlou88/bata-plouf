"""Dresse la carte du projet : où se trouve quoi, en une page.

Lire le code pour retrouver une fonction coûte cher — en temps pour un
humain, en jetons pour un assistant. Cette carte dit, pour chaque module, ce
qu'il fait et ce qu'il expose, avec le numéro de ligne. On y cherche d'abord,
on n'ouvre le fichier qu'ensuite, et seulement le bon.

    uv run python outils/carte.py          écrit CARTE.md à la racine
    uv run python outils/carte.py --voir   l'affiche sans rien écrire

Elle se régénère en une seconde et n'est pas versionnée : c'est une vue du
code à un instant donné, pas une source de vérité. Le code reste le seul
texte qui fasse foi — une carte qui aurait vieilli égare plus qu'elle n'aide,
donc on la refait plutôt que de la corriger.
"""

import ast
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIERS = ("bata_plouf", "outils")
CARTE = RACINE / "CARTE.md"

# Ce qu'on ne peut pas lire dans le code et qu'il faut pourtant savoir avant
# d'y toucher. Tenue à la main, volontairement courte.
PREAMBULE = """# Carte de Bata-plouf

Fichier **non versionné**, régénéré par `uv run python outils/carte.py`.
À consulter avant de fouiller le code : il dit où chercher.

## Ce qui ne se devine pas en lisant un fichier

- **Architecture hexagonale.** `domaine/` ne connaît ni Qt, ni les fichiers,
  ni le réseau ; `adaptateurs/` fait le reste ; `app.py` assemble.
  `outils/verifier_architecture.py` le vérifie et doit rester vert.
- **Tout en français**, code et commentaires compris. Un commentaire dit
  *pourquoi*, jamais *quoi*.
- **Stockage en fichiers JSON**, pas de base de données. Écriture atomique
  (fichier temporaire puis `os.replace`). `DepotFichiers.enregistrer_article`
  réécrit tout `articles.json` : pour une modification en masse, muter en
  mémoire puis appeler `_ecrire_articles()` une fois.
- **Suppression douce partout** : rien n'est effacé, tout va en corbeille.
- **Le dépôt GitHub est public et les données réelles sont à côté.** Jamais
  de nom de client réel dans le code, les commentaires ou les messages de
  commit.
- **Qt** : le « px » des feuilles de style vaut toujours 1/96 de pouce, quelle
  que soit la définition de l'appareil — voir `impression/styles.py`.
- **Avant de modifier les données**, arrêter l'application : elle garde tout
  en mémoire et réécrit en quittant.
- Contrôles : `verifier_architecture.py`, `verifier_modules.py`,
  `verifier_metier.py`, `verifier_impression.py`.

## Où sont les choses

- Données de l'utilisateur : `~/Documents/Bata-plouf` — `clients.json`,
  `articles.json`, `chantiers.json`, `parametres.json`, `modele-devis.json`,
  `compteurs.json`, `devis/`, `factures/`, `pdf/`, `sauvegardes/`, et
  `sauvegarde.env` (secrets, jamais dans une archive).
- Reprise de l'ancien logiciel : `BatAppli 2000.rar` à la racine, non
  versionné. `ARTOUV.FIC` y porte la composition des ouvrages.

## Commandes

    uv run python -m bata_plouf                      lancer
    uv run python outils/verifier_metier.py          les règles métier
    uv run python outils/carte.py                    refaire cette carte
    QT_QPA_PLATFORM=offscreen …                      pour un essai sans écran

Pour chercher : `grep -A 12 "nom_du_fichier.py" CARTE.md` dit où aller sans
ouvrir le code.

"""


def premiere_ligne(noeud) -> str:
    """La première phrase de la docstring, ou rien."""
    texte = ast.get_docstring(noeud) or ""
    ligne = texte.strip().split("\n")[0].strip()
    return ligne[:110]


def membres(arbre: ast.Module) -> list[str]:
    """Les classes et fonctions du module, dans l'ordre du fichier."""
    lignes = []
    constantes = []
    for noeud in arbre.body:
        if isinstance(noeud, ast.ClassDef):
            # Les méthodes privées comptent : dans les écrans, presque toute
            # la logique porte un tiret bas, et c'est elle qu'on cherche.
            methodes = [n.name for n in noeud.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and not n.name.startswith("__")]
            resume = premiere_ligne(noeud)
            detail = f" — {resume}" if resume else ""
            lignes.append(f"  - `{noeud.name}` (l. {noeud.lineno}){detail}")
            if methodes:
                lignes.append("    " + " · ".join(f"`{m}`" for m in methodes[:18]))
        elif isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if noeud.name.startswith("_"):
                continue
            resume = premiere_ligne(noeud)
            detail = f" — {resume}" if resume else ""
            lignes.append(f"  - `{noeud.name}()` (l. {noeud.lineno}){detail}")
        elif isinstance(noeud, ast.Assign):
            # Les constantes de haut de fichier disent souvent l'essentiel :
            # les taux de TVA, les unités, les colonnes d'un document.
            constantes += [c.id for c in noeud.targets
                           if isinstance(c, ast.Name) and c.id.isupper()]
    if constantes:
        lignes.insert(0, "  - constantes : "
                      + ", ".join(f"`{n}`" for n in constantes[:14]))
    return lignes


def fichiers() -> list[Path]:
    trouves = []
    for dossier in DOSSIERS:
        trouves += sorted((RACINE / dossier).rglob("*.py"))
    return [f for f in trouves if "__pycache__" not in f.parts]


def dresser() -> str:
    morceaux = [PREAMBULE, "## Les modules\n"]
    dossier_courant = ""
    total_lignes = 0
    for fichier in fichiers():
        relatif = fichier.relative_to(RACINE)
        source = fichier.read_text(encoding="utf-8")
        total_lignes += source.count("\n")
        try:
            arbre = ast.parse(source)
        except SyntaxError as erreur:
            morceaux.append(f"### `{relatif}`\n  - illisible : {erreur}\n")
            continue

        if str(relatif.parent) != dossier_courant:
            dossier_courant = str(relatif.parent)
            morceaux.append(f"\n### {dossier_courant}/\n")
        resume = premiere_ligne(arbre)
        morceaux.append(f"\n**`{relatif.name}`** — {resume or 'sans résumé'}"
                        f"  ({source.count(chr(10))} lignes)\n")
        corps = membres(arbre)
        if corps:
            morceaux.append("\n".join(corps) + "\n")

    morceaux.append(f"\n---\n\n{len(fichiers())} fichiers, "
                    f"{total_lignes} lignes de Python.\n")
    morceaux.append(derniers_commits())
    return "\n".join(morceaux)


def derniers_commits() -> str:
    """Les dernières décisions prises, titres seuls : elles éclairent le code."""
    try:
        sortie = subprocess.run(
            ["git", "log", "-12", "--pretty=format:- %s"], cwd=RACINE,
            capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""
    return "\n## Les douze derniers commits\n\n" + sortie + "\n"


def main() -> int:
    carte = dresser()
    if "--voir" in sys.argv:
        print(carte)
        return 0
    CARTE.write_text(carte, encoding="utf-8")
    print(f"{CARTE} — {len(carte) // 1024} Ko, "
          f"{carte.count(chr(10))} lignes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
