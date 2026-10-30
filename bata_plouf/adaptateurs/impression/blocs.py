"""Chaque bloc du devis, construit séparément.

Un bloc = une fonction qui reçoit le contexte et rend du HTML. Pour ajouter,
retirer ou réordonner quelque chose sur le devis, il suffit de toucher au bloc
concerné et à l'assemblage dans document.py.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from ...domaine.gabarit import Gabarit
from ...domaine import (
    Devis, Facture, Ligne, date_fr, euros, nombre, sous_totaux_sections, taux_tva_txt,
)
from .styles import Palette, echapper, espace, mm_en_px, palette


@dataclass
class Contexte:
    """Tout ce dont les blocs ont besoin, pour un devis ou pour une facture."""

    depot: object
    document: object          # Devis ou Facture
    gabarit: Gabarit
    dpi: int = 96
    palette: Palette = field(init=False)

    def __post_init__(self):
        self.palette = palette(self.gabarit)
        self.totaux = self.document.totaux()
        self.sous_totaux = sous_totaux_sections(self.document)
        self.numeros = numeroter(self.document) if self.gabarit.numeroter_lignes else {}

    @property
    def est_facture(self) -> bool:
        return isinstance(self.document, Facture)

    @property
    def societe(self):
        return self.depot.societe

    @property
    def client(self):
        return self.depot.client(self.document.client_id)

    @property
    def chantier(self):
        return self.depot.chantier(self.document.chantier_id)


def numeroter(document) -> dict[str, str]:
    """Numérotation façon devis bâtiment : 1, 1.1, 1.2, 2, 2.1…"""
    resultat: dict[str, str] = {}
    section, prestation = 0, 0
    for ligne in document.lignes:
        if ligne.type == "section":
            section += 1
            prestation = 0
            resultat[ligne.id] = str(section)
        elif ligne.chiffree:
            prestation += 1
            resultat[ligne.id] = (f"{section}.{prestation}" if section else str(prestation))
    return resultat


# --- description des colonnes du tableau ---------------------------------


@dataclass
class ColonneDevis:
    cle: str
    titre: str
    largeur: int          # en pourcentage de la largeur du tableau
    alignement: str = "left"


def colonnes(gabarit: Gabarit) -> list[ColonneDevis]:
    liste = []
    if gabarit.numeroter_lignes:
        liste.append(ColonneDevis("numero", "N°", 5, "left"))
    liste.append(ColonneDevis("designation", "Désignation", 0))
    liste.append(ColonneDevis("quantite", "Qté", 9, "right"))
    if gabarit.colonne_unite:
        liste.append(ColonneDevis("unite", "Un.", 8, "center"))
    liste.append(ColonneDevis("prix", "P.U. HT", 13, "right"))
    if gabarit.colonne_tva:
        liste.append(ColonneDevis("tva", "TVA", 8, "center"))
    if gabarit.colonne_remise:
        liste.append(ColonneDevis("remise", "Remise", 8, "right"))
    liste.append(ColonneDevis("total", "Total HT", 15, "right"))
    # La désignation prend ce qui reste
    reste = 100 - sum(c.largeur for c in liste)
    for colonne in liste:
        if colonne.cle == "designation":
            colonne.largeur = max(20, reste)
    return liste


# --- blocs ----------------------------------------------------------------


def entete(ctx: Contexte) -> str:
    """Coordonnées de l'entreprise et logo."""
    s = ctx.societe
    lignes = [f"<b style='font-size:{ctx.gabarit.taille_police + 3.5:.1f}pt'>"
              f"{echapper(s.nom or 'Votre entreprise')}</b>"]
    for valeur in (s.forme_juridique, s.adresse, f"{s.cp} {s.ville}".strip()):
        if valeur:
            lignes.append(echapper(valeur))
    if s.telephone:
        lignes.append("Tél. " + echapper(s.telephone))
    if s.email:
        lignes.append(echapper(s.email))
    bloc = "<br>".join(lignes)

    logo = ""
    if s.logo and Path(s.logo).exists():
        logo = f"<img src='logo' width='{mm_en_px(ctx.gabarit.logo_largeur_mm, ctx.dpi)}'>"

    if ctx.gabarit.logo_a_droite:
        gauche, droite = bloc, logo
        align_g, align_d = "left", "right"
    else:
        gauche, droite = logo, bloc
        align_g, align_d = "left", "right"

    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='55%' valign='top' align='{align_g}'>{gauche}</td>"
        f"<td width='45%' valign='top' align='{align_d}'>{droite}</td>"
        "</tr></table>"
    )


TITRES_FACTURE = {
    "acompte": "FACTURE D'ACOMPTE",
    "solde": "FACTURE DE SOLDE",
    "avoir": "AVOIR",
}


def _titre(ctx: Contexte) -> str:
    """« DEVIS », ou le libellé propre au type de facture."""
    if not ctx.est_facture:
        return ctx.gabarit.titre_document
    document = ctx.document
    if document.type in ("directe", "totale"):
        return ctx.gabarit.titre_facture
    if document.type == "situation":
        return f"SITUATION N° {document.numero_situation or 1}"
    return TITRES_FACTURE.get(document.type, "FACTURE")


def _taille_titre(ctx: Contexte, titre: str) -> float:
    """Le titre occupe une colonne étroite : on le rétrécit s'il est long.

    Sans cela « FACTURE D'ACOMPTE » passe à la ligne et décale tout l'en-tête.
    """
    pleine = ctx.gabarit.taille_police * 2
    reference = 11
    if len(titre) <= reference:
        return pleine
    return max(ctx.gabarit.taille_police * 1.15, pleine * reference / len(titre))


def titre_et_client(ctx: Contexte) -> str:
    """Titre du document, numéro, dates, et encadré du destinataire."""
    g, p, d = ctx.gabarit, ctx.palette, ctx.document
    client = ctx.client

    if client:
        lignes = [f"<b>{echapper(client.libelle)}</b>"]
        if client.type == "professionnel" and client.nom:
            nom = " ".join(x for x in [client.civilite, client.prenom, client.nom] if x)
            lignes.append(echapper(nom))
        for valeur in (client.adresse, f"{client.cp} {client.ville}".strip()):
            if valeur:
                lignes.append(echapper(valeur))
        if client.siret:
            lignes.append("SIRET " + echapper(client.siret))
        bloc_client = "<br>".join(lignes)
    else:
        bloc_client = "<i>(aucun client sélectionné)</i>"

    intitule = _titre(ctx)
    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        "<td width='52%' valign='top'>"
        f"<div style='font-size:{_taille_titre(ctx, intitule):.1f}pt; font-weight:bold; "
        f"color:{p.accent};'>{echapper(intitule)}</div>"
        f"<div style='font-size:{g.taille_police + 1.5:.1f}pt;'>"
        f"n° {echapper(d.numero or '(non attribué)')}</div>"
        "<table cellspacing='0' cellpadding='0'>"
        f"<tr><td style='padding:6px 10px 0 0; color:{p.gris};'>Date</td>"
        f"<td style='padding:6px 0 0 0;'><b>{echapper(date_fr(d.date_document))}</b></td></tr>"
        + (f"<tr><td style='color:{p.gris}; padding-right:10px;'>Échéance</td>"
           f"<td>le <b>{echapper(date_fr(d.date_echeance))}</b></td></tr>"
           if ctx.est_facture else
           f"<tr><td style='color:{p.gris}; padding-right:10px;'>Validité</td>"
           f"<td>jusqu'au <b>{echapper(date_fr(d.date_validite))}</b></td></tr>")
        +
        "</table></td>"
        "<td width='6%'></td>"
        f"<td width='42%' valign='top' bgcolor='{p.cadre}' style='padding:8px;'>"
        f"<span style='font-size:{g.taille_police - 1.5:.1f}pt; color:{p.gris};'>"
        f"CLIENT</span><br>{bloc_client}</td></tr></table>"
    )


def informations(ctx: Contexte) -> str:
    """Objet du devis et chantier concerné."""
    lignes = []
    if ctx.document.objet:
        lignes.append(("Objet", ctx.document.objet))
    if ctx.est_facture and ctx.document.devis_id:
        devis = ctx.depot.un_devis(ctx.document.devis_id)
        if devis is not None:
            lignes.append(("Devis", f"{devis.numero} du {date_fr(devis.date_devis)}"))
    if ctx.gabarit.afficher_bloc_chantier:
        chantier = ctx.chantier
        libre = (getattr(ctx.document, "adresse_chantier", "") or "").strip()
        if chantier:
            lieu = ", ".join(x for x in [chantier.adresse,
                                         f"{chantier.cp} {chantier.ville}".strip()] if x)
            lignes.append(("Chantier",
                           chantier.libelle + (f" — {lieu}" if lieu else "")))
        elif libre:
            # Petit chantier sans fiche : l'adresse saisie sur le document suffit
            lignes.append(("Chantier", libre.replace("\n", ", ")))
    if not lignes:
        return ""
    corps = "".join(
        f"<tr><td width='18%' style='padding:2px 0; color:{ctx.palette.gris};'>"
        f"{echapper(cle)}</td>"
        f"<td style='padding:2px 0;'><b>{echapper(valeur)}</b></td></tr>"
        for cle, valeur in lignes
    )
    return (f"<table width='100%' cellspacing='0' cellpadding='0' "
            f"style='font-size:{ctx.gabarit.taille_police - 0.5:.1f}pt;'>{corps}</table>")


def paragraphe(ctx: Contexte, texte: str) -> str:
    if not texte:
        return ""
    return (f"<div style='font-size:{ctx.gabarit.taille_police:.1f}pt;'>"
            f"{echapper(texte)}</div>")


def tableau(ctx: Contexte) -> str:
    """Le tableau des lignes, avec sections et sous-totaux."""
    g, p = ctx.gabarit, ctx.palette
    cols = colonnes(g)
    petit = g.taille_police - 1.5

    entetes = "".join(
        f"<td width='{c.largeur}%' align='{c.alignement}' "
        f"style='padding:5px 6px; color:{p.texte_accent};'><b>{echapper(c.titre)}</b></td>"
        for c in cols
    )
    rangs = [f"<tr bgcolor='{p.accent}'>{entetes}</tr>"]

    for ligne in ctx.document.lignes:
        if ligne.type == "section":
            rangs.append(_rang_section(ctx, ligne, cols))
        elif ligne.type == "texte":
            rangs.append(
                f"<tr><td colspan='{len(cols)}' style='padding:4px 6px; color:{p.gris};'>"
                f"<i>{echapper(ligne.designation)}</i></td></tr>"
            )
        else:
            rangs.append(_rang_prestation(ctx, ligne, cols, petit))

    if len(rangs) == 1:
        rangs.append(f"<tr><td colspan='{len(cols)}' style='padding:10px;'>"
                     "<i>Aucune ligne</i></td></tr>")

    return (f"<table width='100%' cellspacing='0' cellpadding='0' "
            f"style='font-size:{g.taille_police - 0.5:.1f}pt;'>{''.join(rangs)}</table>")


def _rang_section(ctx: Contexte, ligne: Ligne, cols: list[ColonneDevis]) -> str:
    p, g = ctx.palette, ctx.gabarit
    numero = f"{ctx.numeros.get(ligne.id, '')} " if g.numeroter_lignes else ""
    style = f"padding:5px 6px; color:{p.texte_section};"
    if g.afficher_sous_totaux_sections:
        total = ctx.sous_totaux.get(ligne.id, Decimal("0.00"))
        return (
            f"<tr bgcolor='{p.section}'>"
            f"<td colspan='{len(cols) - 1}' style='{style}'>"
            f"<b>{echapper(numero + ligne.designation)}</b></td>"
            f"<td align='right' style='{style}'><b>{echapper(euros(total))}</b></td></tr>"
        )
    return (f"<tr bgcolor='{p.section}'><td colspan='{len(cols)}' style='{style}'>"
            f"<b>{echapper(numero + ligne.designation)}</b></td></tr>")


def _rang_prestation(ctx: Contexte, ligne: Ligne, cols: list[ColonneDevis],
                     petit: float) -> str:
    p, g = ctx.palette, ctx.gabarit
    bordure = f"padding:4px 6px; border-bottom:1px solid {p.trait};"

    designation = echapper(ligne.designation)
    if ligne.detail and g.afficher_detail_lignes:
        designation += (f"<br><span style='font-size:{petit:.1f}pt; color:{p.gris};'>"
                        f"{echapper(ligne.detail)}</span>")
    if ligne.remise_pct and not g.colonne_remise:
        designation += (f"<br><span style='font-size:{petit:.1f}pt; color:{p.gris};'>"
                        f"remise {nombre(ligne.remise_pct)} %</span>")

    valeurs = {
        "numero": ctx.numeros.get(ligne.id, ""),
        "designation": designation,
        "quantite": echapper(nombre(ligne.quantite, 3)),
        "unite": echapper(ligne.unite),
        "prix": echapper(euros(ligne.prix_unitaire)),
        "tva": echapper(taux_tva_txt(ligne.taux_tva)),
        "remise": echapper(f"{nombre(ligne.remise_pct)} %") if ligne.remise_pct else "",
        "total": echapper(euros(ligne.total_ht)),
    }
    cellules = "".join(
        f"<td align='{c.alignement}' style='{bordure}'>{valeurs[c.cle]}</td>" for c in cols
    )
    return f"<tr>{cellules}</tr>"


def conditions_et_recapitulatif(ctx: Contexte) -> str:
    """Conditions de règlement à gauche, récapitulatif chiffré à droite."""
    g, p, d, t = ctx.gabarit, ctx.palette, ctx.document, ctx.totaux
    s = ctx.societe

    gauche = []
    if g.afficher_conditions:
        texte = d.conditions or s.conditions_paiement
        if texte:
            gauche.append(f"<b>Conditions de règlement</b><br>{echapper(texte)}")
    if g.afficher_mentions:
        texte = d.mentions or s.mentions_devis
        if texte:
            gauche.append(f"<b>Mentions</b><br>{echapper(texte)}")
    if any(l.taux == 0.0 for l in t.tva):
        gauche.append("<i>Autoliquidation de la TVA : TVA due par le preneur, "
                      "article 283-2 nonies du CGI.</i>")
    if s.iban:
        titre_banque = ("Règlement par virement" if ctx.est_facture
                        else "Coordonnées bancaires")
        gauche.append(f"<b>{titre_banque}</b><br>IBAN {echapper(s.iban)}"
                      + (f"<br>BIC {echapper(s.bic)}" if s.bic else ""))
    if ctx.est_facture:
        gauche.append("<b>Net à payer</b><br>"
                      f"<span style='font-size:{g.taille_police + 2:.1f}pt;'>"
                      f"<b>{echapper(euros(t.total_ttc))}</b></span>"
                      f" avant le {echapper(date_fr(d.date_echeance))}")

    recap = []
    if t.remise:
        recap.append(("Total brut HT", euros(t.brut_ht), False))
        recap.append((f"Remise {nombre(d.remise_globale_pct)} %",
                      "− " + euros(t.remise), False))
    recap.append(("Total HT", euros(t.total_ht), True))
    if g.afficher_recap_tva:
        for l in t.tva:
            recap.append((f"TVA {taux_tva_txt(l.taux)} sur {euros(l.base_ht)}",
                          euros(l.montant), False))
    else:
        recap.append(("TVA", euros(t.total_tva), False))
    recap.append(("Total TTC", euros(t.total_ttc), True))
    if g.afficher_acompte and not ctx.est_facture and d.acompte_pct:
        recap.append((f"Acompte à la commande ({nombre(d.acompte_pct)} %)",
                      euros(t.acompte), False))
        recap.append(("Solde à la fin des travaux", euros(t.solde), False))

    corps = "".join(
        f"<tr><td style='padding:3px 8px;{'font-weight:bold;' if fort else ''}'>"
        f"{echapper(libelle)}</td>"
        f"<td align='right' style='padding:3px 8px;"
        f"{'font-weight:bold;' if fort else ''}'>{echapper(valeur)}</td></tr>"
        + (f"<tr><td colspan='2' bgcolor='{p.accent}' style='font-size:1pt;'></td></tr>"
           if fort else "")
        for libelle, valeur, fort in recap
    )

    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='52%' valign='top' style='font-size:{g.taille_police - 1:.1f}pt; "
        f"color:#333333;'>{'<br><br>'.join(gauche)}</td>"
        "<td width='4%'></td>"
        "<td width='44%' valign='top'>"
        f"<table width='100%' cellspacing='0' cellpadding='0' "
        f"style='font-size:{g.taille_police:.1f}pt;' bgcolor='{p.cadre}'>{corps}</table>"
        "</td></tr></table>"
    )


def recapitulatif_marche(ctx: Contexte) -> str:
    """Rappel du marché sur une facture : total, déjà facturé, reste.

    C'est ce qui permet au client de relier la facture qu'il reçoit au devis
    qu'il a signé, et de vérifier qu'on ne lui facture pas deux fois la même
    chose.
    """
    if not (ctx.est_facture and ctx.gabarit.afficher_recapitulatif_marche):
        return ""
    from ...domaine.facturation import recapitulatif_marche as calculer

    infos = calculer(ctx.depot, ctx.document)
    if infos is None:
        return ""

    g, p = ctx.gabarit, ctx.palette
    rangs = [
        (f"Marché — devis {infos['devis'].numero} du "
         f"{date_fr(infos['devis'].date_devis)}", euros(infos["marche_ht"])),
        ("Déjà facturé à ce jour", euros(infos["anterieur_ht"])),
        ("Présente facture", euros(infos["courant_ht"])),
        ("Reste à facturer", euros(infos["reste_ht"])),
    ]
    corps = "".join(
        f"<tr><td style='padding:3px 8px;'>{echapper(libelle)}</td>"
        f"<td align='right' style='padding:3px 8px;'>{echapper(valeur)} HT</td></tr>"
        for libelle, valeur in rangs
    )
    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        "<td width='52%'></td><td width='4%'></td>"
        f"<td width='44%' valign='top' bgcolor='{p.cadre}'>"
        f"<table width='100%' cellspacing='0' cellpadding='0' "
        f"style='font-size:{g.taille_police - 1:.1f}pt;'>{corps}</table>"
        "</td></tr></table>"
    )


def signature(ctx: Contexte) -> str:
    """Cadre « Bon pour accord » — propre au devis, jamais sur une facture."""
    g, p = ctx.gabarit, ctx.palette
    if not g.afficher_signature or ctx.est_facture:
        return ""
    vide = "<br>" * max(1, int(g.hauteur_signature_mm / 5))
    return (
        f"<table width='100%' cellspacing='0' cellpadding='6' "
        f"style='font-size:{g.taille_police - 0.5:.1f}pt;'><tr>"
        f"<td width='48%' valign='top' style='border:1px solid {p.accent}; padding:8px;'>"
        "<b>Bon pour accord</b><br>"
        f"<span style='font-size:{g.taille_police - 1.5:.1f}pt; color:{p.gris};'>"
        f"{echapper(g.texte_signature)}</span>{vide}</td>"
        "<td width='4%'></td>"
        "<td width='48%' valign='top' style='padding:8px;'>"
        f"<span style='font-size:{g.taille_police - 1.5:.1f}pt; color:{p.gris};'>"
        f"Devis établi à {echapper(ctx.societe.ville or '…')}, "
        f"le {echapper(date_fr(ctx.document.date_document))}<br>"
        f"{echapper(ctx.societe.nom)}</span></td></tr></table>"
    )
