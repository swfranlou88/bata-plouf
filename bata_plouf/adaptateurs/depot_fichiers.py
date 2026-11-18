"""Adaptateur de stockage : des fichiers JSON, sans base de données.

Cette classe remplit le port `domaine.ports.Depot`. Le domaine ne la connaît
pas : il ne voit que le contrat.

Tout vit dans un dossier unique que l'utilisateur peut ouvrir, copier sur une clé
USB ou déposer dans iCloud :

    Bata-plouf/
      parametres.json      les informations de l'entreprise
      clients.json
      chantiers.json
      articles.json        la bibliothèque de prix
      compteurs.json       le dernier numéro de devis attribué
      devis/D2026-0001.json   un fichier par devis
      factures/1451.json      un fichier par facture
      pdf/                 les devis imprimés, archivés
      sauvegardes/         un instantané zippé par état des données

Deux règles tiennent la fiabilité de l'ensemble, faute de transactions :
  - toute écriture passe par un fichier temporaire puis un renommage atomique,
    donc une coupure de courant ne peut pas laisser un fichier à moitié écrit ;
  - un devis = un fichier, donc un problème sur l'un n'atteint jamais les autres.
"""

import json
import os
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from .systeme import dossier_documents
from ..domaine.gabarit import Gabarit
from ..domaine import (
    Article, Chantier, Client, Devis, Facture, Societe,
    depuis_dict, en_dict, nouvel_id,
)

DOSSIER_DEFAUT = dossier_documents() / "Bata-plouf"
# Le logiciel s'est appelé autrement avant : on récupère son dossier plutôt
# que de laisser l'utilisateur devant une base vide.
ANCIENS_DOSSIERS = [dossier_documents() / "DevisMacon"]
# Deux : l'état précédent et le nouveau. Un filet local sert à rattraper la
# fausse manœuvre du jour, pas à tenir des archives — celles-ci partent en
# ligne chaque mois, chiffrées, et remontent plus loin que n'importe quelle
# pile de copies locales.
SAUVEGARDES_CONSERVEES = 2


class ErreurReference(Exception):
    """Lancée quand une suppression casserait une référence existante."""


def ecrire_json(chemin: Path, donnees) -> None:
    """Écriture atomique : fichier temporaire, vidage disque, puis renommage."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(chemin.suffix + ".tmp")
    with open(temporaire, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporaire, chemin)


def lire_json(chemin: Path, defaut):
    if not chemin.exists():
        return defaut
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # On met le fichier illisible de côté plutôt que de l'écraser
        secours = chemin.with_name(f"{chemin.stem}.illisible-{datetime.now():%Y%m%d%H%M%S}.json")
        try:
            shutil.copy2(chemin, secours)
        except OSError:
            pass
        return defaut


class DepotFichiers:
    """Charge tout en mémoire au démarrage et réécrit à chaque modification.

    Volumétrie attendue pour un artisan : quelques milliers d'enregistrements,
    soit quelques mégaoctets. Le chargement est instantané et la recherche se
    fait par filtrage en mémoire.
    """

    def __init__(self, racine: Path | str = DOSSIER_DEFAUT):
        self.racine = Path(racine).expanduser()
        self.societe = Societe()
        self.gabarit = Gabarit()
        self._clients: dict[str, Client] = {}
        self._chantiers: dict[str, Chantier] = {}
        self._articles: dict[str, Article] = {}
        self._devis: dict[str, Devis] = {}
        self._factures: dict[str, Facture] = {}
        self.compteurs: dict[str, int] = {}
        self.anomalies: list[str] = []
        self.migration = ""

    # --- chemins ---------------------------------------------------------

    @property
    def f_parametres(self) -> Path:
        return self.racine / "parametres.json"

    @property
    def f_gabarit(self) -> Path:
        return self.racine / "modele-devis.json"

    @property
    def f_clients(self) -> Path:
        return self.racine / "clients.json"

    @property
    def f_chantiers(self) -> Path:
        return self.racine / "chantiers.json"

    @property
    def f_articles(self) -> Path:
        return self.racine / "articles.json"

    @property
    def f_compteurs(self) -> Path:
        return self.racine / "compteurs.json"

    @property
    def d_devis(self) -> Path:
        return self.racine / "devis"

    @property
    def d_factures(self) -> Path:
        return self.racine / "factures"

    @property
    def d_pdf(self) -> Path:
        return self.racine / "pdf"

    @property
    def d_sauvegardes(self) -> Path:
        return self.racine / "sauvegardes"

    # --- chargement ------------------------------------------------------

    def charger(self) -> None:
        # Le relevé repart de zéro : un rechargement — après un import, par
        # exemple — ne doit pas traîner les anomalies du précédent.
        self.anomalies = []
        self.migration = self._reprendre_ancien_dossier()
        for dossier in (self.racine, self.d_devis, self.d_factures, self.d_pdf,
                        self.d_sauvegardes):
            dossier.mkdir(parents=True, exist_ok=True)

        self.societe = depuis_dict(Societe, lire_json(self.f_parametres, {}))
        self.gabarit = depuis_dict(Gabarit, lire_json(self.f_gabarit, {}))
        self._clients = {c.id: c for c in
                         (depuis_dict(Client, d) for d in lire_json(self.f_clients, []))}
        self._chantiers = {c.id: c for c in
                           (depuis_dict(Chantier, d) for d in lire_json(self.f_chantiers, []))}
        self._articles = {a.id: a for a in
                          (depuis_dict(Article, d) for d in lire_json(self.f_articles, []))}
        self.compteurs = lire_json(self.f_compteurs, {})

        self._devis = {}
        for fichier in sorted(self.d_devis.glob("*.json")):
            if fichier.name.endswith(".tmp"):
                continue
            donnees = lire_json(fichier, None)
            if donnees is None:
                self.anomalies.append(f"Devis illisible : {fichier.name}")
                continue
            devis = depuis_dict(Devis, donnees)
            self._devis[devis.id] = devis

        self._factures = {}
        for fichier in sorted(self.d_factures.glob("*.json")):
            if fichier.name.endswith(".tmp"):
                continue
            donnees = lire_json(fichier, None)
            if donnees is None:
                self.anomalies.append(f"Facture illisible : {fichier.name}")
                continue
            facture = depuis_dict(Facture, donnees)
            self._factures[facture.id] = facture

        self._verifier_coherence()

    def _reprendre_ancien_dossier(self) -> str:
        """Déplace le dossier de données d'une version précédente, s'il existe.

        Ne s'applique que si l'emplacement actuel est encore vide : on ne
        touche jamais à des données déjà en place.
        """
        if self.racine.exists() and any(self.racine.iterdir()):
            return ""
        for ancien in ANCIENS_DOSSIERS:
            if ancien.is_dir() and any(ancien.iterdir()):
                self.racine.parent.mkdir(parents=True, exist_ok=True)
                if self.racine.exists():
                    self.racine.rmdir()
                ancien.rename(self.racine)
                return f"Données reprises depuis {ancien}"
        return ""

    def _verifier_coherence(self) -> None:
        """Signale les références cassées sans rien supprimer.

        Les fichiers illisibles relevés par le chargement en cours sont déjà
        dans la liste : on complète, on ne remet pas à zéro.
        """
        for devis in self._devis.values():
            if devis.supprime:
                continue
            if devis.client_id and devis.client_id not in self._clients:
                self.anomalies.append(f"Devis {devis.numero} : client introuvable")
            if devis.chantier_id and devis.chantier_id not in self._chantiers:
                self.anomalies.append(f"Devis {devis.numero} : chantier introuvable")
        for facture in self._factures.values():
            if facture.supprime:
                continue
            if facture.client_id and facture.client_id not in self._clients:
                self.anomalies.append(f"Facture {facture.numero} : client introuvable")
            if facture.devis_id and facture.devis_id not in self._devis:
                self.anomalies.append(f"Facture {facture.numero} : devis d'origine introuvable")
        for chantier in self._chantiers.values():
            if chantier.client_id and chantier.client_id not in self._clients:
                self.anomalies.append(f"Chantier « {chantier.libelle} » : client introuvable")

    # --- sauvegarde complète ---------------------------------------------

    def _fichiers_de_donnees(self) -> list[Path]:
        return (sorted(self.racine.glob("*.json"))
                + sorted(self.d_devis.glob("*.json"))
                + sorted(self.d_factures.glob("*.json")))

    def empreinte(self) -> str:
        """Une signature du contenu des données, pour savoir s'il a bougé.

        Sur le contenu, pas sur les dates : enregistrer un devis sans rien y
        changer réécrit le fichier et change sa date, mais pas ce qu'il dit.
        Trois méga-octets de JSON se hachent en quelques millisecondes.
        """
        signature = hashlib.sha256()
        for fichier in self._fichiers_de_donnees():
            signature.update(fichier.name.encode("utf-8"))
            signature.update(fichier.read_bytes())
        return signature.hexdigest()

    def _sauvegardes_rangees(self) -> list[Path]:
        """Les instantanés, du plus ancien au plus récent.

        Rangés par date d'écriture, pas par nom : « 15h37-50-2.zip » précède
        « 15h37-50.zip » dans l'ordre alphabétique, et la purge jetterait
        alors le plus récent des deux.
        """
        if not self.d_sauvegardes.is_dir():
            return []
        existantes = [p for p in self.d_sauvegardes.iterdir()
                      if not p.name.startswith(".")]
        return sorted(existantes, key=lambda p: p.stat().st_mtime)

    def derniere_sauvegarde(self) -> Path | None:
        """La sauvegarde locale la plus récente, zip ou ancien dossier."""
        rangees = self._sauvegardes_rangees()
        return rangees[-1] if rangees else None

    def creer_sauvegarde(self, forcer: bool = False) -> Path | None:
        """Instantané zippé des données. None si rien n'a changé depuis le dernier.

        Rien n'oblige à garder trente copies d'un même état : ouvrir le
        logiciel sans rien modifier n'est pas un événement, et chaque copie
        inutile chassait un vrai état antérieur de la liste.
        """
        from . import archive

        if not self._fichiers_de_donnees():
            return None
        empreinte = self.empreinte()
        if not forcer and empreinte == self._empreinte_gardee():
            # Rien de neuf à écrire, mais le ménage reste à faire : c'est par
            # là que les trente instantanés d'avant finiront par partir.
            self._purger_sauvegardes()
            return None

        # Les secondes font partie du nom, et un rang s'ajoute au besoin :
        # deux états distincts dans la même seconde — ce qui arrive en
        # restaurant une archive — ne doivent pas s'écraser l'un l'autre
        # alors qu'on n'en garde que deux.
        quand = datetime.now().strftime("%Y-%m-%d_%Hh%M-%S")
        cible = self.d_sauvegardes / f"{quand}.zip"
        rang = 2
        while cible.exists():
            cible = self.d_sauvegardes / f"{quand}-{rang}.zip"
            rang += 1
        self.d_sauvegardes.mkdir(parents=True, exist_ok=True)
        # Le même format que l'export et la sauvegarde en ligne : une archive
        # de secours doit se rouvrir par le chemin habituel, pas par un autre.
        archive.ecrire(self, cible)
        self._garder_empreinte(empreinte)
        self._purger_sauvegardes()
        return cible

    def _fichier_empreinte(self) -> Path:
        return self.d_sauvegardes / ".empreinte"

    def _empreinte_gardee(self) -> str:
        try:
            return self._fichier_empreinte().read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _garder_empreinte(self, empreinte: str) -> None:
        try:
            self._fichier_empreinte().write_text(empreinte, encoding="utf-8")
        except OSError:
            pass  # sans elle, on sauvegardera une fois de trop, rien de grave

    def _purger_sauvegardes(self) -> None:
        # Les anciens instantanés étaient des dossiers : ils vieillissent dans
        # la même file que les zip, et s'effacent par le même compte.
        for vieille in self._sauvegardes_rangees()[:-SAUVEGARDES_CONSERVEES]:
            if vieille.is_dir():
                shutil.rmtree(vieille, ignore_errors=True)
            else:
                vieille.unlink(missing_ok=True)

    def exporter_vers(self, destination: Path) -> Path:
        """Copie complète des données vers un disque externe, un dossier iCloud…"""
        destination = Path(destination) / f"Bata-plouf-{datetime.now():%Y-%m-%d_%Hh%M}"
        shutil.copytree(self.racine, destination,
                        ignore=shutil.ignore_patterns("sauvegardes", "*.tmp"))
        return destination

    # --- clients ---------------------------------------------------------

    def clients(self, recherche: str = "", supprimes: bool = False) -> list[Client]:
        valeurs = sorted((c for c in self._clients.values() if c.supprime == supprimes),
                         key=lambda c: c.libelle.lower())
        if recherche:
            valeurs = [c for c in valeurs if c.correspond(recherche)]
        return valeurs

    def client(self, id_: str) -> Client | None:
        return self._clients.get(id_)

    def prochain_numero_client(self, reserver: bool = False) -> str:
        """Séquence continue, sans année : un client dure plus longtemps qu'un an.

        Les numéros sont de simples entiers, pour prolonger celle que
        l'entreprise tenait dans son ancien logiciel plutôt que d'ouvrir une
        série parallèle. Le compteur est recalé sur les fiches existantes,
        pour qu'une restauration de sauvegarde ne crée jamais de doublon.
        """
        dernier = int(self.compteurs.get("client", 0))
        for client in self._clients.values():
            if client.numero.isdigit():
                dernier = max(dernier, int(client.numero))
        suivant = dernier + 1
        if reserver:
            self.compteurs["client"] = suivant
            ecrire_json(self.f_compteurs, self.compteurs)
        return str(suivant)

    def enregistrer_client(self, client: Client) -> Client:
        if not client.numero:
            client.numero = self.prochain_numero_client(reserver=True)
        client.modifie_le = datetime.now().isoformat(timespec="seconds")
        self._clients[client.id] = client
        self._ecrire_clients()
        return client

    def supprimer_client(self, id_: str, definitif: bool = False) -> None:
        client = self._clients.get(id_)
        if client is None:
            return
        if not definitif:
            client.supprime_le = datetime.now().isoformat(timespec="seconds")
            self._ecrire_clients()
            return
        chantiers = [c.libelle for c in self._chantiers.values() if c.client_id == id_]
        devis = [d.numero for d in self._devis.values() if d.client_id == id_]
        factures = [f.numero for f in self._factures.values() if f.client_id == id_]
        if chantiers or devis or factures:
            details = []
            if devis:
                details.append(f"{len(devis)} devis")
            if factures:
                details.append(f"{len(factures)} facture(s)")
            if chantiers:
                details.append(f"{len(chantiers)} chantier(s)")
            raise ErreurReference(
                "Ce client ne peut pas être effacé définitivement : il reste "
                "rattaché à " + ", ".join(details) + ". Laissez-le dans la corbeille."
            )
        self._clients.pop(id_, None)
        self._ecrire_clients()

    def restaurer_client(self, id_: str) -> None:
        client = self._clients.get(id_)
        if client is not None:
            client.supprime_le = ""
            self._ecrire_clients()

    def _ecrire_clients(self) -> None:
        ecrire_json(self.f_clients, [en_dict(c) for c in self.clients()])

    # --- chantiers -------------------------------------------------------

    def chantiers(self, client_id: str = "", recherche: str = "",
                  supprimes: bool = False) -> list[Chantier]:
        valeurs = sorted((c for c in self._chantiers.values() if c.supprime == supprimes),
                         key=lambda c: (c.date_debut or "9999", c.libelle.lower()),
                         reverse=True)
        if client_id:
            valeurs = [c for c in valeurs if c.client_id == client_id]
        if recherche:
            t = recherche.lower()
            valeurs = [c for c in valeurs
                       if t in c.libelle.lower() or t in c.ville.lower()
                       or t in (self.nom_client(c.client_id) or "").lower()]
        return valeurs

    def chantier(self, id_: str) -> Chantier | None:
        return self._chantiers.get(id_)

    def enregistrer_chantier(self, chantier: Chantier) -> Chantier:
        chantier.modifie_le = datetime.now().isoformat(timespec="seconds")
        self._chantiers[chantier.id] = chantier
        self._ecrire_chantiers()
        return chantier

    def supprimer_chantier(self, id_: str, definitif: bool = False) -> None:
        chantier = self._chantiers.get(id_)
        if chantier is None:
            return
        if not definitif:
            chantier.supprime_le = datetime.now().isoformat(timespec="seconds")
            self._ecrire_chantiers()
            return
        devis = [d.numero for d in self._devis.values() if d.chantier_id == id_]
        if devis:
            raise ErreurReference(
                f"Ce chantier ne peut pas être effacé définitivement : {len(devis)} "
                f"devis y sont rattachés ({', '.join(devis[:3])}…)."
            )
        self._chantiers.pop(id_, None)
        self._ecrire_chantiers()

    def restaurer_chantier(self, id_: str) -> None:
        chantier = self._chantiers.get(id_)
        if chantier is not None:
            chantier.supprime_le = ""
            self._ecrire_chantiers()

    def _ecrire_chantiers(self) -> None:
        ecrire_json(self.f_chantiers, [en_dict(c) for c in self._chantiers.values()])

    # --- bibliothèque de prix --------------------------------------------

    def articles(self, recherche: str = "", famille: str = "", type_: str = "",
                 supprimes: bool = False) -> list[Article]:
        valeurs = sorted((a for a in self._articles.values() if a.supprime == supprimes),
                         key=lambda a: (a.famille.lower(), a.designation.lower()))
        if famille:
            valeurs = [a for a in valeurs if a.famille == famille]
        if type_:
            valeurs = [a for a in valeurs if a.type == type_]
        if recherche:
            valeurs = [a for a in valeurs if a.correspond(recherche)]
        return valeurs

    def article(self, id_: str) -> Article | None:
        return self._articles.get(id_)

    def enregistrer_article(self, article: Article) -> Article:
        article.modifie_le = datetime.now().isoformat(timespec="seconds")
        self._articles[article.id] = article
        self._ecrire_articles()
        return article

    def supprimer_article(self, id_: str, definitif: bool = False) -> None:
        # Un article déjà utilisé dans un devis n'y est plus qu'une référence
        # historique : le devis garde sa propre copie des libellés et des prix,
        # donc la suppression est sans danger, même définitive.
        article = self._articles.get(id_)
        if article is None:
            return
        if definitif:
            self._articles.pop(id_, None)
        else:
            article.supprime_le = datetime.now().isoformat(timespec="seconds")
        self._ecrire_articles()

    def restaurer_article(self, id_: str) -> None:
        article = self._articles.get(id_)
        if article is not None:
            article.supprime_le = ""
            self._ecrire_articles()

    def _ecrire_articles(self) -> None:
        ecrire_json(self.f_articles, [en_dict(a) for a in self._articles.values()])

    def familles(self) -> list[str]:
        return sorted({a.famille for a in self._articles.values() if a.famille})

    # --- devis -----------------------------------------------------------

    def devis(self, recherche: str = "", statut: str = "", client_id: str = "",
              supprimes: bool = False) -> list[Devis]:
        valeurs = sorted((d for d in self._devis.values() if d.supprime == supprimes),
                         key=lambda d: (d.date_devis, d.numero), reverse=True)
        if statut:
            valeurs = [d for d in valeurs if d.statut == statut]
        if client_id:
            valeurs = [d for d in valeurs if d.client_id == client_id]
        if recherche:
            t = recherche.lower()
            valeurs = [d for d in valeurs
                       if t in d.numero.lower() or t in d.objet.lower()
                       or t in (self.nom_client(d.client_id) or "").lower()]
        return valeurs

    def un_devis(self, id_: str) -> Devis | None:
        return self._devis.get(id_)

    def enregistrer_devis(self, devis: Devis) -> Devis:
        if not devis.numero:
            devis.numero = self.prochain_numero(reserver=True)
        devis.modifie_le = datetime.now().isoformat(timespec="seconds")
        self._devis[devis.id] = devis
        ecrire_json(self._fichier_devis(devis), en_dict(devis))
        return devis

    def supprimer_devis(self, id_: str, definitif: bool = False) -> None:
        devis = self._devis.get(id_)
        if devis is None:
            return
        if not definitif:
            devis.supprime_le = datetime.now().isoformat(timespec="seconds")
            ecrire_json(self._fichier_devis(devis), en_dict(devis))
            return
        facturees = [f.numero for f in self._factures.values() if f.devis_id == id_]
        if facturees:
            raise ErreurReference(
                f"Ce devis ne peut pas être effacé définitivement : "
                f"{len(facturees)} facture(s) en découlent "
                f"({', '.join(facturees[:3])}…)."
            )
        self._devis.pop(id_, None)
        fichier = self._fichier_devis(devis)
        if fichier.exists():
            # Le fichier part dans un sous-dossier plutôt qu'au néant :
            # même effacé définitivement, il reste récupérable à la main.
            corbeille = self.racine / "corbeille"
            corbeille.mkdir(exist_ok=True)
            fichier.replace(corbeille / fichier.name)

    def restaurer_devis(self, id_: str) -> None:
        devis = self._devis.get(id_)
        if devis is not None:
            devis.supprime_le = ""
            ecrire_json(self._fichier_devis(devis), en_dict(devis))

    def dupliquer_devis(self, id_: str) -> Devis | None:
        """Recopie un devis pour en repartir — l'usage le plus fréquent au quotidien."""
        source = self._devis.get(id_)
        if source is None:
            return None
        copie = depuis_dict(Devis, en_dict(source))
        copie.id = nouvel_id()
        copie.numero = ""
        copie.statut = "brouillon"
        copie.date_devis = datetime.now().date().isoformat()
        copie.date_reponse = ""
        copie.cree_le = copie.modifie_le = datetime.now().isoformat(timespec="seconds")
        for ligne in copie.lignes:
            ligne.id = nouvel_id()
        return self.enregistrer_devis(copie)

    def _fichier_devis(self, devis: Devis) -> Path:
        base = (devis.numero or devis.id).replace("/", "-")
        return self.d_devis / f"{base}.json"

    # --- factures --------------------------------------------------------

    def factures(self, recherche: str = "", statut: str = "", client_id: str = "",
                 devis_id: str = "", supprimes: bool = False) -> list[Facture]:
        valeurs = sorted((f for f in self._factures.values() if f.supprime == supprimes),
                         key=lambda f: (f.date_facture, f.numero), reverse=True)
        if statut == "en retard":
            valeurs = [f for f in valeurs if f.en_retard]
        elif statut:
            valeurs = [f for f in valeurs if f.statut == statut]
        if client_id:
            valeurs = [f for f in valeurs if f.client_id == client_id]
        if devis_id:
            valeurs = [f for f in valeurs if f.devis_id == devis_id]
        if recherche:
            t = recherche.lower()
            valeurs = [f for f in valeurs
                       if t in f.numero.lower() or t in f.objet.lower()
                       or t in (self.nom_client(f.client_id) or "").lower()]
        return valeurs

    def une_facture(self, id_: str) -> Facture | None:
        return self._factures.get(id_)

    def enregistrer_facture(self, facture: Facture) -> Facture:
        if not facture.numero:
            facture.numero = self.prochain_numero_facture(reserver=True)
        facture.modifie_le = datetime.now().isoformat(timespec="seconds")
        self._factures[facture.id] = facture
        ecrire_json(self._fichier_facture(facture), en_dict(facture))
        return facture

    def supprimer_facture(self, id_: str, definitif: bool = False) -> None:
        """Seule une facture encore en brouillon peut disparaître.

        Une facture émise fait partie d'une séquence comptable continue : elle
        s'annule par un avoir, elle ne s'efface pas.
        """
        facture = self._factures.get(id_)
        if facture is None:
            return
        if facture.statut != "brouillon":
            raise ErreurReference(
                f"La facture {facture.numero} a été émise : elle ne peut plus être "
                "supprimée, même dans la corbeille. Créez un avoir pour l'annuler."
            )
        if not definitif:
            facture.supprime_le = datetime.now().isoformat(timespec="seconds")
            ecrire_json(self._fichier_facture(facture), en_dict(facture))
            return
        self._factures.pop(id_, None)
        fichier = self._fichier_facture(facture)
        if fichier.exists():
            corbeille = self.racine / "corbeille"
            corbeille.mkdir(exist_ok=True)
            fichier.replace(corbeille / fichier.name)

    def restaurer_facture(self, id_: str) -> None:
        facture = self._factures.get(id_)
        if facture is not None:
            facture.supprime_le = ""
            ecrire_json(self._fichier_facture(facture), en_dict(facture))

    def _fichier_facture(self, facture: Facture) -> Path:
        base = (facture.numero or facture.id).replace("/", "-")
        return self.d_factures / f"{base}.json"

    def prochain_numero_facture(self, reserver: bool = False) -> str:
        """Séquence continue d'entiers, distincte de celle des devis : 1451…

        Une numérotation de factures doit être continue et sans trou, et
        celle de l'entreprise court depuis son ancien logiciel. On la
        prolonge, au lieu d'ouvrir une seconde série que le comptable
        aurait à rapprocher de la première. Elle n'est donc pas remise à
        zéro chaque année, ce qu'aucune règle n'impose.

        Le compteur est recalé sur les factures existantes, pour qu'une
        restauration de sauvegarde ne crée jamais de doublon.
        """
        dernier = int(self.compteurs.get("facture", 0))
        for facture in self._factures.values():
            if facture.numero.isdigit():
                dernier = max(dernier, int(facture.numero))
        suivant = dernier + 1
        if reserver:
            self.compteurs["facture"] = suivant
            ecrire_json(self.f_compteurs, self.compteurs)
        return str(suivant)

    def nom_devis(self, devis_id: str) -> str:
        devis = self._devis.get(devis_id)
        return devis.numero if devis else ""

    # --- numérotation ----------------------------------------------------

    def prochain_numero(self, reserver: bool = False) -> str:
        """Séquence continue par année : D2026-0001, D2026-0002…

        Le compteur est persisté, et recalé sur les devis existants pour qu'une
        restauration de sauvegarde ne provoque jamais de doublon de numéro.
        """
        annee = datetime.now().year
        cle = f"devis-{annee}"
        dernier = int(self.compteurs.get(cle, 0))
        prefixe = f"D{annee}-"
        for devis in self._devis.values():
            if devis.numero.startswith(prefixe):
                try:
                    dernier = max(dernier, int(devis.numero[len(prefixe):]))
                except ValueError:
                    continue
        suivant = dernier + 1
        if reserver:
            self.compteurs[cle] = suivant
            ecrire_json(self.f_compteurs, self.compteurs)
        return f"{prefixe}{suivant:04d}"

    # --- paramètres ------------------------------------------------------

    def enregistrer_compteurs(self) -> None:
        ecrire_json(self.f_compteurs, self.compteurs)

    def enregistrer_gabarit(self, gabarit: Gabarit) -> None:
        self.gabarit = gabarit
        ecrire_json(self.f_gabarit, en_dict(gabarit))

    def enregistrer_societe(self, societe: Societe) -> None:
        self.societe = societe
        ecrire_json(self.f_parametres, en_dict(societe))

    # --- aides -----------------------------------------------------------

    def nom_client(self, client_id: str) -> str:
        client = self._clients.get(client_id)
        return client.libelle if client else ""

    def nom_chantier(self, chantier_id: str) -> str:
        chantier = self._chantiers.get(chantier_id)
        return chantier.libelle if chantier else ""

    def taille_corbeille(self) -> int:
        """Nombre de fiches archivées, toutes catégories confondues."""
        return sum(len(liste(supprimes=True)) for liste in
                   (self.clients, self.chantiers, self.articles,
                    self.devis, self.factures))

    def statistiques(self) -> dict:
        from ..domaine import calculer_totaux
        zero_ = __import__("decimal").Decimal("0.00")
        accepte = sum((calculer_totaux(d).total_ht for d in self.devis()
                       if d.statut == "accepté"), start=zero_)
        en_attente = sum((calculer_totaux(d).total_ht for d in self.devis()
                          if d.statut == "envoyé"), start=zero_)
        zero = __import__("decimal").Decimal("0.00")
        # L'écran d'accueil annonce « facturé cette année », et il faut donc
        # s'en tenir à l'année en cours. Le filtre manquait : avec les neuf
        # ans d'historique repris de l'ancien logiciel, c'est le cumul de
        # toutes les années qui s'affichait sous ce libellé.
        annee = f"{datetime.now().year}-"
        facture_ht = sum((calculer_totaux(f).total_ht for f in self.factures()
                          if f.statut in ("émise", "payée")
                          and f.date_facture.startswith(annee)), start=zero)
        # « Restant à encaisser » et « en retard », eux, ne se bornent pas à
        # l'année : une facture impayée de l'an dernier reste à encaisser.
        impaye_ttc = sum((calculer_totaux(f).total_ttc for f in self.factures()
                          if f.statut == "émise"), start=zero)
        en_retard = sum((calculer_totaux(f).total_ttc for f in self.factures()
                         if f.en_retard), start=zero)
        # Articles et ouvrages ont leur écran chacun : un sac de ciment se
        # commande, une heure de pose se vend. On les compte donc à part.
        articles = self.articles()
        ouvrages = [a for a in articles if a.type == "ouvrage"]
        return {
            "clients": len(self.clients()),
            "chantiers": len(self.chantiers()),
            "bibliotheque": len(articles),
            "articles": len(articles) - len(ouvrages),
            "ouvrages": len(ouvrages),
            "devis": len(self.devis()),
            "factures": len(self.factures()),
            "corbeille": self.taille_corbeille(),
            "ttc_en_retard": en_retard,
            "ht_accepte": accepte,
            "ht_en_attente": en_attente,
            "ht_facture": facture_ht,
            "ttc_impaye": impaye_ttc,
        }
