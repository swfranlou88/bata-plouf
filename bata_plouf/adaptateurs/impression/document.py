"""Assemblage du document imprimé à partir des blocs.

Deux mises en page cohabitent, et c'est ici qu'on choisit entre elles :

  - « moderne » : blocs colorés, encadré du client, récapitulatif à droite ;
  - « classique » : le devis d'artisan, en-tête à trois colonnes et tableau
    encadré descendant jusqu'au bas de la page.

Dans les deux cas, l'ordre des blocs est défini à un seul endroit, pour le
devis comme pour la facture. Les blocs qui ne concernent qu'un type de
document se rendent vides pour l'autre : le cadre de signature n'apparaît que
sur un devis, le rappel du marché que sur une facture.
"""

from . import blocs_classique as classique
from .blocs import (
    Contexte, conditions_et_recapitulatif, entete, informations, paragraphe,
    recapitulatif_marche, signature, tableau, titre_et_client,
)
from .styles import espace


def corps_moderne(ctx: Contexte) -> str:
    rappel = recapitulatif_marche(ctx)
    morceaux = [
        entete(ctx),
        espace(6),
        titre_et_client(ctx),
        espace(7),
        informations(ctx),
        espace(7),
        paragraphe(ctx, ctx.gabarit.texte_introduction),
        espace(6) if ctx.gabarit.texte_introduction else "",
        tableau(ctx),
        espace(8),
        rappel,
        espace(8) if rappel else "",
        paragraphe(ctx, ctx.gabarit.texte_conclusion),
        espace(6) if ctx.gabarit.texte_conclusion else "",
        conditions_et_recapitulatif(ctx),
        espace(10),
        signature(ctx),
    ]
    return "".join(m for m in morceaux if m)


def corps_classique(ctx: Contexte) -> str:
    objet = classique.objet(ctx)
    rappel = recapitulatif_marche(ctx)
    morceaux = [
        classique.entete(ctx),
        espace(8),
        classique.titre_et_client(ctx),
        espace(10),
        objet,
        espace(6) if objet else "",
        paragraphe(ctx, ctx.gabarit.texte_introduction),
        espace(5) if ctx.gabarit.texte_introduction else "",
        classique.tableau(ctx),
        espace(5),
        paragraphe(ctx, ctx.gabarit.texte_conclusion),
        espace(5) if ctx.gabarit.texte_conclusion else "",
        rappel,
        espace(5) if rappel else "",
        classique.bas_de_page(ctx),
        espace(6),
        classique.signature(ctx),
    ]
    return "".join(m for m in morceaux if m)


def corps_html(ctx: Contexte) -> str:
    corps = corps_classique(ctx) if ctx.gabarit.classique else corps_moderne(ctx)
    return "<html><body>" + corps + "</body></html>"


def html_document(depot, document, dpi: int = 96) -> str:
    """Le HTML complet d'un devis ou d'une facture."""
    gabarit = getattr(depot, "gabarit", None)
    if gabarit is None:
        from ...domaine.gabarit import Gabarit
        gabarit = Gabarit()
    return corps_html(Contexte(depot=depot, document=document, gabarit=gabarit, dpi=dpi))
