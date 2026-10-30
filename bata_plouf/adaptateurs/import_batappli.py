"""Reprise des données de l'ancien logiciel (Batappli XP, Windows).

Le format exact des fichiers n'est pas connu à l'avance, donc rien n'est codé en
dur : le module analyse le fichier (encodage, séparateur, colonnes), propose une
correspondance entre les colonnes trouvées et les champs du logiciel, et
l'utilisateur corrige ce qui n'a pas été deviné. Le jour où les fichiers
arrivent, il n'y a normalement rien à reprogrammer — seulement à vérifier la
correspondance à l'écran.

Pièges connus des exports Windows XP, tous traités ici :
  - encodage Windows-1252 ou CP850, qui transforme les accents en charabia ;
  - montants à virgule décimale et séparateur de milliers en espace ;
  - dates en JJ/MM/AA ;
  - enregistrements à largeur fixe, sans aucun séparateur.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ..domaine import Article, Chantier, Client, Devis, Ligne, date_iso, nouvel_id

ENCODAGES = ["utf-8-sig", "utf-8", "cp1252", "cp850", "mac-roman", "latin-1"]
SEPARATEURS = [";", "\t", "|", ","]

# Caractères qu'on s'attend à trouver dans un fichier français correctement décodé
LETTRES_FR = set("àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ°€")
# Caractères qui trahissent un mauvais décodage
SUSPECTS = set("ÃÂ¢£¤¥¦§¨ª«¬®¯±µ¶·¸¹º»¼½¾ðþý")


# --- sondage du fichier ---------------------------------------------------


@dataclass
class Sondage:
    chemin: Path
    taille: int = 0
    encodage: str = "cp1252"
    separateur: str = ";"
    largeur_fixe: bool = False
    colonnes: int = 0
    lignes: int = 0
    entete: list[str] = field(default_factory=list)
    a_un_entete: bool = False
    apercu: list[list[str]] = field(default_factory=list)
    remarques: list[str] = field(default_factory=list)

    @property
    def separateur_lisible(self) -> str:
        return {";": "point-virgule", "\t": "tabulation", "|": "barre verticale",
                ",": "virgule"}.get(self.separateur, self.separateur)


def _score_encodage(texte: str) -> int:
    """Plus le texte contient d'accents français plausibles, meilleur il est."""
    bons = sum(1 for c in texte if c in LETTRES_FR)
    mauvais = sum(1 for c in texte if c in SUSPECTS)
    illisibles = texte.count("�")
    controle = sum(1 for c in texte if ord(c) < 32 and c not in "\r\n\t")
    return bons * 3 - mauvais * 4 - illisibles * 10 - controle * 2


def detecter_encodage(octets: bytes) -> tuple[str, list[str]]:
    remarques = []
    try:
        octets.decode("utf-8")
        return ("utf-8-sig" if octets.startswith(b"\xef\xbb\xbf") else "utf-8"), remarques
    except UnicodeDecodeError:
        pass
    meilleur, score_max = "cp1252", None
    for encodage in ENCODAGES:
        try:
            texte = octets.decode(encodage)
        except (UnicodeDecodeError, LookupError):
            continue
        score = _score_encodage(texte)
        if score_max is None or score > score_max:
            meilleur, score_max = encodage, score
    if meilleur in ("cp1252", "cp850", "mac-roman"):
        remarques.append(
            f"Fichier non UTF-8, décodé en {meilleur} — vérifiez les accents dans l'aperçu."
        )
    return meilleur, remarques


def detecter_separateur(lignes: list[str]) -> tuple[str, int]:
    """Retient le séparateur dont le nombre d'occurrences est le plus régulier."""
    meilleur, meilleures_colonnes, meilleure_note = "", 0, -1.0
    echantillon = [l for l in lignes if l.strip()][:200]
    if not echantillon:
        return "", 0
    for separateur in SEPARATEURS:
        comptes = [l.count(separateur) for l in echantillon]
        if max(comptes) == 0:
            continue
        frequent = max(set(comptes), key=comptes.count)
        if frequent == 0:
            continue
        regularite = comptes.count(frequent) / len(comptes)
        note = regularite * 100 + frequent
        if regularite >= 0.7 and note > meilleure_note:
            meilleur, meilleures_colonnes, meilleure_note = separateur, frequent + 1, note
    return meilleur, meilleures_colonnes


def _normaliser(texte: str) -> str:
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", texte or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", sans_accent.lower())


def _semble_entete(champs: list[str]) -> bool:
    """Une ligne d'en-tête ne contient ni montant ni date."""
    if not champs:
        return False
    remplis = [c for c in champs if c.strip()]
    if len(remplis) < max(2, len(champs) // 2):
        return False
    for valeur in remplis:
        if re.fullmatch(r"[-+]?[\d  ]*[.,]?\d*", valeur.strip()):
            return False
        if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", valeur.strip()):
            return False
    return True


def sonder(chemin: Path | str, max_lignes_apercu: int = 12) -> Sondage:
    chemin = Path(chemin)
    octets = chemin.read_bytes()
    sondage = Sondage(chemin=chemin, taille=len(octets))

    sondage.encodage, sondage.remarques = detecter_encodage(octets)
    texte = octets.decode(sondage.encodage, errors="replace")
    lignes = [l for l in texte.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    utiles = [l for l in lignes if l.strip()]
    sondage.lignes = len(utiles)

    separateur, colonnes = detecter_separateur(utiles)
    if separateur:
        sondage.separateur = separateur
        sondage.colonnes = colonnes
        decoupees = [l.split(separateur) for l in utiles[:max_lignes_apercu + 1]]
    else:
        sondage.largeur_fixe = True
        sondage.separateur = ""
        longueurs = {len(l) for l in utiles[:200]}
        sondage.remarques.append(
            "Aucun séparateur régulier détecté : le fichier est probablement à "
            "largeur fixe"
            + (" (toutes les lignes font la même longueur)." if len(longueurs) == 1 else ".")
            + " Indiquez les positions de coupe pour le lire."
        )
        decoupees = [[l] for l in utiles[:max_lignes_apercu + 1]]
        sondage.colonnes = 1

    decoupees = [[c.strip().strip('"') for c in ligne] for ligne in decoupees]
    if decoupees and _semble_entete(decoupees[0]):
        sondage.a_un_entete = True
        sondage.entete = decoupees[0]
        sondage.apercu = decoupees[1:]
        sondage.lignes = max(0, sondage.lignes - 1)
    else:
        sondage.entete = [f"Colonne {i + 1}" for i in range(sondage.colonnes)]
        sondage.apercu = decoupees

    return sondage


def lire_enregistrements(sondage: Sondage) -> list[list[str]]:
    """Relit tout le fichier avec les réglages du sondage."""
    texte = sondage.chemin.read_bytes().decode(sondage.encodage, errors="replace")
    lignes = [l for l in texte.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]
    if sondage.a_un_entete:
        lignes = lignes[1:]
    if sondage.largeur_fixe or not sondage.separateur:
        return [[l] for l in lignes]
    return [[c.strip().strip('"') for c in l.split(sondage.separateur)] for l in lignes]


# --- champs importables ---------------------------------------------------


@dataclass
class Champ:
    cle: str
    libelle: str
    synonymes: tuple[str, ...] = ()
    conversion: str = "texte"  # texte | nombre | date


CHAMPS = {
    "clients": [
        Champ("ref_externe", "Référence d'origine", ("code", "ref", "numero", "no", "id", "cle")),
        Champ("civilite", "Civilité", ("civilite", "titre", "qualite")),
        Champ("nom", "Nom", ("nom", "patronyme", "client")),
        Champ("prenom", "Prénom", ("prenom",)),
        Champ("societe", "Raison sociale", ("societe", "raisonsociale", "entreprise")),
        Champ("siret", "SIRET", ("siret", "siren")),
        Champ("adresse", "Adresse", ("adresse", "adr", "rue", "voie")),
        Champ("cp", "Code postal", ("cp", "codepostal", "postal")),
        Champ("ville", "Ville", ("ville", "commune", "localite")),
        Champ("telephone", "Téléphone", ("tel", "telephone", "fixe", "telfixe")),
        Champ("mobile", "Mobile", ("mobile", "portable", "gsm", "telportable")),
        Champ("email", "Courriel", ("email", "mail", "courriel", "adressemail")),
        Champ("notes", "Notes", ("note", "notes", "observation", "commentaire", "remarque")),
    ],
    "chantiers": [
        Champ("ref_externe", "Référence d'origine", ("code", "ref", "numero", "no", "id")),
        Champ("client_ref", "Référence du client", ("client", "codeclient", "refclient")),
        Champ("libelle", "Libellé", ("libelle", "designation", "nom", "chantier", "objet")),
        Champ("adresse", "Adresse", ("adresse", "adr", "rue")),
        Champ("cp", "Code postal", ("cp", "codepostal")),
        Champ("ville", "Ville", ("ville", "commune")),
        Champ("date_debut", "Date de début", ("datedebut", "debut", "date"), "date"),
        Champ("date_fin", "Date de fin", ("datefin", "fin"), "date"),
        Champ("notes", "Notes", ("note", "observation", "commentaire")),
    ],
    "articles": [
        Champ("ref_externe", "Référence d'origine", ("id", "cle", "codearticle")),
        Champ("reference", "Référence", ("reference", "ref", "code")),
        Champ("designation", "Désignation", ("designation", "libelle", "intitule", "article")),
        Champ("detail", "Détail", ("detail", "description", "complement")),
        Champ("famille", "Famille", ("famille", "categorie", "groupe", "lot")),
        Champ("unite", "Unité", ("unite", "un", "ut")),
        Champ("prix_achat", "Prix d'achat", ("prixachat", "achat", "pa", "cout"), "nombre"),
        Champ("prix_vente", "Prix de vente", ("prixvente", "vente", "pv", "prix",
                                              "prixunitaire", "pu"), "nombre"),
        Champ("taux_tva", "Taux de TVA", ("tva", "tauxtva", "txtva"), "nombre"),
    ],
    "devis": [
        Champ("ref_externe", "Référence d'origine", ("id", "cle", "codedevis")),
        Champ("numero", "Numéro de devis", ("numero", "no", "numdevis", "devis", "reference")),
        Champ("client_ref", "Référence du client", ("client", "codeclient", "refclient")),
        Champ("chantier_ref", "Référence du chantier", ("chantier", "codechantier")),
        Champ("objet", "Objet", ("objet", "libelle", "designation", "intitule")),
        Champ("date_devis", "Date", ("date", "datedevis"), "date"),
        Champ("statut", "Statut", ("statut", "etat", "situation")),
        Champ("remise_globale_pct", "Remise %", ("remise", "remisepct"), "nombre"),
        Champ("acompte_pct", "Acompte %", ("acompte",), "nombre"),
        Champ("notes_internes", "Notes", ("note", "observation", "commentaire")),
    ],
    "lignes": [
        Champ("devis_ref", "Référence du devis", ("devis", "numero", "no", "numdevis",
                                                  "codedevis", "refdevis")),
        Champ("ordre", "Ordre", ("ordre", "rang", "ligne", "position"), "nombre"),
        Champ("type", "Type de ligne", ("type", "nature")),
        Champ("designation", "Désignation", ("designation", "libelle", "intitule", "texte")),
        Champ("detail", "Détail", ("detail", "description", "complement")),
        Champ("quantite", "Quantité", ("quantite", "qte", "qt"), "nombre"),
        Champ("unite", "Unité", ("unite", "un", "ut")),
        Champ("prix_unitaire", "Prix unitaire", ("prixunitaire", "pu", "prix",
                                                 "prixvente"), "nombre"),
        Champ("taux_tva", "Taux de TVA", ("tva", "tauxtva", "txtva"), "nombre"),
        Champ("remise_pct", "Remise %", ("remise",), "nombre"),
    ],
}

LIBELLES_CIBLES = {
    "clients": "Clients",
    "chantiers": "Chantiers",
    "articles": "Bibliothèque de prix",
    "devis": "Devis (en-têtes)",
    "lignes": "Lignes de devis",
}


def deviner_correspondance(entete: list[str], cible: str) -> dict[str, int]:
    """Associe chaque champ à une colonne d'après le nom des en-têtes.

    Le rapprochement est fait sans accents ni ponctuation, et accepte qu'un nom
    de colonne contienne le synonyme (« code_client », « N° Client »…).
    """
    normalises = [_normaliser(c) for c in entete]
    correspondance: dict[str, int] = {}
    pris: set[int] = set()
    for champ in CHAMPS.get(cible, []):
        candidats = (_normaliser(champ.libelle), _normaliser(champ.cle)) + champ.synonymes
        meilleur_index, meilleure_note = None, 0
        for index, nom in enumerate(normalises):
            if index in pris or not nom:
                continue
            for candidat in candidats:
                if not candidat:
                    continue
                if nom == candidat:
                    note = 100
                elif nom.startswith(candidat) or nom.endswith(candidat):
                    note = 60
                elif candidat in nom:
                    note = 40
                else:
                    continue
                if note > meilleure_note:
                    meilleur_index, meilleure_note = index, note
        if meilleur_index is not None:
            correspondance[champ.cle] = meilleur_index
            pris.add(meilleur_index)
    return correspondance


# --- conversions ----------------------------------------------------------


def en_nombre(valeur: str) -> float:
    """« 1 234,56 », « 1.234,56 », « 12.5 » ou « 1 234,56 € » -> float."""
    texte = re.sub(r"[^\d,.\-]", "", str(valeur or "").replace(" ", " "))
    if not texte or texte in "-.,":
        return 0.0
    if "," in texte and "." in texte:
        # Le dernier séparateur rencontré est le séparateur décimal
        if texte.rfind(",") > texte.rfind("."):
            texte = texte.replace(".", "").replace(",", ".")
        else:
            texte = texte.replace(",", "")
    else:
        texte = texte.replace(",", ".")
    try:
        return float(texte)
    except ValueError:
        return 0.0


def convertir(valeur: str, conversion: str):
    if conversion == "nombre":
        return en_nombre(valeur)
    if conversion == "date":
        return date_iso(valeur)
    return str(valeur or "").strip()


# --- import ---------------------------------------------------------------


@dataclass
class Rapport:
    cible: str = ""
    lus: int = 0
    crees: int = 0
    mis_a_jour: int = 0
    ignores: int = 0
    erreurs: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    simulation: bool = True

    def resume(self) -> str:
        mode = "Simulation" if self.simulation else "Import"
        texte = (f"{mode} — {LIBELLES_CIBLES.get(self.cible, self.cible)}\n"
                 f"{self.lus} enregistrement(s) lu(s), {self.crees} créé(s), "
                 f"{self.mis_a_jour} mis à jour, {self.ignores} ignoré(s).")
        if self.avertissements:
            texte += "\n\nAvertissements :\n" + "\n".join(
                f"  · {a}" for a in self.avertissements[:15])
            if len(self.avertissements) > 15:
                texte += f"\n  · … et {len(self.avertissements) - 15} autre(s)"
        if self.erreurs:
            texte += "\n\nErreurs :\n" + "\n".join(f"  · {e}" for e in self.erreurs[:15])
            if len(self.erreurs) > 15:
                texte += f"\n  · … et {len(self.erreurs) - 15} autre(s)"
        return texte


class Importateur:
    """Applique une correspondance à un fichier sondé.

    Toute reprise peut d'abord être lancée en simulation : rien n'est écrit, mais
    le rapport dit exactement ce qui serait créé, modifié ou ignoré.
    """

    def __init__(self, depot):
        self.depot = depot

    def _index_externe(self, elements) -> dict[str, object]:
        return {e.ref_externe: e for e in elements if getattr(e, "ref_externe", "")}

    def executer(self, sondage: Sondage, cible: str, correspondance: dict[str, int],
                 simulation: bool = True) -> Rapport:
        rapport = Rapport(cible=cible, simulation=simulation)
        enregistrements = lire_enregistrements(sondage)
        rapport.lus = len(enregistrements)
        champs = {c.cle: c for c in CHAMPS[cible]}

        def valeur(ligne: list[str], cle: str):
            index = correspondance.get(cle)
            if index is None or index >= len(ligne):
                return "" if champs[cle].conversion == "texte" else (
                    0.0 if champs[cle].conversion == "nombre" else "")
            return convertir(ligne[index], champs[cle].conversion)

        methode = getattr(self, f"_importer_{cible}")
        methode(enregistrements, valeur, rapport, simulation)
        return rapport

    # --- une méthode par cible -------------------------------------------

    def _importer_clients(self, enregistrements, valeur, rapport, simulation):
        existants = self._index_externe(self.depot.clients())
        for numero, ligne in enumerate(enregistrements, start=1):
            nom = valeur(ligne, "nom")
            societe = valeur(ligne, "societe")
            if not (nom or societe):
                rapport.ignores += 1
                rapport.avertissements.append(f"Ligne {numero} : ni nom ni raison sociale")
                continue
            ref = valeur(ligne, "ref_externe")
            client = existants.get(ref) if ref else None
            nouveau = client is None
            client = client or Client()
            for cle in ("civilite", "nom", "prenom", "societe", "siret", "adresse",
                        "cp", "ville", "telephone", "mobile", "email", "notes"):
                setattr(client, cle, valeur(ligne, cle))
            client.ref_externe = ref
            client.type = "professionnel" if (societe or client.siret) else "particulier"
            if not simulation:
                self.depot.enregistrer_client(client)
                existants[ref] = client
            rapport.crees += nouveau
            rapport.mis_a_jour += not nouveau

    def _importer_chantiers(self, enregistrements, valeur, rapport, simulation):
        existants = self._index_externe(self.depot.chantiers())
        clients = self._index_externe(self.depot.clients())
        for numero, ligne in enumerate(enregistrements, start=1):
            libelle = valeur(ligne, "libelle")
            if not libelle:
                rapport.ignores += 1
                rapport.avertissements.append(f"Ligne {numero} : libellé vide")
                continue
            ref = valeur(ligne, "ref_externe")
            chantier = existants.get(ref) if ref else None
            nouveau = chantier is None
            chantier = chantier or Chantier()
            chantier.libelle = libelle
            for cle in ("adresse", "cp", "ville", "notes", "date_debut", "date_fin"):
                setattr(chantier, cle, valeur(ligne, cle))
            chantier.ref_externe = ref
            client_ref = valeur(ligne, "client_ref")
            client = clients.get(client_ref)
            if client is None and client_ref:
                rapport.avertissements.append(
                    f"Ligne {numero} : client « {client_ref} » introuvable, chantier non rattaché")
            chantier.client_id = client.id if client else ""
            if not simulation:
                self.depot.enregistrer_chantier(chantier)
                existants[ref] = chantier
            rapport.crees += nouveau
            rapport.mis_a_jour += not nouveau

    def _importer_articles(self, enregistrements, valeur, rapport, simulation):
        existants = self._index_externe(self.depot.articles())
        par_reference = {a.reference: a for a in self.depot.articles() if a.reference}
        for numero, ligne in enumerate(enregistrements, start=1):
            designation = valeur(ligne, "designation")
            if not designation:
                rapport.ignores += 1
                rapport.avertissements.append(f"Ligne {numero} : désignation vide")
                continue
            ref = valeur(ligne, "ref_externe")
            reference = valeur(ligne, "reference")
            article = existants.get(ref) or par_reference.get(reference)
            nouveau = article is None
            article = article or Article()
            article.designation = designation
            article.reference = reference
            for cle in ("detail", "famille", "unite"):
                setattr(article, cle, valeur(ligne, cle))
            article.prix_achat = valeur(ligne, "prix_achat")
            article.prix_vente = valeur(ligne, "prix_vente") or article.prix_achat
            tva = valeur(ligne, "taux_tva")
            article.taux_tva = tva if tva else self.depot.societe.taux_tva_defaut
            article.famille = article.famille or "Divers"
            article.unite = article.unite or "u"
            article.ref_externe = ref
            if not simulation:
                self.depot.enregistrer_article(article)
                existants[ref] = article
                if reference:
                    par_reference[reference] = article
            rapport.crees += nouveau
            rapport.mis_a_jour += not nouveau

    def _importer_devis(self, enregistrements, valeur, rapport, simulation):
        existants = self._index_externe(self.depot.devis())
        clients = self._index_externe(self.depot.clients())
        chantiers = self._index_externe(self.depot.chantiers())
        statuts = {"accepte": "accepté", "accepté": "accepté", "signe": "accepté",
                   "refuse": "refusé", "refusé": "refusé", "perdu": "refusé",
                   "envoye": "envoyé", "envoyé": "envoyé", "encours": "envoyé",
                   "brouillon": "brouillon", "annule": "annulé"}
        for numero, ligne in enumerate(enregistrements, start=1):
            ref = valeur(ligne, "ref_externe") or valeur(ligne, "numero")
            if not ref:
                rapport.ignores += 1
                rapport.avertissements.append(f"Ligne {numero} : ni référence ni numéro")
                continue
            devis = existants.get(ref)
            nouveau = devis is None
            devis = devis or Devis()
            devis.numero = valeur(ligne, "numero") or ref
            devis.objet = valeur(ligne, "objet")
            devis.notes_internes = valeur(ligne, "notes_internes")
            devis.date_devis = valeur(ligne, "date_devis") or devis.date_devis
            devis.remise_globale_pct = valeur(ligne, "remise_globale_pct")
            devis.acompte_pct = valeur(ligne, "acompte_pct")
            brut = _normaliser(valeur(ligne, "statut"))
            devis.statut = statuts.get(brut, "accepté" if not brut else "brouillon")
            client = clients.get(valeur(ligne, "client_ref"))
            if client is None:
                rapport.avertissements.append(
                    f"Ligne {numero} : client introuvable pour le devis {devis.numero}")
            devis.client_id = client.id if client else ""
            chantier = chantiers.get(valeur(ligne, "chantier_ref"))
            devis.chantier_id = chantier.id if chantier else ""
            devis.ref_externe = ref
            if not simulation:
                self.depot.enregistrer_devis(devis)
                existants[ref] = devis
            rapport.crees += nouveau
            rapport.mis_a_jour += not nouveau

    def _importer_lignes(self, enregistrements, valeur, rapport, simulation):
        devis_par_ref: dict[str, Devis] = {}
        for devis in self.depot.devis():
            if devis.ref_externe:
                devis_par_ref[devis.ref_externe] = devis
            if devis.numero:
                devis_par_ref.setdefault(devis.numero, devis)

        touches: dict[str, Devis] = {}
        orphelines: set[str] = set()
        for numero, ligne in enumerate(enregistrements, start=1):
            ref = valeur(ligne, "devis_ref")
            devis = devis_par_ref.get(ref)
            if devis is None:
                rapport.ignores += 1
                orphelines.add(ref)
                continue
            if devis.id not in touches:
                # Première ligne reprise pour ce devis : on repart d'un devis vide
                devis.lignes = []
                touches[devis.id] = devis
            type_brut = _normaliser(valeur(ligne, "type"))
            if type_brut.startswith(("sect", "lot", "titre", "chapitre")):
                type_ligne = "section"
            elif type_brut.startswith(("texte", "comment", "obs")):
                type_ligne = "texte"
            else:
                type_ligne = "prestation"
            nouvelle = Ligne(
                id=nouvel_id(),
                type=type_ligne,
                designation=valeur(ligne, "designation"),
                detail=valeur(ligne, "detail"),
                quantite=valeur(ligne, "quantite") or 1.0,
                unite=valeur(ligne, "unite") or "u",
                prix_unitaire=valeur(ligne, "prix_unitaire"),
                taux_tva=valeur(ligne, "taux_tva") or self.depot.societe.taux_tva_defaut,
                remise_pct=valeur(ligne, "remise_pct"),
            )
            devis.lignes.append(nouvelle)
            rapport.crees += 1

        if orphelines:
            rapport.avertissements.append(
                f"{len(orphelines)} référence(s) de devis inconnue(s) : "
                + ", ".join(sorted(orphelines)[:5])
                + " — importez d'abord les en-têtes de devis."
            )
        if not simulation:
            for devis in touches.values():
                self.depot.enregistrer_devis(devis)
        rapport.mis_a_jour = len(touches)


def appliquer_reglages(sondage: Sondage, encodage: str, separateur: str,
                       a_un_entete: bool) -> Sondage:
    """Reconstruit un sondage avec des réglages corrigés à la main.

    Sert quand la détection automatique se trompe : l'utilisateur change
    l'encodage ou le séparateur et l'aperçu se met à jour aussitôt.
    """
    nouveau = Sondage(chemin=sondage.chemin, taille=sondage.taille)
    nouveau.encodage = encodage
    nouveau.separateur = separateur
    nouveau.largeur_fixe = not separateur
    nouveau.remarques = list(sondage.remarques)

    texte = sondage.chemin.read_bytes().decode(encodage, errors="replace")
    lignes = [l for l in texte.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]
    decoupees = [[c.strip().strip('"') for c in l.split(separateur)] if separateur else [l]
                 for l in lignes[:13]]
    nouveau.colonnes = max((len(l) for l in decoupees), default=1)
    nouveau.a_un_entete = a_un_entete
    nouveau.lignes = max(0, len(lignes) - (1 if a_un_entete else 0))
    if a_un_entete and decoupees:
        nouveau.entete = decoupees[0]
        nouveau.apercu = decoupees[1:]
    else:
        nouveau.entete = [f"Colonne {i + 1}" for i in range(nouveau.colonnes)]
        nouveau.apercu = decoupees
    return nouveau
