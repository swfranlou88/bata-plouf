"""Point d'entrée de l'application empaquetée.

PyInstaller a besoin d'un script, pas d'un module exécutable : ce fichier ne
fait que démarrer l'application.
"""

from bata_plouf.app import main

if __name__ == "__main__":
    main()
