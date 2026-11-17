"""La sauvegarde du mois, de bout en bout.

Elle enchaîne trois modules qui ne se connaissent pas : l'archive des données,
le coffre qui la chiffre, et le dépôt sur GitHub. C'est ici qu'on décide
quand elle part, et c'est ici qu'on note qu'elle est partie.

Le rythme est mensuel et se mesure au calendrier, pas à un compte de jours :
une sauvegarde par mois civil, faite au premier lancement du mois. Un maçon
n'ouvre pas son logiciel tous les jours ; compter trente jours ferait sauter
des mois entiers sans que personne s'en aperçoive.

Rien ne part sans que les trois pièces soient là — dépôt, jeton, phrase de
passe. Le réseau n'est pas sollicité autrement.
"""

import tempfile
from datetime import date
from pathlib import Path

from . import archive, coffre, environnement
from . import sauvegarde_en_ligne as envoi
from .sauvegarde_en_ligne import ErreurSauvegarde


def mois_courant(jour: date | None = None) -> str:
    return f"{jour or date.today():%Y-%m}"


def depot_vise(depot) -> str:
    """Le dépôt réglé dans le profil, à défaut celui du fichier d'environnement."""
    reglage = (getattr(depot.societe, "depot_sauvegardes", "") or "").strip()
    return reglage or environnement.lire(depot.racine).get(environnement.DEPOT, "")


def prete(depot) -> bool:
    """A-t-on de quoi sauvegarder sans rien demander ?

    Le dépôt et le jeton suffisent. La phrase de passe est facultative :
    le dépôt est privé, elle n'est qu'une seconde serrure. Sans elle,
    l'archive part telle quelle — et son nom le dit.
    """
    secrets = environnement.lire(depot.racine)
    return bool(depot_vise(depot) and secrets[environnement.JETON])


def due(depot, jour: date | None = None) -> bool:
    """La sauvegarde du mois reste-t-elle à faire ?"""
    if not prete(depot):
        return False
    fait = (getattr(depot.societe, "dernier_mois_sauvegarde", "") or "").strip()
    return fait != mois_courant(jour)


def sauvegarder(depot, jour: date | None = None) -> str:
    """Archive, chiffre s'il y a une phrase, dépose, et note le mois.

    Le fichier ne touche jamais le disque de façon durable : il naît dans un
    dossier temporaire, et celui-ci disparaît dans tous les cas — même si le
    dépôt échoue.
    """
    secrets = environnement.lire(depot.racine)
    phrase = secrets[environnement.PHRASE]
    jeton = secrets[environnement.JETON]
    cible = depot_vise(depot)

    # Une phrase trop courte est refusée, une phrase absente non : c'est le
    # choix de ne pas chiffrer, pas une étourderie à moitié faite.
    if phrase:
        faute = coffre.reproche(phrase)
        if faute:
            raise ErreurSauvegarde(faute)

    # ignore_cleanup_errors : le dossier part de toute façon au prochain
    # ménage du système, et un échec d'effacement ne doit pas faire
    # croire que la sauvegarde a raté alors qu'elle est déposée.
    with tempfile.TemporaryDirectory(prefix="bata-plouf-sauvegarde-",
                                     ignore_cleanup_errors=True) as atelier:
        envoyer = archive.ecrire(depot, Path(atelier) / "sauvegarde.zip")
        if phrase:
            envoyer = coffre.chiffrer_fichier(
                envoyer, Path(atelier) / "sauvegarde.enc", phrase)
        adresse = envoi.deposer(cible, jeton, envoyer,
                                envoi.nom_du_mois(jour, chiffre=bool(phrase)))

    societe = depot.societe
    societe.dernier_mois_sauvegarde = mois_courant(jour)
    depot.enregistrer_societe(societe)
    return adresse


def etat(depot) -> str:
    """Une phrase pour les Paramètres : où en est la sauvegarde en ligne."""
    if not depot_vise(depot):
        return "Aucun dépôt indiqué : rien ne part."
    secrets = environnement.lire(depot.racine)
    if not secrets[environnement.JETON]:
        return "Il manque le jeton GitHub."
    forme = ("chiffrée" if secrets[environnement.PHRASE]
             else "en clair, sans phrase de passe")
    fait = (getattr(depot.societe, "dernier_mois_sauvegarde", "") or "").strip()
    ou = f"Vers {depot_vise(depot)}, {forme}"
    if not fait:
        return f"{ou} — aucune sauvegarde déposée pour l'instant."
    if fait == mois_courant():
        return f"{ou} — à jour, sauvegarde de {fait} déposée."
    return f"{ou} — dernière sauvegarde : {fait}."
