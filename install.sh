#!/usr/bin/env sh
# Instalador do MRQ VS para macOS e Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/MQueirozair/MRQ-VS/main/install.sh | sh
#
# Baixa o binário da última release, põe em ~/.local/bin e confere dependências.
# Sem sudo, sem escrever fora da home. Para desinstalar: rm ~/.local/bin/mrq-vs
set -eu

REPO="MQueirozair/MRQ-VS"
BIN_DIR="${MRQVS_BIN_DIR:-$HOME/.local/bin}"

os=$(uname -s)
arch=$(uname -m)
case "$os" in
  Darwin) asset="mrq-vs-macos-arm64"; [ "$arch" = "x86_64" ] && asset="mrq-vs-macos-x64" ;;
  Linux)  asset="mrq-vs-linux-x64" ;;
  *) echo "sistema não suportado: $os (use o .exe no Windows)" >&2; exit 1 ;;
esac

url="https://github.com/$REPO/releases/latest/download/$asset"
echo "baixando $url"
mkdir -p "$BIN_DIR"
if command -v curl >/dev/null 2>&1; then
  curl -fL "$url" -o "$BIN_DIR/mrq-vs"
else
  wget -O "$BIN_DIR/mrq-vs" "$url"
fi
chmod +x "$BIN_DIR/mrq-vs"
# macOS marca downloads com quarentena; sem isso o Gatekeeper bloqueia.
if [ "$os" = "Darwin" ] && command -v xattr >/dev/null 2>&1; then
  xattr -d com.apple.quarantine "$BIN_DIR/mrq-vs" 2>/dev/null || true
fi

echo "instalado em $BIN_DIR/mrq-vs"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "aviso: adicione ao PATH ->  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

echo
echo "conferindo dependências:"
"$BIN_DIR/mrq-vs" doctor || true
cat <<'TXT'

Próximos passos:
  ffmpeg (obrigatório p/ MP3/MP4 e áudio do YouTube)
    macOS:  brew install ffmpeg yt-dlp
    Debian: sudo apt install ffmpeg && python3 -m pip install -U yt-dlp
  separação por IA (opcional, recomendado)
    python3 -m pip install demucs      # ~2 GB, traz torch
TXT
