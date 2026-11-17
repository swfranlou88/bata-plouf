"""Chiffrer une sauvegarde pour la déposer là où tout le monde peut la lire.

Une archive de Bata-plouf contient six cents fiches clients avec leurs noms,
leurs adresses et leurs téléphones. Déposée publiquement, elle ne doit rien
livrer à qui la télécharge — et elle restera téléchargeable longtemps, par
des machines plus rapides que celles d'aujourd'hui.

D'où les deux choix de ce module :

  — AES-256 en mode GCM, qui chiffre et authentifie d'un même geste : un
    fichier modifié d'un octet est rejeté au lieu d'être déchiffré de
    travers ;
  — scrypt pour tirer la clé de la phrase de passe, réglé à 256 Mo de
    mémoire par essai. Une demi-seconde à l'ouverture d'une sauvegarde, mais
    un mur pour qui essaie des millions de mots de passe : c'est la mémoire,
    pas le temps, qui ruine les cartes graphiques.

Le format tient en un en-tête lisible et le reste chiffré :

    BPLOUF1\\n  8 octets   de quoi reconnaître le fichier
    version     1 octet    le format, pour pouvoir en changer
    n, r, p     3 octets   les réglages de scrypt, en clair
    sel        16 octets   tiré au sort à chaque sauvegarde
    nonce      12 octets   idem
    chiffré     le reste   l'archive et le sceau de GCM

Les réglages voyagent en clair, mais signés : ils entrent dans les données
authentifiées, donc personne ne peut les abaisser en chemin pour affaiblir la
dérivation. Et une sauvegarde de 2026 reste lisible par une version de 2030
qui aurait changé de réglages, puisqu'elle lit les siens dans le fichier.
"""

import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIE = b"BPLOUF1\n"
VERSION = 1
# 2^18 : 256 Mo et une demi-seconde par essai sur une machine d'aujourd'hui.
COUT, BLOC, PARALLELE = 18, 8, 1
TAILLE_SEL, TAILLE_NONCE = 16, 12
EN_TETE = struct.calcsize("<8sBBBB") + TAILLE_SEL + TAILLE_NONCE

# En dessous, une phrase ne protège rien contre un essai hors ligne : le
# fichier est public, et l'attaquant a tout son temps.
LONGUEUR_MINIMALE = 16


class ErreurCoffre(Exception):
    """Le fichier n'est pas une sauvegarde chiffrée, ou la phrase est fausse."""


def reproche(phrase: str) -> str:
    """Ce qu'on peut dire d'une phrase de passe avant de s'en servir.

    Chaîne vide si elle convient. On ne mesure pas une entropie savante : la
    longueur est le seul conseil qui tienne devant quelqu'un qui tape.
    """
    phrase = phrase or ""
    if not phrase.strip():
        return "Sans phrase de passe, il n'y a rien à chiffrer."
    if len(phrase) < LONGUEUR_MINIMALE:
        return (f"Trop courte : {LONGUEUR_MINIMALE} caractères au moins. "
                "Une phrase de quatre mots vaut mieux qu'un mot tordu.")
    return ""


def _cle(phrase: str, sel: bytes, cout: int, bloc: int, parallele: int) -> bytes:
    return Scrypt(salt=sel, length=32, n=2 ** cout, r=bloc,
                  p=parallele).derive(phrase.encode("utf-8"))


def chiffrer(donnees: bytes, phrase: str) -> bytes:
    """Rend l'archive chiffrée, en-tête compris."""
    faute = reproche(phrase)
    if faute:
        raise ErreurCoffre(faute)
    sel = os.urandom(TAILLE_SEL)
    nonce = os.urandom(TAILLE_NONCE)
    entete = struct.pack("<8sBBBB", MAGIE, VERSION, COUT, BLOC, PARALLELE) \
        + sel + nonce
    cle = _cle(phrase, sel, COUT, BLOC, PARALLELE)
    return entete + AESGCM(cle).encrypt(nonce, donnees, entete)


def dechiffrer(blob: bytes, phrase: str) -> bytes:
    """Rend l'archive en clair, ou explique pourquoi elle ne s'ouvre pas."""
    if len(blob) < EN_TETE or not blob.startswith(MAGIE):
        raise ErreurCoffre("Ce fichier n'est pas une sauvegarde Bata-plouf.")
    _, version, cout, bloc, parallele = struct.unpack_from("<8sBBBB", blob)
    if version != VERSION:
        raise ErreurCoffre(
            f"Sauvegarde au format {version} : il faut une version plus "
            "récente du logiciel pour l'ouvrir.")
    debut = struct.calcsize("<8sBBBB")
    sel = blob[debut:debut + TAILLE_SEL]
    nonce = blob[debut + TAILLE_SEL:EN_TETE]
    cle = _cle(phrase, sel, cout, bloc, parallele)
    try:
        return AESGCM(cle).decrypt(nonce, blob[EN_TETE:], blob[:EN_TETE])
    except InvalidTag as erreur:
        # GCM ne distingue pas les deux cas, et c'est voulu : il refuse, sans
        # dire si c'est la phrase ou le fichier qui cloche.
        raise ErreurCoffre(
            "Impossible d'ouvrir : phrase de passe fausse, ou fichier abîmé."
        ) from erreur


def chiffrer_fichier(source: Path | str, destination: Path | str,
                     phrase: str) -> Path:
    destination = Path(destination)
    destination.write_bytes(chiffrer(Path(source).read_bytes(), phrase))
    return destination


def dechiffrer_fichier(source: Path | str, destination: Path | str,
                       phrase: str) -> Path:
    destination = Path(destination)
    destination.write_bytes(dechiffrer(Path(source).read_bytes(), phrase))
    return destination
