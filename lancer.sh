#!/bin/sh
# Lance le logiciel en développement sous Linux ou macOS.
cd "$(dirname "$0")" || exit 1
exec uv run python -m bata_plouf
