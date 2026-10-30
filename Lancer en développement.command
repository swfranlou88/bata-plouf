#!/bin/zsh
# Double-cliquez ce fichier pour lancer le logiciel.
cd "$(dirname "$0")" || exit 1
exec "$HOME/.local/bin/uv" run python -m bata_plouf
