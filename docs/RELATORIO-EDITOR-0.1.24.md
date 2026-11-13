# Relatório — correção do editor musical (0.1.24)

Origem: pacote de transferência `transferencia-MRQ-VS-codigo-relatorio-testes.zip`
(Drive), que trouxe a árvore da 0.1.23 no commit `d5b0b6a`, o histórico Git
local daquele checkout, a amostra real `demomix-96BPM`, as capturas do usuário
e os relatórios das rodadas 31 (0.1.22) e 32 (0.1.23).

Regra seguida: **nenhuma causa foi declarada sem ser reproduzida no código e
travada por teste**. O que não pôde ser executado aqui está na seção 6.

---

## 1. O que o pacote acrescentou ao repositório remoto

O `main` do remoto havia sido restaurado a partir da 0.1.21; a 0.1.23 que o
usuário conhecia **nunca foi enviada** (`git log` do remoto tinha só o commit
inicial e a restauração). Comparei as duas árvores antes de escrever código:

| Item | Situação | Ação |
|---|---|---|
| `codigo/` (0.1.23) | código anterior ao desta rodada | auditoria das causas (seção 2) |
| `MRQ-VS-historico.bundle` | 43 commits locais, HEAD `d5b0b6a` | verificado e importado como remoto `bundle` só para diff — **nada foi mesclado no histórico** |
| `amostra-real/demomix-96BPM` | 7 stems + `_MIX` + `ENSAIO_LR`, WAV reais de 24 s | usada para testar reabertura e dados legados |
| `amostra-real/…-apoio` | `clique.wav`, `guia.wav`, `projeto.json`, `edicoes.json` reais | serviu de fixture para o teste de compatibilidade (seção 4) |
| `imagens/image-39..42.png` | capturas do usuário | as falhas visíveis foram conferidas contra o código |
| `scripts-jsdom/` | scripts de depuração com caminhos do sandbox anterior | **não reaproveitados** (paths absolutos, premissas de áudio simulado) |

Os testes da 0.1.23 foram executados contra o código atual para medir regressão:
`test_biblioteca`, `test_guia_acordes`, `test_mixdown`, `test_faixas_de_ensaio`,
`test_upload` passam; os 13 "failures" de `test_studio.py` são **asserções de
string** que apontam para nomes internos da implementação antiga
(`studioDesenharCifra`, `f.el.muted = !ok`, `rgba(255,255,255,.55)`) — o
comportamento que eles queriam provar está coberto de forma executável em
`tests/test_studio_musical_editor.py` (33 testes). Não copiei esses assertos
para não transformar nome de função em contrato.

## 2. Causas comprovadas das falhas

### 2.1 Cifra (captura `image-39`: "F#mEBD#" embaralhado na música de 6:39)
1. `studioDesenharCifra` impunha **largura mínima de 26 px** por acorde. Com a
   música inteira na tela (262 compassos), duas células seguidas ocupam menos
   que isso e o texto de uma invade o da outra.
2. A grade só era gerada até **400 compassos** (`n < 400`) — e sem limite de
   densidade, o que só empurrava o problema para frente.
3. O vazio entre acordes era preenchido **herdando o vizinho**, inventando
   cifra onde a detecção não tinha nada.
4. Acordes de baixa confiança (8%) apareciam como se fossem certos.
5. Setas de transposição chamavam `transporAcorde(..., true)`: **bemol fixo**,
   então F# menor era escrito em Gb.

Correção: uma célula **por compasso**, largura exata, agrupamento apenas quando
o texto não cabe (`compacta`/`micro`, ajuste de fonte), "—" quando não há
acorde ou a confiança é < 0,2, sem teto de compassos, e a grafia segue o modo
(`F# menor` → sustenido; `F menor` → bemol), inclusive em acordes invertidos
(`D/F#`).

### 2.2 Compassos (régua e playhead fora do áudio)
`batidasPorCompasso()` usava `Math.round(num/2)`: **7/8 dava 4** em vez de 3,5.
`compassoDe()` dividia pelo **numerador** enquanto a duração usava outra
função — inconsistente para denominador 8. `inicioDoCompasso()` e
`totalCompassos()` ignoravam o offset inicial, e a lista de fórmulas não tinha
5/4 nem 7/8. O código auditado ainda tinha `passoBase = inicioDoCompasso(1) - t`
(ficava zero no segundo compasso e negativo depois) como passo das subdivisões.

Correção: `bar_sec = (60/BPM) · num · (4/den)` — a **unidade do BPM é a
semínima** e isso está escrito no código e no comentário de `unidadesDoCompasso`.
6/8 = `6·30/BPM`, 7/8 = `7·30/BPM`, 12/8 = `12·15/BPM`. Offset, mudanças de
fórmula (`mudancasCompasso`), cache de prefixo e busca binária. 398 s / 158 BPM
/ 4/4 dá **262,0167** compassos — calculado, nunca fixo.

### 2.3 Clique
`setInterval(40)` era o relógio: a régua andava em degraus e o clique tinha
jitter. Não havia scheduler nem pré-contagem real. E `faixaAudivel` tratava
clique e guia pelo mesmo `Studio.metronomo`, então desligar o ⏱ calava a guia e
o Solo do clique não soava.

Correção: **AudioContext como fonte única**; a interface só consulta
(`requestAnimationFrame`). Clique agendado com lookahead (oscilador por pulso,
acentos forte/médio/fraco por fórmula: 6/8 = 3+3, 7/8 = 3+2+2, 12/8 =
3+3+3+3), pré-contagem 0/1/2 compassos, reancoragem no seek e no loop. Clique e
Guia têm interruptores independentes; Solo vence o global.

### 2.4 Faixas, alturas e ondas
`--h-linha` era lido em `documentElement` (vazio → 62 px) e cortava PAN/VOL;
painel e timeline usavam alturas diferentes; clique/guia entravam **depois**
dos stems; stems desconhecidos colidiam no mesmo `id: "other"`; não havia
rolagem vertical sincronizada; `carregarPicos()` abria um `AudioContext` por
faixa; e cada trilha tinha um canvas do tamanho da música inteira.

Correção: ordem canônica (Click, Guia, Vocais, Bateria, Contrabaixo, Guitarra,
Piano, Outros, extras, Instrumental, Mix), altura única para painel e trilha,
scroll espelhado nos dois sentidos, fila de decodificação com um contexto só,
ladrilhos de canvas e zoom da onda na **amplitude vertical** (não no tempo).

### 2.5 Rótulo da pré-contagem ilegível
O botão da barra inferior trazia os três pulsos do metrônomo **como
caracteres**, então a leitura saía `123 Sem Pré-contagem` — visualmente um
número colado na frase, e no leitor de tela um número solto. Agora os pulsos
são desenho (SVG inline) e o texto é só o estado (`sem contagem`,
`2 compassos de contagem`), com `.on` e dica próprios.

### 2.6 Duração travada em 0:24 (captura da 0.1.23)
`loadedmetadata` só atualizava a duração se o arquivo fosse **mais longo** que
o `projeto.json`. Com JSON de 24 s e áudio de 6:38, ficava 24 s para sempre.
Corrigido para valer para mais **e para menos**.

## 3. Arquivos modificados nesta rodada

| Arquivo | O que mudou |
|---|---|
| `src/mrqvs/web/index.html` | motor do Studio: matemática do compasso, cifra, relógio/clique, faixas, ondas, mixer |
| `src/mrqvs/web/__init__.py` | `POST /api/importar-faixa`, `POST /api/atalho`, `denominador` no payload |
| `src/mrqvs/mixdown.py` | `guiaAtiva` (e os campos do editor) na lista de campos aceitos |
| `src/mrqvs/acordes.py`, `src/mrqvs/project.py` | `compasso_e_grade_do_modelo()`, `StudioData.denominador` |
| `src/mrqvs/app.py` | `criar_atalho_desktop()`, `_pasta_area_de_trabalho()`, `_plataforma()` |
| `src/mrqvs/cli.py` | subcomando `atalho` |
| `windows/installer.iss` | instalador Inno Setup (ícone na Área de Trabalho por padrão) |
| `tests/test_studio_musical_editor.py` | 33 testes executáveis (JS real em Node + HTTP real) |
| `tests/js/harness.js`, `tests/js/minidom.js` | mini-DOM e AudioContext com relógio controlável |

## 4. Testes executados

```
166 passed  (suíte completa, 3 execuções seguidas + 1 com -p no:randomly)
ruff check src tests → All checks passed
python -m mrqvs.release → pacote gerado e auto-testado
```

Destaques verificados **medindo estado/áudio**, não texto:

- **matemática**: 262,0167 compassos em 398 s/158 BPM; `inicioDoCompasso(261)`
  = 396,4557 s; 6/8 = 3,0; 7/8 = 3,5; 5/4 = 5,0; 2/4 = 2,0; busca binária
  conferida contra varredura linear em toda a grade;
- **cifra**: 500 compassos sem sobreposição; nenhuma célula inventada;
  transposição F# menor ↔ Gb coerente; editor grava e apaga de verdade;
- **compatibilidade (novo)**: o `edicoes.json` real da 0.1.23 reabre com as
  três seções do usuário (`Verso/Refrão/Final`), a cifra com confiança 0,9, o
  mix (volume 0,4 / pan −0,25 / solo na voz) e a faixa oculta preservada;
- **seções × áudio (novo)**: apagar todas as seções mantém a Guia montada,
  audível e com ganho 1,0; criar seção nova desenha a marca na trilha sem
  trocar o elemento de áudio (requisito "marcadores não apagam áudio");
- **relógio**: após `avancar(2.5)` posição 2,440 (0,06 s de pré-roll); seek
  6 + 1 s → 7,0; pré-contagem de 2 compassos a 100 BPM → 4,86 s; loop A=2 B=4
  reancora em 2,0;
- **mixer**: mute/solo/volume/pan conferidos no `GainNode`/`StereoPannerNode`;
  Solo múltiplo; master não sobrescreve volume individual; mixdown do servidor
  concorda com a tela (`_MIX.wav` real, pico normalizado, sem clipping);
- **importar faixa**: anexa stem sem apagar nada e recusa pasta fora das raízes.

## 5. Instalador Windows

`windows/installer.iss` gera `MRQ-VS-Setup-windows-x64.exe` (Inno Setup 6),
**sem prompt de Administrador**, com atalho na **Área de Trabalho** (marcado
por padrão), Menu Iniciar e desinstalador. O CI compila o Setup no job
`windows-latest` e publica junto dos binários. O caminho do atalho é o real do
usuário (Windows `USERPROFILE\Desktop`, XDG `XDG_DESKTOP_DIR`, depois
`~/Desktop` e `~/Área de Trabalho`), e o `.lnk` aponta para `mrq-vs.ico` ao lado
do executável.

## 6. Pendências — o que NÃO foi verificado aqui

1. **A música real do usuário (6:39, 158 BPM, F# menor) não está no pacote.**
   A validação de 262 compassos usa o caso descrito (398 s) com dados
   sintéticos e a demo real de 24 s. Para fechar a aceitação é preciso a pasta
   da música + a pasta `-apoio` (`projeto.json`, `edicoes.json`, stems,
   `clique.wav`, `guia.wav`).
2. **Sem navegador real neste ambiente** (o CDN do Chromium é bloqueado): não
   houve screenshot nem escuta em Windows. O que existe é execução do JS de
   verdade em Node com AudioContext controlável + HTTP real, que mede estado e
   ganho, mas não prova som audível na máquina do usuário.
3. **O `.exe` não foi executado em Windows nesta rodada** — o job de CI
   compilou o Setup, mas instalar e abrir ficam para a conferência do usuário.
4. **`pan` continua oculto em telas muito estreitas** (fica no menu ⋯ da
   faixa). É decisão de layout documentada no CSS, não falha de áudio.
5. A waveform é desenhada a partir dos picos decodificados do arquivo; quando a
   decodificação falha, a trilha diz "forma de onda indisponível" em vez de
   desenhar rabisco — mas isso não foi exercitado com um arquivo corrompido
   real.
