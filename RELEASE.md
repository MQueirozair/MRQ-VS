# Como publicar uma versão

O `dist/` local serve para inspecionar/rodar o pacote; os binários nativos
(Windows/macOS/Linux) são compilados pelo GitHub Actions — não dá para
compilar um `.exe` no macOS nem um Mach-O no Linux sem toolchain cruzada.

## Passo a passo

```bash
# 1. gere e valide o pacote portátil + manifesto (roda o app de verdade)
python -m mrqvs.release

# 2. suba o código
git add -A && git commit -m "..." && git push

# 3. crie a tag: isso dispara build.yml -> test, binary (3 SOs), portable, release
git tag v0.1.21
git push origin v0.1.21
```

Em ~5 minutos o release aparece em
`https://github.com/MQueirozair/MRQ-VS/releases/tag/v0.1.21` com:

| Arquivo | Origem |
|---|---|
| `mrq-vs-windows-x64.exe` | PyInstaller no `windows-latest` |
| `mrq-vs-macos-arm64` | PyInstaller no `macos-latest` (Apple Silicon) |
| `mrq-vs-linux-x64` | PyInstaller no `ubuntu-latest` |
| `mrq-vs-0.1.21.pyz` | zipapp (roda em qualquer SO com Python 3.10+) |
| `mrq-vs-0.1.21-linux-x64.zip` | pyz + LEIA-ME + licença |
| `release-manifest.json` | sha256 de cada artefato |
| `SHA256SUMS.txt` | sha256 de **todos** os arquivos do release |

Sem tag, todo push em `main` já gera os três binários como **artefatos** da
execução (aba Actions → run → Artifacts), que é como testar sem publicar.

## Por que o binário não embute o torch

Seria 2 GB por download. O binário é um app Python congelado que **chama o
Python do sistema** para rodar `demucs`, `audio_separator`, `spleeter` e
`yt_dlp` quando eles estão instalados (`src/mrqvs/runtime.py`). Sem Python
instalado ele continua rodando com o backend DSP e o `mrq-vs doctor` explica
o que falta. É o mesmo desenho do yt-dlp.exe + ffmpeg: o "instalador" é o
binário, as dependências pesadas são escolha do usuário.

## Conferir um download

```bash
sha256sum -c SHA256SUMS.txt        # Linux
shasum -a 256 -c SHA256SUMS.txt    # macOS
certutil -hashfile mrq-vs-windows-x64.exe SHA256   # Windows
```

## Notas por sistema

- **Windows SmartScreen**: o `.exe` não é assinado (certificado EV custa
  caro); na primeira execução escolha "Mais informações → Executar assim
  mesmo".
- **macOS Gatekeeper**: baixado pela release fica com quarentena;
  `xattr -d com.apple.quarantine ~/.local/bin/mrq-vs`. O `install.sh` já
  tenta isso quando o comando existe.
- **Linux**: `chmod +x` (o `install.sh` faz). Para IA, instale `demucs` no
  Python do sistema.
