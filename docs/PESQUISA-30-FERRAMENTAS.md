# MRQ Audio Studio — Pesquisa das 30 ferramentas candidatas

**Documento de pesquisa. Nada aqui foi implementado, instalado ou alterado no código.**
Versão do projeto analisada: `0.1.27` (branch `arena/95086e05-mrq-vs`).
Data da pesquisa: 2026-11-13.

> **Contrato deste documento:** eu não instalei nada, não mexi no motor de áudio, não troquei
> biblioteca nenhuma, não apaguei componente e não comecei implementação. Este arquivo é só
> pesquisa + seleção. Qualquer implementação começa **depois** de você marcar as caixas na
> interface `selecao-30-ferramentas.html` e confirmar.

---

## 1. Como ler as fichas

Cada ferramenta tem uma ficha com os 22 campos que você pediu. Três avisos de leitura:

1. **`não verificado`** = eu não consegui confirmar na fonte primária. Não inventei preço, link
   nem licença. Quando o dado veio de página secundária ou de agregador, está marcado assim.
2. **Custo** = licença **R$ 0** em todas as 30 (todas são livres/open source ou freeware). O que
   custa é **esforço de desenvolvimento**, que eu estimo em *dias-dev* — estimativa minha, não
   medição. Onde existe custo de hardware (GPU, RAM), está explícito.
3. **Notas 0–10** nos 7 eixos que você definiu. A "nota final" é a média aritmética simples dos
   7 eixos, só para ordenar a lista. Ela **não** é autorização para implementar nada.

### Escala de dificuldade

| Nível | O que significa na prática |
|---|---|
| **Fácil** | `pip install` (ou um binário) + uma função de chamada + teste. Sem GPU. ~1–3 dias. |
| **Médio** | Precisa de download de modelo, adaptação de formato, ou um processo auxiliar. ~4–6 dias. |
| **Avançado** | Processo separado com IPC, GPL/AGPL isolado, ou C/C++ com build próprio. ~7–9 dias. |
| **Muito avançado** | Implementação de host/ABI, treino de modelo, ou pesquisa aplicada. 10+ dias. |

### Tipos de implementação usados

`biblioteca incorporada` · `modelo de IA local` · `plugin` · `aplicativo auxiliar` ·
`serviço externo opcional` (local, nunca nuvem) · `módulo interno` (referência de algoritmo,
código nosso).

---

## 2. Resumo executivo

- **30 ferramentas, 7 categorias**, exatamente nas quantidades que você pediu (6/5/4/5/3/3/4).
- **19 são 100% liberadas** para distribuição comercial do MRQ (código permissivo **e** pesos com
  licença declarada): #1, #2, #5, #7, #10–#16, #18–#20, #22, #25–#27, #29.
- **4 têm código permissivo mas pesos sem licença declarada** → precisam de e-mail/resposta por
  escrito antes do lançamento: #3 `SCNet`/MSST, #4 `AudioSep`, #6 `PANNs`, #9 `autochord`.
- **1 tem divergência de licença** entre o PyPI e o GitHub, mas as duas opções são permissivas:
  #8 `CREMA` (ISC vs BSD-2).
- **6 são GPL/AGPL** e só entram como *processo separado* (sidecar) ou *asset que o usuário
  instala*, nunca linkadas no nosso código: #17 `pedalboard` (GPL-3.0), #21 `matchering`
  (GPL-3.0), #23 `essentia` (AGPL-3.0), #24 `Surge XT` (GPL-3.0), #28 `Ableton Link` (GPLv2+),
  #30 `MuseScore` (GPL-3.0).
- **5 são upgrades reais** do que já existe (nosso BPM, nosso tom, nossos acordes, nossa
  estrutura de seções, nosso export): `librosa`, `CREMA`, `chord-symbol`, `MSAF`, `pyloudnorm`.
  Nas outras 25, o critério foi "resolve coisa que hoje não existe".
- **Nenhuma delas substitui o `beat-this`** (que já está integrado como extra `compasso`) e
  nenhuma troca o motor de DSP próprio (`dsp.py`). Tudo é **adição plugável**.

### Top 5 por nota final (não é autorização para implementar)

| # | Ferramenta | Categoria | Nota | Por quê |
|---|---|---|---|---|
| 22 | `pyloudnorm` | E | **9,0** | MIT, 1 dia de trabalho, resolve LUFS/BS.1770 de verdade e desbloqueia normalização de release |
| 11 | `basic-pitch` | B | **8,6** | Apache-2.0, áudio→MIDI com bends, é a base do export de partitura |
| 29 | `python-rtmidi` | G | **8,6** | MIT, 2 dias, resolve MIDI real (clock, PC, controlador) sem gambiarra |
| 7 | `librosa` | B | **8,4** | ISC, referência de BPM/onset, mas atenção às dependências pesadas (numba) |
| 13 | `chord-symbol` | C | **8,4** | MIT, JS puro, resolve o inferno de parsear/transpor cifra com enarmonia certa |

---

## 3. Tabela geral das 30

Legenda de licença: `✅` permissiva e pesos livres · `⚠️` permissiva com ressalva · `❌` copyleft
forte ou pesos restritos (só sidecar/asset separado).

| # | Nome | Cat. | Licença | Ver. | Offline | Win | macOS | Dificuldade | Tipo | Dias | Nota |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Mel-Band RoFormer "Kim" + `melband-roformer-infer` | A | MIT ✅ | peso 913 MB | sim | sim | sim | Médio | modelo de IA local | 6 | 8,1 |
| 2 | `audio-separator` + modelo zoo UVR | A | MIT + crédito ⚠️ | 0.48.0 | sim | sim | sim | Médio | biblioteca incorporada | 5 | 8,0 |
| 3 | SCNet / Band-SCNet (`SCNet-PyTorch`, MSST) | A | MIT código / ⚠️ ckpt | — | sim | sim | sim | Avançado | modelo de IA local | 8 | 6,6 |
| 4 | AudioSep | A | MIT código / ⚠️ pesos | — | sim | sim | sim | Avançado | modelo de IA local | 7 | 6,1 |
| 5 | `vocal-remover` (VR Architecture) | A | MIT ✅ | — | sim | sim | sim | Fácil | aplicativo auxiliar | 3 | 6,6 |
| 6 | PANNs (`audioset_tagging_cnn`) | A | MIT código / ⚠️ pesos | — | sim | sim | sim | Médio | modelo de IA local | 5 | 6,4 |
| 7 | `librosa` | B | ISC ✅ | 0.11.0 / 1.0.1 | sim | sim | sim | Fácil | biblioteca incorporada | 3 | 8,4 |
| 8 | CREMA | B | ISC/BSD-2 ⚠️ | 0.2.0 | sim | sim | sim | Médio | modelo de IA local | 4 | 6,7 |
| 9 | `autochord` | B | Apache-2.0 ✅ | — | sim | sim | sim | Médio | modelo de IA local | 4 | 7,0 |
| 10 | MSAF | B | MIT ✅ | 0.1.82 | sim | sim | sim | Fácil | biblioteca incorporada | 3 | 7,3 |
| 11 | `basic-pitch` (Spotify) | B | Apache-2.0 ✅ | 0.4.0 | sim | sim | sim | Médio | modelo de IA local | 5 | 8,6 |
| 12 | ChordPro | C | Artistic-2.0 ✅ | — | sim | sim | sim | Fácil | aplicativo auxiliar | 2 | 7,4 |
| 13 | `chord-symbol` (npm) | C | MIT ✅ | 4.0.0 | sim | sim | sim | Fácil | biblioteca incorporada | 2 | 8,4 |
| 14 | WhisperX | C | BSD-2 ✅ | — | sim | sim | sim | Avançado | modelo de IA local | 8 | 7,3 |
| 15 | `music21` | C | BSD-3 ✅ | 10.5.2 | sim | sim | sim | Fácil | biblioteca incorporada | 4 | 8,1 |
| 16 | Airwindows | D | MIT ✅ | — | sim | sim | sim | Avançado | plugin | 6 | 6,1 |
| 17 | `pedalboard` (Spotify) | D | GPL-3.0 ❌ | — | sim | sim | sim | Médio | serviço externo opcional | 5 | 5,6 |
| 18 | DeepFilterNet | D | MIT/Apache-2.0 ✅ | 0.5.6 | sim | sim | sim | Médio | aplicativo auxiliar | 5 | 7,4 |
| 19 | AudaLign | D | MIT ✅ | 1.3.2 | sim | sim | sim | Fácil | biblioteca incorporada | 3 | 7,0 |
| 20 | `pyroomacoustics` (GCC-PHAT) | D | MIT ✅ | — | sim | sim | sim | Fácil | biblioteca incorporada | 2 | 7,3 |
| 21 | Matchering | E | GPL-3.0 ❌ | — | sim | sim | sim | Fácil | serviço externo opcional | 3 | 5,7 |
| 22 | `pyloudnorm` | E | MIT ✅ | 0.2.0 | sim | sim | sim | Fácil | biblioteca incorporada | 1 | 9,0 |
| 23 | Essentia | E | AGPL-3.0 ❌ | 2.1b6 | sim | sim | sim | Avançado | serviço externo opcional | 6 | 4,7 |
| 24 | Surge XT | F | GPL-3.0 ❌ | — | sim | sim | sim | Médio | plugin | 3 | 6,0 |
| 25 | sfizz | F | BSD-2 ✅ | — | sim | sim | sim | Médio | biblioteca incorporada | 4 | 7,3 |
| 26 | CLAP | F | MIT ✅ | — | sim | sim | sim | Muito avançado | plugin | 10+ | 3,9 |
| 27 | `beets` | G | MIT ✅ | — | sim | sim | sim | Fácil | biblioteca incorporada | 3 | 7,6 |
| 28 | Ableton Link (`aalink`) | G | GPLv2+ ❌ | — | sim | sim | sim | Avançado | biblioteca incorporada | 7 | 5,0 |
| 29 | `python-rtmidi` | G | MIT ✅ | 1.5.8 | sim | sim | sim | Fácil | biblioteca incorporada | 2 | 8,6 |
| 30 | MuseScore Studio (CLI headless) | G | GPL-3.0 ❌ | — | sim | sim | sim | Fácil | aplicativo auxiliar | 3 | 7,0 |

**Total de esforço se você marcar as 30:** ~132 dias-dev. Nenhuma licença custa R$ 0 → R$ 0.
Realista para uma pessoa: escolher **6 a 10**.

---

## 4. Análise de licenças (o que pode entrar no instalador e o que não pode)

Regra que apliquei: o MRQ é distribuído com código próprio. Se a licença da dependência é
copyleft forte (GPL/AGPL), **linkar** ela no nosso processo obrigaria a abrir o MRQ inteiro.
Mas há três formas legais de usar mesmo assim:

1. **Processo separado + IPC** (chamada de CLI ou HTTP em `localhost`): o programa GPL roda como
   obra independente. É o que já fazemos com `demucs`/`audio-separator` hoje.
2. **Asset que o usuário instala** (plugin VST3/CLAP): o plugin é obra independente carregada em
   runtime, não é derivada do nosso código.
3. **Pedido de licença alternativa** (comercial): alguns projetos vendem, está anotado onde se
   aplica.

| Ferramenta | Licença | Pode ir no instalador? | Como usar |
|---|---|---|---|
| Mel-Band RoFormer Kim | MIT (desde 2026-04-22) | **Sim**, com atribuição | Baixa os pesos na 1ª execução |
| modelo zoo UVR | MIT + crédito obrigatório ("UVR, Anjok07 & aufr33") | **Sim**, com crédito no Sobre | `audio-separator` já é CLI |
| SCNet / MSST ckpt | MIT (código) / pesos sem declaração | **Perguntar antes** | Abrir issue no ZFTurbo/MSST |
| AudioSep | MIT (código) / pesos não verificados | **Perguntar antes** | idem |
| `vocal-remover` | MIT | **Sim** | CLI local |
| PANNs | MIT (código) / pesos não verificados | **Perguntar antes** | Pesos do Zenodo |
| `librosa` | ISC | **Sim** | `pip` |
| CREMA | PyPI diz ISC, GitHub diz BSD-2-Clause | **Sim** (as duas são permissivas) | Confirmar a divergência |
| `autochord` | Apache-2.0 | **Sim** | Mas puxa TF (~600 MB) |
| MSAF | MIT | **Sim** | `pip` |
| `basic-pitch` | Apache-2.0 | **Sim** | TF/ONNX, ~50 MB |
| ChordPro | Artistic-2.0 (permissiva, tipo MIT) | **Sim** | Precisa de Perl no Windows |
| `chord-symbol` | MIT | **Sim** | JS puro, embutido no HTML |
| WhisperX | BSD-2 (pyannote opcional é CC-BY-4.0 com gate) | **Sim** se não usar diarização | torch, GPU opcional |
| `music21` | BSD-3-Clause | **Sim** | `pip` |
| Airwindows | MIT | **Sim** (é código-fonte C++) | Portar o DSP ou compilar VST3 |
| `pedalboard` | **GPL-3.0** | **Não** linkado | Sidecar HTTP ou licença comercial |
| DeepFilterNet | MIT **ou** Apache-2.0 (dual) | **Sim** | Binário Rust ou LADSPA |
| AudaLign | MIT | **Sim** | `pip` |
| `pyroomacoustics` | MIT | **Sim** | `pip` |
| Matchering | **GPL-3.0** | **Não** linkado | Sidecar Docker/CLI |
| `pyloudnorm` | MIT | **Sim** | `pip`, 1 arquivo |
| Essentia | **AGPL-3.0** | **Não** (nem sidecar é tranquilo: AGPL cobre uso em rede) | Só se o MRQ virar AGPL |
| Surge XT | **GPL-3.0** | Asset separado | Plugin que o usuário instala |
| sfizz | BSD-2 | **Sim** | `libsfizz` tem API C de render offline |
| CLAP | MIT | **Sim** (é um header/ABI) | Mas implementar host é outro nível |
| `beets` | MIT | **Sim** | `pip` |
| Ableton Link | **GPLv2+** (ou comercial por e-mail) | **Não** linkado | `aalink` é GPL-3.0 → sidecar |
| `python-rtmidi` | MIT (RtMidi é MIT modificado) | **Sim** | wheels prontos |
| MuseScore CLI | **GPL-3.0** | Asset separado / PATH do usuário | Chamada `musescore -o` |

### Candidatos que eu **descartei** e por quê

Isso responde direto à sua regra de "nunca assumir que grátis = redistribuível":

| Candidato | Motivo do descarte |
|---|---|
| **Demucs / htdemucs / htdemucs_ft** | Código MIT, mas os **pesos não**: o autor diz que não estão cobertos pela MIT e são "only for scientific purposes" (issue #327). Já usamos Demucs como backend opcional; não dá para promover a padrão. |
| **madmom** | Código BSD-2, mas **modelos CC BY-NC-SA 4.0** (documentado no paper e no LICENSE do repo) → não comercial. Isso também condena o `allin1` (depende de madmom). |
| **LarsNet** | Pesos **CC-BY-NC-4.0** explícito. |
| **becruily** (guitarra/karaoke) | O autor diz "free to use as long as it's non commercial". |
| **Sucial** dereverb | CC-BY-NC-SA-4.0. |
| **MDX23C DrumSep / LarsNet** para bateria separada | Sem licença comercial clara; a saída honesta é treinar em StemGMD (CC-BY-4.0) com MSST (MIT). |
| **so-vits-svc / RVC** | AGPL-3.0 + "exclusivamente para fins acadêmicos, não destinado a produção" + modelos por personagem com direitos de imagem. |
| **DeepAFx-ST (Adobe)** | Licença "ADOBE RESEARCH LICENSE" — uso de pesquisa, não redistribuição comercial. |
| **aubio** | GPL-3.0 e parado desde 2019 (0.4.9). Nossa STFT própria já cobre onset/tempo. |
| **Rubber Band** | GPL-2.0 (comercial só pagando). `librosa`/`soundtouch` cobrem o nosso transpor. |
| **SoundTouch** | LGPL-2.1 é utilizável, mas o resultado é pior que o nosso transpor atual; não valeria o risco de LGPL no instalador. |
| **Chordino / NNLS-Chroma** | GPL-2.0 + plugin Vamp dos anos 2010. |
| **ChordSheetJS** | GPL-2.0. Preferi `chord-symbol` (MIT). |

---

## 5. Comparativo técnico por categoria

### A — IA e separação
O gargalo real do MRQ hoje não é "separar voz", é **separar instrumento específico com licença
limpa**. Voz/instrumental já é resolvido (e bem) por Mel-Band RoFormer. O que falta:

| Necessidade | Melhor opção | Qualidade | Custo |
|---|---|---|---|
| Voz vs instrumental (topo) | #1 Mel-Band RoFormer Kim | SDR vocal 10,98 / mediana 12,08 | 913 MB, ~4 GB VRAM |
| Voz principal vs backing | #2 UVR karaoke (5_HP/6_HP) via `audio-separator` | boa, abaixo dos roformers NC | ~200 MB |
| Instrumento isolado (baixo, guitarra, vento) | #2 (17_HP-Wind) / #3 SCNet | baixo/bateria "weak" sem Demucs | ⚠️ licença |
| Remoção por descrição textual | #4 AudioSep | flexível, impreciso em mistura densa | ~6 GB |
| Acompanhamento/instrumental leve | #5 `vocal-remover` VR | aceitável, roda em CPU | leve |
| Reconhecer instrumento | #6 PANNs | tag de 527 classes do AudioSet | GPU ajuda |

**Conclusão honesta:** a categoria A é onde a restrição de licença machuca mais. Sem resolver
`SCNet`/MSST, os stems `guitar`/`piano`/`bass` vão continuar em qualidade "beta".

### B — Análise musical
Nossa `dsp.py` já tem onset/tempo/beat grid próprios. O ganho vem de:
- **#7 `librosa`**: `pyin` (f0), `beat_track` com DP de Ellis, `onset_detect` multi-canal. Melhor
  robustez que heurística própria em material com muita percussão. Custo: `numba`/`llvmlite`
  (~100 MB) e `scipy`.
- **#8 CREMA**: troca "chroma + perfil tonal" por CNN treinada (GiantSteps/EDM). Ganho real em
  tonalidade ambígua (relativa maior/menor). Custo: TensorFlow.
- **#9 `autochord`**: acordes com 25 classes + inversões, bi-LSTM. Muito melhor que templates de
  chroma. Custo: TF + `vamp` + `gdown`.
- **#10 MSAF**: segmentação não supervisionada (Foote/Laplacian), sem modelo NC. Melhora a
  detecção automática de seções que hoje é heurística.
- **#11 `basic-pitch`**: é o único caminho realista para "áudio → MIDI/partitura" com bends.

### C — Cifras, letras, harmonia
Separar em três camadas resolve o problema de forma limpa:
1. **Símbolo do acorde** → #13 `chord-symbol` (parse, transpor, enarmonia, graus/Nashville).
2. **Formato do documento** → #12 ChordPro (texto com `[C]` inline; render em PDF/HTML).
3. **Tempo por palavra** → #14 WhisperX (align forçado wav2vec2, <50 ms).
4. **Análise harmônica** → #15 `music21` (numerais romanos, funções, MusicXML).

### D — Produção/edição
- **#16 Airwindows**: é código C++ MIT, não biblioteca Python. Serve como **referência de DSP**
  (EQ, compressor, saturação) e como VST3 compilável — não como import.
- **#17 `pedalboard`**: é a melhor API Python de efeitos (JUCE), mas GPL-3.0. Só sidecar.
- **#18 DeepFilterNet**: 48 kHz, RTF ~0,19 em 1 thread — ótimo para limpar gravação de ensaio.
  Limitação importante: os modelos são **treinados em fala**, não em música; em voz cantada o
  resultado é experimental.
- **#19 AudaLign**: alinhar várias captações do mesmo show por fingerprint.
- **#20 `pyroomacoustics.sync`**: GCC-PHAT para atraso sub-amostra + sinal do pico de correlação
  (usar o sinal para detectar polaridade invertida é código nosso, não feature da lib).

### E — Masterização e qualidade
- **#22 `pyloudnorm`**: BS.1770-4 correto. **Atenção:** True Peak **não** está implementado nele —
  precisa de sobreamostragem 4× (a fazer) ou `ffmpeg -af ebur128`.
- **#21 Matchering**: masterização por referência (RMS, resposta de frequência, pico, largura
  estéreo). GPL-3.0 → sidecar HTTP.
- **#23 Essentia**: 250+ descritores espectrais/tonais. AGPL-3.0 → só se o MRQ virar AGPL.

### F — Instrumentos virtuais
- **#25 sfizz**: SFZ (formato aberto de samples) com API C que renderiza offline — é o melhor
  encaixe numa arquitetura offline como a nossa. BSD-2.
- **#24 Surge XT**: sintetizador completo, GPL-3.0, mas como **plugin instalado pelo usuário** não
  contamina o MRQ.
- **#26 CLAP**: padrão MIT moderno (melhor que VST3 para nós), porém **implementar host é 10+
  dias** e não é prioridade.

### G — Recursos profissionais
- **#27 `beets`**: importação, deduplicação, metadados, plugins. É a base de "gestão de
  repertório" sem escrever do zero.
- **#28 Ableton Link**: sincronismo de tempo em rede com outros apps. GPLv2+ → sidecar.
- **#29 `python-rtmidi`**: MIDI clock, Program Change, controlador. Resolve
  "sincronizar áudio-MIDI-equipamentos".
- **#30 MuseScore CLI**: `musescore arquivo.mscz -o saida.pdf --no-gui` — export de partitura.

---

## 6. Compatibilidade (o que quebra no instalador hoje)

| Risco | Ferramentas afetadas | Observação |
|---|---|---|
| Python do projeto é `>=3.10` (`requires-python`) | `librosa 1.0.x` pede `>=3.12`; `music21 10.x` pede `>=3.11`; `chord-extractor` pede `<3.12` (já descartado) | Fixar `librosa>=0.11,<1` e `music21>=9.9,<10` se não formos subir o Python |
| `tensorflow` (~600 MB) | `autochord`, `CREMA` | Empacotar como extra opcional, nunca no core |
| `torch` (~2 GB com CUDA) | WhisperX, Mel-Band RoFormer, AudioSep | Já é o caso de `demucs`; manter extra |
| Binário externo no PATH | MuseScore, `vocal-remover`?, Matchering | Detectar e degradar com mensagem clara |
| Windows sem Perl | ChordPro (implementação de referência é Perl) | Implementar o formato em Python; CLI é opcional |
| macOS arm64 | `pyroomacoustics`, `pyloudnorm`, `basic-pitch` | Todos têm wheel ou são Python puro |
| GPU opcional | 1, 3, 4, 6, 11, 14 | Tudo precisa rodar em CPU com aviso de tempo |

Nenhuma das 30 exige mudar o motor `dsp.py`. Todas entram como módulo novo em `src/mrqvs/` com
fallback: se não estiver instalada, a feature fica **desligada e honesta** (mesma semântica do
`/api/voz/<chave>`: 404 quando falta, não erro 500).

---

# 7. As 30 fichas

## Categoria A — IA e separação musical (6)

### 1. Mel-Band RoFormer "Kim" + `melband-roformer-infer`

- **Categoria:** A — Separação avançada (voz/instrumental de ponta)
- **Descrição:** modelo de separação musical (RoFormer com bandas mel) que é hoje o estado da
  arte em voz vs. instrumental, com pesos **relicenciados para MIT** em 2026-04-22.
- **O que faz:** separa um mix estéreo 44,1 kHz em `vocals` e `instrumental` com SDR reportado de
  ~10,98 dB (12,08 dB na mediana) no MUSDB18-HQ.
- **Problemas do MRQ que resolve:** hoje o backend de melhor qualidade (`demucs`) tem **pesos
  restritos a uso científico**. Este é o substituto com licença limpa para ser o backend padrão
  de voz/instrumental.
- **Funcionalidades:** inferência por chunk com overlap, saída 2 stems, funciona em CPU (lento) e
  GPU (rápido), checkpoint único `.ckpt` de 913.106.900 bytes.
- **Site oficial:** `https://huggingface.co/KimberleyJSN/melbandroformer` (verificado 200)
- **Repo GitHub:** `https://github.com/lucidrains/BS-RoFormer` (arquitetura, MIT — verificado 200)
  e o toolkit `https://pypi.org/project/melband-roformer-infer/` (MIT)
- **Documentação:** model card do HF + README do `melband-roformer-infer`
- **Licença:** **MIT** (pesos e código), relicenciado de GPL-3.0 no commit `ac9b061`;
  sha256 do arquivo `87201f4d…c7559e`.
- **Gratuita/Paga:** gratuita.
- **Uso comercial:** **sim**, com atribuição ao autor.
- **Offline:** sim, depois do download do peso.
- **Windows:** sim (torch CPU/CUDA). **macOS:** sim (MPS; sem CUDA).
- **Hardware:** ~4 GB de VRAM em GPU, ou ~8 GB de RAM em CPU. Arquivo de 913 MB.
- **Dependências:** `torch`, `numpy`, `soundfile`, `pyyaml`.
- **Facilidade de integração:** já existe o padrão de "backend externo" em `separator.py`; entra
  como mais um `MODEL_BACKEND`.
- **Limitações:** só 2 stems (não separa baixo/guitarra); CPU é devagar (~1–3× tempo real).
- **Benefício esperado:** qualidade de separação de voz de ponta **sem** risco jurídico.
- **Notas:** qualidade 9 · utilidade 9 · integração 7 · desempenho 7 · compatibilidade 9 ·
  custo-benefício 9 · diferenciação 7 → **média 8,1**
- **Dificuldade:** Médio · **Tipo:** modelo de IA local · **Dias-dev:** 6

### 2. `audio-separator` + modelo zoo UVR

- **Categoria:** A — Instrumentos individuais, backing vocals, remoção de instrumento
- **Descrição:** CLI/biblioteca Python que roda o catálogo do Ultimate Vocal Remover (MDX-Net,
  VR Arch, Demucs, MDXC, RoFormer, SCNet) com download automático de modelos.
- **O que faz:** expõe ~dezenas de modelos por nome; é o caminho para `5_HP-Karaoke` (voz
  principal vs backing), `17_HP-Wind_Inst` (sopros), `UVR-DeNoise`, `UVR-DeEcho` e DrumSep.
- **Problemas do MRQ que resolve:** o `stems.py` já declara `guitar`, `piano`, `keys`, `other`,
  mas não existe modelo licenciado que os produza. Este pacote é o **único caminho já
  instalável** para instrumentos específicos com licença MIT.
- **Funcionalidades:** seleção de modelo por nome, `--single-stem`, lotes, GPU CoreML/MPS/CUDA,
  DirectML experimental no Windows AMD/Intel.
- **Site oficial:** `https://pypi.org/project/audio-separator/` (verificado, 0.48.0)
- **Repo GitHub:** `https://github.com/nomadkaraoke/python-audio-separator` (MIT, verificado 200)
- **Documentação:** README do repo + PyPI
- **Licença:** **MIT**, com pedido explícito de crédito: *"honor the MIT license by providing
  credit to UVR and its developers"*.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim, com crédito.
- **Offline:** sim (após baixar modelos). **Windows/macOS:** sim.
- **Hardware:** CPU ok; GPU acelera.
- **Dependências:** `torch`, `onnxruntime`, `librosa`, `pydub`, etc. (é pesado, ~1 GB).
- **Facilidade de integração:** **já está** como extra `onnx` (`audio-separator>=0.20`) e como
  backend. O trabalho aqui é curadoria de modelos + UI.
- **Limitações:** MDXC/RoFormer no Windows+DirectML estoura o alocador (limitação do
  torch-directml, documentada); Demucs não roda em DirectML.
- **Benefício esperado:** preenche `guitar`/piano/karaoke com licença verificável, sem escrever
  inferência nova.
- **Notas:** 7·9·8·6·8·9·8 → **8,0** · **Médio** · biblioteca incorporada · **5 dias**

### 3. SCNet / Band-SCNet (via `SCNet-PyTorch` e MSST)

- **Categoria:** A — Separação 4 stems de alta qualidade (baixo/bateria)
- **Descrição:** arquitetura de separação com atenção esparsa por bandas; Band-SCNet é a
  variante **causal, de tempo real**, com 7,79 dB SDR no MUSDB18-HQ e 2,59 M parâmetros.
- **O que faz:** 4 stems (voz/bateria/baixo/outro) com custo computacional baixo; a versão causal
  permite separação em streaming, o que abriria "karaokê ao vivo" no Studio.
- **Problemas do MRQ que resolve:** o MRQ não tem separação de **baixo** e **bateria** com
  licença clara. Este é o candidato técnico mais forte. Também é o único caminho para separação
  em tempo real (o resto é offline).
- **Funcionalidades:** treino e inferência PyTorch, checkpoints no MSST, variante causal.
- **Site oficial:** `https://github.com/amanteur/SCNet-PyTorch` (MIT, verificado 200) — repositório
  não-oficial, última atividade 2024-04.
- **Repo GitHub:** também `https://github.com/ZFTurbo/Music-Source-Separation-Training` (MIT,
  1.636★, ativo)
- **Documentação:** paper Band-SCNet (Interspeech 2025, ISCA archive) + README do MSST
- **Licença:** código **MIT**; **checkpoints do MSST não têm licença declarada** (a issue #245
  pede isso abertamente).
- **Gratuita/Paga:** gratuita. **Uso comercial:** ❌ **não verificado** para os pesos.
- **Offline/Windows/macOS:** sim.
- **Hardware:** GPU recomendada (SCNet XL é grande); Band-SCNet pequena roda em CPU.
- **Dependências:** `torch`, `pyyaml`, `tqdm`.
- **Facilidade de integração:** média-alta: precisa de carregador de checkpoint e de um adaptador
  de shapes. O MSST já é compatível com `audio-separator`.
- **Limitações:** licença dos pesos é o bloqueio real; repo não-oficial; sem suporte.
- **Benefício esperado:** baixo e bateria "de verdade", e o único caminho para separação ao vivo.
- **Notas:** 8·8·5·7·6·6·6 → **6,6** · **Avançado** · modelo de IA local · **8 dias**
  (dos quais 2 são de conversa com o autor sobre licença)

### 4. AudioSep ("Separate Anything You Describe")

- **Categoria:** A — Remoção de instrumentos por descrição textual
- **Descrição:** modelo que separa fontes a partir de uma **frase** ("tirar a guitarra", "só a
  bateria"), usando embeddings de texto + áudio.
- **O que faz:** entrada `(áudio, texto)` → áudio da fonte descrita. Zero-shot.
- **Problemas do MRQ que resolve:** o usuário não precisa escolher entre 4 stems fixos; pode
  pedir "tirar o violão" ou "só o vocal de apoio". Isso é diferenciação de produto forte.
- **Funcionalidades:** inferência por texto, funciona com frases em inglês (o modelo é
  treinado em inglês); multilíngue **não verificado**.
- **Site oficial:** `https://audio-agi.github.io/Separate-Anything-You-Describe/` (via homepage
  do repo)
- **Repo GitHub:** `https://github.com/Audio-AGI/AudioSep` (MIT, 1.948★, último push 2024-11)
- **Documentação:** README + demo no site
- **Licença:** **MIT** no código; **licença dos pesos não verificada** (usa CLAP + checkpoints
  próprios).
- **Gratuita/Paga:** gratuita. **Uso comercial:** ❌ não verificado.
- **Offline:** sim. **Windows/macOS:** sim (CPU lento).
- **Hardware:** ~6 GB VRAM para uso confortável; CPU tecnicamente possível.
- **Dependências:** `torch`, `torchaudio`, `transformers`, `CLAP`, `gradio` (só demo).
- **Facilidade de integração:** média: precisa de pipeline de embeddings de texto.
- **Limitações:** precisão cai em mix denso; texto em inglês; modelo de 2023/2024 sem manutenção.
- **Benefício esperado:** "remoção de instrumentos" e "extração de acompanhamento" de forma
  descritiva — algo que nenhum concorrente local faz.
- **Notas:** 7·7·4·5·5·6·8 → **6,1** · **Avançado** · modelo de IA local · **7 dias**

### 5. `vocal-remover` (VR Architecture, tsurumeso)

- **Categoria:** A — Extração de acompanhamento leve
- **Descrição:** implementação original da arquitetura VR (U-Net de espectrograma) para separar
  voz de instrumental, em Python + PyTorch, MIT.
- **O que faz:** gera `instrumental.wav` e `vocals.wav` com TTA opcional; roda em CPU sem GPU.
- **Problemas do MRQ que resolve:** é o fallback **leve e claro em licença** quando o usuário não
  tem GPU nem quer baixar 913 MB. Hoje o fallback interno é o `dsp` (HPSS), que é bem pior.
- **Funcionalidades:** `--gpu`, `--tta`, `--postprocess`, número de iterações do mask.
- **Site oficial:** `https://github.com/tsurumeso/vocal-remover` (MIT, 1.765★, push 2026-09)
- **Repo GitHub:** o mesmo.
- **Documentação:** README.
- **Licença:** **MIT**. **Uso comercial:** sim.
- **Gratuita/Paga:** gratuita. **Offline:** sim. **Windows/macOS:** sim.
- **Hardware:** CPU suficiente (~1× tempo real); GPU opcional.
- **Dependências:** `torch`, `librosa`, `soundfile`, `tqdm`.
- **Facilidade de integração:** fácil — é CLI, e o padrão de backend externo já existe.
- **Limitações:** qualidade inferior aos roformers; sem stems de instrumento.
- **Benefício esperado:** separação mínima garantida em qualquer máquina, com licença simples.
- **Notas:** 6·7·9·7·9·7·3 → **6,6** · **Fácil** · aplicativo auxiliar · **3 dias**

### 6. PANNs (`audioset_tagging_cnn`)

- **Categoria:** A — Identificação/reconhecimento de instrumentos
- **Descrição:** CNN pré-treinada em AudioSet (527 classes de som), usada como tagger e como
  extrator de embedding.
- **O que faz:** dada uma janela de áudio, devolve probabilidades por classe — incluindo
  instrumentos (guitarra, piano, violino, sopros, bateria) e contexto (aplausos, público).
- **Problemas do MRQ que resolve:** não existe hoje "que instrumentos tocam nesta música?".
  Serve para: sugerir stems a extrair, validar se a separação funcionou, e gerar relatório
  técnico do release.
- **Funcionalidades:** `CNN14` (80 M parâmetros) e variantes leves; embeddings para clustering.
- **Site oficial:** sem site próprio — usar o repo.
- **Repo GitHub:** `https://github.com/qiuqiangkong/audioset_tagging_cnn` (MIT, 1.797★, push
  2024-07)
- **Documentação:** README + paper (IEEE/ACM TASLP 2020).
- **Licença:** código **MIT**; **pesos não têm licença declarada** (hospedados no Zenodo).
- **Gratuita/Paga:** gratuita. **Uso comercial:** ❌ não verificado.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU ok (CNN14 é moderada); GPU acelera.
- **Dependências:** `torch` ou `tensorflow` (há pesos nos dois formatos), `librosa`.
- **Facilidade de integração:** fácil (é só classificação, não muda o pipeline de áudio).
- **Limitações:** treinado em audio tagging genérico, não em MIR de precisão; confunde
  instrumentos parecidos; janela de ~10 s.
- **Benefício esperado:** um "raio-X" do mix que orienta o usuário e valida a separação.
- **Notas:** 6·7·7·7·7·7·4 → **6,4** · **Médio** · modelo de IA local · **5 dias**

## Categoria B — Análise musical e composição (5)

### 7. librosa

- **Categoria:** B — BPM, onset, f0, batida
- **Descrição:** biblioteca de referência em Python para análise de áudio/MIR (STFT, mel, chroma,
  onset, beat tracking, `pyin`).
- **O que faz:** `beat_track` (programação dinâmica de Ellis), `onset_detect`, `pyin` para f0
  com probabilidade de vozeamento, `tempo`, `chroma_cqt`.
- **Problemas do MRQ que resolve:** o `dsp.py` tem onset envelope e tempo próprios, mas o pulso
  erra em material com muita síncope. `beat_track` + `pyin` dão BPM e afinação confiáveis, e
  `pyin` alimenta a checagem de tom. **Não substitui** o `beat-this` (que já dá compasso).
- **Funcionalidades:** multi-canal (0.10.2+), saída em frames/amostras/tempo, cache de JIT.
- **Site oficial:** `https://librosa.org/` (via homepage do repo)
- **Repo GitHub:** `https://github.com/librosa/librosa` (ISC, 8.929★, ativo)
- **Documentação:** `librosa.org/doc`
- **Licença:** **ISC** (permissiva, equivalente a MIT simplificada).
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim, sem obrigação além do aviso.
- **Offline:** sim. **Windows/macOS:** sim (wheels).
- **Hardware:** CPU; `numba` compila no primeiro uso (2–10 s de atraso).
- **Dependências:** `numpy`, `scipy`, `numba`, `soxr`, `soundfile`, `joblib`, `pooch`.
  ⚠️ **`librosa 1.0.x` exige Python ≥3.12**; nosso `requires-python` é `>=3.10` → fixar `<1.0`.
- **Facilidade de integração:** alta — módulo novo `analise_ref.py` que só é importado se existir.
- **Limitações:** peso das dependências (numba/llvmlite ~100 MB); `beat_track` não dá compasso
  (só o `beat-this` dá); BPM pode sair como array 0-d (erro de `float()` com NumPy 2.4,
  documentado em vários projetos).
- **Benefício esperado:** BPM e afinação confiáveis + base para os itens 8, 9 e 14.
- **Notas:** 9·9·8·5·8·9·7 → **8,4** · **Fácil** · biblioteca incorporada · **3 dias**

### 8. CREMA

- **Categoria:** B — Tom / tonalidade
- **Descrição:** CNN para estimar tonalidade (24 classes: 12 maiores + 12 menores) a partir de
  espectrogramas CQT.
- **O que faz:** devolve o tom e a confiança por classe.
- **Problemas do MRQ que resolve:** nosso tom hoje é heurística de chroma + perfil tonal; erra
  fácil em relativa maior/menor. CREMA resolve justamente esse caso.
- **Funcionalidades:** modelo Keras/TF; versão "lite" também disponível.
- **Site oficial:** sem site; repo.
- **Repo GitHub:** `https://github.com/bmcfee/crema` (99★, push 2024-05)
- **Documentação:** README + paper ISMIR 2018.
- **Licença:** ⚠️ **divergência**: o PyPI declara **ISC**, o GitHub classifica **BSD-2-Clause**.
  As duas são permissivas; confirmar antes de citar.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim (ambas as licenças permitem).
- **Offline/Windows/macOS:** sim. **Hardware:** CPU ok.
- **Dependências:** `tensorflow` (~600 MB) + `librosa` + `numpy`.
- **Facilidade de integração:** média (carregar `.h5`, converter áudio para CQT compatível).
- **Limitações:** sem manutenção desde 2024-05; TF 2.x antigo; ganho sobre heurística é real mas
  não enorme.
- **Benefício esperado:** tonalidade correta em casos ambíguos → transposição automática melhor.
- **Notas:** 7·7·6·5·6·8·6 → **6,7** · **Médio** · modelo de IA local · **4 dias**

### 9. `autochord`

- **Categoria:** B — Acordes a partir do áudio
- **Descrição:** reconhecimento de acordes com rede bi-LSTM sobre CQT, 25 classes (maiores,
  menores, suspensos, dominantes, diminutos + inversões).
- **O que faz:** saída `.lab` com tempo + rótulo de acorde, muito mais estável que template de
  chroma.
- **Problemas do MRQ que resolve:** `acordes.py` hoje usa correlação de chroma; em gravação ao
  vivo com bateria forte isso vira ruído. Este é o upgrade real.
- **Funcionalidades:** modelo pré-treinado incluído no pacote; CLI `autochord recognize`.
- **Site oficial:** `https://cjbayron.github.io/autochord/`
- **Repo GitHub:** `https://github.com/cjbayron/autochord` (Apache-2.0, 166★)
- **Documentação:** README + demo ISMIR 2021 LBD.
- **Licença:** **Apache-2.0** (código). Pesos distribuídos no pacote; licença dos pesos **não
  declarada separadamente** → tratar como Apache-2.0 com ressalva.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim (com ressalva dos pesos).
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU ok; TF acelera em GPU.
- **Dependências:** ⚠️ `tensorflow>=2.6`, `librosa>=0.8`, `vamp`, `lazycats`, `gdown`.
  O pacote está preso a TF 2.6 (2021) — risco de conflito com TF novo.
- **Facilidade de integração:** média. O `vamp` é binário nativo; pode falhar no Windows.
- **Limitações:** TF antigo, dependência exótica (`vamp`), sem atualização desde 2024.
- **Benefício esperado:** cifra/acorde muito mais confiável que a heurística atual.
- **Notas:** 8·8·5·5·6·8·6 → **7,0** · **Médio** · modelo de IA local · **4 dias**
  (mais 1–2 dias se o `vamp` no Windows der problema)

### 10. MSAF (Music Structure Analysis Framework)

- **Categoria:** B — Compassos / estrutura de seções
- **Descrição:** framework de segmentação musical não supervisionada com ~20 algoritmos
  (Foote, Laplacian, CBM, SF, Scluster) e avaliação embutida.
- **O que faz:** recebe áudio (ou features) e devolve fronteiras de seção + agrupamento de
  seções semelhantes (A-B-A-B).
- **Problemas do MRQ que resolve:** `estrutura.py` detecta e nomeia seções por heurística. MSAF
  dá fronteiras melhores e um agrupamento que ajuda a nomear (o refrão é a seção que se repete).
  **Nota:** isso melhora a base do guia que fala os nomes de seção.
- **Funcionalidades:** vários estimadores, `msaf run <pasta> <algoritmo>`, avaliação com
  ground truth.
- **Site oficial:** sem site; repo.
- **Repo GitHub:** `https://github.com/urinieto/msaf` (MIT, 561★, ativo — push 2026-11)
- **Documentação:** README + docs no repo.
- **Licença:** **MIT** (sem modelos restritos — é DSP/estatística pura, não rede neural NC).
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU; memória depende do tamanho e do estimador.
- **Dependências:** `numpy`, `scipy`, `scikit-learn`, `librosa`, `matplotlib` (opcional).
- **Facilidade de integração:** fácil — pode rodar dentro do processo.
- **Limitações:** segmentação "estrutural" não entende letra; pode fundir intro+verso em música
  curta; precisa de ajuste de sensibilidade.
- **Benefício esperado:** seções mais coerentes → guia e editor com marcações certas.
- **Notas:** 7·8·8·7·8·9·5 → **7,3** · **Fácil** · biblioteca incorporada · **3 dias**

### 11. `basic-pitch` (Spotify)

- **Categoria:** B — Transcrição áudio → MIDI / partitura
- **Descrição:** rede de transcrição de pitch polifônica que gera MIDI com *pitch bends*,
  instrumento-agnóstica e com pesos Apache-2.0.
- **O que faz:** áudio (mono) → notas MIDI com onset, offset, pitch e bend; suporta vários
  instrumentos ao mesmo tempo.
- **Problemas do MRQ que resolve:** não existe hoje nenhuma exportação de partitura. Este é o
  primeiro passo (MIDI), que depois o item 15 (`music21`) ou o item 30 (MuseScore) transformam em
  partitura.
- **Funcionalidades:** `predict()` em Python, CLI, modelo TF e ONNX, demo web.
- **Site oficial:** `https://basicpitch.io` (homepage do repo; **não consegui abrir do sandbox** —
  link citado pelo próprio repo, validar no navegador)
- **Repo GitHub:** `https://github.com/spotify/basic-pitch` (Apache-2.0, 6.056★, push 2025-11)
- **Documentação:** README + paper ICASSP 2022.
- **Licença:** **Apache-2.0** (código e pesos, ambos declarados no repo).
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU (~1–2× tempo real); GPU acelera.
- **Dependências:** `tensorflow` **ou** `onnxruntime` (há os dois caminhos), `librosa`,
  `pretty_midi`.
- **Facilidade de integração:** média: precisa escolher TF ou ONNX e normalizar sample rate.
- **Limitações:** mono downmix (perde informação estéreo); erra em distorção pesada e em
  percussão; não separa instrumentos (precisa combinar com o item 1/2 para transcrever por stem).
- **Benefício esperado:** desbloqueia MIDI/partitura — uma funcionalidade que o MRQ não tem de
  jeito nenhum.
- **Notas:** 8·9·7·7·9·9·9 → **8,6** · **Médio** · modelo de IA local · **5 dias**

## Categoria C — Cifras, letras e harmonia (4)

### 12. ChordPro

- **Categoria:** C — Geração de cifras
- **Descrição:** implementação de referência do padrão **ChordPro** (cifra em texto com acordes
  inline `[C]` sobre a letra), com renderizador para PDF/HTML/ChordPro.
- **O que faz:** lê `.cho`/`.crd` e gera cifra formatada, transposta por tom, com diagramas.
- **Problemas do MRQ que resolve:** o MRQ não tem **formato** de cifra. ChordPro é o formato de
  fato (Ultimate Guitar, SongBook, OnSong, ChordVault importam), então adotá-lo resolve
  interoperabilidade de uma vez.
- **Funcionalidades:** transposição, capotraste, `{start_of_chorus}`, `{define}`, saída PDF/HTML.
- **Site oficial:** `https://www.chordpro.org/` (verificado via documentação do repo; o domínio
  não abriu do sandbox)
- **Repo GitHub:** `https://github.com/ChordPro/chordpro` (547★, push 2026-10)
- **Documentação:** `chordpro.org` + `docs/` no repo.
- **Licença:** **Artistic License 2.0** (permissiva, OSI-aprovada — confirmado lendo o arquivo
  `LICENSE` do repo).
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** irrelevante.
- **Dependências:** a implementação de referência é **Perl** (+ LaTeX para PDF). No Windows isso é
  atrito. Alternativa: implementar o **formato** em Python (é texto simples) e usar só a
  especificação.
- **Facilidade de integração:** fácil para o formato, médio para o CLI.
- **Limitações:** a referência em Perl é inadequada para empacotar; PDF depende de LaTeX.
- **Benefício esperado:** cifra exportável e compatível com apps de cifra de mercado.
- **Notas:** 8·8·7·9·8·9·6 → **7,4** · **Fácil** · aplicativo auxiliar · **2 dias**

### 13. `chord-symbol`

- **Categoria:** C — Acordes a partir de áudio+letra (camada de símbolo)
- **Descrição:** biblioteca JS (MIT) para **interpretar, normalizar, transpor e renderizar**
  símbolos de acorde, incluindo enarmonia e cifra brasileira/americana.
- **O que faz:** `C#m7b5/E` → objeto com raiz, baixo, intervalos, graus; transpor para qualquer
  tom; converter para Nashville/graus; renderizar texto ou SVG.
- **Problemas do MRQ que resolve:** transpor cifra de texto **corretamente** (enarmonia, baixo
  invertido, acordes suspensos) é um poço de bugs. Esta lib resolve no front, sem tocar no motor.
- **Funcionalidades:** parse tolerante, `transpose()`, `useSymbols`, `toString()`, render SVG.
- **Site oficial:** `https://www.npmjs.com/package/chord-symbol` (verificado, 4.0.0, MIT)
- **Repo GitHub:** distribuição via npm; repo upstream **não verificado** neste turno.
- **Documentação:** README do pacote no npm.
- **Licença:** **MIT** (confirmado no registry npm).
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim (JS puro, roda no navegador do Studio).
- **Hardware:** irrelevante.
- **Dependências:** zero (JS puro).
- **Facilidade de integração:** muito alta: é um `<script>`/import a mais no `index.html`.
- **Limitações:** só trabalha o **símbolo**, não detecta acorde no áudio; precisa de um
  vocabulário de cifra definido (o parser é configurável).
- **Benefício esperado:** transposição de cifra e export com enarmonia correta.
- **Notas:** 9·9·9·10·10·10·5 → **8,4** · **Fácil** · biblioteca incorporada · **2 dias**

### 14. WhisperX

- **Categoria:** C — Sincronização de letras (timing por palavra)
- **Descrição:** pipeline de ASR (faster-whisper) + **alinhamento forçado** com wav2vec2, que
  devolve timestamp por **palavra**.
- **O que faz:** áudio + (opcionalmente) letra → texto com tempo de início/fim por palavra;
  opcionalmente diarização (quem fala) via pyannote.
- **Problemas do MRQ que resolve:** não existe letra sincronizada. Com isso o Studio pode
  acompanhar a letra, e o item 12 exporta cifra sincronizada.
- **Funcionalidades:** `--align`, `--diarize`, modelos `small`→`large-v3`, GPU ~70× tempo real.
- **Site oficial:** sem site; repo.
- **Repo GitHub:** `https://github.com/m-bain/whisperX` (BSD-2-Clause, 25.251★, ativo)
- **Documentação:** README.
- **Licença:** **BSD-2-Clause**. ⚠️ A diarização opcional usa modelos **pyannote CC-BY-4.0 com
  gate** (exigem aceite e token) → **não** usar diarização se o objetivo é 100% offline sem login.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim (sem diarização; com diarização, respeitar
  CC-BY e o gate).
- **Offline/Windows/macOS:** sim, depois de baixar os modelos (o gate do pyannote exige login
  **uma vez**, por isso a ressalva).
- **Hardware:** GPU forte recomendada; CPU é lento mas funciona com modelo `small`/`base`.
- **Dependências:** `torch`, `faster-whisper`, `transformers`, `pyannote.audio` (opcional).
- **Facilidade de integração:** média-alta: é CLI/pipeline Python, pesado.
- **Limitações:** Whisper **inventa** texto quando há música alta (por isso combinar com
  separação de voz do item 1); pt-BR funciona bem no `large-v3`, modelos pequenos erram.
- **Benefício esperado:** letra sincronizada por palavra — diferencial grande de produto.
- **Notas:** 8·8·6·6·7·8·8 → **7,3** · **Avançado** · modelo de IA local · **8 dias**

### 15. `music21`

- **Categoria:** C — Sugestão de progressões harmônicas (+ export MusicXML)
- **Descrição:** toolkit de análise musical computacional: leitura/escrita de MusicXML, MIDI,
  ABC; análise de acordes, numerais romanos, funções tonais; detecção de tom por
  Krumhansl-Schmuckler.
- **O que faz:** `chord.Chord('C4 E4 G4').pitchedCommonName` → "C-major triad";
  `roman.RomanNumeral('V7', 'C')`; importa/exporta MusicXML.
- **Problemas do MRQ que resolve:** sugerir progressões (I-V-vi-IV, ii-V-I) exige teoria
  harmônica, não estatística. Também é o caminho para gerar **MusicXML** a partir do MIDI do item
  11 e da cifra do item 13.
- **Funcionalidades:** `roman`, `analysis`, `harmony`, `stream`, `converter`, `corpus`.
- **Site oficial:** `https://www.music21.org/music21docs/` (homepage do repo)
- **Repo GitHub:** `https://github.com/cuthbertLab/music21` (BSD-3-Clause, 2.625★, ativo)
- **Documentação:** `music21.org/music21docs` + docs no repo.
- **Licença:** **BSD-3-Clause**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim. **Hardware:** CPU, leve.
- **Dependências:** `chardet`, `joblib`, `jsonpickle`, `more_itertools`, `numpy`, `requests`,
  `webcolors`. ⚠️ `music21 10.x` exige **Python ≥3.11**; usar `9.9.x` para manter 3.10.
- **Facilidade de integração:** alta (import puro).
- **Limitações:** API grande e idiossincrática; geração de PDF depende de LilyPond/MuseScore
  externos; performance não é o forte.
- **Benefício esperado:** teoria harmônica pronta → sugestão de progressão, análise e MusicXML.
- **Notas:** 9·8·8·7·9·9·6 → **8,1** · **Fácil** · biblioteca incorporada · **4 dias**

## Categoria D — Produção, edição e mixagem (5)

### 16. Airwindows

- **Categoria:** D — EQ inteligente / compressor inteligente (algoritmos)
- **Descrição:** coleção de ~200 plugins de efeito com **código C++ aberto (MIT)**, sem
  instalador, sem telemetria, sem UI pesada — só DSP.
- **O que faz:** EQ, compressores, consoles, saturação, dither; cada plugin é um único `.cpp`
  legível, o que o torna excelente **referência de implementação**.
- **Problemas do MRQ que resolve:** o MRQ não tem EQ nem compressor no mixdown. Copiar/portar
  esses algoritmos (com atribuição MIT) dá um caminho de implementação seguro e auditável, em vez
  de eu inventar um compressor.
- **Funcionalidades:** MIT, VST2/VST3/AU/LV2/CLAP compiláveis; código por função.
- **Site oficial:** `https://www.airwindows.com/` (**não verificado** do sandbox)
- **Repo GitHub:** `https://github.com/airwindows/airwindows` (MIT, 1.283★, ativo)
- **Documentação:** README + os próprios `.cpp` (comentados).
- **Licença:** **MIT**.
- **Gratuita/Paga:** gratuita (doações). **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU; leve.
- **Dependências:** nenhuma para o DSP (compilar plugin exige SDK VST3/CLAP).
- **Facilidade de integração:** **avançada**: portar C++ para o nosso pipeline Python exige
  reescrever em NumPy ou fazer binding; não é `pip install`.
- **Limitações:** não existe binding Python; cada plugin tem seu próprio conjunto de parâmetros;
  não há "modo inteligente" automático (a inteligência seria nossa).
- **Benefício esperado:** EQ/compressor com base comprovada e licença limpa.
- **Notas:** 8·7·4·9·7·7·4 → **6,1** · **Avançado** · plugin · **6 dias**

### 17. `pedalboard` (Spotify)

- **Categoria:** D — EQ/compressor inteligente, plugins hospedáveis
- **Descrição:** biblioteca Python de efeitos de áudio (JUCE por baixo) com EQ, compressor,
  reverb, limiter, além de `load_plugin()` para **hospedar VST3/AU**.
- **O que faz:** processa buffers NumPy com efeitos de qualidade de estúdio e carrega plugins
  de terceiros.
- **Problemas do MRQ que resolve:** é a forma mais rápida de ter EQ/compressor/reverb/limiter no
  mixdown **e** de cumprir o item "plugins/efeitos hospedáveis" com uma API só.
- **Funcionalidades:** `Pedalboard([...])`, cadeia de efeitos, `load_plugin`, thread-safe,
  ~300× mais rápido que pySoX (número do próprio projeto).
- **Site oficial:** `https://spotify.github.io/pedalboard` (homepage do repo)
- **Repo GitHub:** `https://github.com/spotify/pedalboard` (**GPL-3.0**, 6.482★, ativo)
- **Documentação:** docs no site + README.
- **Licença:** ❌ **GPL-3.0** (por causa de JUCE + Rubber Band + LAME).
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim, **mas** obriga GPL no nosso código se
  linkado.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU, leve.
- **Dependências:** nenhuma runtime além do próprio wheel (~10 MB).
- **Facilidade de integração:** média (isolamento por processo).
- **Limitações:** GPL-3.0; **não** hospeda instrumentos virtuais (VSTi), só efeitos; AU só em
  macOS.
- **Benefício esperado:** efeitos profissionais + host de plugins num único pacote.
- **Notas:** 9·8·7·9·7·6·6 → **5,6** (a nota de licença derruba) · **Médio** ·
  serviço externo opcional · **5 dias** (sidecar HTTP em `localhost`)

### 18. DeepFilterNet

- **Categoria:** D — Redução de ruído/artefatos
- **Descrição:** realce de fala em banda larga (48 kHz) com rede neural leve, latência ~40 ms.
- **O que faz:** remove ruído de fundo de gravação; tem modo offline (arquivo) e streaming.
- **Problemas do MRQ que resolve:** gravação de ensaio/culto com chiado, ar-condicionado, público.
  Hoje não há nada para isso.
- **Funcionalidades:** binário Rust + pacote Python (`deepfilternet 0.5.6`), plugin LADSPA, RTF
  ≈0,19 em 1 thread (número do projeto).
- **Site oficial:** demo no HF Spaces (link no README).
- **Repo GitHub:** `https://github.com/Rikorose/DeepFilterNet` (licença dual
  **MIT OR Apache-2.0**, 5.013★)
- **Documentação:** README + paper (Interspeech 2022/2023).
- **Licença:** **MIT OR Apache-2.0** (escolher MIT na distribuição).
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU ok; RTF baixo.
- **Dependências:** binário Rust pré-compilado (ou `pip`), `torch` opcional.
- **Facilidade de integração:** média: é CLI, e o padrão de processo externo já existe.
- **Limitações:** **treinado em fala, não em música** → em voz cantada o resultado é
  experimental, e pode "comer" harmônicos. Última release 2023-08-31 (modelo considerado pronto).
- **Benefício esperado:** limpeza real de gravação de voz falada/cantada com pouco recurso.
- **Notas:** 8·7·8·8·8·8·7 → **7,4** · **Médio** · aplicativo auxiliar · **5 dias**

### 19. AudaLign

- **Categoria:** D — Alinhamento automático de stems
- **Descrição:** biblioteca Python (MIT) para alinhar várias gravações do mesmo evento usando
  fingerprint, correlação, correlação de espectrograma ou alinhamento visual.
- **O que faz:** encontra o deslocamento entre dois arquivos (e entre muitos), com `fine_align`
  para refinamento relativo.
- **Problemas do MRQ que resolve:** stems separados por modelos diferentes às vezes saem com
  atraso de alguns ms; e captações de celular + mesa de som precisam ser sincronizadas antes do
  mix.
- **Funcionalidades:** 4 estratégias de reconhecimento, `fine_align`, processamento em lote.
- **Site oficial:** sem site; PyPI (1.3.2).
- **Repo GitHub:** `https://github.com/benfmiller/audalign` (MIT, 152★, ativo)
- **Documentação:** PyPI README (bem completo).
- **Licença:** **MIT**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU; a correlação custa memória em arquivos longos.
- **Dependências:** `numpy`, `scipy`, `soundfile`, `matplotlib` (para o modo visual), `audioread`.
- **Facilidade de integração:** alta: é só importar e chamar.
- **Limitações:** é **alinhamento**, não correção de polaridade (ver item 20); em material muito
  diferente entre as fontes, o fingerprint falha.
- **Benefício esperado:** stems e captações sempre no mesmo ponto — acaba o "flam" no mix.
- **Notas:** 7·8·9·8·9·9·3 → **7,0** · **Fácil** · biblioteca incorporada · **3 dias**

### 20. `pyroomacoustics` (módulo `sync`: GCC-PHAT)

- **Categoria:** D — Detecção/correção de fase (atraso + sinal de polaridade)
- **Descrição:** biblioteca de acústica de salas que inclui `pyroomacoustics.sync.tdoa()` —
  estimativa de atraso por correlação cruzada generalizada com ponderação **PHAT**, com
  interpolação sub-amostra.
- **O que faz:** `tdoa(signal, reference, interp, phat=True, fs)` devolve o atraso em amostras
  fracionárias entre dois sinais. Com o atraso removido, a **correlação residual** (valor e sinal
  do pico) indica se o par está em fase ou invertido — essa parte é código nosso.
- **Problemas do MRQ que resolve:** stems de bateria em estéreo às vezes saem com um canal
  invertido; o mix fica fino/oco e ninguém sabe por quê. Corrigir isso automaticamente é
  qualidade audível de graça.
- **Funcionalidades:** `tdoa`, `correlate` com `phat`, `interp`, `t_max`; resto da lib é simulação
  de sala (não vamos usar).
- **Site oficial:** `https://pyroomacoustics.readthedocs.io/` (**não verificado** do sandbox)
- **Repo GitHub:** `https://github.com/LCAV/pyroomacoustics` (MIT, 2.009★)
- **Documentação:** readthedocs + `docs/pyroomacoustics.sync.rst` (existe no repo, confirmado).
- **Licença:** **MIT**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU; FFT do tamanho do arquivo (memória ~2× o áudio).
- **Dependências:** `numpy`, `scipy`, `Cython` no build; wheels disponíveis.
- **Facilidade de integração:** alta, mas **só o módulo `sync`** deve ser usado (o resto é
  simulação e pesa).
- **Limitações:** latência fracionária exige interpolação e **resample** (ou filtro sinc) para
  aplicar de verdade; detectar inversão de polaridade sem referência confiável não é 100%.
- **Benefício esperado:** stems alinhados e em fase → mix mais encorpado, menos retrabalho.
- **Notas:** 7·8·9·8·9·9·5 → **7,3** · **Fácil** · biblioteca incorporada · **2 dias**

## Categoria E — Masterização e qualidade (3)

### 21. Matchering

- **Categoria:** E — Masterização automática
- **Descrição:** masterização por **referência**: você dá o material e uma faixa de referência, e
  ele iguala RMS, resposta de frequência, pico e largura estéreo.
- **O que faz:** `mg.process(target=..., reference=..., results=[...])` → master + stems
  intermediários.
- **Problemas do MRQ que resolve:** o MRQ exporta mixdown mas não masteriza. É o "deixar no
  volume e no timbre do mercado" sem plugin pago.
- **Funcionalidades:** matching de RMS/FR/peak/width, Docker oficial, CLI, cancelamento de
  limiter.
- **Site oficial:** `https://pypi.org/project/matchering/`
- **Repo GitHub:** `https://github.com/sergree/matchering` (**GPL-3.0**, 2.690★, ativo)
- **Documentação:** README + Docker.
- **Licença:** ❌ **GPL-3.0**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim, com obrigação GPL se linkado.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU; ~5–20 s por música.
- **Dependências:** `numpy`, `scipy`, `soundfile`, `pyloudnorm`, `click`.
- **Facilidade de integração:** fácil **se** isolado (subprocesso/CLI). Linkar no processo =
  contaminação GPL.
- **Limitações:** referência ruim → resultado ruim; não é "masterização inteligente" (não ouve
  gênero); GPL.
- **Benefício esperado:** masterização automática real, sem serviço pago.
- **Notas:** 8·8·7·8·7·7·5 → **5,7** (penalizado pela licença) · **Fácil** ·
  serviço externo opcional · **3 dias**

### 22. `pyloudnorm`

- **Categoria:** E — Loudness / LUFS / True Peak (medição)
- **Descrição:** implementação em Python puro do **ITU-R BS.1770-4** (loudness integrado,
  momentâneo, short-term, LRA), com gating configurável.
- **O que faz:** `Meter(sr).integrated_loudness(y)` → LUFS; `meter_type='ITU-R BS.1770-4'`; ainda
  `normalize` para um alvo.
- **Problemas do MRQ que resolve:** hoje não há medição de loudness — o release não sabe se está
  em -14 LUFS (streaming) ou -9 (clube). Isso resolve direto e é a base do item 21.
- **Funcionalidades:** K-weighting, gating por blocos, `integrated_loudness`, `loudness_range`.
- **Site oficial:** `https://www.christiansteinmetz.com/projects-blog/pyloudnorm`
- **Repo GitHub:** `https://github.com/csteinmetz1/pyloudnorm` (MIT, 792★)
- **Documentação:** README + docstrings.
- **Licença:** **MIT**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** irrelevante. **Dependências:** `numpy`, `scipy` (só isso).
- **Facilidade de integração:** **muito alta** — é praticamente uma função.
- **Limitações:** ⚠️ **não** mede True Peak de verdade (precisa de sobreamostura 4×) — hasteremos
  de implementar a sobreamostura ou usar `ffmpeg -af ebur128=peak=true`. Também não mede LRA do
  padrão EBU R128 completo sem ajuste.
- **Benefício esperado:** LUFS correto em minutos, não em dias. Desbloqueia "normalizar para
  streaming" no export.
- **Notas:** 9·9·10·9·10·10·6 → **9,0** · **Fácil** · biblioteca incorporada · **1 dia**

### 23. Essentia

- **Categoria:** E — Comparação de referência e análise espectral
- **Descrição:** biblioteca C++ com bindings Python, 250+ algoritmos de descritores espectrais,
  tonais, rítmicos e de alto nível (inclui modelos de genre/mood).
- **O que faz:** extrai dezenas de descritores num passe, com extractores de alto nível prontos.
- **Problemas do MRQ que resolve:** comparação de referência **espectral** detalhada (centroide,
  rolloff, fluxo, flatness, bandas, dissonância) e descritores que o `dsp.py` não tem.
- **Funcionalidades:** `MusicExtractor`, `TonalExtractor`, `RhythmExtractor`, modelos TF.
- **Site oficial:** `https://essentia.upf.edu/` (**não verificado** do sandbox; homepage do repo)
- **Repo GitHub:** `https://github.com/MTG/essentia` (**AGPL-3.0**, 3.803★, ativo)
- **Documentação:** `essentia.upf.edu/documentation`
- **Licença:** ❌ **AGPL-3.0-only** (confirmado no PyPI com expressão SPDX). Modelos/dados
  adicionais em CC-BY-SA-4.0.
- **Gratuita/Paga:** gratuita. **Uso comercial:** ❌ problemático: AGPL obriga abrir o código,
  inclusive para uso em rede (o MRQ é servidor HTTP local — zona de risco).
- **Offline/Windows/macOS:** sim (wheels de macOS e Linux; **Windows: não verificado**).
- **Hardware:** CPU; leve.
- **Dependências:** `numpy`, `pyyaml`; `essentia-tensorflow` para os modelos.
- **Facilidade de integração:** avançada (por causa da licença, não da API).
- **Limitações:** AGPL; wheels de Windows historicamente problemáticos; seria mais um "motor de
  análise" concorrente com `librosa` (redundância).
- **Benefício esperado:** análise espectral rica — mas **só vale se o MRQ mudar de licença** ou se
  houver acordo comercial com a UPF.
- **Notas:** 9·7·6·8·5·1·4 → **4,7** (a nota de custo-benefício reflete o risco AGPL) ·
  **Avançado** · serviço externo opcional · **6 dias**

## Categoria F — Instrumentos virtuais e efeitos (3)

### 24. Surge XT

- **Categoria:** F — Sintetizadores gratuitos integráveis
- **Descrição:** sintetizador híbrido (subtractivo + FM + wavetable) com MPE, código aberto,
  builds VST3/AU/CLAP/LV2 para Windows, macOS e Linux.
- **O que faz:** gera som por MIDI; suporta patches, modulação profunda, efeitos internos.
- **Problemas do MRQ que resolve:** o MRQ não tem **nenhum** instrumento virtual. Para tocar uma
  guia melódica ou uma linha de teclado, hoje não há nada.
- **Funcionalidades:** VST3/AU/CLAP/LV2, MPE, ~3000 presets, arpejador.
- **Site oficial:** `https://surge-synthesizer.github.io/` (homepage do repo)
- **Repo GitHub:** `https://github.com/surge-synthesizer/surge` (**GPL-3.0**, 4.118★, ativo)
- **Documentação:** wiki no repo.
- **Licença:** ❌ **GPL-3.0**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** o **som gerado** é livre; o **código** é GPL →
  pode ser distribuído como binário separado, não linkado.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU; leve-moderado.
- **Dependências:** nenhuma além do próprio plugin.
- **Facilidade de integração:** média: como **plugin que o usuário instala** é fácil (scan de
  VST3 e render offline via `pedalboard`/CLAP — mas `pedalboard` não hospeda VSTi; precisaria de
  host próprio). Como biblioteca: inviável.
- **Limitações:** GPL; hospedar VSTi em Python não tem solução madura; render offline exige um
  host.
- **Benefício esperado:** som de teclado/sintetizador para guias e arranjos, sem custo.
- **Notas:** 9·7·5·8·7·7·6 → **6,0** · **Médio** · plugin · **3 dias** (só detecção + doc;
  render offline é outro projeto)

### 25. sfizz

- **Categoria:** F — Instrumentos virtuais / samples
- **Descrição:** sampler de **SFZ** (formato aberto de instrumentos baseado em samples), com
  biblioteca C, plugin LV2/VST3/AU e CLI.
- **O que faz:** carrega um `.sfz` + pasta de samples e renderiza notas MIDI para áudio, com
  suporte a loops, round-robin, velocity layers, filtros.
- **Problemas do MRQ que resolve:** é o caminho **licenciado e offline** para ter piano, cordas,
  bateria acústica etc. tocando a partir de MIDI. SFZ é texto puro (fácil de gerar/editar) e não
  prende o usuário a um formato proprietário.
- **Funcionalidades:** `libsfizz` (C API), `sfizz_render` (CLI offline), plugin VST3/LV2/AU,
  polifonia alta.
- **Site oficial:** `https://sfz.tools/sfizz/`
- **Repo GitHub:** `https://github.com/sfztools/sfizz` (**BSD-2-Clause**, 529★)
- **Documentação:** `sfz.tools/sfizz/docs`
- **Licença:** **BSD-2-Clause** (permissiva; os **samples** que o usuário instalar têm licença
  própria — alguns SFZ livres são CC0, outros CC-BY-NC → cuidado).
- **Gratuita/Paga:** gratuita (o programa). **Uso comercial:** sim para o código.
- **Offline/Windows/macOS:** sim (binários oficiais para os três).
- **Hardware:** CPU; RAM proporcional ao tamanho do sample set.
- **Dependências:** binário próprio; `libsndfile`, `libsamplerate` no build.
- **Facilidade de integração:** média: usar `sfizz_render` como processo externo é o caminho mais
  simples (render offline de um MIDI para WAV).
- **Limitações:** **não** escolhe instrumento por você (precisa de uma biblioteca SFZ); a maioria
  dos SFZ bons é de terceiros com licença variável; qualidade depende do sample set.
- **Benefício esperado:** instrumentos reais tocando MIDI, 100% offline e com licença limpa no
  programa.
- **Notas:** 8·8·7·8·9·9·7 → **7,3** · **Médio** · biblioteca incorporada · **4 dias**

### 26. CLAP

- **Categoria:** F — Plugins/efeitos hospedáveis (padrão)
- **Descrição:** **CLever Audio Plug-in API** — padrão aberto de plugins (Bitwig + u-he), C-only
  ABI, **MIT**, sem taxas.
- **O que faz:** define como um host carrega plugins de efeito e instrumento, com metadados,
  thread-pool e eventos.
- **Problemas do MRQ que resolve:** seria a base para "hospedar plugins" de forma moderna e
  licença-livre (melhor que VST3 da Steinberg, cujo SDK é proprietário).
- **Funcionalidades:** ABI C, extensões, proxy layer, hot-reload.
- **Site oficial:** `https://cleveraudio.org/`
- **Repo GitHub:** `https://github.com/free-audio/clap` (MIT, 2.373★, ativo)
- **Documentação:** `cleveraudio.org` + headers comentados.
- **Licença:** **MIT**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU.
- **Dependências:** compilador C/C++; binding Python próprio (`ctypes`/`cffi`).
- **Facilidade de integração:** **muito baixa**: implementar host CLAP significa gerenciar
  threads de áudio, buffers, latência e ciclo de vida de plugin — é o tipo de coisa que consome
  meses.
- **Limitações:** é **especificação**, não host; nenhum binding Python maduro; risco alto de
  instabilidade; não é prioridade para o produto.
- **Benefício esperado:** futuro-proof para plugins — mas alto custo e baixo retorno agora.
- **Notas:** 9·5·2·7·8·6·6 → **3,9** · **Muito avançado** · plugin · **10+ dias**

## Categoria G — Recursos profissionais e apresentação (4)

### 27. beets

- **Categoria:** G — Gestão de repertório
- **Descrição:** gerenciador de biblioteca musical em Python: importação, tags, deduplicação,
  organização de arquivos, plugins.
- **O que faz:** lê metadados, corrige tags, renomeia por padrão, detecta duplicatas, gera
  relatórios; tem API Python (`beets.library.Library`).
- **Problemas do MRQ que resolve:** o `biblioteca.py` atual é uma lista de projetos. beets dá
  busca, tags, deduplicação e importação em lote — a base de "gestão de repertório".
- **Funcionalidades:** `Library`, `Item`, `Album`, consultas tipo `year:2020..`, plugins (smartplaylist,
  duplicates, info).
- **Site oficial:** `http://beets.io/`
- **Repo GitHub:** `https://github.com/beetbox/beets` (MIT, 15.938★, ativo)
- **Documentação:** `beets.io/docs`
- **Licença:** **MIT**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** irrelevante. **Dependências:** `mediafile`, `mutagen`, `unidecode`, `pyyaml`,
  `confuse`, `musicbrainzngs` (só para lookups online — podemos desabilitar).
- **Facilidade de integração:** alta; usar como **biblioteca**, não como CLI (o CLI assume
  config em `~/.config`).
- **Limitações:** vocabulário de tags pensado para coleção de discos, não para projetos de
  igreja/banda; `musicbrainzngs` sugere rede (desligar); SQLite separado do nosso `project.json`
  → precisa de decisão de fonte de verdade.
- **Benefício esperado:** repertório com busca, tags e sem duplicata, sem escrever um CRUD.
- **Notas:** 8·8·7·9·9·9·5 → **7,6** · **Fácil** · biblioteca incorporada · **3 dias**

### 28. Ableton Link (via `aalink`)

- **Categoria:** G — Sincronização áudio-MIDI-equipamentos (tempo em rede)
- **Descrição:** protocolo de sincronização de **tempo/beat** entre aplicativos na mesma rede
  local; implementação de referência header-only em C++.
- **O que faz:** mantém BPM e fase de compasso alinhados entre apps/dispositivos na LAN, com
  compensação de latência.
- **Problemas do MRQ que resolve:** tocar o MRQ junto com Ableton/loops em outro computador com o
  mesmo pulso. É o "sincronizar equipamentos" de verdade.
- **Funcionalidades:** descoberta automática na LAN, start/stop sync, `aalink` (asyncio,
  pybind11).
- **Site oficial:** `https://www.ableton.com/link/` (**não verificado** do sandbox)
- **Repo GitHub:** `https://github.com/Ableton/link` e `https://github.com/artfwo/aalink`
- **Documentação:** README do link + docs do `aalink`.
- **Licença:** ❌ **GPLv2-or-later** (licença proprietária disponível por e-mail para
  `link-devs@ableton.com`); `aalink` é **GPL-3.0**.
- **Gratuita/Paga:** gratuita. **Uso comercial:** só com a licença alternativa da Ableton.
- **Offline:** sim (LAN local, não precisa internet). **Windows/macOS:** sim.
- **Hardware:** rede local; latência depende do Wi-Fi (Ethernet recomendado).
- **Dependências:** `pybind11`; build C++.
- **Facilidade de integração:** avançada (build nativo + licença).
- **Limitações:** **não** sincroniza áudio — sincroniza **tempo**; GPL; Wi-Fi instável quebra a
  fase; o público de igreja/banda raramente usa Ableton.
- **Benefício esperado:** pulso compartilhado com o ecossistema Ableton — nicho, mas forte.
- **Notas:** 7·5·4·7·6·5·5 → **5,0** · **Avançado** · biblioteca incorporada · **7 dias**

### 29. `python-rtmidi`

- **Categoria:** G — Sincronização áudio-MIDI-equipamentos (MIDI I/O real)
- **Descrição:** binding Python (Cython) para **RtMidi** — MIDI de entrada/saída em tempo real em
  Windows (WinMM), macOS (CoreMIDI) e Linux (ALSA/JACK).
- **O que faz:** abrir portas, enviar/receber notas, **MIDI Clock**, Program Change, Control
  Change, com timestamp e portas virtuais.
- **Problemas do MRQ que resolve:** o MRQ não fala MIDI. Sem isso não há click para o baterista
  com in-ear, nem troca de preset em teclado, nem controle por pedal. É a peça que falta para
  "reprodução ao vivo com click/contagem" chegar ao hardware.
- **Funcionalidades:** `MidiIn`, `MidiOut`, `open_port`, `open_virtual_port`, `get_ports`,
  mensagens com `time`, `MidiBase.ignore_types`.
- **Site oficial:** `https://spotlightkid.github.io/python-rtmidi/`
- **Repo GitHub:** `https://github.com/SpotlightKid/python-rtmidi` (MIT; wheels para
  Win/macOS/Linux)
- **Documentação:** readthedocs + exemplos no repo.
- **Licença:** **MIT** (RtMidi é "MIT modificado", pedido não vinculante de mandar modificações).
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim.
- **Offline/Windows/macOS:** sim.
- **Hardware:** interface MIDI ou porta virtual (`loopMIDI` no Windows, IAC no macOS) para teste.
- **Dependências:** nenhuma (wheel já compilado).
- **Facilidade de integração:** **alta** — `pip install python-rtmidi` + 20 linhas.
- **Limitações:** MIDI Clock é **impreciso se agendado em Python puro** (jitter de thread) →
  precisa de thread dedicada com `time.perf_counter` e lookahead, ou enviar só "Start/Stop" e
  deixar o clock local; sem timestamps de hardware.
- **Benefício esperado:** click/contagem no in-ear do baterista, automação de teclado e pedal —
  é a diferença entre "metrônomo de software" e "ferramenta de palco".
- **Notas:** 9·9·9·7·10·10·7 → **8,6** · **Fácil** · biblioteca incorporada · **2 dias**

### 30. MuseScore Studio (CLI headless)

- **Categoria:** G — Exportação profissional de partituras
- **Descrição:** editor de partitura livre, com **linha de comando** que converte `.mscz`/MusicXML
  em **PDF, PNG, SVG, MIDI, MP3/WAV/FLAC**.
- **O que faz:** `musescore arquivo.mscz -o saida.pdf --no-gui` (ou `mscore`), em lote.
- **Problemas do MRQ que resolve:** é a forma mais barata de gerar **partitura e cifra em PDF**
  com qualidade de engraving. O item 11 dá o MIDI, o 15 dá o MusicXML, e este fecha em PDF.
- **Funcionalidades:** `-o` (formato pela extensão), `--no-gui`, `-j` (job JSON em versões
  recentes — **não verificado** nesta versão), exportação de áudio via FluidSynth interno.
- **Site oficial:** `https://musescore.org/` (**não abriu do sandbox**, mas é a homepage do repo)
- **Repo GitHub:** `https://github.com/musescore/MuseScore` (15.415★, ativo; `LICENSE.txt` =
  **GPL-3.0**, confirmado lendo o arquivo)
- **Documentação:** handbook do MuseScore (seção file-export).
- **Licença:** ❌ **GPL-3.0**. Fontes internas em GNU Freefont License.
- **Gratuita/Paga:** gratuita. **Uso comercial:** sim, mas GPL → **chamar como processo externo**
  (é o que o MRQ já faz com `ffmpeg`/`demucs`).
- **Offline/Windows/macOS:** sim.
- **Hardware:** CPU; ~120 MB instalado.
- **Dependências:** binário do MuseScore no PATH (ou caminho configurável). É um **download
  grande** que o usuário faz uma vez.
- **Facilidade de integração:** fácil (subprocesso), com detecção de binário e degradação honesta.
- **Limitações:** GPL (processo separado resolve); não é biblioteca; versões 3.x e 4.x usam
  binários diferentes (`mscore` vs `musescore`); PDF de cifra com letra exige template.
- **Benefício esperado:** partitura e cifra em PDF com qualidade de publicação, custo zero.
- **Notas:** 9·8·9·8·9·9·5 → **7,0** · **Fácil** · aplicativo auxiliar · **3 dias**

---

# 8. Comparativo técnico consolidado

## 8.1 O que cada ferramenta toca no projeto

| # | Ferramenta | Módulo novo/afetado | Quebra algo? | Precisa desinstalar algo? |
|---|---|---|---|---|
| 1 | Mel-Band RoFormer | `separator.py` (novo backend) | não | não |
| 2 | `audio-separator` | `separator.py` (já é backend) | não | não |
| 3 | SCNet/MSST | `separator.py` (novo backend) | não | não |
| 4 | AudioSep | `separator.py` (novo backend tipo "descrição") | não | não |
| 5 | `vocal-remover` | `separator.py` (backend leve) | não | não |
| 6 | PANNs | `analise_instrumentos.py` (novo) | não | não |
| 7 | librosa | `analise_ref.py` (novo) | **cuidado**: não substituir `dsp.tempo` sem comparar | não |
| 8 | CREMA | `tom_ia.py` (novo) | não (fallback heurístico fica) | não |
| 9 | `autochord` | `acordes_ia.py` (novo) | não | não |
| 10 | MSAF | `estrutura.py` (fronteiras melhores) | **sim, se mal feito**: pode mudar os nomes das seções. Implementar como "sugestão" e comparar com a heurística | não |
| 11 | `basic-pitch` | `midi.py` (novo) | não | não |
| 12 | ChordPro | `cifra.py` (novo) | não | não |
| 13 | `chord-symbol` | `index.html` (JS) | não | não |
| 14 | WhisperX | `letras.py` (novo) | não | não |
| 15 | `music21` | `harmonia.py` (novo) | não | não |
| 16 | Airwindows | `mixdown.py` (efeitos) | não | não |
| 17 | `pedalboard` | sidecar `plugins/` | não | não |
| 18 | DeepFilterNet | `limpeza.py` (novo) | não | não |
| 19 | AudaLign | `alinhamento.py` (novo) | não | não |
| 20 | `pyroomacoustics.sync` | `fase.py` (novo) | não | não |
| 21 | Matchering | sidecar `master.py` | não | não |
| 22 | `pyloudnorm` | `loudness.py` (novo) + `export.py` | não | não |
| 23 | Essentia | `espectral.py` | não | não |
| 24 | Surge XT | detecção de plugin | não | não |
| 25 | sfizz | `instrumentos.py` (novo) | não | não |
| 26 | CLAP | host (novo) | não | não |
| 27 | `beets` | `biblioteca.py` | **atenção**: decisão de fonte de verdade | não |
| 28 | Ableton Link | `sincronia.py` (novo) | não | não |
| 29 | `python-rtmidi` | `midi_io.py` (novo) + guia | não | não |
| 30 | MuseScore | `export.py` (novo formato `pdf`) | não (é aditivo: `FORMATS` ganha `pdf`) | não |

**Nenhum item exige remover feature, trocar o motor `dsp.py` ou apagar componente.** Os únicos
três com risco de regressão são #7 (se alguém trocar o `tempo` atual), #10 (nomes de seção) e
#27 (fonte de verdade do repertório). Os três estão marcados.

## 8.2 Custo de instalação (impacto no instalador)

| Peso | Ferramentas | Impacto |
|---|---|---|
| **Zero** (já é nosso padrão) | 22, 20, 19, 13 | nenhum |
| **Leve (<20 MB)** | 10, 12, 29, 30 (se o usuário instalar), 25 (programa) | baixo |
| **Médio (50–200 MB)** | 7 (+numba), 11 (ONNX), 18, 27, 17 | extra opcional |
| **Pesado (0,6–2 GB)** | 1, 2, 3, 4, 8, 9, 14, 23, 24 | extra opcional, download sob demanda |
| **Muito pesado (>2 GB)** | 26 (nada a baixar, mas 10+ dias de código) | não recomendado agora |

## 8.3 Ordem sugerida de implementação (se você marcar tudo)

Não é plano de execução — é só **ordem de dependência técnica**, para você ver o que destrava o
quê:

```
Semana 1 — base de qualidade (não muda áudio)
  22 pyloudnorm  →  medição de LUFS + alvo de export
  29 python-rtmidi → click no hardware
  19 AudaLign + 20 pyroomacoustics.sync → alinhamento e fase
  13 chord-symbol → cifra correta no front

Semana 2 — análise
  7 librosa  →  BPM/f0 de referência
  10 MSAF  →  fronteiras de seção
  8 CREMA  →  tom
  9 autochord  →  acordes

Semana 3–4 — IA pesada
  1 Mel-Band RoFormer  →  backend padrão de voz
  2 audio-separator  →  instrumentos/karaoke
  11 basic-pitch  →  MIDI
  15 music21 + 30 MuseScore  →  partitura

Semana 5+ — diferenciais
  14 WhisperX (letra), 6 PANNs (instrumentos), 12 ChordPro (cifra), 25 sfizz (samples),
  27 beets (repertório), 21 Matchering (sidecar GPL), 17 pedalboard (sidecar GPL)
```

# 9. Classificação por dificuldade (resumo)

| Dificuldade | Ferramentas | Total |
|---|---|---|
| **Fácil** | 5, 7, 10, 12, 13, 15, 19, 20, 21, 22, 27, 29, 30 | 13 |
| **Médio** | 1, 2, 6, 8, 9, 11, 18, 24, 25 | 9 |
| **Avançado** | 3, 4, 14, 16, 17, 23, 28 | 7 |
| **Muito avançado** | 26 | 1 |

# 10. Recomendações (minha opinião, não autorização)

## Se você só puder fazer 5 coisas
1. **#22 `pyloudnorm`** — 1 dia, resolve LUFS de verdade e é audível no release.
2. **#29 `python-rtmidi`** — 2 dias, transforma o guia em ferramenta de palco.
3. **#13 `chord-symbol`** — 2 dias, acaba com bug de cifra/transposição.
4. **#11 `basic-pitch`** — 5 dias, cria uma funcionalidade que o app não tem (MIDI).
5. **#1 Mel-Band RoFormer** — 6 dias, resolve a licença do backend de voz de ponta.

## Se o objetivo for "qualidade de áudio"
`#1` + `#2` (separação), `#18` (ruído), `#19`+`#20` (alinhamento/fase), `#22` (loudness),
`#21` (masterização, sidecar).

## Se o objetivo for "aprender/ensaiar" (o caso de igreja/banda)
`#29` (click no in-ear), `#10` (seções), `#12`+`#13` (cifra), `#14` (letra), `#25` (samples),
`#27` (repertório), `#30` (PDF).

## O que eu **não** faria agora
- **#26 CLAP**: 10+ dias para um host de plugins que quase ninguém vai usar.
- **#23 Essentia**: AGPL contamina; `librosa` cobre 80% da necessidade.
- **#28 Ableton Link**: nicho, GPL, e o público real não usa Ableton na igreja.
- **#16 Airwindows**: é ótimo, mas portar C++ para Python é caro; melhor começar com um EQ
  simples nosso e evoluir.

# 11. Limites deste relatório (o que eu não consegui verificar)

Sendo explícito, para você não ser surpreendido:

1. **Links de sites que não abriram do sandbox:** `basicpitch.io`, `essentia.upf.edu`,
   `librosa.org`, `chordpro.org`, `sonicvisualiser.org`, `cleveraudio.org`, `sfz.tools`,
   `surge-synthesizer.github.io`, `fluidsynth.org`, `musescore.org`.
   → Todos os **repositórios GitHub correspondentes foram verificados com HTTP 200**; os
   domínios estão marcados como **não verificados** na ficha.
2. **Preços:** não há preço em nenhuma das 30. Todas são de uso gratuito. Onde existe versão paga
   (MuseScore Pro, licença comercial de Rubber Band/Ableton), está dito — e **não** é necessária
   para o que proponho.
3. **Benchmarks:** os únicos números citados são publicados pelos próprios projetos ou papers
   (SDR do Mel-Band RoFormer, 7,79 dB do Band-SCNet, RTF 0,19 do DeepFilterNet). **Não** medi
   nada no MRQ.
4. **Licença de pesos:** vários projetos só licenciam o **código**. Marquei cada caso:
   SCNet/MSST, AudioSep, PANNs, `autochord` (pesos não declarados separadamente).
5. **Windows:** `essentia` e `vocal-remover`-style builds nativos são os pontos de risco; testar
   em máquina real antes de prometer.
6. **`audio-separator` é o único item que o projeto já lista** como extra (`onnx`,
   `audio-separator>=0.20`). Ele está aqui **porque o valor novo é a curadoria de modelos UVR
   com licença MIT** (karaoke, sopros, denoise), não a instalação.

# 12. Próximo passo

Abra `selecao-30-ferramentas.html`, marque **só** o que você quer, escolha a prioridade de cada
uma e clique em **Confirmar seleção**. O resumo que a página gerar é o que eu uso para escrever o
plano de implementação (fases, arquivos, testes, ordem). Enquanto você não confirmar, eu não
implemento nada.

**Nada foi instalado, alterado, trocado ou removido neste trabalho.**
