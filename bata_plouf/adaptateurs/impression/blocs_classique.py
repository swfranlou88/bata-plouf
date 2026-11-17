"""Le devis d'artisan, tel qu'on l'imprimait avant.

Mise en page reprise des documents de l'entreprise : en-tête à trois colonnes
(logo et identifiants à gauche, métiers au centre, nom et qualité à droite),
objet souligné au milieu, tableau entièrement encadré dont les filets
descendent jusqu'au bas de la page, et le bas partagé en trois — mentions,
adresse du chantier, cadre des totaux.

Deux partis pris la distinguent de la mise en page moderne :

  - pas de couleur. Ces documents partent sur une imprimante laser noir et
    blanc ; un aplat de couleur y devient un aplat de gris qui mange le texte.
  - le cadre du tableau descend jusqu'au bas de la page même quand le devis
    tient en trois lignes. C'est ce qui empêche qu'on y ajoute une ligne après
    signature sans que cela se voie.

Les blocs suivent la même convention que ceux de blocs.py : une fonction qui
reçoit le contexte et rend du HTML. L'assemblage est dans document.py.
"""

from decimal import Decimal

from ...domaine import Ligne, date_fr, euros, nombre
from .blocs import Contexte, conditions_par_defaut
from .styles import echapper, mm_en_px_css

NOIR = "#000000"
FILET = f"1px solid {NOIR}"
# Un trait horizontal sur toute la largeur. Qt refuse de dessiner la bordure
# basse de la dernière rangée d'un tableau ; on la pose donc juste en dessous.
TRAIT = (f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
         f"<td style='border-top:{FILET}; font-size:1pt;'>&nbsp;</td>"
         f"</tr></table>")

# L'en-tête des documents d'artisan est traditionnellement en romain : le
# reste de la page suit la police choisie dans le modèle, l'en-tête non.
SERIF = "Georgia, 'Times New Roman', serif"


def montant(valeur) -> str:
    """« 1 107,49 » — sans le symbole, la colonne annonce déjà l'euro."""
    return euros(valeur).removesuffix(" €")


def _pourcentage(taux: float) -> str:
    return f"{float(taux or 0):.2f}".replace(".", ",")


# --- en-tête --------------------------------------------------------------


def entete(ctx: Contexte) -> str:
    """Logo et identifiants, métiers au centre, nom et qualité à droite."""
    g, s = ctx.gabarit, ctx.societe
    petit = max(5.5, g.taille_police - 3)

    logo = ""
    if s.logo:
        from pathlib import Path
        if Path(s.logo).exists():
            logo = (f"<img src='logo' "
                    f"width='{mm_en_px_css(g.logo_largeur_mm)}'><br>")

    identifiants = "<br>".join(
        echapper(texte) for texte in (
            f"N° SIRET : {s.siret}" if s.siret else "",
            f"N° TVA : {s.tva_intracom}" if s.tva_intracom else "",
            f"N° RCS : {s.rcs}" if s.rcs else "",
            f"APE {s.code_ape}" if s.code_ape and not s.rcs else "",
        ) if texte
    )

    # L'assurance décennale est obligatoire sur un devis de bâtiment, et la
    # mise en page classique n'a pas de pied de page pour la porter. Elle
    # prend donc la place qu'elle occupait sur le papier à en-tête :
    # au-dessus du dessin, dans la colonne de gauche.
    decennale = ""
    if s.assurance_nom:
        contrat = f" n° {s.assurance_contrat}" if s.assurance_contrat else ""
        lignes = [f"Assurance de responsabilité décennale{contrat}",
                  s.assurance_nom]
        if s.assurance_couverture:
            lignes.append(f"Garantie accordée sur les chantiers exécutés en "
                          f"{s.assurance_couverture}.")
        decennale = "<br>".join(echapper(x) for x in lignes) + "<br><br>"

    metiers = "<br>".join(
        echapper(ligne.strip()) for ligne in (g.entete_activite or "").split("\n")
        if ligne.strip()
    )
    nom = "<br>".join(echapper(texte) for texte in (
        s.nom or "Votre entreprise", g.entete_qualite) if texte)

    lieu = " - ".join(x for x in [s.adresse, f"{s.cp} {s.ville}".strip()] if x)
    coordonnees = []
    if lieu:
        coordonnees.append(echapper(lieu))
    if s.telephone:
        coordonnees.append("Tél : " + echapper(s.telephone))
    if s.email:
        coordonnees.append(echapper(s.email))

    # Les filets n'encadrent que la partie droite de l'en-tête : à gauche,
    # ils buteraient sur le logo.
    filet = TRAIT
    bandeau = (
        f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='68%' align='center' valign='top' "
        f"style=\"font-family:{SERIF}; font-size:{g.taille_police + 3:.1f}pt; "
        f"font-weight:bold; font-style:italic;\">{metiers}</td>"
        f"<td width='32%' align='right' valign='top' "
        f"style=\"font-family:{SERIF}; font-size:{g.taille_police + 1:.1f}pt; "
        f"font-weight:bold;\">{nom}</td></tr></table>"
        + filet
        + f"<div align='center' style=\"font-family:{SERIF}; font-style:italic; "
          f"font-size:{g.taille_police + 1:.1f}pt;\">"
        + "<br>".join(coordonnees) + "</div>"
        + filet
    )

    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='23%' valign='top' style='font-size:{petit:.1f}pt;'>"
        f"{decennale}{logo}{identifiants}</td>"
        f"<td width='2%'></td>"
        f"<td width='75%' valign='top'>{bandeau}</td>"
        "</tr></table>"
    )


# --- titre, client, objet -------------------------------------------------


def _intitule(ctx: Contexte) -> str:
    from .blocs import _titre
    return _titre(ctx)


def titre_et_client(ctx: Contexte) -> str:
    """« DEVIS N° 932 le 30/01/2013 » à gauche, le destinataire à droite."""
    g, d = ctx.gabarit, ctx.document
    client = ctx.client

    if client:
        lignes = [echapper(client.libelle)]
        for valeur in (client.adresse, f"{client.cp} {client.ville}".strip()):
            if valeur:
                lignes.append(echapper(valeur))
        bloc_client = "<br>".join(lignes)
    else:
        bloc_client = "<i>(aucun client sélectionné)</i>"

    gros = g.taille_police + 4
    entete_gauche = (
        f"<span style='font-size:{gros:.1f}pt; font-weight:bold;'>"
        f"{echapper(_intitule(ctx))} N° {echapper(d.numero or '—')}</span>"
    )
    if ctx.est_facture:
        secondes = [f"Date : {date_fr(d.date_document)}"]
        if d.date_echeance and d.date_echeance != d.date_document:
            secondes.append(f"à régler avant le {date_fr(d.date_echeance)}")
    else:
        entete_gauche += f"&nbsp;&nbsp;le {echapper(date_fr(d.date_document))}"
        secondes = [f"valable jusqu'au {date_fr(d.date_validite)}"]

    bas = "<br>".join(echapper(texte) for texte in secondes)
    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='55%' valign='top'>{entete_gauche}</td>"
        f"<td width='45%' valign='top'>{bloc_client}</td></tr>"
        f"<tr><td valign='top' style='padding-top:6px;'>{bas}</td>"
        "<td></td></tr></table>"
    )


def objet(ctx: Contexte) -> str:
    """L'objet des travaux, centré et souligné — le titre de la page."""
    texte = (ctx.document.objet or "").strip()
    if not texte:
        return ""
    return (f"<div align='center' style='font-size:{ctx.gabarit.taille_police + 1:.1f}pt; "
            f"font-weight:bold; text-decoration:underline;'>"
            f"{echapper(texte.upper())}</div>")


# --- tableau --------------------------------------------------------------

# Les intitulés sont ceux des documents de l'entreprise, que ses clients
# reçoivent depuis trente ans.
COLONNES = [
    ("designation", "LIBELLE", 51, "left"),
    ("quantite", "QTE", 8, "right"),
    ("unite", "U", 5, "center"),
    ("prix", "P.U.", 12, "right"),
    ("total", "TOTAL EU", 12, "right"),
    ("tva", "TAUX TVA", 12, "right"),
]


def colonnes(ctx: Contexte) -> list[tuple]:
    retenues = [c for c in COLONNES
                if (c[0] != "unite" or ctx.gabarit.colonne_unite)
                and (c[0] != "tva" or ctx.gabarit.colonne_tva)]
    # La désignation récupère la place des colonnes écartées.
    reste = 100 - sum(c[2] for c in retenues if c[0] != "designation")
    return [(c[0], c[1], reste if c[0] == "designation" else c[2], c[3])
            for c in retenues]


def _bordures(index: int, dernier: int, haut: bool = False,
              bas: bool = False) -> str:
    style = f"border-left:{FILET};"
    if index == dernier:
        style += f"border-right:{FILET};"
    if haut:
        style += f"border-top:{FILET};"
    if bas:
        style += f"border-bottom:{FILET};"
    return style


def tableau(ctx: Contexte) -> str:
    """Les lignes, dans un cadre qui descend jusqu'au bas de la page."""
    g = ctx.gabarit
    cols = colonnes(ctx)
    dernier = len(cols) - 1
    petit = g.taille_police - 1.5

    entetes = "".join(
        f"<td width='{largeur}%' align='center' "
        f"style='padding:3px 5px; {_bordures(i, dernier, haut=True, bas=True)}'>"
        f"<b>{echapper(titre)}</b></td>"
        for i, (_, titre, largeur, _align) in enumerate(cols)
    )
    # <thead> : Qt en fait une rangée d'en-tête, qu'il réimprime en haut de
    # chaque page. Sans cela, la deuxième feuille d'un long devis arrive sans
    # dire quelle colonne porte la quantité et laquelle porte le prix.
    rangs = [f"<thead><tr>{entetes}</tr></thead>"]

    for ligne in ctx.document.lignes:
        if ligne.type == "section":
            rangs.append(_rang_section(ctx, ligne, cols, dernier))
        elif ligne.type == "texte":
            rangs.append(_rang_texte(ctx, ligne, cols, dernier))
        else:
            rangs.append(_rang_prestation(ctx, ligne, cols, dernier, petit))

    rangs.append(_rang_final(ctx, cols, dernier))
    return (f"<table width='100%' cellspacing='0' cellpadding='0' "
            f"style='font-size:{g.taille_police:.1f}pt;'>{''.join(rangs)}</table>"
            + TRAIT)


def _cellules_vides(cols, dernier, depuis: int) -> str:
    return "".join(
        f"<td style='padding:2px 5px; {_bordures(i, dernier)}'></td>"
        for i in range(depuis, len(cols))
    )


def _rang_section(ctx: Contexte, ligne: Ligne, cols, dernier: int) -> str:
    """Un lot : son intitulé en gras, et son sous-total s'il est demandé."""
    if ctx.gabarit.afficher_sous_totaux_sections:
        total = ctx.sous_totaux.get(ligne.id, Decimal("0.00"))
        milieu = "".join(
            f"<td style='padding:3px 5px; {_bordures(i, dernier)}'></td>"
            for i in range(1, len(cols) - 1)
        )
        return (
            f"<tr><td style='padding:3px 5px; {_bordures(0, dernier)}'>"
            f"<b>{echapper(ligne.designation)}</b></td>{milieu}"
            f"<td align='right' style='padding:3px 5px; "
            f"{_bordures(len(cols) - 1, dernier)}'><b>{echapper(montant(total))}"
            f"</b></td></tr>"
        )
    return (f"<tr><td style='padding:3px 5px; {_bordures(0, dernier)}'>"
            f"<b>{echapper(ligne.designation)}</b></td>"
            f"{_cellules_vides(cols, dernier, 1)}</tr>")


def _rang_texte(ctx: Contexte, ligne: Ligne, cols, dernier: int) -> str:
    return (f"<tr><td style='padding:2px 5px; {_bordures(0, dernier)}'>"
            f"{echapper(ligne.designation)}</td>"
            f"{_cellules_vides(cols, dernier, 1)}</tr>")


def _rang_prestation(ctx: Contexte, ligne: Ligne, cols, dernier: int,
                     petit: float) -> str:
    g = ctx.gabarit
    designation = echapper(ligne.designation)
    if ligne.detail and g.afficher_detail_lignes:
        designation += (f"<br><span style='font-size:{petit:.1f}pt;'>"
                        f"{echapper(ligne.detail)}</span>")
    if ligne.remise_pct:
        designation += (f"<br><span style='font-size:{petit:.1f}pt;'>"
                        f"remise {nombre(ligne.remise_pct)} %</span>")

    valeurs = {
        "designation": designation,
        "quantite": echapper(nombre(ligne.quantite, 2)),
        "unite": echapper(ligne.unite),
        "prix": echapper(montant(ligne.prix_unitaire)),
        "total": echapper(montant(ligne.total_ht)),
        "tva": echapper(_pourcentage(ligne.taux_tva)),
    }
    cellules = "".join(
        f"<td align='{align}' style='padding:2px 5px; {_bordures(i, dernier)}'>"
        f"{valeurs[cle]}</td>"
        for i, (cle, _titre, _largeur, align) in enumerate(cols)
    )
    return f"<tr>{cellules}</tr>"


def _rang_final(ctx: Contexte, cols, dernier: int) -> str:
    """Le fond du cadre : c'est lui qu'on étire pour atteindre le bas de page."""
    # Padding détaillé, et non le raccourci « padding » : Qt applique les
    # raccourcis après les propriétés détaillées, et écraserait la hauteur.
    bourrage = max(0, int(ctx.remplissage_px))
    creux = "<tr>" + "".join(
        f"<td style='padding-left:5px; padding-right:5px; padding-top:2px; "
        f"padding-bottom:{bourrage}px; {_bordures(i, dernier)}'></td>"
        for i in range(len(cols))
    ) + "</tr>"
    return creux


# --- bas de page ----------------------------------------------------------


def _adresse_chantier(ctx: Contexte) -> str:
    chantier = ctx.chantier
    if chantier:
        return "<br>".join(echapper(x) for x in [
            chantier.adresse, f"{chantier.cp} {chantier.ville}".strip()] if x)
    libre = (getattr(ctx.document, "adresse_chantier", "") or "").strip()
    return echapper(libre) if libre else ""


def _mentions(ctx: Contexte) -> str:
    g, d, s = ctx.gabarit, ctx.document, ctx.societe
    morceaux = []
    if g.afficher_conditions:
        texte = d.conditions or conditions_par_defaut(s, ctx.est_facture)
        if texte:
            morceaux.append(echapper(texte))
    if g.afficher_mentions:
        texte = d.mentions or (s.mentions_facture if ctx.est_facture
                               else s.mentions_devis)
        if texte:
            morceaux.append(echapper(texte))
    if any(l.taux == 0.0 for l in ctx.totaux.tva):
        morceaux.append("Autoliquidation de la TVA : TVA due par le preneur, "
                        "article 283-2 nonies du CGI.")
    if (not ctx.est_facture and g.afficher_acompte
            and getattr(d, "acompte_pct", 0)):
        # Le cadre des totaux finit sur le TTC : l'acompte et le solde se
        # disent ici, avec leurs montants, pour que le client sache ce qu'il
        # avance à la commande et ce qui restera.
        morceaux.append(
            f"Acompte de {nombre(d.acompte_pct)} % à la commande : "
            f"{euros(ctx.totaux.acompte)} — solde de "
            f"{euros(ctx.totaux.solde)} à la fin des travaux.")
    if ctx.est_facture and getattr(d, "statut", "") == "payée":
        # Le cadre des totaux ne porte plus de « reste dû » : c'est ici que
        # se lit qu'il n'y a plus rien à payer.
        regle = getattr(d, "date_paiement", "")
        morceaux.append("Facture acquittée"
                        + (f" le {date_fr(regle)}" if regle else ""))
    if s.iban:
        morceaux.append("IBAN " + echapper(s.iban)
                        + (f" — BIC {echapper(s.bic)}" if s.bic else ""))
    return "<br><br>".join(morceaux)


def _lignes_totaux(ctx: Contexte) -> list[tuple[str, str, bool]]:
    g, d, t = ctx.gabarit, ctx.document, ctx.totaux
    lignes = []
    if t.remise:
        lignes.append(("TOTAL BRUT HT", montant(t.brut_ht), False))
        lignes.append((f"REMISE {nombre(d.remise_globale_pct)} %",
                       "− " + montant(t.remise), False))
    lignes.append(("TOTAL HT", montant(t.total_ht), True))
    if g.afficher_recap_tva:
        for index, taux in enumerate(t.tva, start=1):
            # Une décimale dans le cadre des totaux, deux dans la colonne du
            # tableau : c'est l'usage des documents de l'entreprise.
            lignes.append((f"TVA {index} : {nombre(taux.taux, 1)}%",
                           montant(taux.montant), False))
    else:
        lignes.append(("TVA", montant(t.total_tva), False))
    # Et rien en dessous : c'est le total TTC qu'on cherche des yeux au bas
    # d'un devis, et il doit être la dernière ligne du cadre. L'acompte et le
    # solde se disent dans les conditions, à gauche ; une facture acquittée le
    # dit dans les mentions.
    lignes.append(("TOTAL TTC", montant(t.total_ttc), True))
    return lignes


def totaux(ctx: Contexte) -> str:
    """Le cadre chiffré du bas de page, aligné à droite."""
    g = ctx.gabarit
    corps = "".join(
        f"<tr><td style='padding:2px 6px; {_bordures(0, 1, haut=fort)}"
        f"{'font-weight:bold;' if fort else ''}'>{echapper(libelle)}</td>"
        f"<td align='right' style='padding:2px 6px; {_bordures(1, 1, haut=fort)}"
        f"{'font-weight:bold;' if fort else ''}'>{echapper(valeur)}</td></tr>"
        for libelle, valeur, fort in _lignes_totaux(ctx)
    )
    return (f"<table width='100%' cellspacing='0' cellpadding='0' "
            f"style='font-size:{g.taille_police:.1f}pt;'>{corps}</table>" + TRAIT)


def bas_de_page(ctx: Contexte) -> str:
    """Mentions à gauche, adresse du chantier au milieu, totaux à droite."""
    g = ctx.gabarit
    petit = max(5.5, g.taille_police - 2.5)

    chantier = _adresse_chantier(ctx) if g.afficher_bloc_chantier else ""
    if chantier:
        chantier = ("<span style='text-decoration:underline;'>"
                    "Adresse de chantier :</span><br>" + chantier)

    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='40%' valign='top' style='font-size:{petit:.1f}pt; "
        f"padding-right:8px;'>{_mentions(ctx)}</td>"
        f"<td width='26%' valign='top' style='font-size:{petit:.1f}pt; "
        f"padding-right:8px;'>{chantier}</td>"
        f"<td width='34%' valign='top'>{totaux(ctx)}</td>"
        "</tr></table>"
    )


def signature(ctx: Contexte) -> str:
    """Place laissée à la signature du client — absente par défaut."""
    g = ctx.gabarit
    if not g.afficher_signature or ctx.est_facture:
        return ""
    vide = "<br>" * max(1, int(g.hauteur_signature_mm / 5))
    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        "<td width='52%'></td>"
        f"<td width='48%' valign='top' style='font-size:"
        f"{g.taille_police - 1:.1f}pt; border:{FILET}; padding:6px;'>"
        f"<b>Bon pour accord</b><br>{echapper(g.texte_signature)}{vide}</td>"
        "</tr></table>"
    )
