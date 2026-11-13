#!/usr/bin/env sh
# Empacota o executável portátil localmente (o mesmo que o CI faz).
# Requer: python com pip, e PyInstaller (`pip install pyinstaller`).
set -eu
python -m pip install -q -U pyinstaller

# O separador de --add-data é diferente no Windows (";" x ":") — por isso
# não dá para ter um comando único nos três sistemas.
case "$(uname -s 2>/dev/null || echo Windows)" in
  MINGW*|MSYS*|CYGWIN*) SEP=";"; ICON_ARGS="--icon windows/mrq-vs.ico" ;;
  *) SEP=":"; ICON_ARGS="" ;;
esac

# shellcheck disable=SC2086
python -m PyInstaller --onefile --console --name mrq-vs \
  $ICON_ARGS \
  --collect-all soundfile \
  --add-data "src/mrqvs/web/index.html${SEP}mrqvs/web" \
  --add-data "src/mrqvs/web/favicon.ico${SEP}mrqvs/web" \
  --add-data "src/mrqvs/web/icone-192.png${SEP}mrqvs/web" \
  --add-data "src/mrqvs/web/icone-512.png${SEP}mrqvs/web" \
  src/mrqvs/_build.py

echo
echo "pronto: dist/mrq-vs (Linux/macOS) ou dist/mrq-vs.exe (Windows)"
./dist/mrq-vs --version || ./dist/mrq-vs.exe --version
