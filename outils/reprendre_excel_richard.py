"""Reprise des données de l'Entreprise Xavier RICHARD.

Son père ne travaillait pas sur Batappli mais sur Excel : un tableur par
chantier, contenant le métré — désignation, formule de calcul, quantité,
unité — et un STOCK.xls tenant l'inventaire par corps de métier. Les clients
vivent dans des en-têtes Word, un par client.

Il n'y a **aucun prix** nulle part : ces fichiers ne chiffrent pas, ils
mesurent. La reprise amène donc les quantités et laisse les prix à zéro,
à compléter depuis la bibliothèque une fois celle-ci tarifée.

    uv run --with xlrd python outils/reprendre_excel_richard.py \\
        "<…>/Mes documents" [dossier-destination]

Écrit dans un dossier neuf, jamais dans les données en service : on regarde
le résultat avant de l'adopter.
"""

import glob
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# Le zip a été déplié avec le mauvais jeu de caractères : les noms de
# fichiers portent des octets CP850 relus en CP1252. On les remet d'aplomb.
def reparer(texte: str) -> str:
    try:
        return texte.encode("cp1252").decode("cp850")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texte


UNITES_CONNUES = {
    "m2": "m²", "m²": "m²", "m3": "m³", "m³": "m³", "ml": "ml", "m": "ml",
    "pe": "u", "u": "u", "unite": "u", "kg": "kg", "t": "t", "l": "u",
    "sac": "u", "h": "h", "j": "j", "ens": "ens", "forfait": "forfait",
}

CIVILITES = {"mr": "M.", "m.": "M.", "mme": "Mme", "melle": "Mlle", "mlle": "Mlle"}


def nombre(texte: str) -> float | None:
    """« 13,44 » ou « 79,00 » -> float ; None si ce n'est pas un nombre."""
    t = str(texte).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def quantite_et_unite(cellule: str) -> tuple[float, str]:
    """« 13,44 m3 » -> (13.44, « m³ »). Sans unité reconnue, on met « u »."""
    texte = str(cellule).strip()
    # L'unité peut contenir un chiffre — m2, m3 — donc on la reconnaît à sa
    # lettre initiale plutôt qu'à l'absence de chiffres.
    motif = re.match(r"^\s*([\d\s.,]*?)\s*([A-Za-zÀ-ÿ²³][\w²³]*)?\s*$", texte)
    if not motif:
        return 0.0, "u"
    valeur = nombre(motif.group(1)) or 0.0
    brut = (motif.group(2) or "").strip().lower().rstrip(".")
    sans_accent = "".join(c for c in unicodedata.normalize("NFD", brut)
                          if unicodedata.category(c) != "Mn")
    return valeur, UNITES_CONNUES.get(sans_accent, UNITES_CONNUES.get(brut, "u"))


# --- les clients, lus dans les en-têtes Word ------------------------------


def lire_doc(chemin: Path) -> str:
    """Convertit un .doc en texte avec l'outil fourni par macOS."""
    resultat = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(chemin)],
        capture_output=True, text=True)
    return resultat.stdout if resultat.returncode == 0 else ""


MODELES = {"fiches clients", "pochettes clients", "pochettes", "enveloppe"}


def clients_des_entetes(source: Path) -> list[dict]:
    """Nom, adresse, code postal, ville et téléphone de chaque en-tête."""
    trouves = []
    for chemin in sorted(source.glob("*.doc")):
        if chemin.stem.lower() in MODELES:
            continue
        lignes = [re.sub(r"\s{2,}", " ", l).strip()
                  for l in lire_doc(chemin).splitlines()]
        lignes = [l for l in lignes if l and not re.match(
            r"^(Entreprise|Maçonnerie|30 Quater|:|\d{2}-\d{2})", l)]
        if not lignes:
            continue

        fiche = {"civilite": "", "prenom": "", "nom": "", "adresse": "",
                 "cp": "", "ville": "", "telephone": ""}
        for ligne in lignes:
            cp = re.match(r"^(\d{5})\s+(.+)$", ligne)
            tel = re.search(r"(0\d[-.\s]?(?:\d{2}[-.\s]?){4})", ligne)
            if cp and not fiche["cp"]:
                fiche["cp"], fiche["ville"] = cp.group(1), cp.group(2).strip()
            elif tel and not fiche["telephone"]:
                fiche["telephone"] = tel.group(1).strip()
            elif not fiche["nom"]:
                mots = ligne.split()
                if mots and mots[0].lower().rstrip(".") in CIVILITES:
                    fiche["civilite"] = CIVILITES[mots[0].lower().rstrip(".")]
                    mots = mots[1:]
                # Le nom de famille est en majuscules, le prénom non
                majuscules = [m for m in mots if m.isupper() and len(m) > 1]
                fiche["nom"] = " ".join(majuscules) or " ".join(mots)
                fiche["prenom"] = " ".join(m for m in mots if m not in majuscules)
            elif not fiche["adresse"] and re.match(r"^\d", ligne):
                fiche["adresse"] = ligne
        if fiche["nom"]:
            fiche["origine"] = chemin.stem
            trouves.append(fiche)
    return trouves


# --- la bibliothèque, lue dans STOCK.xls ----------------------------------


def articles_du_stock(chemin: Path) -> list[dict]:
    """Une feuille par corps de métier ; on en fait des familles."""
    import xlrd

    articles = []
    livre = xlrd.open_workbook(str(chemin))
    for feuille in livre.sheets():
        famille = feuille.name.strip().title()
        for r in range(feuille.nrows):
            valeurs = [str(feuille.cell_value(r, c)).strip()
                       for c in range(feuille.ncols)]
            designation = valeurs[0] if valeurs else ""
            unite = valeurs[2] if len(valeurs) > 2 else ""
            # Les lignes de titre n'ont qu'une désignation, sans unité
            if not designation or not unite:
                continue
            if designation.upper() == feuille.name.strip().upper():
                continue
            _, unite_propre = quantite_et_unite("1 " + unite)
            articles.append({"designation": designation, "unite": unite_propre,
                             "famille": famille})
    return articles


# --- les devis, lus dans les métrés ---------------------------------------


def devis_du_metre(chemin: Path) -> dict | None:
    """Un tableur de chantier devient un devis à compléter.

    Une ligne qui porte une désignation et une quantité est un poste ; une
    ligne qui ne porte qu'un texte est un titre de lot ; les formules de
    calcul deviennent le détail du poste, parce que c'est là que se trouve
    le raisonnement du métreur.
    """
    import xlrd

    livre = xlrd.open_workbook(str(chemin))
    feuille = livre.sheets()[0]
    if feuille.nrows == 0:
        return None

    lignes, intitule = [], ""
    for r in range(feuille.nrows):
        valeurs = [str(feuille.cell_value(r, c)).strip()
                   for c in range(max(3, feuille.ncols))]
        texte = valeurs[0]
        calcul = valeurs[1] if len(valeurs) > 1 else ""
        mesure = valeurs[2] if len(valeurs) > 2 else ""

        if r == 0 and texte and not mesure:
            intitule = texte
            continue
        if texte and mesure:
            quantite, unite = quantite_et_unite(mesure)
            lignes.append({"type": "prestation", "designation": texte,
                           "detail": "", "quantite": quantite, "unite": unite})
        elif texte and not calcul and not mesure:
            lignes.append({"type": "section", "designation": texte})
        elif texte and calcul and lignes and lignes[-1]["type"] == "prestation":
            # formule de calcul : elle documente la quantité
            detail = lignes[-1]["detail"]
            lignes[-1]["detail"] = (detail + " · " if detail else "") + texte
    return {"intitule": intitule or chemin.stem, "lignes": lignes} if lignes else None


# --- assemblage -----------------------------------------------------------


def convertir(source: Path, destination: Path) -> dict:
    from bata_plouf.adaptateurs.depot_fichiers import DepotFichiers
    from bata_plouf.domaine import Article, Chantier, Client, Devis, Ligne, Societe

    depot = DepotFichiers(destination)
    depot.charger()
    depot.enregistrer_societe(Societe(
        nom="Entreprise Xavier RICHARD",
        forme_juridique="Maçonnerie — Rénovation",
        adresse="30 Quater Grande Rue", cp="88120", ville="SAINT-AMÉ",
        telephone="03 29 61 24 58",
        taux_tva_defaut=10.0, acompte_defaut_pct=30.0))

    bilan = {"clients": 0, "articles": 0, "devis": 0, "lignes": 0, "sans_client": 0}

    par_nom = {}
    for fiche in clients_des_entetes(source):
        client = depot.enregistrer_client(Client(
            civilite=fiche["civilite"], nom=fiche["nom"], prenom=fiche["prenom"],
            adresse=fiche["adresse"], cp=fiche["cp"], ville=fiche["ville"],
            telephone=fiche["telephone"],
            notes=f"Repris de « {fiche['origine']}.doc »"))
        bilan["clients"] += 1
        for cle in filter(None, [fiche["nom"].lower(), fiche["prenom"].lower()]):
            par_nom.setdefault(cle.split()[0], client)

    stock = source / "STOCK.xls"
    if stock.exists():
        vus = set()
        for a in articles_du_stock(stock):
            cle = (a["designation"].lower(), a["famille"])
            if cle in vus:
                continue
            vus.add(cle)
            depot.enregistrer_article(Article(
                designation=a["designation"], unite=a["unite"],
                famille=a["famille"], type="matériau"))
            bilan["articles"] += 1

    for chemin in sorted(source.glob("*.xls")):
        if chemin.name.upper() == "STOCK.XLS":
            continue
        try:
            metre = devis_du_metre(chemin)
        except Exception:
            continue
        if metre is None:
            continue

        nom_fichier = reparer(chemin.stem)
        racine_nom = re.split(r"[\s\d]", nom_fichier)[0].lower()
        client = par_nom.get(racine_nom)
        if client is None:
            client = depot.enregistrer_client(Client(
                nom=nom_fichier,
                notes="Repris d'un métré Excel — coordonnées à compléter"))
            bilan["clients"] += 1
            bilan["sans_client"] += 1
            par_nom[racine_nom] = client

        chantier = depot.enregistrer_chantier(Chantier(
            client_id=client.id, libelle=metre["intitule"][:80], statut="terminé"))
        devis = Devis(client_id=client.id, chantier_id=chantier.id,
                      objet=metre["intitule"][:120], statut="accepté",
                      notes_internes=f"Métré repris de « {nom_fichier}.xls ». "
                                     "Les prix restent à saisir.")
        for l in metre["lignes"]:
            if l["type"] == "section":
                devis.lignes.append(Ligne(type="section", designation=l["designation"]))
            else:
                devis.lignes.append(Ligne(
                    designation=l["designation"], detail=l["detail"],
                    quantite=l["quantite"], unite=l["unite"],
                    prix_unitaire=0.0, taux_tva=10.0))
                bilan["lignes"] += 1
        depot.enregistrer_devis(devis)
        bilan["devis"] += 1

    return bilan


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1]).expanduser()
    destination = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 \
        else Path.home() / "Documents" / "Bata-plouf-reprise"
    if not source.is_dir():
        raise SystemExit(f"Dossier introuvable : {source}")

    bilan = convertir(source, destination)
    print(f"\nReprise écrite dans {destination}\n")
    print(f"  {bilan['clients']:4d} clients "
          f"({bilan['sans_client']} sans coordonnées, déduits des noms de fichiers)")
    print(f"  {bilan['articles']:4d} articles dans la bibliothèque, sans prix")
    print(f"  {bilan['devis']:4d} devis repris des métrés")
    print(f"  {bilan['lignes']:4d} postes chiffrables, tous à 0,00 €")
    print("\n  Les prix sont à saisir : les fichiers d'origine n'en contiennent aucun.")


if __name__ == "__main__":
    main()
