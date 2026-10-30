"""Contrôle les règles métier qui ne doivent jamais se briser.

Pas une suite de tests exhaustive : les quelques vérités dont dépend la
confiance qu'on peut accorder au logiciel. Un devis dont les totaux dérivent,
une facturation qui ne retombe pas sur le marché ou un journal comptable
déséquilibré sont des fautes qu'on ne rattrape pas après coup.

    uv run python outils/verifier_metier.py
"""

import sys
import tempfile
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
    verifier("le client reçoit un numéro", client.numero == "C0001", client.numero)
    second = depot.enregistrer_client(Client(nom="Lafont"))
    verifier("la numérotation s'incrémente", second.numero == "C0002", second.numero)
    verifier("le numéro sert à la recherche",
             depot.clients("C0002") == [second])
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
