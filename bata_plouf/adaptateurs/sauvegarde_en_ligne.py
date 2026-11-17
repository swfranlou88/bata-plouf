"""Déposer la sauvegarde mensuelle dans une release GitHub.

Une sauvegarde qui dort sur le même disque que les données ne protège de
rien : l'incendie, le vol et la panne de disque emportent les deux. Celle-ci
part ailleurs, une fois par mois, chiffrée avant de quitter la machine.

Trois choix qui méritent une phrase :

  — **une seule release, étiquetée « sauvegardes »**, qui porte un fichier
    par mois. Une release par mois noierait les vraies versions du logiciel ;
  — **marquée pré-version**. GitHub exclut les pré-versions de
    « releases/latest », qui est exactement là où l'application va chercher
    ses mises à jour : sans cela, la sauvegarde de novembre deviendrait la
    « dernière version » et le logiciel essaierait de l'installer ;
  — **un dépôt séparé de celui du logiciel**. Le jeton d'écriture dort sur la
    machine de l'utilisateur ; s'il tombe entre d'autres mains, il ne doit
    pas permettre de publier une fausse mise à jour que toutes les
    installations iraient chercher toutes seules.
"""

import json
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

API = "https://api.github.com"
ETIQUETTE = "sauvegardes"
DELAI = 60  # secondes


class ErreurSauvegarde(Exception):
    """Ce qui empêche la sauvegarde d'arriver à destination."""


def normaliser(depot: str) -> str:
    """« compte/nom », quel que soit ce qu'on a collé.

    On colle volontiers l'adresse de la page GitHub, ou le lien de clonage
    qui finit par « .git ». Les deux désignent le bon dépôt et méritent
    mieux qu'un « introuvable ».
    """
    texte = (depot or "").strip()
    prefixes = ("https://github.com/", "http://github.com/", "git@github.com:",
                "github.com/", "https://", "http://", "www.")
    # En boucle : un copier-coller malheureux donne « https://https://… », et
    # chaque passage n'enlève qu'une couche. Le reste du collage est bon, il
    # n'y a pas de raison de le refuser.
    change = True
    while change:
        change = False
        for prefixe in prefixes:
            if texte.lower().startswith(prefixe):
                texte = texte[len(prefixe):]
                change = True
    texte = texte.strip("/")
    if texte.endswith(".git"):
        texte = texte[:-4]
    return texte


# Ce que le début d'un jeton dit de lui. GitHub préfixe les siens depuis
# 2021, ce qui permet de reconnaître un jeton classique d'un jeton fin sans
# rien demander au réseau — et sans jamais l'afficher.
GENRES_JETON = {
    "github_pat_": ("fin", ""),
    "ghp_": ("classique", "Jeton classique : il lui faut la portée « repo » "
                          "entière pour voir un dépôt privé. Un jeton fin, "
                          "limité à ce seul dépôt, est plus sûr."),
    "gho_": ("OAuth", "Jeton OAuth : ce n'est pas un jeton d'accès personnel."),
    "ghs_": ("serveur", "Jeton d'application : ce n'est pas un jeton d'accès "
                        "personnel."),
}


def genre_du_jeton(jeton: str) -> tuple[str, str]:
    """Le genre du jeton et ce qu'il y a à en dire, d'après son préfixe."""
    jeton = (jeton or "").strip()
    if not jeton:
        return "", ""
    for prefixe, (genre, remarque) in GENRES_JETON.items():
        if jeton.startswith(prefixe):
            return genre, remarque
    return "inconnu", ("Ce jeton ne ressemble à aucun de ceux que GitHub "
                       "délivre — un morceau manque peut-être au collage.")


def verifier_acces(depot: str, jeton: str) -> str:
    """Dit en une phrase ce que le jeton peut faire sur ce dépôt.

    GitHub répond 404 aussi bien pour un dépôt qui n'existe pas que pour un
    dépôt privé que le jeton n'a pas le droit de voir — c'est voulu, cela
    évite de révéler l'existence des dépôts privés. D'où ce contrôle à
    part, qui va chercher ce que l'API veut bien dire de plus.
    """
    depot = normaliser(depot)
    if "/" not in depot:
        raise ErreurSauvegarde(
            "Le dépôt s'écrit « compte/nom », par exemple "
            "« dupont/bata-plouf-sauvegardes ».")
    fiche = _demander(f"{API}/repos/{depot}", jeton)
    droits = fiche.get("permissions") or {}
    if not droits.get("push"):
        raise ErreurSauvegarde(
            f"Le jeton voit {depot} mais n'a pas le droit d'y écrire. "
            "Il lui faut « Contents : Read and write ».")
    visibilite = "privé" if fiche.get("private") else "public"
    return f"{depot} ({visibilite}) — écriture autorisée."


def nom_du_mois(jour: date | None = None, chiffre: bool = True) -> str:
    """Un fichier par mois, écrasé s'il existe.

    L'extension dit ce qu'il est : « bata-plouf-2026-11.zip.enc » pour une
    sauvegarde chiffrée, « .zip » pour une archive ordinaire. Celui qui la
    rapatrie dans trois ans doit pouvoir le savoir sans l'ouvrir.
    """
    jour = jour or date.today()
    return f"bata-plouf-{jour:%Y-%m}.zip" + (".enc" if chiffre else "")


def _demander(url: str, jeton: str, methode: str = "GET", corps=None,
              type_contenu: str = "application/json"):
    requete = urllib.request.Request(url, method=methode, data=corps)
    requete.add_header("Authorization", f"Bearer {jeton}")
    requete.add_header("Accept", "application/vnd.github+json")
    requete.add_header("X-GitHub-Api-Version", "2022-11-28")
    requete.add_header("User-Agent", "Bata-plouf")
    if corps is not None:
        requete.add_header("Content-Type", type_contenu)
    try:
        with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
            brut = reponse.read()
            return json.loads(brut) if brut else {}
    except urllib.error.HTTPError as erreur:
        raise ErreurSauvegarde(_message(erreur)) from erreur
    except (urllib.error.URLError, TimeoutError) as erreur:
        raise ErreurSauvegarde(
            f"GitHub est injoignable : {getattr(erreur, 'reason', erreur)}"
        ) from erreur


def _message(erreur: urllib.error.HTTPError) -> str:
    """Traduire le code de GitHub en quelque chose qu'on peut corriger."""
    if erreur.code == 401:
        return "Jeton refusé par GitHub : il est faux, révoqué ou périmé."
    if erreur.code == 403:
        return ("Jeton sans le droit d'écrire sur ce dépôt. Il lui faut "
                "« Contents : Read and write ».")
    if erreur.code == 404:
        # GitHub répond 404 au lieu de 403 sur un dépôt privé qu'on n'a pas
        # le droit de voir : « introuvable » veut souvent dire « pas pour
        # vous ». Les trois causes se valent, autant les dire toutes.
        return ("Dépôt introuvable — ou invisible pour ce jeton, ce que "
                "GitHub ne distingue pas. Trois choses à vérifier :\n\n"
                "· le nom, « compte/dépôt », sans l'adresse complète ;\n"
                "· le jeton : dans « Repository access », le dépôt doit être "
                "coché nommément (« Only select repositories ») ;\n"
                "· ses permissions : « Contents » doit être sur « Read and "
                "write », pas seulement « Read ».")
    if erreur.code == 422:
        return "GitHub a refusé la demande : " + erreur.read().decode(
            "utf-8", "replace")[:200]
    return f"GitHub a répondu : {erreur.code}"


def _release(depot: str, jeton: str) -> dict:
    """La release des sauvegardes, créée au premier passage."""
    try:
        return _demander(f"{API}/repos/{depot}/releases/tags/{ETIQUETTE}", jeton)
    except ErreurSauvegarde as erreur:
        if "introuvable" not in str(erreur):
            raise
    corps = json.dumps({
        "tag_name": ETIQUETTE,
        "name": "Sauvegardes chiffrées",
        "body": ("Sauvegardes mensuelles de Bata-plouf, chiffrées par phrase "
                 "de passe (AES-256-GCM, clé dérivée par scrypt).\n\n"
                 "Sans la phrase de passe, ces fichiers ne s'ouvrent pas.\n\n"
                 "Marquée pré-version pour ne pas passer pour une version du "
                 "logiciel : la mise à jour automatique ignore les "
                 "pré-versions."),
        "prerelease": True,
    }).encode("utf-8")
    return _demander(f"{API}/repos/{depot}/releases", jeton, "POST", corps)


def deposer(depot: str, jeton: str, fichier: Path | str,
            nom: str = "") -> str:
    """Envoie le fichier chiffré et rend son adresse de téléchargement."""
    depot = normaliser(depot)
    if "/" not in depot:
        raise ErreurSauvegarde(
            "Le dépôt s'écrit « compte/nom », par exemple "
            "« dupont/bata-plouf-sauvegardes ».")
    if not (jeton or "").strip():
        raise ErreurSauvegarde("Sans jeton GitHub, rien ne peut être déposé.")

    fichier = Path(fichier)
    nom = nom or fichier.name
    release = _release(depot, jeton)

    # Le fichier du mois existe peut-être déjà : on remplace, pour ne pas
    # accumuler douze versions du même mois.
    for piece in release.get("assets") or []:
        if piece.get("name") == nom:
            _demander(f"{API}/repos/{depot}/releases/assets/{piece['id']}",
                      jeton, "DELETE")

    adresse = (release.get("upload_url") or "").split("{")[0]
    if not adresse:
        raise ErreurSauvegarde("GitHub n'a pas dit où déposer le fichier.")
    depose = _demander(f"{adresse}?name={nom}", jeton, "POST",
                       fichier.read_bytes(), "application/octet-stream")
    return depose.get("browser_download_url", "")


class _SansJetonApresRedirection(urllib.request.HTTPRedirectHandler):
    """Suit la redirection de GitHub sans emporter le jeton.

    Télécharger une pièce jointe privée se fait en deux temps : GitHub
    renvoie vers son serveur de fichiers, avec une adresse déjà signée. Si
    l'en-tête d'autorisation suit jusque-là, le serveur refuse — « only one
    auth mechanism allowed » —, et urllib la recopie par défaut.
    """

    def redirect_request(self, requete, fp, code, message, entetes, url):
        suivante = super().redirect_request(requete, fp, code, message,
                                            entetes, url)
        if suivante is not None:
            for nom in ("Authorization", "authorization"):
                suivante.headers.pop(nom, None)
                suivante.unredirected_hdrs.pop(nom, None)
        return suivante


def telecharger(depot: str, jeton: str, nom: str, destination: Path | str) -> Path:
    """Rapatrie une sauvegarde, y compris depuis un dépôt privé.

    L'adresse publique d'une pièce jointe ne répond pas sur un dépôt privé :
    il faut passer par l'API, qui redirige vers le fichier lui-même.
    """
    depot = normaliser(depot)
    release = _demander(f"{API}/repos/{depot}/releases/tags/{ETIQUETTE}", jeton)
    piece = next((p for p in release.get("assets") or []
                  if p.get("name") == nom), None)
    if piece is None:
        connues = ", ".join(p.get("name", "") for p in release.get("assets") or [])
        raise ErreurSauvegarde(
            f"« {nom} » n'est pas en ligne. Disponibles : {connues or 'aucune'}.")

    requete = urllib.request.Request(
        f"{API}/repos/{depot}/releases/assets/{piece['id']}")
    requete.add_header("Authorization", f"Bearer {jeton}")
    requete.add_header("Accept", "application/octet-stream")
    requete.add_header("User-Agent", "Bata-plouf")
    ouvreur = urllib.request.build_opener(_SansJetonApresRedirection())
    destination = Path(destination)
    try:
        with ouvreur.open(requete, timeout=DELAI) as reponse:
            destination.write_bytes(reponse.read())
    except urllib.error.HTTPError as erreur:
        raise ErreurSauvegarde(_message(erreur)) from erreur
    except (urllib.error.URLError, TimeoutError) as erreur:
        raise ErreurSauvegarde(
            f"Téléchargement impossible : {getattr(erreur, 'reason', erreur)}"
        ) from erreur
    return destination


def liste(depot: str, jeton: str) -> list[tuple[str, int, str]]:
    """Ce qui est déjà en ligne : nom, taille, date — pour pouvoir le dire."""
    try:
        release = _demander(f"{API}/repos/{normaliser(depot)}/releases/tags/"
                            f"{ETIQUETTE}", jeton)
    except ErreurSauvegarde as erreur:
        if "introuvable" in str(erreur):
            return []
        raise
    return sorted(((p.get("name", ""), int(p.get("size") or 0),
                    (p.get("updated_at") or "")[:10])
                   for p in release.get("assets") or []), reverse=True)
