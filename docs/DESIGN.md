# MRQ VS — decisões de projeto

Documento das escolhas que não são óbvias no código. Cada seção diz **o que
fazemos**, **por quê** e **o que isso custa**.

## 1. Por que não é um script único de 50 linhas

O pedido era "igual ao Moises": link entra, pasta com stems + BPM sai. O
Moises faz isso com uma pilha grande (modelo proprietário, cloud, detector
de acordes, metrônomo inteligente). Aqui a pilha é aberta e o produto é:

```
mídia → análise → separação → derivação → exportação → pasta + relatório
```

Cada etapa é um módulo testável e **cada etapa sabe degradar**:

| Etapa | Se falta dependência |
|---|---|
| mídia | sem `yt-dlp`: aceita arquivo local; sem `ffmpeg`: só lê o que libsndfile abrir, e avisa antes de prometer MP3/MP4 |
| análise | numpy é obrigatório, mas a análise nunca é bloqueada por modelo ausente |
| separação | cai `demucs` → `audio-separator` → `spleeter` → DSP |
| derivação | cada derivado que não pode ser calculado vira **aviso**, nunca arquivo vazio |
| exportação | WAV sempre; MP3/MP4 são validados no início (falha rápido, com o comando de instalação) |

## 2. Nome da pasta: título abreviado + BPM

`naming.project_folder_name()`:

- limpa lixo de YouTube (`(Official Video)`, `[HD]`, `| Lyric Video`, `(Clipe Oficial)`…);
- separa artista/título; a convenção do YouTube é **"Artista - Título"** e o
  nome do canal desempata quando o vídeo usa a ordem inversa;
- remove acentos (`Coração → Coracao`), tira espaços e pontuação;
- corta em fronteira de palavra, com orçamento = `max_len − sufixo do BPM`;
- termina sempre em `-96BPM` (`BPMdesconhecido` se a análise não achar pulso).

Exemplo: `Evidências - Chitãozinho & Xororó (Clipe Oficial)` @ 96.2 →
`EvidenciasChitaozinhoXororo-96BPM`.

A pasta é criada **depois** da análise (o nome depende do BPM) e o trabalho
pesado roda numa pasta temporária: execução interrompida não deixa pasta
meio-feita com nome errado.

## 3. Análise: honesta antes de precisa

- **BPM**: envelope de onsets por fluxo espectral → autocorrelação →
  refino parabólico do pico → dobra de oitava para 70–160. A confiança
  (`pico/AC[0]`) vai no relatório; abaixo de 0.15 o campo vira "desconhecido"
  em vez de um número inventado. `--bpm` existe porque errar a oitava é o
  modo de falha clássico (96 e 192 são a mesma batida).
- **Tonalidade**: cromagrama com saliência harmônica (cada bin também conta
  para as classes das suas sub-harmônicas — senão o 3º harmônico inventa uma
  quinta que não está tocando) + perfis de Krumhansl-Kessler nos 12 tons
  maiores/menores, correlação de Pearson, confiança = melhor correlação.
  Roda de Camelot por tabela fixa (8B = Dó maior, 8A = Lá menor).
- **Seções**: curva de novidade (Foote) → picos separados por ≥8 s → rótulos
  por similaridade espectral (A, A, B…); seções vizinhas de mesmo rótulo e
  trechos < 2 s são absorvidos. O relatório deixa claro que A/B **não** são
  "verso/refrão".
- **Loudness**: RMS por seção, para ver onde o arranjo cresce.

Tudo em numpy puro (sem scipy/librosa): DSP auditável e uma dependência menos.

## 4. Stems: catálogo, nativos e derivados

Nenhum modelo aberto entrega "vocais + bateria + baixo + guitarra + teclado +
piano + percussão + loops + fx". Prometer isso produziria stems vazios.
Então:

- **Nativo** = saiu do modelo (`htdemucs_6s`: 6 stems).
- **Derivado** = calculado por DSP a partir de um nativo e **marcado como
  aproximado** no relatório e no JSON.
  - `instrumental` = mix − vocais (subtração; o derivado mais confiável);
  - `kick/snare/hihat/percussion` = partição espectral da bateria
    (30–120 Hz / 150–600 Hz / 6–16 kHz / o resto), máscaras que **somam 1**,
    então a soma volta a ser o stem de bateria;
  - `keys` = banda 200–4000 Hz de `other`, menos o que já está em `piano`;
  - `fx` = resíduo não-tonal de `other` (mediana no tempo = tonal; o resto é
    riser/impacto/textura);
  - `loops` = blocos de 0,5 s repetidos (impressão digital espectral
    centralizada + similaridade ≥ 0,90); sem repetição, **não** gera o stem.
- Pedir um derivado traz o pai (`--stems kick` separa `drums` e entrega `kick`).
- Stems sem suporte no modelo/backend entram em "sem suporte" — nunca viram
  arquivo vazio.

## 5. Backend DSP: por que ele existe e o que ele vale

`separate_dsp()` é HPSS (mediana no tempo = harmonia, na frequência =
percussão) + pesos de banda para voz (300 Hz–4 kHz) e baixo (< 180 Hz), com
máscaras tipo Wiener. As quatro máscaras formam uma **partição**: a soma dos
stems reconstrói o mix (teste de regressão exige > 30 dB de SNR).

Isso não é IA: na demo sintética o SDR fica em **~4,6 dB de média** (vocais
4,2 · bateria 6,6 · baixo 4,4 · outros 3,3) — comparável aos baselines
clássicos da literatura (HPSS ~4,4, REPET ~3,4, NMF ~4,1 de SDR médio) e bem
abaixo dos ~9–10 dB do Demucs. Serve para: funcionar em qualquer máquina, validar o
pipeline sem torch e dar um esboço para quem ainda não instalou o modelo.
O relatório chama esses stems de "aproximado (DSP, sem IA)".

## 6. Exportação

- **WAV**: `soundfile`, 16/24 bits ou float32. **Sem normalizar por padrão**:
  normalizar cada stem individualmente destrói a relação de volume do mix e o
  usuário perde a referência. `--normalize` existe para quem quer.
- **MP3**: ffmpeg + LAME 320k, com tags ID3 (título, artista, `TBPM`, "MRQ VS").
- **MP4**: áudio AAC + visualizador `showwaves`; se o build do ffmpeg não
  tiver o filtro, cai para vídeo de fundo sólido em vez de falhar por enfeite.
- `check_export_capabilities()` roda **antes** do download: melhor recusar
  MP3 sem ffmpeg no começo do que depois de 5 minutos de processamento.
- `stems/00_mix` é a soma dos stems exportados — conferência imediata.

## 7. Relatório

`relatorio.md` + `projeto.json`. O Markdown responde: de onde veio o áudio,
quanto mediu (com confiança), o que é nativo e o que é derivado, quais avisos
valem para esta execução, como importar na DAW, **o que fazer se o resultado
não ficou bom** e a situação de licença dos modelos. O JSON carrega a mesma
informação em formato consumível (`mrqvs.evaluate`, scripts, dashboards).

## 8. Interface web

Uma página, `http.server`, sem dependências. Rotas: `GET /`, `/api/status`,
`/api/file?p=…` (restrito à pasta de saída, com checagem de path traversal) e
`POST /api/analyze`, `/api/run`. Um trabalho por vez (lock): separar música é
caro e duas requisições simultâneas só fariam as duas ficarem lentas. O
servidor é local — não é para expor na internet.

## 9. Testes

65 testes que rodam sem internet e sem torch. Os que valem mais:

- STFT→ISTFT com SNR > 30 dB e cobertura do fim do arquivo (bug real
  encontrado no caminho: frames de borda fora da análise faziam o mix voltar
  com 5 dB de erro);
- partição de máscaras: soma dos stems = mix com SNR > 30 dB;
- BPM em pulsos sintéticos a 80/96/120/140, com tolerância de oitava;
- tonalidade de uma tríade de Dó = C maior;
- cada stem gerado correlaciona mais com a sua fonte verdadeira do que com
  as outras (teste de regressão contra a demo sintética);
- nomes de pasta para os casos reais do YouTube, inclusive com o canal
  desempatando a ordem artista/título.

## 10. O que ficou de fora (de propósito)

- **Acordes e letra**: o Moises mostra acordes; aqui só tonalidade + BPM +
  seções. Acorde por acorde exige cromagrama por batida + casamento de
  templates — dá para adicionar depois sem mudar a arquitetura.
- **Real-time (Moises Live)**: precisa de NPU/GPU e modelo menor; fora do
  escopo de um utilitário de arquivo.
- **Normalização EBU R128**: depende do filtro `ebur128` do ffmpeg; fica como
  opção futura.
