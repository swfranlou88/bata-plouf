"""Point d'entrée et composition de l'application.

C'est le seul endroit où l'on choisit les adaptateurs concrets : le stockage
en fichiers, les écrans Qt. Changer de stockage se joue ici, et nulle part
ailleurs.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication, QMessageBox

from .adaptateurs.depot_fichiers import DOSSIER_DEFAUT, DepotFichiers
from .adaptateurs.interface.fenetre import RUBRIQUES, FenetrePrincipale

# Indice de la rubrique « Paramètres » dans la barre de navigation
RUBRIQUES_PARAMETRES = [r for r in RUBRIQUES if r[1] != "parametres"]


def lancer(racine: Path | str = DOSSIER_DEFAUT) -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Bata-plouf")
    application.setOrganizationName("Bata-plouf")
    # Virgule décimale et espace comme séparateur de milliers dans tous les champs
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))

    depot = DepotFichiers(racine)
    depot.charger()
    premier_lancement = not depot.societe.nom and not depot.clients()
    depot.creer_sauvegarde()

    fenetre = FenetrePrincipale(depot)
    fenetre.show()
    fenetre.verifier_en_arriere_plan()

    if depot.anomalies:
        QMessageBox.warning(
            fenetre, "Données à vérifier",
            "Le contrôle de cohérence a relevé :\n\n"
            + "\n".join(f"· {a}" for a in depot.anomalies[:10])
            + ("\n…" if len(depot.anomalies) > 10 else ""))

    if premier_lancement:
        fenetre.navigation.setCurrentRow(len(RUBRIQUES_PARAMETRES))
        QMessageBox.information(
            fenetre, "Bienvenue",
            "Commencez par renseigner les informations de votre entreprise : "
            "elles figureront sur chaque devis imprimé.\n\n"
            "Si vous avez des fichiers de l'ancien logiciel, le bouton "
            "« Reprendre les données de Batappli… » en bas de cet écran les lira.\n\n"
            f"Vos données seront enregistrées dans :\n{depot.racine}")

    return application.exec()


def main() -> None:
    sys.exit(lancer())


if __name__ == "__main__":
    main()
