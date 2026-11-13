# demomix-96BPM

Gerado por **MRQ VS** em 11/11/2026 22:28.

## Identificação

- **Título usado:** demo_mix
- **Fonte:** /home/user/MRQ-VS/out/_demo/demo_mix.wav
- **Duração:** 0:24

## Análise musical

- **BPM:** 95.9 — pulso claro (confiança 0.77)
  - Grade de batidas: 39 tempos, primeiro em 0.000 s
- **Tonalidade:** F maior (confiança 0.86) · Camelot **7B**
- **Loudness médio:** -17.8 dBFS · **pico:** -1.0 dBFS

### Estrutura detectada

| # | Início | Fim | Seção | Loudness |
|---|--------|-----|-------|----------|
| 1 | 0:00 | 0:22 | A | -17.4 dB |
| 2 | 0:22 | 0:24 | B | -27.0 dB |

_Rótulos iguais (A, A, B...) indicam trechos com material semelhante; não são nomes de seção (verso/refrão) — o programa não transcreve letra._

## Stems exportados

Formato **WAV**, 44100 Hz. Backend: `dsp-fallback/dsp-fallback`.

| # | Stem | Tipo | Arquivo | Tamanho |
|---|------|------|---------|---------|
| 1 | Mix completo | soma de conferência | `demomix-96BPM_00_mix.wav` | 3 MB |
| 2 | Vocais | aproximado (DSP, sem IA) | `demomix-96BPM_01_vocals.wav` | 3 MB |
| 3 | Bateria | aproximado (DSP, sem IA) | `demomix-96BPM_03_drums.wav` | 3 MB |
| 4 | Contrabaixo | aproximado (DSP, sem IA) | `demomix-96BPM_08_bass.wav` | 3 MB |
| 5 | Outros | aproximado (DSP, sem IA) | `demomix-96BPM_12_other.wav` | 3 MB |

**Nativo** = saiu do modelo de separação. **Derivado** = calculado por processamento de sinal em cima de um stem nativo; serve para trabalhar, não é a mesma coisa que separação por IA.

## Avisos desta execução

- separação feita pelo backend DSP (HPSS + máscaras): é aproximada e não substitui um modelo de IA. Instale `demucs` para qualidade de verdade.

## Como usar esta pasta

1. `stems/` — importe as faixas na DAW (Reaper, Ableton, FL, Logic). Todas começam no mesmo instante, então alinham sem esforço.
2. `projeto.m3u` — playlist; `projeto.cue` — marcadores das seções detectadas.
3. `clique.wav` — metrônomo na grade do BPM detectado, para gravar por cima.
4. `projeto.json` — mesmos dados em formato de máquina (útil para scripts).

### Se o resultado não ficou bom

- Voz “vazando” no instrumental: normal em material com muita reverb; experimente `--model htdemucs_ft` (mais lento, melhor em voz).
- Bateria e baixo misturados: confira se o BPM está na oitava certa (`--bpm 96`, por exemplo); o resto não muda.
- Guitarra/piano fracos: o modelo de 6 stems é o elo mais fraco do Demucs; considere rodar de novo com `--model htdemucs` e tratar guitarra como `other`.

## Licença dos modelos (leia antes de publicar)

- **Demucs** (Meta): código MIT, **pesos com uso voltado a pesquisa**. Para uso comercial do áudio separado, verifique os termos atuais do repositório.
- **Spleeter** (Deezer): MIT.
- **audio-separator / MDX**: cada modelo tem sua licença; os arquivos `.onnx` baixados trazem os termos no próprio repositório de origem.
- O áudio de entrada continua sendo obra de terceiros: separar não dá direito de redistribuir a gravação.

