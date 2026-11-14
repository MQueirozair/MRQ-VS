# MRQ Audio Studio — gerador de VS multitrack

O que este documento é: a descrição do que foi **implementado** (não proposto)
no projeto existente, com as decisões técnicas, as licenças conferidas, o que
foi testado e o que continua pendente. Tudo que aparece aqui existe no código
e tem teste; o que não foi feito está na seção "Pendências" — sem promessa.

Data desta versão: novembro de 2026 · versão **0.1.30** (o projeto multitrack
entrou na 0.1.29; a 0.1.30 corrige a ficha que o navegador baixava em vez de
abrir).

---

## 1. O fluxo, de ponta a ponta

```
fonte (URL, arquivo ou envio)
   │
   ├─ mídia ............ resolve_source  → WAV 44,1 kHz
   ├─ análise .......... BPM, tonalidade, seções, croma
   ├─ separação ........ demucs / audio-separator / openunmix / DSP de reserva
   ├─ grade ............ compasso (beat_this quando instalado, heurística de acento)
   ├─ cifra ............ acorde por compasso, com confiança
   ├─ clique + guia .... clique por tempo, guia falada, ENSAIO_LR
   ├─ exportação ....... stems + mix (+ MP3/MP4 quando há ffmpeg)
   └─ projeto .......... projeto.mrqvs.json, cifra.txt/.cho/.csv, MIDI, ficha
```

Cada etapa continua sendo chamada do mesmo jeito que antes: nada do pipeline
foi reescrito. O que mudou é o que acontece **depois** da separação — o
programa passou a gravar um projeto editável e uma cifra pronta para levar.

---

## 2. Módulos novos e do que cada um é responsável

| módulo | responsabilidade | por que separado |
|---|---|---|
| `mapa_tempo.py` | régua mestra: BPM e compasso variáveis, inverso exato tempo ↔ compasso | o `TempoInfo` responde "o BPM é 96"; música de verdade acelera e troca de fórmula |
| `cifra.py` | acorde por compasso com confiança, correção manual, transposição, TXT/ChordPro/CSV | a tela já desenhava acordes; faltava o que o músico leva embora |
| `midi.py` | SMF tipo 1: mapa de tempo, clique, cifra, marcadores | importar na DAW exige arquivo, não tela |
| `letra.py` | `.lrc`/`.srt`/texto, alinhamento por energia, transcrição com motor instalado | não se inventa letra; e alinhamento estimado precisa dizer que é estimado |
| `projeto_vs.py` | `projeto.mrqvs.json`: faixas, mixer não-destrutivo, marcadores, loop, render | `projeto.json` é saída da análise e pode ser refeito; edição do usuário não |
| `ficha.py` | cifra + letra + seções em HTML A4 autocontido | imprimir/salvar em PDF sem biblioteca de PDF |
| `cli.py` (`projeto`) | lista, mix, stems, exportar, transpor, corrigir, letra, marcar | mesmo módulo da tela, sem interface gráfica |

Nada disso toca os arquivos originais: render de mix e de stems sempre escreve
arquivo novo (`_MIX-vs.wav`, `<faixa>_edit.wav`), e a cifra/letra sempre vão
para a pasta `-apoio`.

---

## 3. Decisões técnicas (e o que foi descartado)

### 3.1 Mapa de tempo: medido, não presumido
O BPM é medido **a cada batida** da grade (`_bpm_por_batida`) e os vizinhos
dentro de 3% são fundidos (`andamentos`). Um compasso que cai na fronteira
entre dois andamentos mistura metade de cada um e inventa um BPM inexistente —
isso apareceu num teste com 90 → 120 BPM e foi corrigido medindo na batida.
Sem grade suficiente, o mapa devolve o BPM nominal marcado `estimado` e a ficha
imprime "régua extrapolada do BPM".

### 3.2 Compasso: cada compasso pertence a uma seção só
A primeira versão atribuía por sobreposição de janela e um compasso de
fronteira entrava em duas seções (duplicado na cifra). Agora a seção é a que
contém o **início** do compasso; compasso fora de qualquer seção vai para
"Trecho sem seção" em vez de sumir.

### 3.3 Cifra: confiança é dado
Acorde com confiança < 0,20 sai `C?` no TXT, `[C?]` no ChordPro e `incerto=sim`
no CSV. Sem acorde sai `N.C.`. A correção manual (`manual=true`) vence a
detecção e não é marcada como incerta. Transposição mexe na tônica e no baixo
(`D/F#` → `E/G#`), nunca no sufixo, e a grafia (bemol/sustenido) segue o tom
de destino.

Teste com o áudio sintético do `demo.py` (I–V–vi–IV em Dó): a detecção
devolveu **C, G, Am, F** — os quatro acordes certos, na ordem; transposta +2
virou **D, A, Bm, G**.

### 3.4 MIDI escrito à mão
`mido`/`pretty_midi` resolveriam em uma linha, mas trazem dependência para
tocar ~40 linhas de `struct`. O SMF 1.0 é estável desde 1991; o arquivo sai com
`MThd` + N `MTrk`, PPQ 480, `set_tempo` por trecho, `time_signature` por troca
de fórmula, acento de compasso composto (6/8, 7/8) e marcadores. O teste
`test_midi_lido_por_leitor_externo_se_disponivel` valida com `mido` quando ele
existe no ambiente.

### 3.5 Letra: três métodos, todos declarados
| situação | método | confiança |
|---|---|---|
| `.lrc`/`.srt` com tempo | `importada` | 1,00 (preservado, não "melhorado") |
| texto colado/importado | `energia` (energia da voz) | 0,85 com 1 linha/talhado; 0,45 aproximado |
| áudio sem letra | `motor` (faster-whisper / whisper / vosk) | a do motor |

Sem motor instalado a rota responde **501 + manual de instalação** — nunca
letra inventada. O alinhamento por energia usa o stem de vocais quando existe
(melhor que o mix para medir voz) e avisa quando o material parece
instrumental.

### 3.6 Mixer não-destrutivo
O `.mrqvs.json` é a fonte da verdade: volume, pan, mute, solo, offset, fades,
ordem e ocultar. O play do navegador passa por `tempoLocalDaFaixa` (offset por
faixa), o render do servidor usa a mesma regra de solo/mute. O arquivo de áudio
nunca é alterado; se um stem sumir do disco, o render **avisa** (`ausentes`) e
continua com o que existe.

### 3.7 Motores avaliados e por que não entraram
| motor | decisão | motivo |
|---|---|---|
| Demucs/htdemucs | já integrado, mantido | pesos "not covered by MIT… only for scientific purposes" (issue #327) — continua como está, o programa já avisa a origem |
| BS-RoFormer / Mel-Band RoFormer | **não integrado nesta rodada** | pesos de 913 MB sem licença declarada no checkpoint; integrar exige download separado e aceite explícito |
| Essentia | descartado | AGPL-3.0 |
| Rubber Band / Chordino / aubio / pedalboard / Matchering / Surge XT / MuseScore CLI / Ableton Link | descartados | GPL/AGPL — distribuir o binário junto criaria obrigação de relicenciar o programa |
| `beat-this` | já é extra opcional | MIT, melhora downbeat; sem ele a heurística de acento responde com confiança |
| librosa | não adicionado | ISC, mas o DSP do projeto (`dsp.py`) já cobre o que é usado; duplicaria biblioteca de áudio |
| music21 | não adicionado | BSD-3, mas 105 MB para o que o MIDI próprio já resolve |
| pyloudnorm | candidato (extra) | MIT, BS.1770-4; útil para normalização de loudness no render |

Resumo da regra: **nada de GPL/AGPL no núcleo**, nada de peso sem ganho
concreto, e toda decisão registrada aqui em vez de escondida no código.

---

## 4. Como usar

### 4.1 Interface (o caminho do músico)
```bash
mrq-vs serve            # abre a interface no navegador
```
1. cole o link ou envie o arquivo e gere os stems;
2. a timeline abre com todas as faixas, clique e guia;
3. **Exportar música** → Cifra (txt + ChordPro + CSV), Ficha para imprimir,
   MIDI, Stems editados, Mixagem;
4. **Letra** (barra de ferramentas) → colar, importar `.lrc`/`.srt` ou
   transcrever (se houver motor);
5. menu `⋯` de cada faixa → mute/solo/volume/pan, subir/descer, alinhar ±10 ms,
   fades;
6. **Salvar projeto** grava tudo em `projeto.mrqvs.json`; reabrir a música pela
   biblioteca traz o estado de volta.

### 4.2 Terminal
```bash
mrq-vs "https://youtu.be/XXXX"                  # separa e já cria o projeto
mrq-vs projeto lista  ~/musicas/Minha-96BPM
mrq-vs projeto mix    ~/musicas/Minha-96BPM --destino mix.wav
mrq-vs projeto stems  ~/musicas/Minha-96BPM
mrq-vs projeto exportar ~/musicas/Minha-96BPM    # cifra, MIDI, letra, ficha
mrq-vs projeto transpor ~/musicas/Minha-96BPM --semitons -2
mrq-vs projeto corrigir ~/musicas/Minha-96BPM --compasso 6/8
mrq-vs projeto marcar  ~/musicas/Minha-96BPM --tempo 12.5 --nome "Refrão"
mrq-vs projeto letra   ~/musicas/Minha-96BPM --letra letra.txt
```

Transcrição de letra (opcional, escolha um):
```bash
pip install faster-whisper      # MIT, recomendado (CPU ok)
pip install openai-whisper      # MIT
pip install vosk                # Apache-2.0 (precisa do modelo em português)
```

### 4.3 O que sai na pasta
```
<Nome>-<BPM>/                      áudio
  <Nome>_00_mix.wav  ...           stems exportados
  <Nome>_ENSAIO_LR.wav             clique+guia | banda
  stems-editados/                  só depois de "Stems editados"
<Nome>-<BPM>-apoio/                apoio
  projeto.json                     análise (gerado)
  projeto.mrqvs.json               projeto editável (fonte da verdade)
  edicoes.json                     compatibilidade com o editor anterior
  <Nome>_cifra_cifra.txt/.cho/.csv cifra
  <Nome>_cifra-e-clique.mid        MIDI
  <Nome>_ficha.html                ficha A4 (imprime em PDF)
  letra.json/.lrc/.srt/.txt        quando houver letra
  clique.wav  guia.wav  capa.jpg   ensaio e capa
```

---

## 5. Testes

```
303 passed, 1 skipped        (pytest, ~30 s)
ruff check src tests         All checks passed
```

Cobertura por área (arquivos novos):

* `tests/test_projeto_vs_multitrack.py` (54 testes) — mapa de tempo (inverso,
  BPM variado, 6/8 e 7/8, troca de fórmula, sem grade), cifra (confiança,
  `N.C.`, transposição, correção manual, três formatos), MIDI (cabeçalho,
  trilhas, mapa de tempo, ausência de nota para acorde incerto), letra (LRC,
  SRT com horas, alinhamento sem estourar o fim), projeto (salvar/abrir,
  formato do futuro recusado, solo/mute, render com volume e pan, arquivo
  original intacto, stem ausente vira aviso), rotas HTTP e CLI.
* `tests/test_interface_multitrack.py` (24 testes) — o JS real do `index.html`
  rodando em Node: cada botão novo chama a rota certa, a letra aparece com
  marca de "estimada", marcadores desenham e somem no duplo clique, salvar
  leva offset/fade/ordem/letra/marcadores, abrir música carrega o projeto,
  offset desloca o áudio de verdade, seek reposiciona todas as faixas.
* Testes de guarda: nenhum botão novo sem handler; todo botão do menu Exportar
  ligado; rotas e handlers existem no servidor.

Teste de resistência do harness: para os testes de interface funcionarem de
verdade, o mini-DOM ganhou `setTimeout` controlável (antes só empilhava e o
debounce de salvar nunca disparava), `getElementById` que respeita remoção e
ids criados por JS, e `textarea` no parser de `innerHTML`.

### Defeitos reais encontrados e corrigidos no caminho
1. compasso de fronteira entrava em duas seções (acorde duplicado na cifra);
2. mudança de andamento criava um trecho de transição com BPM inexistente;
3. `ENSAIO_LR` nascia como stem **e** como ensaio (duas faixas iguais);
4. `clique`/`guia` idem, com caminho relativo errado na segunda cópia;
5. ChordPro emitia `[]` vazio em compasso sem acorde;
6. parser de `.srt` ignorava as horas (10 s viravam 0,5 s);
7. "Salvar projeto" gravava o estado do botão ⟳ no campo de loop;
8. `edicoes.json` desfazia o mudo salvo no projeto ao reabrir;
9. play reposicionava todas as faixas no tempo da régua (offset ignorado);
10. a ficha saía de `/api/file` como `application/octet-stream`, então o
    `window.open` **baixava** o HTML em vez de abrir a aba para imprimir —
    `.html`, `.txt`, `.csv` e `.md` passaram a ser servidos com o tipo certo e
    `Content-Disposition: inline`. O `.mrqvs.json` continua sendo download de
    propósito: HTML servido na mesma origem pode carregar script.

---

## 6. Pendências (o que ainda não está pronto)

| item | estado | o que falta |
|---|---|---|
| BS-RoFormer / Mel-Band RoFormer | **não integrado** | download de pesos (913 MB) com aceite de licença; hoje o caminho de voz boa é `audio-separator` (UVR/MDX) |
| transcrição de letra | implementada, **sem motor instalado no pacote** | instalar `faster-whisper` (MIT) — a rota responde 501 + manual enquanto não houver |
| ficha em PDF direto | HTML que imprime em PDF | gerar PDF exige biblioteca (weasyprint/reportlab); o caminho atual usa o navegador |
| separação nativa de guitarra/piano | só `htdemucs_6s` | o programa **não** promete esses stems: apresenta como derivados e avisa |
| click/guia com mapa de tempo variável | clique segue a grade batida a batida | o acento já usa a fórmula de cada compasso; falta gravar o clique acentuado por andamento no WAV (hoje acentua pela fórmula) |
| instaladores Windows/macOS | inalterados nesta rodada | precisam ser regerados para incluir os módulos novos (`mrqvs.release`) |
| interface em navegador real | harness Node + servidor local | o sandbox não permitiu baixar Chromium; a validação de UI é do JS real, não de pixel |

---

## 7. Ferramentas e licenças

Já em uso (verificado no repositório e nos metadados):

| ferramenta | licença | uso aqui |
|---|---|---|
| numpy | BSD-3 | DSP, mixer, análise |
| soundfile | BSD-3 | leitura/escrita de WAV |
| yt-dlp (extra) | Unlicense | baixar a fonte |
| demucs (extra) | MIT (pesos restritos) | separação |
| audio-separator (extra) | MIT | UVR/MDX |
| openunmix (extra) | MIT | separação leve em CPU |
| beat-this (extra) | MIT | downbeats/compasso |
| ffmpeg (externo) | LGPL/GPL conforme build | MP3/MP4 e transposição |
| faster-whisper (extra, opcional) | MIT | transcrição de letra |

Nenhuma dependência nova foi adicionada ao núcleo: o projeto continua com
`numpy` + `soundfile`, e todo o resto é extra opcional. As decisões de licença
que excluíram motores estão na seção 3.7 e em `docs/PESQUISA-30-FERRAMENTAS.md`.
