"""Reprise des données de BatAppli 2000 vers Bata-plouf.

BatAppli 2000 est un programme WinDev ; ses données sont dans des fichiers
HyperFileSQL (.FIC) qu'aucune bibliothèque courante ne sait lire. Le format
a été établi par observation, et vérifié en recoupant les tables entre
elles : les totaux portés sur les 65 devis et les 308 factures tombent
exactement sur la somme de leurs lignes.

Le format, pour mémoire :

  - un en-tête de la taille d'un enregistrement, où cette taille figure en
    clair aux octets 5 à 10 (« *110!  1493hr » → 1493 octets) ;
  - puis les enregistrements à la file, tous de cette taille ;
  - chacun commence par un octet d'état (0x20 = vivant, autre = effacé)
    suivi d'un identifiant sur 4 octets, petit-boutien ;
  - les champs suivent à position fixe à partir de l'octet 5 ;
  - le texte est en cp1252, complété par des espaces, terminé par un octet
    nul, et peut contenir des retours à la ligne ;
  - le type « monétaire » est un entier de 10 octets petit-boutien, divisé
    par un million ;
  - quantités et taux de TVA sont des flottants sur 4 octets ;
  - les dates sont écrites AAAAMMJJ.

Emploi :

    python3 outils/reprendre_batappli.py "<dossier BatAppli 2000>" [destination]

Rien n'est écrasé : si la destination existe déjà et contient des données,
le script s'arrête.
"""
from __future__ import annotations

import collections
import re
import struct
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

MILLION = 1_000_000
VIVANT = 0x20


# --- lecture des fichiers .FIC --------------------------------------------

def lire(chemin: Path) -> list[bytes]:
    """Rend les enregistrements vivants d'une table, ou rien si elle manque."""
    if not chemin.exists():
        return []
    octets = chemin.read_bytes()
    longueur = int(octets[5:11])
    return [enreg for debut in range(longueur, len(octets), longueur)
            if len(enreg := octets[debut:debut + longueur]) == longueur
            and enreg[0] == VIVANT]


def texte(enreg: bytes, debut: int, largeur: int) -> str:
    return enreg[debut:debut + largeur].decode("cp1252", "replace").strip()


def lignes_de(enreg: bytes, debut: int, largeur: int) -> list[str]:
    """Un champ texte multiligne, débité en lignes non vides."""
    brut = enreg[debut:debut + largeur].decode("cp1252", "replace")
    return [l.strip() for l in brut.replace("\r", "\n").split("\n") if l.strip()]


def entier(enreg: bytes, debut: int) -> int:
    return struct.unpack_from("<i", enreg, debut)[0]


def monetaire(enreg: bytes, debut: int) -> float:
    """Le « monétaire » WinDev : 10 octets, six décimales."""
    return round(int.from_bytes(enreg[debut:debut + 10], "little") / MILLION, 2)


def reel(enreg: bytes, debut: int) -> float:
    (v,) = struct.unpack_from("<f", enreg, debut)
    return 0.0 if v != v or abs(v) == float("inf") else round(v, 4)


def date_iso(enreg: bytes, debut: int) -> str:
    brut = enreg[debut:debut + 8].decode("ascii", "replace")
    if not brut.isdigit() or brut == "00000000":
        return ""
    an, mois, jour = brut[:4], brut[4:6], brut[6:8]
    if not ("1900" < an < "2100" and "01" <= mois <= "12" and "01" <= jour <= "31"):
        return ""
    return f"{an}-{mois}-{jour}"


# --- vocabulaire ----------------------------------------------------------

# L'octet 127 de CLIENT, recoupé avec la civilité que BatAppli imprime en
# tête des adresses de facturation.
CIVILITES = {1: "Mme", 2: "Mlle", 3: "M.", 4: ""}

# BatAppli travaille en majuscules et garde les conditionnements du
# fournisseur ; Bata-plouf écrit les unités en minuscules.
UNITES = {
    "PE": "u", "M2": "m²", "M3": "m³", "ML": "ml", "KG": "kg", "H": "h",
    "L": "l", "BT": "bt", "SAC": "sac", "RL": "rl", "POT": "pot", "PAQ": "paq",
    "U": "u", "T": "t", "J": "j", "": "u",
}

# L'octet 13 des lignes : 1 article, 2 ouvrage, 3 titre de lot ou ligne
# vide, 4 texte libre.
PRESTATION, OUVRAGE, TITRE, TEXTE = 1, 2, 3, 4


def unite(brut: str) -> str:
    return UNITES.get(brut.upper().strip(), brut.lower().strip() or "u")


def decouper_adresse(bloc: list[str]) -> tuple[str, str, str]:
    """Débite un bloc d'adresse imprimé en (adresse, code postal, ville).

    BatAppli stocke l'adresse telle qu'elle s'imprime : le destinataire sur
    la première ligne, puis la voie, puis « 88120 SAINT-AMÉ ». On retire le
    destinataire, et on sépare le code postal de la ville.
    """
    if not bloc:
        return "", "", ""
    corps, cp, ville = list(bloc), "", ""
    derniere = re.match(r"^(\d{5})\s+(.+)$", corps[-1])
    if derniere:
        cp, ville = derniere.group(1), derniere.group(2).strip()
        corps.pop()
    # La première ligne est le nom du destinataire, pas une voie.
    if len(corps) > 1:
        corps.pop(0)
    return " ".join(corps).strip(), cp, ville


# --- disposition des champs ----------------------------------------------
# Chaque constante est l'offset du champ dans l'enregistrement.

class C:  # CLIENT, 1493 octets
    NUMERO, NOM_COMPLET, CIVILITE = 5, 26, 127
    NOM, PRENOM, SOCIETE = 128, 179, 230
    ADRESSE, CP, VILLE = 281, 482, 488
    ADR_CHANTIER, CP_CHANTIER, VILLE_CHANTIER = 539, 740, 746
    TEL1, TEL2, TEL3 = 797, 818, 839
    OBSERVATIONS, DATE, DIVERS = 860, 1361, 1391


class A:  # ART, 773 octets
    DESIGNATION, CODE = 5, 506
    PRIX_ACHAT, UNITE, TVA = 527, 537, 541
    REFERENCE, DATE, PRIX_VENTE = 591, 612, 621


class O:  # OUV, 872 octets
    DESIGNATION, CODE = 5, 506
    PRIX_ACHAT, PRIX_VENTE, UNITE, TVA = 527, 537, 547, 551
    COMPOSITION = 669


class D:  # DEVIS, 893 octets
    REFERENCE, CLIENT = 5, 26
    NOM, ADR_FACTURATION, ADR_CHANTIER = 30, 131, 332
    DATE, DATE2, VALIDITE = 533, 542, 551
    CONDITIONS, TOTAL_HT, TOTAL_TTC, OBJET = 568, 769, 779, 789
    # L'octet 563 porte « A » sur 64 devis sur 65 — il veut dire « actif »,
    # pas « accepté », et ne nous apprend donc rien. BatAppli ne note pas
    # la réponse du client : on la déduit de l'existence d'une facture.
    ETAT = 563


class F:  # FACTURE, 903 octets
    DEVIS, NUMERO, CLIENT = 5, 9, 30
    NOM, ADR_FACTURATION, ADR_CHANTIER = 34, 135, 336
    DATE, DATE2, ECHEANCE = 537, 546, 555
    CONDITIONS, TOTAL_HT, TOTAL_TTC, OBJET = 577, 778, 788, 798
    # Même constat qu'au-dessus : les trois factures qui ne portent pas
    # « A » sont de vraies factures numérotées, avec leurs lignes et leurs
    # montants. L'état est donc inutilisable ; c'est le règlement qui dit
    # si une facture est payée.
    ETAT = 567


class L:  # DEVISDET et FACTDET, 1344 octets
    PIECE, ORDRE, TYPE = 5, 9, 13
    AVANCEMENT, AVANCEMENT_PRECEDENT = 20, 24
    REFERENCE, DESIGNATION = 28, 79
    PRIX_ACHAT, PRIX_VENTE, QUANTITE = 1080, 1090, 1100
    UNITE, MONTANT_HT, TVA = 1104, 1108, 1118


class R:  # REGLEM, 65 octets
    DATE, FACTURE, MONTANT, MODE, LIBELLE = 5, 22, 30, 40, 42


# --- conversion -----------------------------------------------------------

def postes(enregs: list[bytes], Ligne) -> tuple[list, float]:
    """Traduit les lignes d'une pièce, dans l'ordre où BatAppli les range.

    Rend aussi l'écart entre les montants que BatAppli avait enregistrés et
    le produit quantité × prix unitaire. Il est nul partout sauf sur deux
    lignes d'un devis, où BatAppli avait gardé un montant périmé après un
    changement de quantité. Bata-plouf recalculant toujours ses totaux, on
    garde ce que le maçon a saisi et on signale l'écart au lieu de le taire.
    """
    resultat, derive = [], 0.0
    for e in sorted(enregs, key=lambda e: entier(e, L.ORDRE)):
        genre = e[L.TYPE]
        libelles = lignes_de(e, L.DESIGNATION, 1000)
        designation = libelles[0] if libelles else ""
        detail = "\n".join(libelles[1:])

        if genre == TITRE:
            # Les lignes vides de BatAppli n'aèrent qu'une impression ;
            # elles n'ont rien à faire dans les données.
            if not designation:
                continue
            resultat.append(Ligne(type="section", designation=designation,
                                  detail=detail))
            continue
        if genre == TEXTE:
            resultat.append(Ligne(type="texte", designation=designation,
                                  detail=detail))
            continue

        avancement = entier(e, L.AVANCEMENT)
        quantite, prix = reel(e, L.QUANTITE), monetaire(e, L.PRIX_VENTE)
        derive += monetaire(e, L.MONTANT_HT) - round(quantite * prix, 2)
        resultat.append(Ligne(
            designation=designation, detail=detail,
            quantite=quantite, unite=unite(texte(e, L.UNITE, 3)),
            prix_unitaire=prix,
            taux_tva=reel(e, L.TVA),
            avancement_pct=float(avancement) if 0 < avancement <= 100 else 0.0))
    return resultat, round(derive, 2)


def convertir(source: Path, destination: Path) -> dict:
    from bata_plouf.adaptateurs.depot_fichiers import DepotFichiers
    from bata_plouf.domaine import (Article, Chantier, Client, Devis, Facture,
                                    Ligne, Societe)

    depot = DepotFichiers(destination)
    depot.charger()
    depot.enregistrer_societe(Societe(
        nom="Entreprise Xavier RICHARD",
        forme_juridique="Maçonnerie — Rénovation",
        adresse="30 Quater Grande Rue", cp="88120", ville="SAINT-AMÉ",
        telephone="03 29 61 24 58",
        taux_tva_defaut=10.0, acompte_defaut_pct=30.0))

    bilan = collections.Counter()

    # --- les clients ------------------------------------------------------
    # BatAppli désigne ses clients par l'identifiant interne de la fiche ;
    # c'est par là que devis et factures s'y rattachent.
    enregs_clients = lire(source / "CLIENT.FIC")

    # 36 fiches sur 631 n'ont pas de numéro. Le dépôt sait en attribuer un,
    # mais il recale son compteur sur les fiches déjà écrites : une fiche
    # sans numéro rencontrée avant celles qui portent les numéros les plus
    # hauts se verrait donner un numéro déjà pris plus loin dans le fichier.
    # On balaie donc tout le fichier avant d'en attribuer un seul.
    #
    # Les doublons que BatAppli contient déjà — 18 numéros pour 38 fiches —
    # sont conservés tels quels : ce sont ses données, et le logiciel
    # n'identifie pas ses clients par ce numéro.
    dernier_numero = max((int(texte(e, C.NUMERO, 20))
                          for e in enregs_clients if texte(e, C.NUMERO, 20).isdigit()),
                         default=0)

    def numero_libre() -> str:
        nonlocal dernier_numero
        dernier_numero += 1
        return str(dernier_numero)

    par_id = {}
    for e in enregs_clients:
        notes = "\n".join(lignes_de(e, C.OBSERVATIONS, 500)
                          + lignes_de(e, C.DIVERS, 50))
        appellation = texte(e, C.NOM_COMPLET, 100)
        nom_propre = texte(e, C.NOM, 50)
        prenom = texte(e, C.PRENOM, 50)
        complement = texte(e, C.SOCIETE, 50)

        if nom_propre:
            # Une personne : BatAppli a bien séparé le nom du prénom. Le
            # complément reste à sa place, mais la fiche garde le nom de la
            # personne comme intitulé — c'est elle qu'on cherche dans la liste.
            nom, societe = nom_propre, complement
            civilite = CIVILITES.get(e[C.CIVILITE], "")
            professionnel = e[C.CIVILITE] == 4
        else:
            # Pas de nom propre : BatAppli n'a saisi qu'une raison sociale,
            # qu'il recopie dans l'appellation et souvent dans le prénom, en
            # laissant le code civilité à « M. ». Pris au mot, cela donne des
            # « M. SCI DUPONT SCI DUPONT ».
            nom, prenom, societe = appellation, "", appellation
            civilite, professionnel = "", True
            # Le complément porte alors le représentant, pas la société.
            if complement and complement.lower() not in appellation.lower():
                notes = f"Contact : {complement}\n{notes}".strip()
        # Une adresse de courriel traîne souvent dans les observations.
        courriel = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", notes)
        # La date de création n'est renseignée que sur une partie des fiches ;
        # sans elle, on laisse Bata-plouf mettre la date du jour.
        creation = date_iso(e, C.DATE)
        client = depot.enregistrer_client(Client(
            **({"cree_le": creation} if creation else {}),
            numero=texte(e, C.NUMERO, 20) or numero_libre(),
            type="professionnel" if professionnel else "particulier",
            civilite=civilite, nom=nom, prenom=prenom, societe=societe,
            adresse=" ".join(lignes_de(e, C.ADRESSE, 200)),
            cp=texte(e, C.CP, 5), ville=texte(e, C.VILLE, 50),
            telephone=texte(e, C.TEL1, 20),
            mobile=texte(e, C.TEL2, 20),
            email=courriel.group(0) if courriel else "",
            notes="\n".join(filter(None, [
                texte(e, C.TEL3, 20) and f"Autre téléphone : {texte(e, C.TEL3, 20)}",
                notes])),
            ref_externe=f"batappli:client:{entier(e, 1)}"))
        par_id[entier(e, 1)] = client
        bilan["clients"] += 1

    # --- la bibliothèque de prix -----------------------------------------
    for e in lire(source / "ART.FIC"):
        libelles = lignes_de(e, A.DESIGNATION, 500)
        if not libelles:
            continue
        depot.enregistrer_article(Article(
            reference=texte(e, A.REFERENCE, 20) or texte(e, A.CODE, 20),
            designation=libelles[0], detail="\n".join(libelles[1:]),
            type="matériau", unite=unite(texte(e, A.UNITE, 3)),
            prix_achat=monetaire(e, A.PRIX_ACHAT),
            prix_vente=monetaire(e, A.PRIX_VENTE),
            taux_tva=reel(e, A.TVA) or 10.0,
            ref_externe=f"batappli:art:{entier(e, 1)}"))
        bilan["materiaux"] += 1

    for e in lire(source / "OUV.FIC"):
        libelles = lignes_de(e, O.DESIGNATION, 500)
        if not libelles:
            continue
        composition = lignes_de(e, O.COMPOSITION, 200)
        depot.enregistrer_article(Article(
            reference=texte(e, O.CODE, 20),
            designation=libelles[0],
            detail="\n".join(libelles[1:] + composition),
            type="ouvrage", unite=unite(texte(e, O.UNITE, 3)),
            prix_achat=monetaire(e, O.PRIX_ACHAT),
            prix_vente=monetaire(e, O.PRIX_VENTE),
            taux_tva=reel(e, O.TVA) or 10.0,
            ref_externe=f"batappli:ouv:{entier(e, 1)}"))
        bilan["ouvrages"] += 1

    # --- les chantiers ----------------------------------------------------
    # BatAppli n'a pas de fiche chantier : l'adresse des travaux est
    # recopiée sur chaque pièce. On en fait une fiche par adresse distincte.
    chantiers: dict[tuple[str, str], object] = {}

    def chantier_de(client, bloc: list[str], libelle: str):
        adresse, cp, ville = decouper_adresse(bloc)
        if not (adresse or ville):
            return ""
        cle = (client.id, f"{adresse} {cp} {ville}".lower())
        if cle not in chantiers:
            chantiers[cle] = depot.enregistrer_chantier(Chantier(
                client_id=client.id, libelle=libelle[:80] or ville,
                adresse=adresse, cp=cp, ville=ville, statut="terminé",
                notes="Adresse reprise de BatAppli."))
            bilan["chantiers"] += 1
        return chantiers[cle].id

    # --- devis et factures ------------------------------------------------
    lignes_devis = collections.defaultdict(list)
    for l in lire(source / "DEVISDET.FIC"):
        lignes_devis[entier(l, L.PIECE)].append(l)
    lignes_facture = collections.defaultdict(list)
    for l in lire(source / "FACTDET.FIC"):
        lignes_facture[entier(l, L.PIECE)].append(l)

    reglements = collections.defaultdict(list)
    for r in lire(source / "REGLEM.FIC"):
        reglements[entier(r, R.FACTURE)].append(r)

    # Un devis accepté est un devis qui a donné une facture : c'est la seule
    # trace que BatAppli en garde. Il n'y en a que 7 sur 65 — la plupart des
    # factures ont été faites directement, sans devis préalable.
    enregs_factures = lire(source / "FACTURE.FIC")
    devis_factures = {entier(f, F.DEVIS) for f in enregs_factures}

    orphelins = depot.enregistrer_client(Client(
        numero=numero_libre(),
        nom="Client inconnu (reprise BatAppli)",
        notes="Rattache les pièces dont la fiche client avait été effacée.",
        ref_externe="batappli:client:0"))

    devis_par_id = {}
    for e in lire(source / "DEVIS.FIC"):
        ident = entier(e, 1)
        client = par_id.get(entier(e, D.CLIENT))
        if client is None:
            client = orphelins
            bilan["devis_sans_client"] += 1
        objet = texte(e, D.OBJET, 100)
        lignes, derive = postes(lignes_devis.get(ident, []), Ligne)
        devis = Devis(
            numero=depot.prochain_numero(reserver=True),
            client_id=client.id,
            chantier_id=chantier_de(client, lignes_de(e, D.ADR_CHANTIER, 200), objet),
            objet=objet,
            adresse_chantier=" ".join(lignes_de(e, D.ADR_CHANTIER, 200)),
            date_devis=date_iso(e, D.DATE) or "",
            statut="accepté" if ident in devis_factures else "envoyé",
            conditions="\n".join(lignes_de(e, D.CONDITIONS, 200)),
            lignes=lignes,
            ref_externe=f"batappli:devis:{ident}",
            notes_internes=f"Repris de BatAppli (devis {ident}"
                           + (f", référence « {texte(e, D.REFERENCE, 20)} »"
                              if texte(e, D.REFERENCE, 20) else "") + ")."
                           + (f"\nAttention : BatAppli affichait "
                              f"{monetaire(e, D.TOTAL_HT):.2f} € HT, soit "
                              f"{abs(derive):.2f} € de moins que ses propres "
                              "lignes — un montant n'y avait pas été recalculé "
                              "après un changement de quantité."
                              if abs(derive) > 0.02 else ""))
        depot.enregistrer_devis(devis)
        devis_par_id[ident] = devis
        bilan["devis"] += 1
        bilan["postes"] += len(devis.lignes)
        bilan["devis_ht"] += monetaire(e, D.TOTAL_HT)
        if abs(derive) > 0.02:
            bilan["devis_recalcules"] += 1

    numeros_repris = []
    for e in enregs_factures:
        ident = entier(e, 1)
        client = par_id.get(entier(e, F.CLIENT))
        if client is None:
            client = orphelins
            bilan["factures_sans_client"] += 1
        objet = texte(e, F.OBJET, 100)
        numero = texte(e, F.NUMERO, 20)
        regle = reglements.get(ident, [])
        source_devis = devis_par_id.get(entier(e, F.DEVIS))
        lignes, derive = postes(lignes_facture.get(ident, []), Ligne)
        facture = Facture(
            numero=numero or f"BA-{ident}",
            type="directe" if source_devis is None else "totale",
            devis_id=source_devis.id if source_devis else "",
            client_id=client.id,
            chantier_id=chantier_de(client, lignes_de(e, F.ADR_CHANTIER, 200), objet),
            objet=objet,
            adresse_chantier=" ".join(lignes_de(e, F.ADR_CHANTIER, 200)),
            date_facture=date_iso(e, F.DATE) or "",
            statut="payée" if regle else "émise",
            conditions="\n".join(lignes_de(e, F.CONDITIONS, 200)),
            lignes=lignes,
            mode_paiement=texte(regle[0], R.LIBELLE, 20) if regle else "",
            date_emission=date_iso(e, F.DATE) or "",
            date_paiement=max((date_iso(r, R.DATE) for r in regle), default=""),
            ref_externe=f"batappli:facture:{ident}",
            notes_internes=f"Reprise de BatAppli (facture {ident})."
                           + (f"\nAttention : écart de {abs(derive):.2f} € "
                              "entre le total affiché par BatAppli et ses "
                              "propres lignes." if abs(derive) > 0.02 else ""))
        depot.enregistrer_facture(facture)
        numeros_repris.append(numero)
        bilan["factures"] += 1
        bilan["postes_factures"] += len(facture.lignes)
        bilan["factures_ht"] += monetaire(e, F.TOTAL_HT)
        if regle:
            bilan["reglees"] += 1

    # Le client fourre-tout ne sert que s'il a recueilli quelque chose.
    if not (bilan["devis_sans_client"] or bilan["factures_sans_client"]):
        depot.supprimer_client(orphelins.id, definitif=True)

    chiffres = [int(n) for n in numeros_repris if n.isdigit()]
    bilan["dernier_numero"] = max(chiffres) if chiffres else 0
    return dict(bilan)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1]).expanduser()
    destination = (Path(sys.argv[2]).expanduser() if len(sys.argv) > 2
                   else Path.home() / "Documents" / "Bata-plouf-batappli")
    if not (source / "CLIENT.FIC").exists():
        raise SystemExit(f"Pas de données BatAppli dans {source}")
    if (destination / "clients.json").exists():
        raise SystemExit(f"{destination} contient déjà des données ; "
                         "donnez un autre dossier de destination.")

    b = convertir(source, destination)
    print(f"\nReprise écrite dans {destination}\n")
    print(f"  {b['clients']:5d} clients")
    print(f"  {b['chantiers']:5d} chantiers, déduits des adresses de travaux")
    print(f"  {b['materiaux']:5d} matériaux et {b['ouvrages']:5d} ouvrages, avec leurs prix")
    print(f"  {b['devis']:5d} devis   {b['postes']:6d} postes   "
          f"{b['devis_ht']:12,.2f} € HT".replace(",", " "))
    print(f"  {b['factures']:5d} factures {b['postes_factures']:5d} postes   "
          f"{b['factures_ht']:12,.2f} € HT".replace(",", " "))
    print(f"  {b['reglees']:5d} factures réglées")
    if b.get("devis_recalcules"):
        print(f"\n  {b['devis_recalcules']} devis dont BatAppli affichait un total "
              "qui ne correspondait pas à ses propres lignes : Bata-plouf\n"
              "  recalcule le bon montant, et le dit dans les notes du devis.")
    if b.get("devis_sans_client") or b.get("factures_sans_client"):
        print(f"\n  {b.get('devis_sans_client', 0)} devis et "
              f"{b.get('factures_sans_client', 0)} factures dont la fiche client "
              "avait été effacée sont rattachés à « Client inconnu ».")
    print(f"\n  Dernier numéro de facture repris : {b['dernier_numero']}.")


if __name__ == "__main__":
    main()
