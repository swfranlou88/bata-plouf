-- Installateur de Bata-plouf.
--
-- Une petite application à part, qui va chercher la dernière version publiée
-- sur GitHub et l'installe. Elle sert dans les trois cas que le bouton de
-- mise à jour intégré ne peut pas traiter :
--
--   la toute première installation, quand il n'y a encore rien ;
--   la réparation, quand l'application ne démarre plus ;
--   le changement de Mac, où l'on préfère un fichier de 100 Ko à 100 Mo.
--
-- Elle sert aussi, à l'usage, de raccourci de tous les jours : laissée dans
-- le Dock, elle ouvre le logiciel et ne dit quelque chose que lorsqu'une
-- version plus récente existe. D'où les trois issues de main() :
--
--   l'application tourne déjà   -> on la met au premier plan, rien d'autre ;
--   elle est installée et à jour -> on l'ouvre, sans une fenêtre ;
--   une version plus récente     -> on propose, comme avant.
--
-- Écrite en AppleScript pour rester minuscule et afficher de vraies fenêtres
-- du système, sans ouvrir le Terminal devant l'utilisateur.

property depot : "__DEPOT__"
property nomApp : "Bata-plouf.app"
property nomLisible : "Bata-plouf"

on arreter(message)
	display dialog message buttons {"Fermer"} default button 1 with icon stop with title nomLisible
	error number -128
end arreter

-- Où l'application est-elle installée ? Chaîne vide si elle ne l'est pas.
on cheminInstalle()
	set maison to (POSIX path of (path to home folder)) & "Applications/" & nomApp
	repeat with candidat in {"/Applications/" & nomApp, maison}
		try
			do shell script "test -d " & quoted form of (candidat as text)
			return candidat as text
		end try
	end repeat
	return ""
end cheminInstalle

-- Le numéro de version inscrit dans le paquet, ou chaîne vide s'il manque.
on versionInstallee(chemin)
	try
		return do shell script "/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' " & quoted form of (chemin & "/Contents/Info.plist")
	on error
		return ""
	end try
end versionInstallee

-- L'application est-elle déjà en train de tourner ?
--
-- Les crochets autour du B ne sont pas une coquetterie : « do shell script »
-- lance un shell dont la ligne de commande contient le motif, et pgrep le
-- trouverait lui-même. Entre crochets, le motif cherche « Bata » sans
-- l'écrire, et ne se reconnaît donc pas.
on estLancee()
	try
		do shell script "pgrep -f '[B]ata-plouf.app/Contents/MacOS' > /dev/null"
		return true
	on error
		return false
	end try
end estLancee

-- Que faire, au vu des deux numéros ? « ouvrir » ou « installer ».
--
-- Le tri par version de la ligne de commande fait le travail : il sait que
-- 0.10.0 vient après 0.9.0, ce qu'une comparaison de texte ignore. À égalité,
-- et si l'installée est en avance — une version d'essai, par exemple —, il
-- n'y a rien à installer.
on decider(installee, publiee)
	if installee is "" then return "installer"
	if installee is publiee then return "ouvrir"
	set derniere to do shell script "printf '%s\\n%s\\n' " & quoted form of installee & " " & quoted form of publiee & " | sort -V | tail -1"
	if derniere is installee then return "ouvrir"
	return "installer"
end decider

-- La dernière version publiée, pour cette machine : {etiquette, adresse}.
on derniereVersion()
	set architecture to do shell script "uname -m"
	if architecture is "arm64" then
		set cible to "macos-arm64"
	else
		set cible to "macos-x86_64"
	end if

	set fichierJson to do shell script "mktemp /tmp/bataplouf-XXXXXX"
	try
		do shell script "curl -fsSL --max-time 25 'https://api.github.com/repos/" & depot & "/releases/latest' -o " & quoted form of fichierJson
	on error
		do shell script "rm -f " & quoted form of fichierJson
		error "injoignable"
	end try

	set etiquette to do shell script "grep -o '\"tag_name\": *\"[^\"]*\"' " & quoted form of fichierJson & " | head -1 | cut -d'\"' -f4"
	set adresse to do shell script "grep -o '\"browser_download_url\": *\"[^\"]*" & cible & "[^\"]*\"' " & quoted form of fichierJson & " | head -1 | cut -d'\"' -f4"
	do shell script "rm -f " & quoted form of fichierJson

	if adresse is "" then error "aucune archive pour " & cible
	-- L'étiquette porte un « v » que le paquet n'a pas : v0.2.0 contre 0.2.0.
	if etiquette starts with "v" then set etiquette to text 2 thru -1 of etiquette
	return {etiquette:etiquette, adresse:adresse}
end derniereVersion

on ouvrir(chemin)
	do shell script "open " & quoted form of chemin
end ouvrir

on installer(chemin, version, adresse)
	-- Où l'installer ? Le dossier Applications du Mac, sinon celui de
	-- l'utilisateur, qui ne demande aucun droit particulier.
	if chemin is not "" then
		set destination to chemin
		set enPlace to versionInstallee(chemin)
		if enPlace is "" then
			set question to "La version " & version & " va remplacer celle installée."
		else
			set question to "La version " & version & " va remplacer la " & enPlace & "."
		end if
	else
		set dossierApps to "/Applications"
		try
			do shell script "test -w /Applications"
		on error
			set dossierApps to (POSIX path of (path to home folder)) & "Applications"
			do shell script "mkdir -p " & quoted form of dossierApps
		end try
		set destination to dossierApps & "/" & nomApp
		set question to "La version " & version & " va être installée dans " & dossierApps & "."
	end if

	display dialog question & return & return & "Vos devis, factures et clients ne sont pas touchés : ils sont rangés à part, dans le dossier Documents." buttons {"Annuler", "Installer"} default button "Installer" with title nomLisible

	display notification "Téléchargement en cours…" with title nomLisible
	set chantier to do shell script "mktemp -d /tmp/bataplouf-maj-XXXXXX"
	try
		with timeout of 900 seconds
			do shell script "curl -fL --max-time 600 -o " & quoted form of (chantier & "/paquet.zip") & " " & quoted form of adresse
		end timeout
	on error
		do shell script "rm -rf " & quoted form of chantier
		arreter("Le téléchargement n'a pas abouti." & return & return & "Réessayez plus tard, ou prévenez la personne qui vous a donné ce logiciel.")
	end try

	try
		-- ditto, et non unzip : il préserve les liens et les droits du bundle
		do shell script "ditto -x -k " & quoted form of (chantier & "/paquet.zip") & " " & quoted form of (chantier & "/contenu")
		set trouvee to do shell script "find " & quoted form of (chantier & "/contenu") & " -maxdepth 3 -name '*.app' -type d | head -1"
		if trouvee is "" then error "archive vide"
		do shell script "rm -rf " & quoted form of destination
		do shell script "ditto " & quoted form of trouvee & " " & quoted form of destination
		-- Sans cela macOS refuserait d'ouvrir une application téléchargée
		do shell script "xattr -dr com.apple.quarantine " & quoted form of destination
	on error
		do shell script "rm -rf " & quoted form of chantier
		arreter("L'installation a échoué." & return & return & "Essayez de glisser " & nomApp & " à la main dans le dossier Applications.")
	end try
	do shell script "rm -rf " & quoted form of chantier

	display dialog nomLisible & " " & version & " est installé." & return & return & "L'application va s'ouvrir." buttons {"Ouvrir"} default button 1 with title nomLisible
	ouvrir(destination)
end installer

on main()
	set chemin to cheminInstalle()

	-- Déjà ouverte : on la ramène devant, et on s'arrête là. Pas de requête
	-- réseau, pas de fenêtre — on vient de cliquer pour la voir.
	if chemin is not "" and estLancee() then
		ouvrir(chemin)
		return
	end if

	try
		set derniere to derniereVersion()
	on error message
		-- Sans réseau, une application installée s'ouvre quand même : elle
		-- fonctionne hors ligne, et l'installateur n'est pas un péage.
		if chemin is not "" then
			ouvrir(chemin)
			return
		end if
		if message is "injoignable" then
			arreter("Impossible de contacter GitHub." & return & return & "Vérifiez la connexion à internet, puis réessayez.")
		end if
		arreter("Aucune version de " & nomLisible & " n'est disponible pour ce Mac.")
	end try

	if decider(versionInstallee(chemin), etiquette of derniere) is "ouvrir" then
		-- À jour : rien à dire, on ouvre.
		ouvrir(chemin)
		return
	end if

	installer(chemin, etiquette of derniere, adresse of derniere)
end main

main()
