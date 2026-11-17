# Bata-plouf

Devis et factures pour le bâtiment. Tourne entièrement sur le poste de travail
— macOS, Windows ou Linux — sans internet, sans serveur, sans base de données.

## Installer sur un nouveau Mac

Deux cas à ne pas confondre : s'en servir ne demande rien, développer demande
uv.

### Pour s'en servir

**Rien à installer** — ni Python, ni uv, ni git. L'application embarque Python
et Qt, elle ne dépend de rien d'autre.

1. Télécharger **`Installer-Bata-plouf.zip`** (171 Ko). Ce lien sert toujours
   la dernière version, il ne se périme pas :
   https://github.com/swfranlou88/bata-plouf/releases/latest/download/Installer-Bata-plouf.zip
2. Reçu par téléchargement, macOS le met en quarantaine — **clic droit →
   Ouvrir** au premier lancement, une seule fois. Par clé USB, il s'ouvre
   directement.
3. Il détecte l'architecture du Mac, télécharge la dernière version publiée,
   l'installe dans **Applications** et la lance.

Gardé dans le Dock, il sert ensuite de raccourci et ne parle que s'il a
quelque chose à dire : si le logiciel tourne déjà, il le ramène devant ; s'il
est installé et à jour, il l'ouvre, sans une fenêtre ; une version plus
récente est la seule chose qui le fasse proposer quoi que ce soit. Sans
réseau, il ouvre ce qui est installé plutôt que de se plaindre. Pour réparer
une installation abîmée, supprimer `Bata-plouf.app` puis le relancer : il
réinstalle.

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

Paramètres → **Exporter en zip** met toute la base dans un seul fichier, PDF
exclus mais logo compris : neuf ans d'historique tiennent en 600 Ko.
**Importer un zip** la remet en place, mais remplace tout : le logiciel
annonce d'abord ce que contient l'archive, sauvegarde l'existant, et refuse
une archive dont un fichier ne se relit pas plutôt que de laisser une base à
moitié reprise. Le logo est reposé dans le dossier de données et les
paramètres le retrouvent : le chemin de l'ancien poste ne mènerait nulle
part.

Sans logo sous la main, `uv run python outils/logo_provisoire.py` en dessine
un au trait, à remplacer dans Paramètres quand le vrai sera prêt.

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
        chantier.py       heures et fournitures, calculées sur le devis
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

Les textes de second plan — descriptions, notes sous les tableaux, compteurs —
sont d'un **bleu-vert sourd** plutôt que du gris des bordures : sur fond
sombre, ce gris-là se noyait. La teinte se choisit d'après le thème en cours
et se recalcule si le système bascule pendant que le logiciel tourne.

L'accueil présente six catégories — clients, devis, matériaux, ouvrages,
factures, chantiers — avec leurs chiffres et des raccourcis. Chaque catégorie
ouvre une liste avec création, modification et suppression — sauf les
chantiers, qui se calculent.

**Chantiers** n'est pas une liste de fiches : c'est la liste des devis, lus
du côté de l'atelier. Ouvrir un chantier donne ce qu'on veut savoir la veille
d'attaquer — combien d'heures, quelles fournitures, où l'on en est de la
facturation. Les heures viennent de la composition des ouvrages, « Main
d'oeuvre 2.930 » à l'unité telle que l'ancien logiciel la gardait,
multipliée par les quantités du devis ; un ouvrage dont le temps est inconnu
est annoncé comme tel plutôt que compté pour zéro. Rien ne s'enregistre :
tout se recalcule à l'ouverture, donc rien ne peut s'y démoder. Un bouton
mène du devis à son chantier et du chantier à son devis.

Un ouvrage porte sa **composition** : ce qu'il consomme par unité, matière et
heures — « un mètre carré de bouchage en agglos, c'est un bloc creux, un
demi-sac de ciment, 0,03 m³ de sable et 2,93 heures ». Elle se modifie sur la
fiche, sous les prix : une quantité se tape dans la colonne, un matériau
s'ajoute depuis la bibliothèque, et le total des composants s'affiche à côté
— de quoi voir d'un coup d'œil si le prix de vente tient encore. Multipliée par les quantités du devis et additionnée
d'un poste à l'autre, elle donne la liste de courses du chantier ; les heures
de machine y vont à part, car une heure de tractopelle n'est pas une heure
d'homme.

La liste de courses porte les **prix d'achat** et leur total : ce que la
matière coûtera chez le fournisseur, pas ce qu'elle se revend. Un matériau
dont la fiche n'a pas de prix d'achat est signalé, et le total annoncé comme
un minimum. Le bouton **Imprimer la liste…** en fait une feuille à emporter,
avec une case à cocher par ligne pour pointer la livraison — document
interne, à ne pas remettre au client.

Cette composition était dans l'ancien logiciel, dans une table à côté des
ouvrages, et la première reprise l'avait manquée : `outils/reprendre_composition.py`
va la chercher et la pose sur la bibliothèque existante. Les 1274 ouvrages
l'ont reçue, 3536 lignes en tout. On peut s'y fier : sur 1189 d'entre eux, la
somme des composants retombe sur le prix de vente à 2 % près.

**Matériaux** et **ouvrages** sont la même bibliothèque, séparée en deux
écrans : d'un côté ce qui s'achète chez le fournisseur, de l'autre la
prestation posée au prix de vente. Chercher un sac de ciment et chercher un
prix de carrelage posé ne sont pas le même geste, et mêler les deux fait
cinq mille lignes.

Sur un devis ou une facture, le client se cherche au clavier : on tape trois
lettres du nom, de la société ou de la ville et la liste se réduit. Accents
et traits d'union sont ignorés — l'ancien logiciel écrivait « SAINT-AMÉ » et
« SAINT AME » dans la même base.
Un champ posé sur « — aucun — » se vide dès qu'on entre dedans : la mention
dit qu'on n'a rien choisi, elle n'est pas un texte à effacer à la main.

Les fiches couvrent : pour un **client**, numéro automatique, civilité, nom,
adresse, deux téléphones, description ; pour un **matériau**, référence
fournisseur, fournisseur, nom, détail imprimé, notes internes, unité, prix
d'achat et de vente, bénéfice et marge calculés ; pour un **devis** ou une **facture**, numéro,
dates, adresses du client et du chantier, lignes détaillées, TVA par taux, HT
et TTC.

## Devis et factures

Sur une fiche, le **prix de vente suit le prix d'achat** à 25 % de marge dès
qu'on touche à l'achat : un tarif fournisseur qui bouge ne doit pas faire
fondre la marge en silence. Il reste modifiable à la main, une affaire se
négocie. Les deux champs se saisissent sans le symbole « € », qui se mettait
en travers du curseur ; l'intitulé le porte.

Une fiche de la bibliothèque porte deux textes qu'il ne faut pas confondre :
le **détail**, imprimé sous la désignation sur le devis du client, et les
**notes internes** — temps de main d'œuvre, consommations, dates de tarif —
qui servent à bâtir le prix et ne sortent jamais sur papier.

Le bouton **Bibliothèque…** d'un devis ou d'une facture ouvre sur les
**ouvrages** : une ligne de devis vend une prestation posée, pas un sac de
ciment. Les matériaux restent à un clic, pour ce qu'on livre sans le poser.

La recherche de la bibliothèque prend le **début** d'un nom ou d'un code,
pas un mot pris au milieu : quatre mille fiches se consultent comme un
index. La part qui a répondu est surlignée dans la liste, pour qu'on voie
pourquoi chaque fiche est restée. Accents ignorés.

Une désignation plus large que sa colonne se lit **au survol** : l'infobulle
rend le texte entier, et seulement quand il est rogné.

L'adresse du chantier se recopie de la fiche client d'un clic — bouton
**Celle du client** — et reste modifiable : le chantier est presque toujours
chez le client, mais pas toujours.

Double-cliquer sur la désignation d'une ligne venue d'un ouvrage ouvre
**l'ouvrage**, pas le texte de la ligne : c'est le nom ou le prix de la
bibliothèque qu'on vient corriger, et la correction servira aux devis
suivants. Ce qu'on y corrige descend aussi sur la ligne du document ouvert
— mais seulement ce qu'on vient de changer : une ligne porte souvent un prix
négocié pour ce chantier-là, et ouvrir la fiche pour y lire le tarif ne doit
pas l'écraser. Sur une facture émise, rien ne descend : le verrou comptable
tient. Les titres de lot, les textes libres et les lignes reprises de
l'ancien logiciel gardent la saisie directe.

Le devis accepte des sections par lot, des lignes chiffrées, des textes libres,
une remise par ligne et une remise globale. La TVA est **par ligne** : 20 %
neuf, 10 % rénovation, 5,5 % rénovation énergétique, 0 % autoliquidation.

Un devis est **valable six mois** par défaut, et le bouton **Enregistrer**
le confirme par un mot : sans réponse, on ne sait pas si l'enregistrement
s'est fait ou si un champ manquant a tout retenu.

Bouton **Facturer…** depuis la liste des devis ou depuis le devis ouvert,
quatre façons :

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

Écran **Modèle du devis**, avec aperçu en direct — zoomable au Ctrl + molette
ou aux boutons — : couleur, police, titre, logo, colonnes du tableau, blocs
affichés, pied de page, marges. Six modèles
de départ. Une seule couleur est demandée — les fonds en sont dérivés et la
couleur du texte posé dessus est calculée pour rester lisible.

Deux mises en page, au choix. **Moderne** : blocs colorés, encadré du client,
récapitulatif à droite. **Classique** (modèle « Artisan ») : le devis
d'artisan, en-tête à trois colonnes — logo et identifiants, métiers, nom et
qualité —, objet souligné au centre, tableau encadré dont les filets
descendent jusqu'au bas de la page, et les totaux dans un cadre en bas à
droite. Pas de couleur : ces documents partent sur une laser noir et blanc, où
un aplat devient un gris qui mange le texte. Le cadre qui descend jusqu'en bas
n'est pas qu'une habitude — il empêche qu'on ajoute une ligne après signature
sans que cela se voie.

Dix-huit millimètres de blanc sur les côtés : à douze, le cadre du tableau
frôlait le bord de la feuille. Deux documents denses des années passées —
trente-cinq et trente-huit lignes — se réimpriment du coup sur deux pages ;
les marges se règlent écran « Modèle du devis » pour qui préfère l'inverse.

Le cadre des totaux finit sur le **TOTAL TTC** : c'est le chiffre qu'on
cherche des yeux au bas d'un devis, et rien ne doit le suivre. L'acompte et
le solde se lisent en toutes lettres dans les mentions, avec leurs montants ;
une facture réglée s'y dit acquittée.

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

## Sauvegarde mensuelle en ligne

Une sauvegarde sur le même disque que les données ne protège de rien :
l'incendie, le vol et la panne emportent les deux. Une fois par mois, au
premier lancement, le logiciel dépose donc une copie **chiffrée** dans une
release GitHub — 832 Ko pour six cents clients et quatre cents pièces.

Le dépôt est **privé**, et le fichier **chiffré** : il faut franchir les deux
portes. **AES-256-GCM**, clé dérivée par **scrypt réglé à 256 Mo par essai** —
une demi-seconde à l'ouverture, un mur pour qui voudrait essayer des millions
de mots de passe hors ligne. Les réglages voyagent en clair dans l'en-tête
mais sont authentifiés : personne ne peut les abaisser en chemin.

Phrase de passe et jeton GitHub vivent dans `sauvegarde.env`, à côté des
données et **jamais dedans** — ils ne partent donc dans aucune archive.
Demandés une fois, au lancement, puis plus jamais.

Trois précautions de mise en place :

- **Un dépôt séparé de celui du logiciel.** Le jeton d'écriture dort sur la
  machine de l'utilisateur ; s'il tombe entre d'autres mains, il ne doit pas
  permettre de publier une fausse mise à jour que toutes les installations
  iraient chercher toutes seules.
- Un **jeton fin**, limité à ce dépôt, avec `Contents: Read and write`.
- Une **seule release**, étiquetée `sauvegardes` et marquée pré-version, qui
  porte un fichier par mois. GitHub exclut les pré-versions de
  `releases/latest`, où le logiciel cherche ses mises à jour : sans cela la
  sauvegarde de novembre passerait pour une version à installer.

Pour restaurer : **Paramètres → « Restaurer depuis le dépôt… »**. Le logiciel
liste ce qui est en ligne, rapatrie, déchiffre, et passe par le même chemin
qu'une archive ordinaire — inspection, confirmation, sauvegarde de l'état
actuel avant remplacement. C'est la voie à prendre sur un Mac neuf : le
logiciel est le premier à être réinstallé, et il n'a besoin de rien d'autre.

En dernier recours, sans le logiciel, depuis n'importe quelle machine :

    uv run python outils/dechiffrer_sauvegarde.py compte/depot bata-plouf-2026-11.zip.enc

Il accepte aussi un fichier local ou une adresse, et rend un `.zip` ordinaire.
Sur un dépôt privé, il lui faut le jeton — variable `JETON_GITHUB`, ou le
`sauvegarde.env` de la machine.

**La trousse de secours**, à garder ailleurs qu'en ligne : la phrase de passe,
le jeton, et le nom du dépôt. Avec ces trois-là, une sauvegarde se rouvre
depuis n'importe où. Sans la phrase, personne ne le peut.

**La phrase de passe ne se récupère pas.** Ni GitHub, ni le logiciel, ni
personne ne la connaît. Notée ailleurs, ou les sauvegardes sont perdues.

## Publier une version

**Le dépôt doit être public.** L'application interroge GitHub sans
s'authentifier ; un dépôt privé répond 404, et un jeton embarqué dans une
application distribuée est un jeton divulgué.

Première mise en ligne :

    git init && git add . && git commit -m "Bata-plouf, première version"
    git remote add origin https://github.com/swfranlou88/bata-plouf.git
    git push -u origin main
    git tag v0.1.0 && git push origin v0.1.0

Ensuite, à chaque version, **une étiquette suffit** :

    git tag v0.2.0 && git push origin v0.2.0

ou, sans ligne de commande, depuis GitHub : *Releases* → *Draft a new release*
→ *Choose a tag* → taper `v0.2.0` → *Create new tag* → *Publish release*.

C'est l'étiquette qui fait la version : le workflow l'inscrit dans
`bata_plouf/__init__.py` avant de construire, et l'archive comme le paquet
macOS la portent. Rien à modifier dans le code au préalable ; `__version__`
n'est là que pour une exécution depuis les sources. Une étiquette qui n'est
pas un `v1.2.3` arrête la construction avant qu'elle ne commence.

GitHub Actions construit alors les quatre versions et publie la release. S'il
en trouve une déjà créée — c'est le cas quand on passe par l'interface — il y
joint les archives au lieu d'échouer.

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
    uv run python outils/verifier_impression.py     l'encre tombe dans les marges

Et pour s'y retrouver dans le code :

    uv run python outils/carte.py                   dresse CARTE.md

`CARTE.md` liste chaque module, son rôle, ses fonctions et leurs numéros de
ligne, avec les conventions du projet. Elle n'est pas versionnée : c'est une
vue du code à un instant donné, qu'on refait plutôt que de corriger.

Le troisième refait un chantier complet et vérifie les invariants. Il tourne
aussi à chaque poussée, via `.github/workflows/controler.yml`.

Le dernier rend un devis en PDF et mesure où l'encre commence et finit sur la
feuille. Un document peut être juste en HTML et faux sur le papier : c'est la
peinture sur l'imprimante qui le place, et rien d'autre ne le dirait.
