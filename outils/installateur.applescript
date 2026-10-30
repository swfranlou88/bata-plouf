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
-- Écrite en AppleScript pour rester minuscule et afficher de vraies fenêtres
-- du système, sans ouvrir le Terminal devant l'utilisateur.

property depot : "__DEPOT__"
property nomApp : "Bata-plouf.app"
property nomLisible : "Bata-plouf"

on arreter(message)
	display dialog message buttons {"Fermer"} default button 1 with icon stop with title nomLisible
	error number -128
end arreter

on main()
	-- Pour quelle machine ?
	set architecture to do shell script "uname -m"
	if architecture is "arm64" then
		set cible to "macos-arm64"
	else
		set cible to "macos-x86_64"
	end if

	-- Quelle est la dernière version publiée ?
	set fichierJson to do shell script "mktemp /tmp/bataplouf-XXXXXX"
	try
		do shell script "curl -fsSL --max-time 25 'https://api.github.com/repos/" & depot & "/releases/latest' -o " & quoted form of fichierJson
	on error
		arreter("Impossible de contacter GitHub." & return & return & "Vérifiez la connexion à internet, puis réessayez.")
	end try

	set etiquette to do shell script "grep -o '\"tag_name\": *\"[^\"]*\"' " & quoted form of fichierJson & " | head -1 | cut -d'\"' -f4"
	set adresse to do shell script "grep -o '\"browser_download_url\": *\"[^\"]*" & cible & "[^\"]*\"' " & quoted form of fichierJson & " | head -1 | cut -d'\"' -f4"
	do shell script "rm -f " & quoted form of fichierJson

	if adresse is "" then
		arreter("Aucune version de " & nomLisible & " n'est disponible pour ce Mac (" & cible & ").")
	end if

	-- Où l'installer ? Le dossier Applications du Mac, sinon celui de
	-- l'utilisateur, qui ne demande aucun droit particulier.
	set dossierApps to "/Applications"
	try
		do shell script "test -w /Applications"
	on error
		set dossierApps to (POSIX path of (path to home folder)) & "Applications"
		do shell script "mkdir -p " & quoted form of dossierApps
	end try

	set destination to dossierApps & "/" & nomApp
	set dejaInstalle to false
	try
		do shell script "test -d " & quoted form of destination
		set dejaInstalle to true
	end try

	if dejaInstalle then
		set question to "La version " & etiquette & " va remplacer celle installée dans " & dossierApps & "."
	else
		set question to "La version " & etiquette & " va être installée dans " & dossierApps & "."
	end if
	display dialog question & return & return & "Vos devis, factures et clients ne sont pas touchés : ils sont rangés à part, dans le dossier Documents." buttons {"Annuler", "Installer"} default button "Installer" with title nomLisible

	-- Téléchargement et installation
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

	display dialog nomLisible & " " & etiquette & " est installé." & return & return & "L'application va s'ouvrir." buttons {"Ouvrir"} default button 1 with title nomLisible
	do shell script "open " & quoted form of destination
end main

main()
