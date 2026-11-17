"""Les secrets de la sauvegarde en ligne, rangés à part des réglages.

Phrase de passe et jeton GitHub ne sont pas des réglages comme les autres :
ils ne doivent ni partir dans une archive de sauvegarde, ni se retrouver dans
une capture d'écran des Paramètres, ni voyager quand on reprend les données
sur un autre Mac. Ils vivent donc dans un fichier à eux, lisible du seul
compte qui l'a écrit, à côté des données et jamais dedans.

Le format est celui des fichiers d'environnement, pour qu'il s'ouvre dans
n'importe quel éditeur et se corrige à la main :

    # Sauvegarde mensuelle de Bata-plouf
    PHRASE_SAUVEGARDE=quatre mots qui tiennent debout
    JETON_GITHUB=github_pat_...
    DEPOT_SAUVEGARDE=compte/bata-plouf-sauvegardes

Une variable d'environnement du même nom l'emporte sur le fichier : c'est ce
qui permet d'essayer sans rien écrire sur le disque.
"""

import os
from pathlib import Path

NOM_FICHIER = "sauvegarde.env"
PHRASE, JETON, DEPOT = "PHRASE_SAUVEGARDE", "JETON_GITHUB", "DEPOT_SAUVEGARDE"
CLES = (PHRASE, JETON, DEPOT)

ENTETE = (
    "# Secrets de la sauvegarde mensuelle de Bata-plouf.\n"
    "#\n"
    "# Ce fichier ne part dans aucune sauvegarde : il reste sur cette\n"
    "# machine. Notez la phrase de passe ailleurs — sans elle, une\n"
    "# sauvegarde en ligne ne se rouvre pas, personne ne le peut.\n"
)


def chemin(racine: Path | str) -> Path:
    return Path(racine) / NOM_FICHIER


def lire(racine: Path | str) -> dict:
    """Les secrets connus, du fichier puis de l'environnement."""
    valeurs = {cle: "" for cle in CLES}
    fichier = chemin(racine)
    if fichier.is_file():
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            cle = cle.strip()
            if cle in valeurs:
                # Les guillemets d'un fichier écrit à la main ne font pas
                # partie du secret.
                valeurs[cle] = valeur.strip().strip("\"'")
    for cle in CLES:
        valeurs[cle] = os.environ.get(cle) or valeurs[cle]
    return valeurs


def ecrire(racine: Path | str, valeurs: dict) -> Path:
    """Écrit les secrets fournis, garde les autres, et ferme le fichier à clé."""
    actuels = lire(racine)
    actuels.update({c: v for c, v in valeurs.items() if c in CLES})

    fichier = chemin(racine)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    corps = ENTETE + "\n" + "".join(
        f"{cle}={actuels[cle]}\n" for cle in CLES if actuels[cle])
    temporaire = fichier.with_suffix(".env.tmp")
    temporaire.write_text(corps, encoding="utf-8")
    # Avant de le mettre en place : lisible du seul propriétaire.
    try:
        os.chmod(temporaire, 0o600)
    except OSError:
        pass  # Windows n'a pas ces droits-là ; le dossier de l'utilisateur protège.
    os.replace(temporaire, fichier)
    return fichier


def complet(racine: Path | str) -> bool:
    """Y a-t-il de quoi sauvegarder en ligne sans rien demander ?"""
    valeurs = lire(racine)
    return all(valeurs[cle] for cle in CLES)
