"""Les adaptateurs : tout ce qui relie le domaine au monde extérieur.

    depot_fichiers.py   le stockage en fichiers JSON (remplit le port Depot)
    import_batappli.py  la lecture des exports de l'ancien logiciel
    impression/         la composition des documents et leur sortie PDF (Qt)
    interface/          les écrans (Qt)

Les deux premiers sont pilotés par le domaine, les deux suivants le pilotent.
Aucun d'eux n'est connu du domaine autrement que par un port.
"""
