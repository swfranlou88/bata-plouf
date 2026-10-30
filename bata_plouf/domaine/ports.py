"""Les ports : ce que le domaine attend du monde extérieur.

Un port est un contrat, jamais une implémentation. Le cœur métier — la
facturation, la composition des documents — s'adresse à ces interfaces ; un
adaptateur les remplit, aujourd'hui avec des fichiers JSON, demain avec autre
chose si besoin. Rien dans ce module ne sait ce qu'est un fichier.

Chaque port est volontairement étroit : il décrit le besoin de celui qui
l'utilise, pas tout ce que sait faire le dépôt. On voit ainsi d'un coup d'œil
ce dont la facturation dépend vraiment.
"""

from typing import Protocol, runtime_checkable

from .entites import Chantier, Client, Devis, Facture, Societe
from .gabarit import Gabarit


@runtime_checkable
class SourceDocuments(Protocol):
    """Ce qu'il faut pour composer un devis ou une facture à imprimer."""

    societe: Societe
    gabarit: Gabarit

    def client(self, id_: str) -> Client | None: ...

    def chantier(self, id_: str) -> Chantier | None: ...

    def nom_client(self, id_: str) -> str: ...

    def un_devis(self, id_: str) -> Devis | None: ...


@runtime_checkable
class JournalFactures(Protocol):
    """Ce qu'il faut pour savoir où en est la facturation d'un chantier."""

    societe: Societe

    def factures(self, recherche: str = "", statut: str = "", client_id: str = "",
                 devis_id: str = "", supprimes: bool = False) -> list[Facture]: ...

    def un_devis(self, id_: str) -> Devis | None: ...


@runtime_checkable
class RegistreVentes(Protocol):
    """Ce qu'il faut pour sortir la comptabilité des ventes d'une période."""

    societe: Societe

    def factures(self, recherche: str = "", statut: str = "", client_id: str = "",
                 devis_id: str = "", supprimes: bool = False) -> list[Facture]: ...

    def nom_client(self, id_: str) -> str: ...


class Depot(SourceDocuments, JournalFactures, RegistreVentes, Protocol):
    """Le port complet, celui que l'adaptateur de stockage remplit.

    Les écrans s'en servent en entier ; le domaine, lui, ne demande jamais
    plus que l'un des deux ports étroits ci-dessus.
    """

    def clients(self, recherche: str = "", supprimes: bool = False) -> list[Client]: ...

    def devis(self, recherche: str = "", statut: str = "", client_id: str = "",
              supprimes: bool = False) -> list[Devis]: ...

    def enregistrer_client(self, client: Client) -> Client: ...

    def enregistrer_devis(self, devis: Devis) -> Devis: ...

    def enregistrer_facture(self, facture: Facture) -> Facture: ...
