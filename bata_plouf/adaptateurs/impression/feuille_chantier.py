"""La feuille qu'on emporte sur le chantier.

Ce n'est pas un document pour le client : ni prix de vente, ni TVA, ni
conditions. Ce qu'il faut charger dans le camion, ce que cela coûte chez le
fournisseur, et le temps à y passer. D'où le noir et blanc et les colonnes
serrées : elle finit pliée en quatre dans une poche.
"""

from datetime import date

from ...domaine import date_fr, euros, nombre
from .styles import echapper

FILET = "1px solid #000000"
POLICE = "Helvetica, Arial, sans-serif"


def _entete(depot, document) -> str:
    societe = depot.societe
    client = depot.nom_client(getattr(document, "client_id", "")) or "—"
    adresse = getattr(document, "adresse_chantier", "") or "—"
    objet = getattr(document, "objet", "") or "—"
    emise = date_fr(getattr(document, "date_devis", "")
                    or getattr(document, "date_facture", ""))
    return (
        f"<div style='font-size:8pt;'>{echapper(societe.nom)}</div>"
        f"<div style='font-size:15pt; font-weight:bold;'>Feuille de chantier"
        f"</div>"
        f"<table width='100%' cellspacing='0' cellpadding='0' "
        f"style='font-size:9pt; margin-top:6px;'>"
        f"<tr><td width='18%'>Chantier</td>"
        f"<td width='48%'><b>{echapper(objet)}</b></td>"
        f"<td width='14%'>Devis</td>"
        f"<td width='20%'>{echapper(document.numero)} du {emise}</td></tr>"
        f"<tr><td>Client</td><td>{echapper(client)}</td>"
        f"<td>Imprimée le</td>"
        f"<td>{date_fr(date.today().isoformat())}</td></tr>"
        f"<tr><td>Adresse</td><td colspan='3'>{echapper(adresse)}</td></tr>"
        f"</table>"
    )


def _fournitures(prevu) -> str:
    if not prevu.fournitures:
        return ("<p style='font-size:9pt;'>Aucune fourniture connue : les "
                "ouvrages de ce devis n'ont pas de composition.</p>")
    rangs = []
    for f in sorted(prevu.fournitures, key=lambda f: -f.cout):
        prix = euros(f.prix_achat) if f.prix_achat else "—"
        cout = euros(f.cout) if f.prix_achat else "—"
        rangs.append(
            f"<tr>"
            f"<td style='border-bottom:{FILET}; padding:3px 4px;'>"
            f"{echapper(f.designation)}</td>"
            f"<td align='right' style='border-bottom:{FILET}; padding:3px 4px;'>"
            f"<b>{nombre(f.quantite, 2)}</b></td>"
            f"<td align='center' style='border-bottom:{FILET}; padding:3px 4px;'>"
            f"{echapper(f.unite)}</td>"
            f"<td align='right' style='border-bottom:{FILET}; padding:3px 4px;'>"
            f"{prix}</td>"
            f"<td align='right' style='border-bottom:{FILET}; padding:3px 4px;'>"
            f"{cout}</td>"
            # La case à cocher : on pointe la livraison au stylo.
            f"<td align='center' style='border-bottom:{FILET}; "
            f"padding:3px 4px;'>☐</td></tr>")

    manquants = sum(1 for f in prevu.fournitures if not f.prix_achat)
    note = ("" if not manquants else
            f"<div style='font-size:8pt; margin-top:3px;'>{manquants} "
            f"article(s) sans prix d'achat en bibliothèque : le total est "
            f"donc un minimum.</div>")

    return (
        f"<table width='100%' cellspacing='0' cellpadding='0' "
        f"style='font-size:9pt;'>"
        f"<thead><tr>"
        f"<th align='left' style='border-bottom:{FILET}; padding:3px 4px;'>"
        f"ARTICLE</th>"
        f"<th align='right' width='11%' style='border-bottom:{FILET}; "
        f"padding:3px 4px;'>QTÉ</th>"
        f"<th align='center' width='7%' style='border-bottom:{FILET}; "
        f"padding:3px 4px;'>U.</th>"
        f"<th align='right' width='13%' style='border-bottom:{FILET}; "
        f"padding:3px 4px;'>P.U. ACHAT</th>"
        f"<th align='right' width='14%' style='border-bottom:{FILET}; "
        f"padding:3px 4px;'>COÛT</th>"
        f"<th align='center' width='6%' style='border-bottom:{FILET}; "
        f"padding:3px 4px;'>OK</th>"
        f"</tr></thead>"
        + "".join(rangs) +
        f"<tr><td colspan='4' align='right' style='padding:5px 4px; "
        f"font-weight:bold;'>TOTAL FOURNITURES</td>"
        f"<td align='right' style='padding:5px 4px; font-weight:bold;'>"
        f"{euros(prevu.cout_fournitures)}</td><td></td></tr>"
        f"</table>{note}"
    )


def _temps(prevu) -> str:
    machines = ", ".join(f"{echapper(m.designation)} {nombre(m.heures, 1)} h"
                         for m in prevu.machines)
    lignes = [f"<b>{nombre(prevu.heures, 1)} heures</b> de main d'œuvre, "
              f"soit {nombre(prevu.journees, 1)} journées de sept heures."]
    if machines:
        lignes.append(f"Machines : {machines}.")
    if prevu.sans_temps:
        lignes.append(f"{len(prevu.sans_temps)} ligne(s) sans temps connu, "
                      f"non comptées : "
                      + echapper(", ".join(prevu.sans_temps[:4]))
                      + ("…" if len(prevu.sans_temps) > 4 else ""))
    return ("<div style='font-size:9pt; margin-top:10px;'>"
            + "<br>".join(lignes) + "</div>")


def html_feuille(depot, document, prevu) -> str:
    """La feuille de chantier entière, prête à peindre."""
    return (
        f"<body style='font-family:{POLICE}; color:#000000;'>"
        + _entete(depot, document)
        + "<div style='font-size:3pt;'>&nbsp;</div>"
        + _fournitures(prevu)
        + _temps(prevu)
        + "<div style='font-size:8pt; margin-top:12px;'>Document interne — "
          "prix d'achat, à ne pas remettre au client.</div>"
        + "</body>"
    )
