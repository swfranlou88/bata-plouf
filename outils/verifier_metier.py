"""Contrôle les règles métier qui ne doivent jamais se briser.

Pas une suite de tests exhaustive : les quelques vérités dont dépend la
confiance qu'on peut accorder au logiciel. Un devis dont les totaux dérivent,
une facturation qui ne retombe pas sur le marché ou un journal comptable
déséquilibré sont des fautes qu'on ne rattrape pas après coup.

    uv run python outils/verifier_metier.py
"""

import sys
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

ECHECS: list[str] = []


def verifier(intitule: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ✓ {intitule}")
    else:
        ECHECS.append(f"{intitule}{' — ' + detail if detail else ''}")
        print(f"  ✗ {intitule}{' — ' + detail if detail else ''}")


def main() -> int:
    from bata_plouf.adaptateurs.depot_fichiers import DepotFichiers, ErreurReference
    from bata_plouf.adaptateurs.import_batappli import (
        deviner_correspondance, en_nombre, sonder,
    )
    from bata_plouf.domaine import (
        Article, Chantier, Client, Devis, Facture, Ligne, Societe, date_fr,
        date_iso, euros, sou,
    )
    from bata_plouf.domaine.comptabilite import (
        ecritures_ventes, equilibre, periode_annee, recapitulatif_tva,
    )
    from bata_plouf.adaptateurs.impression import html_document
    from bata_plouf.adaptateurs.impression.blocs import Contexte
    from bata_plouf.adaptateurs.impression.document import corps_html
    from bata_plouf.domaine.gabarit import Gabarit, MODELES_PREDEFINIS
    from bata_plouf.domaine.entites import depuis_dict, en_dict
    from bata_plouf.domaine.facturation import (
        acomptes_a_absorber, etat_avancement, generer_acompte, generer_avoir,
        generer_facture_totale, generer_situation, generer_solde,
        reste_a_facturer,
    )

    atelier = Path(tempfile.mkdtemp())
    depot = DepotFichiers(atelier / "données")
    depot.charger()
    depot.enregistrer_societe(Societe(nom="Essai"))
    client = depot.enregistrer_client(Client(nom="Durand", prenom="Paul"))
    chantier = depot.enregistrer_chantier(
        Chantier(client_id=client.id, libelle="Garage"))
    article = depot.enregistrer_article(
        Article(reference="PAR20", designation="Parpaing", prix_vente=62))

    print("\nFiches")
    verifier("le client reçoit un numéro", client.numero == "1", client.numero)
    second = depot.enregistrer_client(Client(nom="Lafont"))
    verifier("la numérotation s'incrémente", second.numero == "2", second.numero)
    verifier("le numéro sert à la recherche",
             depot.clients("2") == [second])
    # La reprise de l'ancien logiciel amène des numéros déjà attribués ; la
    # série doit les prolonger, pas recommencer à côté d'eux.
    depot.enregistrer_client(Client(nom="Ancien", numero="697"))
    verifier("la série reprend après un numéro repris",
             depot.prochain_numero_client() == "698",
             depot.prochain_numero_client())
    verifier("le bénéfice d'un article se calcule",
             Article(prix_achat=38, prix_vente=62).benefice == 24.0)
    verifier("l'article garde son fournisseur",
             depot.enregistrer_article(
                 Article(designation="Sable", fournisseur="Point P")).fournisseur
             == "Point P")

    print("\nTotaux du devis")
    devis = depot.enregistrer_devis(Devis(
        client_id=client.id, chantier_id=chantier.id, statut="accepté",
        remise_globale_pct=0,
        lignes=[Ligne(designation="Gros œuvre", quantite=1, unite="forfait",
                      prix_unitaire=10000, taux_tva=20),
                Ligne(designation="Enduits", quantite=1, unite="forfait",
                      prix_unitaire=5000, taux_tva=10)]))
    totaux = devis.totaux()
    verifier("total HT", totaux.total_ht == Decimal("15000.00"),
             str(totaux.total_ht))
    verifier("TVA ventilée sur deux taux", len(totaux.tva) == 2)
    verifier("TVA = 2000 + 500", totaux.total_tva == Decimal("2500.00"),
             str(totaux.total_tva))
    verifier("TTC = HT + TVA", totaux.total_ttc == totaux.total_ht + totaux.total_tva)

    remise = Devis(lignes=list(devis.lignes), remise_globale_pct=10)
    t2 = remise.totaux()
    verifier("remise globale appliquée au prorata",
             t2.total_ht == Decimal("13500.00")
             and sum((l.base_ht for l in t2.tva), sou(0)) == t2.total_ht,
             str(t2.total_ht))

    print("\nDu devis à la facture")
    simple = depot.enregistrer_devis(Devis(
        client_id=client.id, statut="accepté", objet="Mur de clôture",
        adresse_chantier="8 chemin du Verger, 81990 Cambon",
        lignes=[Ligne(type="section", designation="Maçonnerie"),
                Ligne(designation="Mur 1,80 m", quantite=22, unite="ml",
                      prix_unitaire=165, taux_tva=10)]))
    totale = depot.enregistrer_facture(generer_facture_totale(depot, simple))
    verifier("la facture reprend toutes les lignes du devis",
             len(totale.lignes) == len(simple.lignes))
    # Une suite de factures doit être continue et sans trou, et celle de
    # l'entreprise court depuis son ancien logiciel : la série se prolonge.
    verifier("la facture reçoit un numéro entier", totale.numero == "1",
             totale.numero)
    verifier("la série des factures s'incrémente sans trou",
             depot.prochain_numero_facture() == "2",
             depot.prochain_numero_facture())
    verifier("pour le même montant",
             totale.totaux().total_ttc == simple.totaux().total_ttc,
             f"{euros(totale.totaux().total_ttc)} / {euros(simple.totaux().total_ttc)}")
    verifier("l'adresse de chantier libre est reprise",
             totale.adresse_chantier == simple.adresse_chantier)
    verifier("et imprimée sur les deux documents",
             "Cambon" in html_document(depot, simple)
             and "Cambon" in html_document(depot, totale))
    verifier("le devis est alors entièrement facturé",
             reste_a_facturer(depot, simple) == sou(0))

    print("\nFacturation")
    acompte = depot.enregistrer_facture(generer_acompte(depot, devis, 30))
    s1 = depot.enregistrer_facture(generer_situation(depot, devis, 60))
    s2 = depot.enregistrer_facture(generer_situation(depot, devis, 85))
    solde = depot.enregistrer_facture(generer_solde(depot, devis))
    du_devis = depot.factures(devis_id=devis.id)
    somme = sum((f.totaux().total_ht for f in du_devis), sou(0))
    somme_ttc = sum((f.totaux().total_ttc for f in du_devis), sou(0))
    verifier("acompte de 30 % du marché",
             acompte.totaux().total_ht == Decimal("4500.00"))
    verifier("situation à 60 % ne facture que l'écart",
             s1.totaux().total_ht == Decimal("4500.00"))
    verifier("situation à 85 % ne facture que l'écart",
             s2.totaux().total_ht == Decimal("3750.00"))
    verifier("la somme des factures égale le marché, au centime",
             somme == totaux.total_ht and somme_ttc == totaux.total_ttc,
             f"{euros(somme)} / {euros(totaux.total_ht)}")
    verifier("plus rien à facturer", reste_a_facturer(depot, devis) == sou(0))

    for facture in depot.factures(devis_id=devis.id):
        facture.statut = "émise"
        depot.enregistrer_facture(facture)
    avoir = depot.enregistrer_facture(generer_avoir(depot, acompte))
    acompte.statut = "annulée"
    depot.enregistrer_facture(acompte)
    verifier("l'avoir porte des montants négatifs",
             avoir.totaux().total_ht == Decimal("-4500.00"))
    verifier("l'avoir rouvre le montant à facturer",
             reste_a_facturer(depot, devis) == Decimal("4500.00"))

    print("\nSituations poste par poste")
    chantier2 = depot.enregistrer_chantier(
        Chantier(client_id=client.id, libelle="Extension"))
    detaille = depot.enregistrer_devis(Devis(
        client_id=client.id, chantier_id=chantier2.id, statut="accepté",
        lignes=[Ligne(type="section", designation="Terrassement"),
                Ligne(id="P1", designation="Fouilles", quantite=1, unite="forfait",
                      prix_unitaire=3000, taux_tva=20),
                Ligne(type="section", designation="Maçonnerie"),
                Ligne(id="P2", designation="Murs", quantite=1, unite="forfait",
                      prix_unitaire=7000, taux_tva=20),
                Ligne(type="section", designation="Enduits"),
                Ligne(id="P3", designation="Enduit", quantite=1, unite="forfait",
                      prix_unitaire=5000, taux_tva=10)]))
    marche_detaille = detaille.totaux()
    avance = depot.enregistrer_facture(generer_acompte(depot, detaille, 30))
    avance.statut = "émise"
    depot.enregistrer_facture(avance)

    etape1 = depot.enregistrer_facture(
        generer_situation(depot, detaille, {"P1": 100, "P2": 40, "P3": 0}))
    etape1.statut = "émise"
    depot.enregistrer_facture(etape1)
    verifier("chaque poste est facturé à son propre avancement",
             etape1.totaux().total_ht == Decimal("2800.00"),
             euros(etape1.totaux().total_ht))
    verifier("l'acompte est déduit au bas de la situation",
             any(l.nature == "deduction_acompte" for l in etape1.lignes))
    verifier("la structure en lots est conservée",
             sum(1 for l in etape1.lignes if l.type == "section") == 3)

    etats = {e.ligne.id: e for e in etat_avancement(depot, detaille)}
    verifier("l'avancement déjà atteint est mémorisé par poste",
             etats["P1"].pct_deja == 100.0 and etats["P2"].pct_deja == 40.0
             and etats["P3"].pct_deja == 0.0,
             f"{etats['P1'].pct_deja} / {etats['P2'].pct_deja} / {etats['P3'].pct_deja}")

    etape2 = depot.enregistrer_facture(
        generer_situation(depot, detaille, {"P1": 100, "P2": 100, "P3": 100}))
    etape2.statut = "émise"
    depot.enregistrer_facture(etape2)
    verifier("un poste déjà soldé n'est pas refacturé",
             all(l.ligne_origine != "P1" for l in etape2.lignes))
    verifier("l'acompte n'est déduit qu'une fois",
             acomptes_a_absorber(depot, detaille) == {})

    factures_detaille = depot.factures(devis_id=detaille.id)
    cumul = sum((f.totaux().total_ht for f in factures_detaille), sou(0))
    verifier("la somme des situations retombe sur le marché",
             cumul == marche_detaille.total_ht,
             f"{euros(cumul)} / {euros(marche_detaille.total_ht)}")
    par_taux = {}
    for f in factures_detaille:
        for part in f.totaux().tva:
            par_taux[part.taux] = par_taux.get(part.taux, sou(0)) + part.base_ht
    verifier("et taux de TVA par taux de TVA",
             all(par_taux[l.taux] == l.base_ht for l in marche_detaille.tva),
             str({t: str(v) for t, v in par_taux.items()}))
    verifier("plus rien à facturer sur ce devis",
             reste_a_facturer(depot, detaille) == sou(0))

    print("\nTableau de bord")
    # L'accueil annonce « facturé cette année » : une facture d'un exercice
    # antérieur ne doit pas s'y ajouter, alors qu'elle compte toujours dans
    # ce qui reste à encaisser.
    avant = depot.statistiques()
    ancienne = depot.enregistrer_facture(Facture(
        client_id=client.id, statut="émise", date_facture="2019-06-14",
        lignes=[Ligne(designation="Mur", quantite=1, unite="ml",
                      prix_unitaire=1000, taux_tva=10)]))
    apres = depot.statistiques()
    verifier("une facture d'un exercice passé ne gonfle pas l'année en cours",
             apres["ht_facture"] == avant["ht_facture"],
             f"{euros(avant['ht_facture'])} → {euros(apres['ht_facture'])}")
    verifier("mais elle reste à encaisser",
             apres["ttc_impaye"] - avant["ttc_impaye"] == sou(1100),
             euros(apres["ttc_impaye"] - avant["ttc_impaye"]))
    # On la laisse en place : émise, elle ne peut plus être supprimée — c'est
    # justement la règle que le contrôle suivant vérifie.

    print("\nVerrou comptable")
    try:
        depot.supprimer_facture(s1.id)
        verifier("une facture émise ne peut pas être supprimée", False)
    except ErreurReference:
        verifier("une facture émise ne peut pas être supprimée", True)

    print("\nSuppression douce")
    actifs = len(depot.clients())
    archives = len(depot.clients(supprimes=True))
    depot.supprimer_client(client.id)
    verifier("le client sort des listes", len(depot.clients()) == actifs - 1)
    verifier("il reste dans la corbeille",
             len(depot.clients(supprimes=True)) == archives + 1)
    verifier("les devis le nomment encore",
             depot.nom_client(client.id) == "Paul Durand")
    try:
        depot.supprimer_client(client.id, definitif=True)
        verifier("l'effacement définitif est refusé s'il reste des références", False)
    except ErreurReference:
        verifier("l'effacement définitif est refusé s'il reste des références", True)
    depot.restaurer_client(client.id)
    verifier("la restauration le remet dans les listes",
             len(depot.clients()) == actifs)

    print("\nComptabilité")
    periode = periode_annee(int(acompte.date_facture[:4]))
    ecritures = ecritures_ventes(depot, periode)
    debits, credits = equilibre(ecritures)
    verifier("débit et crédit s'équilibrent", debits == credits,
             f"{euros(debits)} / {euros(credits)}")
    recap = recapitulatif_tva(depot, periode)
    verifier("le récapitulatif de TVA couvre les deux taux", len(recap) == 2)

    print("\nRelecture des fichiers")
    relu = DepotFichiers(depot.racine)
    relu.charger()
    verifier("tout se relit sans anomalie", relu.anomalies == [], str(relu.anomalies))
    verifier("les totaux survivent à l'aller-retour",
             relu.un_devis(devis.id).totaux().total_ht == totaux.total_ht)
    verifier("les factures aussi", len(relu.factures()) == len(depot.factures()))

    print("\nArchive zip")
    # L'import remplace toute la base : il doit rendre exactement ce qu'il a
    # pris, et refuser tout le reste sans rien abîmer.
    from bata_plouf.adaptateurs import archive
    # Le logo part avec le reste : sans lui, l'en-tête des devis arriverait
    # nu sur le poste qui reprend l'archive.
    emblème = atelier / "logo.png"
    emblème.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
    enseigne = depot.societe
    enseigne.logo = str(emblème)
    depot.enregistrer_societe(enseigne)

    zip_ = archive.ecrire(depot, atelier / "archive")
    inventaire = archive.inspecter(zip_)
    verifier("l'archive s'annonce comme la nôtre",
             inventaire.exploitable and inventaire.version != "",
             str(inventaire.problemes or inventaire.version))
    verifier("elle annonce le bon nombre de pièces",
             inventaire.comptes.get("factures") == len(depot.factures()),
             str(inventaire.comptes))

    repris = DepotFichiers(atelier / "repris")
    repris.charger()
    archive.restaurer(repris, zip_)
    verifier("l'import rend les mêmes clients",
             [c.id for c in repris.clients()] == [c.id for c in depot.clients()])
    verifier("et les mêmes factures, au centime",
             [(f.numero, f.totaux().total_ttc) for f in repris.factures()]
             == [(f.numero, f.totaux().total_ttc) for f in depot.factures()])
    verifier("les compteurs de numérotation suivent",
             repris.prochain_numero_facture() == depot.prochain_numero_facture(),
             f"{repris.prochain_numero_facture()} / {depot.prochain_numero_facture()}")
    verifier("l'archive emporte le logo", archive.inspecter(zip_).logo)
    verifier("et il est reposé dans le nouveau dossier",
             Path(repris.societe.logo).is_file()
             and Path(repris.societe.logo).parent == repris.racine,
             repris.societe.logo)

    # Un zip étranger ne doit pas effleurer la base.
    etranger = atelier / "etranger.zip"
    with zipfile.ZipFile(etranger, "w") as z:
        z.writestr("photo.jpg", b"\xff\xd8\xff")
    temoin = [c.id for c in repris.clients()]
    try:
        archive.restaurer(repris, etranger)
        verifier("un zip étranger est refusé", False)
    except archive.ErreurArchive:
        verifier("un zip étranger est refusé", True)
    verifier("et la base n'a pas bougé",
             [c.id for c in repris.clients()] == temoin)

    # Un nom de fichier qui cherche à sortir du dossier est écarté.
    evasion = atelier / "evasion.zip"
    with zipfile.ZipFile(zip_) as source, zipfile.ZipFile(evasion, "w") as cible:
        for membre in source.infolist():
            cible.writestr(membre, source.read(membre))
        cible.writestr("../../PIRATE.json", "[]")
    verifier("un chemin d'évasion est écarté",
             archive.inspecter(evasion).ecartes == ["../../PIRATE.json"],
             str(archive.inspecter(evasion).ecartes))
    archive.restaurer(repris, evasion)
    verifier("et rien ne s'écrit hors du dossier de données",
             not list(atelier.glob("PIRATE*.json"))
             and not list(atelier.parent.glob("PIRATE*.json")))

    print("\nMise en page classique")
    moderne = depot.gabarit
    verifier("le modèle d'origine reste le moderne", not moderne.classique,
             moderne.mise_en_page)

    reglages = en_dict(Gabarit())
    reglages.update(MODELES_PREDEFINIS["Artisan (classique)"])
    reglages["entete_activite"] = "Travaux Divers\nMaçonnerie"
    reglages["entete_qualite"] = "Artisan Maçon"
    artisan = depuis_dict(Gabarit, reglages)
    verifier("le modèle Artisan bascule en classique", artisan.classique)

    depot.enregistrer_gabarit(artisan)
    page = html_document(depot, simple)
    verifier("les métiers sont annoncés dans l'en-tête",
             "Travaux Divers" in page and "Artisan Maçon" in page)
    verifier("l'objet est repris en capitales",
             (simple.objet or "").upper() in page or not simple.objet)
    verifier("les colonnes portent les intitulés de la maison",
             all(mot in page for mot in ("LIBELLE", "QTE", "P.U.", "TOTAL EU")))
    verifier("le cadre des totaux est chiffré",
             "TOTAL HT" in page and "TOTAL TTC" in page)
    verifier("l'adresse du client est imprimée", "Cambon" in page)

    facture_classique = html_document(depot, totale)
    verifier("une facture annonce le reste dû", "RESTE DÛ" in facture_classique)

    # Un devis annonce un acompte, une facture réclame un paiement : les deux
    # ne se règlent pas avec la même phrase.
    profil = depot.societe
    profil.conditions_paiement = "Acompte à la commande."
    profil.conditions_facture = "Règlement à réception."
    depot.enregistrer_societe(profil)
    totale.conditions = ""
    verifier("la facture prend ses propres conditions",
             "Règlement à réception" in html_document(depot, totale))
    simple.conditions = ""
    verifier("le devis garde les siennes",
             "Acompte à la commande" in html_document(depot, simple))
    profil.conditions_facture = ""
    depot.enregistrer_societe(profil)
    verifier("et sans les siennes, la facture reprend celles du devis",
             "Acompte à la commande" in html_document(depot, totale))

    # Le fond du tableau est ce que le rendu étire pour atteindre le bas de
    # page ; sans Qt, on vérifie au moins que la commande arrive jusqu'à lui.
    etire = corps_html(Contexte(depot=depot, document=simple, gabarit=artisan,
                                remplissage_px=400))
    verifier("le fond du tableau se laisse étirer",
             "padding-bottom:400px" in etire)
    verifier("et ne l'est pas sans qu'on le demande",
             "padding-bottom:0px" in html_document(depot, simple))

    depot.enregistrer_gabarit(moderne)
    retour = html_document(depot, simple)
    verifier("la mise en page moderne est intacte",
             "Désignation" in retour and "LIBELLE" not in retour)

    print("\nBibliothèque de prix")
    # Un ouvrage porte deux choses : ce qu'on en dit au client, et ce qui
    # sert à en bâtir le prix. La seconde ne doit jamais sortir sur papier.
    article.detail = "Fourni et posé"
    article.notes_internes = "Main d'oeuvre 2.930 — ne doit jamais sortir"
    depot.enregistrer_article(article)
    relu = depot.article(article.id)
    verifier("les notes internes se conservent",
             relu.notes_internes.startswith("Main d'oeuvre"))

    essai = Devis(client_id=client.id, objet="Essai des notes", lignes=[
        Ligne(designation=relu.designation, detail=relu.detail, quantite=1,
              unite=relu.unite, prix_unitaire=relu.prix_vente,
              taux_tva=relu.taux_tva)])
    papier = html_document(depot, essai)
    verifier("le détail s'imprime sous la désignation",
             "Fourni et posé" in papier)
    verifier("les notes internes ne s'impriment jamais",
             "ne doit jamais sortir" not in papier)
    verifier("mais la bibliothèque les retrouve",
             relu.id in [a.id for a in depot.articles("2.930")])

    # Le bandeau des écrans Matériaux et Ouvrages, lui, ne cherche que sur
    # le nom et le code : la famille a sa propre liste déroulante, et
    # presque toute la bibliothèque porte la même.
    from bata_plouf.adaptateurs.interface.vues import VueCatalogue
    cherche = VueCatalogue.correspond
    class Bandeau:
        champs_recherche = VueCatalogue.champs_recherche
        def __init__(self, texte):
            self.recherche = type("Champ", (), {"text": lambda _: texte})()
    relu.designation, relu.famille = "Carrelage posé", "Maçonnerie"
    relu.reference = "XX"
    verifier("le début du nom trouve la fiche", cherche(Bandeau("carrelage"), relu))
    verifier("le code aussi", cherche(Bandeau("xx"), relu))
    verifier("l'accent ne gêne pas",
             cherche(Bandeau("carrelage pose"), relu)
             and cherche(Bandeau("carrelage posé"), relu))
    verifier("mais pas un mot pris au milieu",
             not cherche(Bandeau("posé"), relu))
    verifier("ni la famille", not cherche(Bandeau("maçonnerie"), relu))

    from bata_plouf.adaptateurs.interface.commun import amorce
    verifier("la part surlignée couvre ce qu'on a tapé",
             amorce("Coffrage des linteaux", "coffrage des") == 12,
             str(amorce("Coffrage des linteaux", "coffrage des")))
    verifier("et tient compte des accents sans décaler",
             amorce("Épinal", "epi") == 3, str(amorce("Épinal", "epi")))
    verifier("rien à surligner quand rien ne correspond",
             amorce("Coffrage", "linteaux") == 0)

    verifier("un ouvrage et un matériau se rangent à part",
             depot.statistiques()["materiaux"]
             + depot.statistiques()["ouvrages"]
             == depot.statistiques()["articles"],
             str({c: depot.statistiques()[c]
                  for c in ("articles", "materiaux", "ouvrages")}))
    pose = depot.enregistrer_article(
        Article(designation="Carrelage posé", type="ouvrage", prix_vente=48.0))
    verifier("l'ouvrage grossit le bon compte",
             depot.statistiques()["ouvrages"] >= 1
             and pose.id in [a.id for a in depot.articles(type_="ouvrage")])
    verifier("et pas celui des matériaux",
             pose.id not in [a.id for a in depot.articles(type_="matériau")])

    print("\nRecherche d'un client")
    from bata_plouf.adaptateurs.interface.commun import (
        cle_recherche, etiquette_client,
    )
    verifier("la ville distingue deux homonymes",
             etiquette_client(Client(nom="Mougel", ville="SAINT AME"))
             != etiquette_client(Client(nom="Mougel", ville="LE SYNDICAT")))
    verifier("une fiche sans ville garde son seul nom",
             "—" not in etiquette_client(Client(nom="Mougel")))
    verifier("l'accent ne change rien",
             cle_recherche("SAINT-AMÉ") == cle_recherche("SAINT-AME"))
    verifier("le trait d'union non plus",
             cle_recherche("SAINT-AMÉ") == cle_recherche("saint ame"),
             cle_recherche("SAINT-AMÉ"))
    verifier("et la recherche porte sur n'importe quel morceau",
             cle_recherche("ame") in cle_recherche("M. Léo MOUGEL — SAINT-AMÉ"))

    print("\nAdresse du chantier")
    from bata_plouf.adaptateurs.interface.commun import adresse_en_ligne
    chez_lui = Client(nom="Mougel", adresse="12 Grande Rue", cp="88120",
                      ville="SAINT-AMÉ")
    verifier("l'adresse du client tient sur une ligne",
             adresse_en_ligne(chez_lui) == "12 Grande Rue, 88120 SAINT-AMÉ",
             adresse_en_ligne(chez_lui))
    verifier("une fiche sans adresse ne rend rien à recopier",
             adresse_en_ligne(Client(nom="Mougel")) == "")
    verifier("ni une absence de fiche", adresse_en_ligne(None) == "")

    print("\nFormats et import")
    verifier("montant français", euros(1234.5) == "1 234,50 €", euros(1234.5))
    verifier("date française", date_fr("2026-10-25") == "25/10/2026")
    verifier("date à deux chiffres", date_iso("05/03/03") == "2003-03-05")
    verifier("nombre à virgule et séparateur", en_nombre("1 234,56 €") == 1234.56)

    exporte = atelier / "CLIENTS.TXT"
    exporte.write_bytes(
        "CODE;NOM;PRENOM;VILLE\r\nC001;Rodrigues;José;Albi\r\n".encode("cp1252"))
    sondage = sonder(exporte)
    correspondance = deviner_correspondance(sondage.entete, "clients")
    verifier("encodage Windows deviné", sondage.encodage == "cp1252", sondage.encodage)
    verifier("accents restitués", sondage.apercu[0][2] == "José")
    verifier("colonnes reconnues",
             correspondance.get("nom") == 1 and correspondance.get("ville") == 3)

    print()
    if ECHECS:
        print(f"{len(ECHECS)} contrôle(s) en échec :")
        print("\n".join(f"  · {e}" for e in ECHECS))
        return 1
    print("Toutes les règles métier tiennent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
