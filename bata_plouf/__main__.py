"""Permet « python -m bata_plouf ».

Le garde-fou est indispensable : sans lui, le simple fait d'importer ce module
— ce que fait tout parcours automatique du paquet — lancerait l'application.
"""

from .app import main

if __name__ == "__main__":
    main()
