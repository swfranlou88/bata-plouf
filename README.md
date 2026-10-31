# Bata-plouf

Devis et factures pour le bâtiment. Tourne entièrement sur le poste de travail
— macOS, Windows ou Linux — sans internet, sans serveur, sans base de données.

## Installer sur un nouveau Mac

Deux cas à ne pas confondre : s'en servir ne demande rien, développer demande
uv.

### Pour s'en servir

**Rien à installer** — ni Python, ni uv, ni git. L'application embarque Python
et Qt, elle ne dépend de rien d'autre.

1. Récupérer **`Installer Bata-plouf.app`** (373 Ko) : clé USB, courriel, ou la
   page des releases du dépôt.
2. Reçu par téléchargement, macOS le met en quarantaine — **clic droit →
   Ouvrir** au premier lancement, une seule fois. Par clé USB, il s'ouvre
   directement.
3. Il détecte l'architecture du Mac, télécharge la dernière version publiée,
   l'installe dans **Applications** et la lance.

Sans installateur, l'archive `Bata-plouf-<version>-macos-<arch>.zip` de la
release se déplie et se glisse à la main dans Applications.

**Reprendre les données de l'ancien Mac** : copier le dossier
`~/Documents/Bata-plouf`. L'Assistant de migration d'Apple le fait tout seul.
Clients, devis, factures, modèle et réglages suivent.

Ensuite, plus rien à faire : **à chaque ouverture**, le logiciel vérifie s'il
existe une version plus récente et s'installe seul. Ce n'est pas un `git pull`
— il télécharge l'archive publiée dans la release, pas le code source.

### Pour développer

uv installe le Python qu'il faut ; inutile de l'installer séparément.

    curl -LsSf https://astral.sh/uv/install.sh | sh
    git clone https://github.com/swfranlou88/bata-plouf.git
    cd bata-plouf
    uv run python -m bata_plouf

La dernière commande crée l'environnement, télécharge Python et PySide6, puis
lance le logiciel : 1,2 Go et quelques minutes la première fois, immédiat
ensuite. `Lancer en développement.command` fait la même chose d'un double-clic.

Pour **construire** l'application, il faut en plus les outils en ligne de
commande d'Xcode, d'où viennent `codesign`, `iconutil` et `ditto` — voir
« Construire » plus bas :

    xcode-select --install

Récupérer les modifications : `git pull`.

## Les données

Tout est dans `~/Documents/Bata-plouf/`, en JSON lisible : `clients.json`,
`chantiers.json`, `articles.json`, `parametres.json`, `modele-devis.json`,
puis un fichier par devis et par facture, les PDF imprimés, et un instantané
horodaté à chaque ouverture dans `sauvegardes/`.

Ce dossier se copie tel quel sur une clé USB. Il vit **en dehors** de
l'application : reconstruire ou remplacer le `.app` n'y touche pas.

Faute de transactions, deux précautions tiennent la fiabilité : toute écriture
passe par un fichier temporaire puis un renommage atomique, et chaque devis a
son propre fichier.

Rien ne s'efface d'un geste. « Supprimer » met la fiche à la corbeille, d'où la
case « Corbeille » de chaque liste permet de la restaurer. L'effacement
définitif est refusé tant que quelque chose pointe vers elle.

## Architecture

Hexagonale : un cœur métier qui ne connaît rien du monde extérieur, des
adaptateurs autour.

    bata_plouf/
      domaine/            ni Qt, ni fichiers, ni réseau
        entites.py        client, chantier, article, devis, facture
        calculs.py        totaux, ventilation de la TVA
        formats.py        montants et dates à la française
        gabarit.py        réglages de présentation
        facturation.py    acompte, situation, solde, avoir
        comptabilite.py   journal, écritures, récapitulatif TVA
        ports.py          ce que le domaine attend de l'extérieur
      adaptateurs/
        systeme.py        ce qui diffère entre les systèmes
        depot_fichiers.py stockage JSON — remplit le port Depot
        import_batappli.py
        export_csv.py
        mise_a_jour.py
        impression/       composition des documents et sortie PDF
        interface/        les écrans
      app.py              la composition : où l'on choisit les adaptateurs

**Les flèches vont toujours vers le centre.** Le domaine n'importe jamais un
adaptateur. `outils/verifier_architecture.py` le vérifie.

## Les écrans

L'accueil présente cinq catégories — clients, devis, matériaux, factures,
chantiers — avec leurs chiffres et des raccourcis. Chaque catégorie ouvre une
liste avec création, modification et suppression.

Les fiches couvrent : pour un **client**, numéro automatique, civilité, nom,
adresse, deux téléphones, description ; pour un **matériau**, référence
fournisseur, fournisseur, nom, libellé, unité, prix d'achat et de vente,
bénéfice et marge calculés ; pour un **devis** ou une **facture**, numéro,
dates, adresses du client et du chantier, lignes détaillées, TVA par taux, HT
et TTC.

## Devis et factures

Le devis accepte des sections par lot, des lignes chiffrées, des textes libres,
une remise par ligne et une remise globale. La TVA est **par ligne** : 20 %
neuf, 10 % rénovation, 5,5 % rénovation énergétique, 0 % autoliquidation.

Bouton **Facturer…** depuis la liste des devis, quatre façons :

- **Facture complète** — reprend toutes les lignes du devis. Refusée si une
  partie est déjà facturée.
- **Acompte** — un pourcentage du marché entier.
- **Situation de travaux** — un avancement **par poste**, saisi dans un
  tableau. Seul l'écart depuis la situation précédente est réclamé. L'acompte
  déjà versé vient en déduction au bas, une seule fois.
- **Solde** — tout ce qui reste.

La somme des factures retombe exactement sur le marché, au centime et taux de
TVA par taux. C'est l'invariant que contrôle `outils/verifier_metier.py`.

**Une facture émise n'est plus modifiable ni supprimable** — obligation
comptable. La correction passe par un **avoir**, qui reprend les lignes au
négatif.

## Export comptable

Menu Fichier → Export comptable. Une période au choix, et trois fichiers CSV :
le **journal des ventes** (une ligne par facture), les **écritures** en partie
double prêtes à importer, et le **récapitulatif de TVA** pour la déclaration.
Le contenu de la période et le contrôle d'équilibre s'affichent avant d'écrire.

Séparateur point-virgule, UTF-8 avec BOM, virgule décimale : les trois
conditions pour qu'Excel les ouvre proprement en français. Les comptes et le
code journal se règlent dans les Paramètres.

## Modèle du devis

Écran **Modèle du devis**, avec aperçu en direct : couleur, police, titre,
logo, colonnes du tableau, blocs affichés, pied de page, marges. Cinq modèles
de départ. Une seule couleur est demandée — les fonds en sont dérivés et la
couleur du texte posé dessus est calculée pour rester lisible.

Pour changer la structure même des documents : `impression/blocs.py` (un bloc =
une fonction) et `impression/document.py` (leur ordre).

## Reprise de Batappli XP

Paramètres → Reprendre les données. Le format n'est pas codé en dur : le
logiciel détecte l'encodage (souvent Windows-1252), le séparateur, la ligne
d'en-tête, et devine la correspondance des colonnes. On vérifie à l'écran, on
**simule**, puis on importe — l'import réel crée d'abord une sauvegarde.

Ordre à respecter : clients, chantiers, devis, lignes de devis.

## Construire

    uv run --with pyinstaller python outils/construire.py

Produit `dist/Bata-plouf.app` (103 Mo) et l'archive à publier. Sur Windows et
Linux, la même commande donne le dossier correspondant — PyInstaller ne sait
pas construire pour un autre système que le sien.

Le script signe le bundle en « ad hoc », fichier par fichier : sans signature,
Apple Silicon refuse de démarrer, et `codesign --deep` plante sur ce bundle.

## Publier une version

**Le dépôt doit être public.** L'application interroge GitHub sans
s'authentifier ; un dépôt privé répond 404, et un jeton embarqué dans une
application distribuée est un jeton divulgué.

Première mise en ligne :

    git init && git add . && git commit -m "Bata-plouf, première version"
    git remote add origin https://github.com/swfranlou88/bata-plouf.git
    git push -u origin main
    git tag v0.1.0 && git push origin v0.1.0

Ensuite, à chaque version : augmenter `__version__` dans
`bata_plouf/__init__.py`, lancer les contrôles, pousser l'étiquette.
GitHub Actions construit les quatre versions et publie la release.

**Poussez l'étiquette, ne créez pas la release à la main** : c'est le workflow
qui s'en charge. S'il en trouve une déjà créée, il y joint les archives plutôt
que d'échouer, mais le chemin normal est l'étiquette seule.

**Si l'étiquette ne correspond pas à `__version__`, la construction s'arrête.**
Sans ce garde-fou, l'application reproposerait la même mise à jour sans fin.

Les images macOS de GitHub expirent régulièrement : le workflow vise
`macos-15` et `macos-15-intel`, à relever quand elles seront retirées. **Les
runners Intel s'arrêtent en août 2027** — après quoi la version macOS Intel ne
pourra plus être construite sur GitHub.

## Mettre à jour

L'installateur se remet une seule fois à l'utilisateur — voir « Installer sur
un nouveau Mac ». Ensuite le logiciel se met à jour seul, selon trois modes
réglables dans les Paramètres : **automatique** (par défaut : téléchargée et
installée au lancement, sans rien demander), **me demander**, ou **jamais**
(aucun accès au réseau).

Un échec est silencieux en mode automatique : le logiciel s'ouvre dans sa
version actuelle et le bandeau de l'accueil permet de réessayer. Une mise à
jour ratée ne doit jamais empêcher de travailler.

L'installateur ne resservira qu'en cas de réparation ou de changement de Mac.

## Contrôles

    uv run python outils/verifier_architecture.py   le domaine reste isolé
    uv run python outils/verifier_modules.py        tout s'importe
    uv run python outils/verifier_metier.py         les règles métier tiennent

Le dernier refait un chantier complet et vérifie les invariants. Il tourne
aussi à chaque poussée, via `.github/workflows/controler.yml`.
