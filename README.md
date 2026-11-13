# MRQ VS

**Separe músicas do YouTube ou arquivos locais de áudio/vídeo em stems, detecte BPM, tonalidade, compasso e acordes, e gere clique, guia e arquivo estéreo `ENSAIO_LR` para o palco.**

```
ColdplayYellow-96BPM/                     só áudio (pronto para DAW / palco)
├── ColdplayYellow-96BPM_00_mix.wav
├── ColdplayYellow-96BPM_01_vocals.wav
├── ColdplayYellow-96BPM_03_drums.wav
├── ...
└── ColdplayYellow-96BPM_ENSAIO_LR.wav    clique + guia (L) | banda (R)

ColdplayYellow-96BPM-apoio/               material de ensaio e metadados
├── clique.wav                            metrônomo com acento no 1º tempo do compasso
├── guia.wav                              contagem + anúncio das seções
├── capa.jpg                              capa do vídeo
├── audio_original.wav                    mix de referência
├── relatorio.md                          BPM, compasso, acordes, seções e avisos
├── projeto.json                          dados estruturados para o Studio e scripts
├── projeto.m3u                           playlist na ordem dos stems
├── projeto.cue                           marcadores das seções detectadas
└── log/                                  saída crua do backend
```

O que ele faz: baixa o áudio do YouTube (ou busca pelo nome da música via `yt-dlp`) ou recebe upload local de áudio/vídeo, mede **BPM**, **compasso**, **tonalidade**, **acordes por compasso**, **estrutura** e **loudness**, separa em stems (vocais, bateria, baixo, outros; guitarra e piano quando o modelo suporta; bumbo/caixa/pratos/percussão, teclados, efeitos e loops por derivação), gera **clique**, **guia** e **`ENSAIO_LR.wav`** (canal esquerdo para o in-ear da banda, canal direito para a mesa/PA), exporta em **WAV, MP3 ou MP4** e abre tudo no **Studio** interativo no navegador com biblioteca persistente.

## Instaladores (Windows, macOS, Linux)

Não precisa de Python: cada release traz um executável único.

| Sistema | Instalação em uma linha |
|---|---|
| **Windows 10/11 (x64)** | `irm https://raw.githubusercontent.com/MQueirozair/MRQ-VS/main/install.ps1 \| iex` |
| **macOS (Apple Silicon)** | `curl -fsSL https://raw.githubusercontent.com/MQueirozair/MRQ-VS/main/install.sh \| sh` |
| **Linux (x64)** | `curl -fsSL https://raw.githubusercontent.com/MQueirozair/MRQ-VS/main/install.sh \| sh` |

Enquanto não existe release publicada, os artefatos gerados nesta sessão
estão em [`download/`](download/) (pacote `.pyz` + zip + manifesto).

Ou baixe direto na página de releases: **`https://github.com/MQueirozair/MRQ-VS/releases/latest`**
— `mrq-vs-windows-x64.exe`, `mrq-vs-macos-arm64`, `mrq-vs-linux-x64`, mais
`SHA256SUMS.txt` para conferir o download.

Os instaladores fazem três coisas: baixam o binário, colocam numa pasta do
usuário (`%LOCALAPPDATA%\MRQVS` ou `~/.local/bin`), ajustam o PATH e rodam
`mrq-vs doctor` para mostrar o que ainda falta (ffmpeg e yt-dlp são externos
de propósito: são os programas que baixam/convertem mídia).

Detalhes por sistema:

- **Windows**: o `.exe` é portátil, sem instalador MSI. Se preferir não usar
  PowerShell, baixe o `.exe` e rode direto.
- **macOS**: o binário não é assinado (sem conta de desenvolvedor Apple). Se o
  Gatekeeper reclamar: `xattr -d com.apple.quarantine ~/.local/bin/mrq-vs`.
  Para IA no Mac, `python3 -m pip install demucs` no Python do sistema — o
  binário encontra o Python sozinho.
- **Linux**: precisa de `ffmpeg` e, para a IA, `python3 -m pip install demucs`.
  Também funciona como pacote Python normal (`pip install -e ".[ai]"`).

O binário portátil **não embute torch** (seriam 2 GB): ele usa o Python do
sistema para rodar Demucs/audio-separator/yt-dlp quando você instala esses
pacotes. Sem Python, ele continua funcionando com o backend DSP e diz isso no
`mrq-vs doctor`.

## Instalação via pip (Windows), passo a passo

```powershell
# 1. Python (marque "Add python.exe to PATH" no instalador)
winget install Python.Python.3.12

# 2. ffmpeg
winget install Gyan.FFmpeg

# 3. o programa
git clone https://github.com/MQueirozair/MRQ-VS && cd MRQ-VS
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[youtube,ai]"

# 4. confira
mrq-vs doctor

# 5. use
mrq-vs "https://youtu.be/XXXXXXXXXXX" --format mp3
```

Se `mrq-vs` não for reconhecido, use `python -m mrqvs.cli` (funciona igual,
sem depender do PATH de scripts do Python).

## Instalação

Precisa de Python 3.9+ e, para tirar som de verdade do YouTube, de
**ffmpeg** e **yt-dlp**.

```bash
# 1. o programa (núcleo: numpy + soundfile)
python -m pip install -e ".[youtube]"

# 2. ffmpeg (necessário para MP3/MP4 e para decodificar m4a/webm)
#    Windows:  winget install Gyan.FFmpeg
#    macOS:    brew install ffmpeg
#    Linux:    sudo apt install ffmpeg

# 3. separação por IA (recomendado — é o que dá qualidade "Moises")
python -m pip install -e ".[ai]"        # demucs + torch, ~2 GB
# ou, sem torch:
python -m pip install -e ".[onnx]"      # audio-separator (MDX/BS-RoFormer)
```

Sem o passo 3 o programa **funciona**, mas a separação é feita pelo backend
DSP (HPSS + máscaras), que é aproximado — o relatório diz isso na cara.
Nada quebra por falta de modelo: ele avisa e entrega o que dá.

## Uso

```bash
mrq-vs "https://youtu.be/XXXXXXXXXXX"                  # WAV, todos os stems do modelo
mrq-vs "https://youtu.be/XXXXXXXXXXX" --format mp3     # MP3 320k com tags (inclui BPM)
mrq-vs "https://youtu.be/XXXXXXXXXXX" --format mp4     # MP4 com visualizador
mrq-vs link --stems vocals,drums,bass,other            # só o que interessa
mrq-vs link --model htdemucs_6s                        # 6 stems: + guitarra e piano
mrq-vs arquivo.m4a --bpm 96 --out "D:\Musica"          # arquivo local, BPM forçado
mrq-vs link --dry-run                                  # plano completo, sem baixar nada
mrq-vs doctor                                          # o que está instalado/faltando
mrq-vs stems                                           # catálogo de stems
mrq-vs models                                          # modelos e seus stems
mrq-vs serve                                           # interface no navegador
```

Também funciona como módulo: `python -m mrqvs.cli ...` (com `PYTHONPATH=src`
no modo desenvolvimento).

### Opções que importam

| Opção | Para quê |
|---|---|
| `--stems a,b,c` | escolhe os stems (`auto` = todos nativos do modelo; `all` = tudo que der para derivar) |
| `--model` | `htdemucs` (equilíbrio), `htdemucs_ft` (melhor voz, 4× mais lento), `htdemucs_6s` (guitarra+piano) |
| `--format wav\|mp3\|mp4` | WAV = estúdio · MP3 = celular · MP4 = compartilhar |
| `--bpm N` | força o BPM quando a detecção erra a oitava (metade/dobro) |
| `--normalize` | normaliza cada arquivo para −1 dBFS (padrão: preserva a relação do mix) |
| `--out` | pasta raiz onde o projeto é criado |
| `--dry-run` | mostra backend, modelo, stems, pasta — sem baixar nem processar |

## Interface web

`mrq-vs serve` abre uma página em `http://127.0.0.1:8765`: cole o link,
escolha formato, modelo e stems, e veja o resultado (BPM, tonalidade,
seções, avisos) com link para cada arquivo e para o relatório. É um servidor
local de uma página, sem build, sem npm.

## Backends de separação

| Backend | Qualidade | Requer | Stems |
|---|---|---|---|
| `demucs` (`htdemucs_6s`) | melhor aberta multi-stem | torch (~2 GB) | vocais, bateria, baixo, outros, guitarra, piano |
| `audio-separator` (BS-RoFormer / UVR-MDX) | estado da arte em voz (~12,9 dB SDR) | audio-separator | vocais, instrumental (ou 4 stems MDX) |
| `openunmix` (`umxl` / `umxhq`) | leve em CPU (substituto do Spleeter em Python 3.10+) | openunmix + torch | vocais, bateria, baixo, outros |
| `spleeter` | legado (Python ≤ 3.11) | tensorflow | vocais, bateria, baixo, outros |
| `dsp-fallback` | aproximada (sem IA) | numpy | vocais, bateria, baixo, outros |

A escolha é automática (`auto`): o melhor que estiver instalado. O modelo
escolhido define o que é **nativo**; o resto é **derivado** por DSP e aparece
marcado como aproximado no relatório (ver `docs/DESIGN.md`).

## Quanto isso separa de verdade

Números medidos, não prometidos. Na faixa de demonstração sintética
(`python -m mrqvs.demo`), comparando com os stems originais por SDR:

| Backend | vocais | bateria | baixo | outros | média |
|---|---|---|---|---|---|
| `dsp-fallback` (numpy puro) | 4,2 | 6,6 | 4,4 | 3,3 | **4,6** |
| `demucs` htdemucs_6s (benchmarks públicos) | ~8,7 | ~9,5 | ~9,1 | ~5,7 | **~8,3** |

Reproduza o seu: `python -m mrqvs.demo` e depois
`python -m mrqvs.evaluate out/_demo/verdade <pasta>/stems`
(resultado completo em `examples/avaliacao-dsp.txt`).

Leitura da escala: 3–6 dB = separação audível com vazamento; 8+ dB = boa;
10+ = muito boa. Ou seja: o fallback serve para rascunho e para máquina sem
torch; para trabalho sério, instale o `demucs`.

## Testes

```bash
python -m pytest -q     # 130+ testes, sem internet e sem torch
```

Cobrem a STFT/ISTFT (reconstrução), o detector de BPM em pulsos sintéticos,
a tonalidade, o nome das pastas, o catálogo de stems, a partição de máscaras
(soma dos stems = mix, > 30 dB de SNR), a separação e a avaliação por SDR.

## Licença e limites

- O código é MIT. **Os pesos do Demucs não são** — o uso é voltado a
  pesquisa; confira os termos do repositório antes de usar comercialmente o
  áudio separado. O relatório de cada projeto repete esse aviso.
- O áudio de entrada é obra de terceiros: separar não dá direito de
  redistribuir a gravação.
- Tonalidade e estrutura são estimativas: o relatório mostra a confiança em
  vez de fingir certeza.
