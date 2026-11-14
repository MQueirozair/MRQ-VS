# Motores de IA para separação musical — pesquisa e recomendação técnica

**Data:** 13/11/2026 · **Alvo:** MRQ Audio Studio (licença MIT) · **Status:** pesquisa concluída, implementação aguardando aprovação

> **Resumo em uma frase:** o motor ideal para o MRQ Audio Studio **não é o Demucs**, e
> também não é o BS-RoFormer SW que todo mundo recomenda. É o **Mel-Band RoFormer
> "Kim" (KimberleyJSN)**, o único modelo de qualidade SOTA com **licença MIT
> declarada pelo próprio autor nos pesos** — os outros dois são, na melhor
> hipótese, ambíguos, e o Demucs é explicitamente **"só para fins científicos"**.

---

## 0. Por que esta pesquisa muda a decisão

O pedido era "não escolher Demucs por ser conhecido". A pesquisa confirma que essa
desconfiança estava certa — mas por um motivo que não é o de costume. O problema
não é qualidade: o Demucs é bom. O problema é que **quase todo modelo aberto de
separação tem licença de código livre e licença de pesos restritiva**, e quase
todos foram treinados no MUSDB18, um dataset que só permite uso acadêmico.

Isso não é detalhe jurídico distante: o MRQ Audio Studio é MIT e as pessoas
instalam em casa para trabalhar com música. Se a gente baixar pesos sem licença
clara automaticamente na máquina do usuário, quem herda o risco é ele.

A boa notícia é que existe **uma** família de modelos que resolve os dois lados —
qualidade SOTA **e** licença limpa — e ela não é a mais famosa.

---

## 1. Camadas de licença: o que ninguém verifica

Todo relatório de separação musical fala de SDR. Quase nenhum fala que existem
**três licenças separadas** em jogo:

| Camada | O que é | Exemplo de armadilha |
|---|---|---|
| **1. Código** | o repositório (arquitetura, treino, inferência) | Quase sempre MIT. É a parte fácil. |
| **2. Pesos** | o arquivo `.ckpt`/`.onnx` treinado | **Raramente tem licença declarada.** É aqui que quebra. |
| **3. Dataset** | os dados de treino | MUSDB18 é "apenas para fins acadêmicos" e está atrás de **quase todos** os modelos. |

### O caso Demucs, com a citação exata

O Demucs é o motor que o app usa hoje. O código é MIT e isso é verdade. Mas o
autor, Alexandre Défossez, respondeu em 2022 uma issue justamente sobre
distribuir os pesos num projeto comercial:

> "The model weights are not covered by the MIT license, and are provided only for
> scientific purposes."
> — adefossez, `facebookresearch/demucs` issue #327

Isso não foi revogado depois, e o `htdemucs` (v4) foi treinado do mesmo jeito
(MUSDB18-HQ + ~800 músicas internas da Meta sem proveniência pública). Ou seja:
**o Demucs que está no instalador do MRQ hoje funciona, é excelente, e tem peso
jurídico indefinido.** Não some com ele — mas não é nele que se baseia um produto.

### O caso BS-RoFormer SW, o "melhor modelo de 6 stems"

Todo fórum recomenda o BS-RoFormer SW (6 stems: vocais, bateria, baixo, guitarra,
piano, outros) porque tem o melhor SDR publicado de 6 stems. Fui atrás da licença:

- O checkpoint original foi publicado **sem licença nenhuma**;
- o re-host mais usado diz "unknown";
- e no repositório do MSST (issue #248) a resposta é literalmente que "SW" significa
  *shared weights*, que ninguém sabe ao certo quem treinou, e que
  **provavelmente o modelo é da Apple — é o modelo do Logic Pro**.

Não é um modelo que a gente possa baixar automaticamente para o computador de
um usuário. Pode virar *opção manual* (o usuário escolhe e aponta o arquivo), mas
não pode ser o padrão de um produto MIT.

### A régua

| Veredito | Critério |
|---|---|
| ✅ **Distribuível** | O autor declarou licença permissiva para os pesos (MIT/Apache) |
| ⚠️ **Condicional** | Licença declarada mas restritiva (GPL, CC-BY-NC) — dá para usar com cuidado ou mediante contato |
| ❌ **Não distribuível** | Sem licença declarada, ou declaração de uso apenas científico |
| ❓ **Ambíguo** | Publicado num repo MIT mas sem declaração sobre os pesos |

---

## 2. Os 5 melhores modelos encontrados

### 2.1 Mel-Band RoFormer "Kim" — `KimberleyJSN/melbandroformer` ✅

| | |
|---|---|
| **Arquitetura** | Mel-Band RoFormer (Transformer com band-split em escala mel + RoPE), 228 M parâmetros |
| **Stems** | 2 nativos (vocais + instrumental por complemento) |
| **Licença dos pesos** | **MIT** — declarada no cartão do modelo, verificada na API do Hugging Face: `"cardData":{"license":"mit"}` |
| **Licença do código** | MIT (`ZFTurbo/Music-Source-Separation-Training`, `lucidrains/BS-RoFormer`) |
| **SDR publicado** | Multisong (MVSep): **vocais 11,01 · instrumental 17,32**; Synth: 12,68 / 12,38; MDX23: 11,54 |
| **Tamanho** | 913 MB (fp32) · ~457 MB em fp16 |
| **Onde baixar** | `huggingface.co/KimberleyJSN/melbandroformer` → `MelBandRoformer.ckpt` |

**Por que é o melhor para nós:** é o único caso em que existe uma **declaração
positiva do autor** sobre os pesos. Houve até um debate público (discussion #2) em
que a autora foi perguntada exatamente sobre usar o modelo num projeto open
source; ela respondeu liberando, primeiro sob GPL-3.0 e depois **relicenciando
para MIT em 22/04/2026**. Isso é o oposto de "ambíguo": é um autor ativamente
facilitando o uso.

**Limitação honesta:** é um modelo de 2 stems. Ele dá voz e instrumental, não
dá bateria/baixo/guitarra/piano separados.

### 2.2 BS-RoFormer SW (6 stems) — o melhor SDR, pior licença ❌

| | |
|---|---|
| **Arquitetura** | Band-Split RoFormer, ~700 MB |
| **Stems** | **6 nativos**: vocais, bateria, baixo, guitarra, piano, outros |
| **SDR publicado** | vocais 11,30 · baixo 14,62 · bateria 14,11 · guitarra 9,05 · piano 7,83 · outros 8,71 (Multisong / MVSep) |
| **Licença dos pesos** | ❌ **Nenhuma.** Não declarada pelo treinador; re-hosts dizem "unknown" ou "MIT" por conta própria |
| **Proveniência** | Provavelmente treinado pela Apple (modelo do Logic Pro) |

**É o modelo dos sonhos em qualidade e o pesadelo em licença.** Seria a escolha
óbvia se a pergunta fosse só "qual separa melhor guitarra e piano". Como a
pergunta inclui "posso distribuir", ele sai do pacote automático.

### 2.3 HTDemucs (`htdemucs` / `htdemucs_ft` / `htdemucs_6s`) ⚠️

| | |
|---|---|
| **Arquitetura** | Hybrid Transformer Demucs (U-Net waveform + espectrograma com bottleneck Transformer) |
| **Stems** | 4 (`htdemucs`, `htdemucs_ft`) ou **6** (`htdemucs_6s`: + guitarra + piano) |
| **SDR publicado (MUSDB18-HQ)** | `htdemucs` ~7,7 dB médio · `htdemucs_ft` **9,20 dB** |
| **Licença dos pesos** | ⚠️ código MIT, **pesos "só para fins científicos"** (issue #327) |
| **VRAM** | ~4 GB (`htdemucs`) · ~6 GB (`htdemucs_ft`) |
| **CPU** | ~1,5× o tempo real (lento, mas viável) |

**É o que o app já usa.** Continua sendo o melhor **4-stem multi-instrumento
aberto** e o único caminho prático para guitarra/piano isolados hoje. Não
devemos removê-lo — devemos **deixar de depender dele**.

### 2.4 SCNet XL / SCNet XL IHF (`ZFTurbo/MSST`) ❓→⚠️

| | |
|---|---|
| **Arquitetura** | Subband modeling + compressão esparsa (Tsinghua SIGS et al.) |
| **Stems** | 4 (vocais, bateria, baixo, outros) |
| **SDR publicado** | MUSDB18: **10,08 dB médio** · Multisong: 9,92 · bateria 11,81 · vocais 11,42 |
| **Licença dos pesos** | ❓ Sem declaração explícita; distribuído nas releases de um repo MIT |

**Qualidade muito boa e custo baixo** (SCNet é conhecido por fazer o que o
BS-RoFormer faz com ~7× menos parâmetros). É o candidato natural para **bateria
e baixo** de verdade. O bloqueio é a licença não declarada — resolvível com uma
confirmação de uma linha do ZFTurbo, que é responsivo no GitHub.

### 2.5 UVR-MDX-NET (Inst HQ 3, Voc FT, Karaoke) ✅ com crédito

| | |
|---|---|
| **Arquitetura** | MDX-Net (TFC-TDF U-Net) — **já distribuído em ONNX** |
| **Stems** | 2 (vocais/instrumental) · variantes karaoke separam **voz principal de backing vocals** |
| **SDR publicado** | `UVR-MDX-NET-Inst_HQ_3`: vocais 9,38 · instrumental 15,68 |
| **Licença dos pesos** | ✅ MIT **com crédito obrigatório**, por declaração no README do UVR |
| **Tamanho** | 28–64 MB por modelo (minúsculo) |

A declaração é explícita: *"For all third-party application developers who wish to
use our models, please honor the MIT license by providing credit to UVR and its
developers."* Não é o melhor SDR, mas é **pequeno, ONNX nativo, roda em CPU em
qualquer lugar** e tem recurso que ninguém mais tem com licença limpa: karaokê
(voz principal × backing).

---

## 3. Tabela comparativa

> **Leia antes de comparar números:** SDR **só é comparável dentro do mesmo
> dataset e do mesmo pipeline de avaliação**. MUSDB18-HQ, Multisong MVSep e Synth
> MVSep dão números bem diferentes para o mesmo modelo — o Mel-RoFormer "Kim", por
> exemplo, aparece com 11,01 (Multisong), 12,68 (Synth) e 13,29 (vocal, MUSDB) em
> fontes distintas. Os valores abaixo vêm de benchmarks publicados; a coluna
> "fonte" diz qual. **Nada aqui foi medido por mim** — ver seção 10.

| Modelo | Arquitetura | SDR (fonte) | Stems | Guitarra? | Piano? | Voz | Transientes | Artefatos | RAM/VRAM | Velocidade | Win | macOS | Offline | Licença pesos | Pesos disp.? | Integração |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Mel-RoFormer Kim** | Mel-Band RoFormer | **11,01 voz / 17,32 instrum** (Multisong) | 2 | ❌ | ❌ | ⭐ excelente | bons | baixos (voz suave) | ~2 GB RAM CPU / 3–5 GB VRAM | lenta em CPU (~2,9× RT), **1,08× RT em M3 MPS** | ✅ | ✅ MPS | ✅ | ✅ **MIT** | ✅ | Média (ckpt → precisa MSST/audio-separator) |
| **BS-RoFormer SW** | Band-Split RoFormer | 11,30 / 14,62 / 14,11 / **9,05 guit** / 7,83 piano / 8,71 (Multisong) | **6** | ✅ | ✅ (fraco) | ⭐ excelente | bons | "menos nebuloso", pode soar duro | ~8–16 GB VRAM em 6 stems | lenta | ✅ | ✅ | ✅ | ❌ **sem licença** | ✅ (não autorizado) | Baixa (uso legal incerto) |
| **HTDemucs ft** | HT Demucs | **9,20** médio (MUSDB18-HQ) | 4 | ❌ | ❌ | boa | ⭐ melhores | baixos | ~6 GB VRAM / ~4 GB RAM | CPU ~1,5× RT | ✅ | ✅ MPS | ✅ | ❌ "só científico" | ✅ | ✅ **já integrado** |
| **HTDemucs 6s** | HT Demucs | ~8,8 voz, outros cai p/ ~5,5 (MUSDB) | **6** | ✅ fraco | ✅ fraco | boa | bons | o "other" piora | ~5 GB VRAM | CPU ~1,5× RT | ✅ | ✅ | ✅ | ❌ "só científico" | ✅ | ✅ já integrado |
| **SCNet XL IHF** | SCNet + IHF | **10,08** médio, bateria 11,81, voz 11,42 (MUSDB) | 4 | ❌ | ❌ | boa | bons | baixos | ~2–4 GB VRAM | média/rápida | ✅ | ✅ | ✅ | ❓ não declarada | ✅ | Média |
| **UVR-MDX-NET Inst HQ3** | MDX-Net (ONNX) | 9,38 voz / 15,68 instrum (Multisong) | 2 (+karaokê) | ❌ | ❌ | boa | bons | baixos | **~1 GB RAM, roda em CPU** | rápida | ✅ DirectML | ✅ CoreML | ✅ | ✅ **MIT + crédito** | ✅ | ⭐ **alta (ONNX puro)** |
| **MDX23C** | TFC-TDF | 7,15 médio (MUSDB) | 4 | ❌ | ❌ | boa | bons | médio | moderado | média | ✅ | ✅ | ✅ | ❓ / ❓ | ✅ | média |
| **Open-Unmix `umxl`** | BiLSTM | 5,3–7,2 (SiSEC) | 4 | ❌ | ❌ | fraca | fracos | altos | leve | rápida | ✅ | ⚠️ torch | ✅ | ❌ **CC-BY-NC-SA** | ✅ | ⭐ alta (é o "leve" atual) |
| **Spleeter** | CNN | ~5,9 | 4/5 | ❌ | ❌ | fraca | fracos | altos | leve | muito rápida | ⚠️ TF quebrado | ⚠️ | ✅ | MIT (legado) | ✅ | já abandonado |

### 3.1 Sobre "guitarra e piano separados" — a resposta honesta

O pedido lista guitarra e piano como stems desejados. A pesquisa mostra que
**esses dois são exatamente o ponto onde o mundo aberto trava**:

| Caminho | Status real |
|---|---|
| `htdemucs_6s` | funciona, mas é fraco (o próprio Demucs avisa que piano "ainda não está bom") **e** o peso é "só científico" |
| BS-RoFormer SW | **excelente** (guitarra 9,05 / piano 7,83), mas **sem licença** |
| `becruily/mel-band-roformer-guitar` | único Mel-RoFormer dedicado a guitarra — autor diz **"free as long as it's non commercial"** ❌ |
| Piano dedicado | **não existe** checkpoint público com licença permissiva |
| MVSep Mega 53-stem | guitarra acústica 5,08 / elétrica 8,19 / piano 6,81 — **é servidor pago**, não roda local ❌ |

**Conclusão:** guitarra e piano ficam como **recurso de "modo avançado"**, com
aviso claro, dependendo de o usuário aceitar baixar um modelo de licença
restrita para uso pessoal — nunca como padrão silencioso.

---

## 4. Compatibilidade Windows e macOS

### 4.1 O que é *de verdade* acelerado

O ponto do pedido "não presumir que PyTorch = Metal" está certíssimo. A tabela
abaixo vem da documentação oficial do `audio-separator` (que é quem vai rodar os
modelos):

| Arquitetura | Apple Silicon (M1–M4) | Windows NVIDIA | Windows AMD/Intel | CPU puro |
|---|---|---|---|---|
| **MDX-Net** (`.onnx`) | ✅ **CoreML** | ✅ CUDA | ✅ **DirectML** | ✅ |
| **VR Arch** (`.pth`) | ✅ PyTorch MPS | ✅ CUDA | ✅ DirectML | ✅ |
| **Mel-Band / BS-RoFormer** (`.ckpt`) | ✅ PyTorch **MPS** | ✅ CUDA | ⚠️ **roda em CPU** (alocador do torch-directml estoura memória) | ✅ |
| **Demucs** | ✅ MPS | ✅ CUDA | ❌ **não suportado** (falta operador LSTM fundido) | ✅ |

**Leia de novo a última coluna da linha RoFormer.** É a limitação mais importante
para um app Windows: **AMD Radeon não acelera RoFormer** — o melhor modelo vai
rodar em CPU na placa da AMD. NVIDIA e Apple Silicon vão bem.

Isso não invalida a escolha, mas muda o desenho: **o app precisa detectar a GPU
e escolher o modelo certo**, em vez de assumir que todo mundo tem CUDA.

### 4.2 macOS — o caso que mais surpreende

Benchmarks públicos reais (não teóricos) em MacBook Air M3 de 8 GB com o
Mel-RoFormer:

| Configuração | Velocidade |
|---|---|
| PyTorch fp32 no MPS (padrão) | **1,08× tempo real** |
| fp16 | 1,35× |
| + RoPE/RMSNorm fora do fp32 | 2,19× |
| + kernels Metal custom | 2,62× |
| + 12 blocos no Neural Engine (CoreML) | 3,61× |
| + atenção fatiada p/ caber no Neural Engine | **4,19×** |

Ou seja: no Mac o modelo **fica apenas no limite do tempo real** com o caminho
padrão; acelerar de verdade exige otimização específica. E há uma causa
identificada e documentada: **RoPE e RMSNorm em fp32 consomem 30–46% do tempo de
atenção** no MPS.

No Windows com NVIDIA, um RoFormer de 20 s leva **~9,8 s em CUDA** contra **172 s
em CPU** — quase 18× de diferença. Conclusão prática: **GPU não é luxo, é o que
torna o Mel-RoFormer viável.** Sem GPU, ele é "deixe rodando".

---

## 5. Requisitos de hardware e consumo

| Cenário | Hardware | Mel-RoFormer | HTDemucs ft | UVR-MDX |
|---|---|---|---|---|
| **Mínimo** | 4 núcleos, 8 GB RAM, sem GPU | ⚠️ funciona, **muito lento** (RTF ~2,9) | ⚠️ ~1,5× RT | ✅ ok, RTF ~0,3–0,5 |
| **Recomendado** | 8 GB+ VRAM NVIDIA ou Apple Silicon 16 GB | ✅ rápido | ✅ | ✅ |
| **Memória** | — | ~2 GB RAM (CPU) / 3–5 GB VRAM | ~4 GB RAM / 6 GB VRAM | **~1 GB RAM** |
| **Disco** | — | ~913 MB ckpt (457 MB fp16) | ~640 MB (bag) | 28–64 MB |

**Um dado importante:** um projeto que reimplementou o Mel-RoFormer em Rust
relata **7,8 GB de pico** processando com janela de 8 s — e 6,7 GB com janela
menor. No Mac isso é problema com 8 GB de RAM total. É por isso que o
processamento **em blocos com sobreposição** não é opcional: é requisito.

---

## 6. Arquitetura de instalação proposta

O app **já tem** exatamente o fluxo pedido (item 6 do briefing): `ai.py` baixa um
Python embutido, instala pacotes num ambiente isolado `mrq-ai/`, mostra progresso
em MB e apaga tudo se falhar no meio. O que muda é *o que* ele instala.

```
Usuário instala o MRQ (zip/exe, sem IA)
        │
        ▼
Primeira execução → /api/status → ai.estado()
        │
        ├── não instalado → cartão "Instalar IA (grátis)" com 3 perfis:
        │      ├─ Leve      ~250 MB   UVR-MDX-Net (ONNX, CPU)     → voz/instrumental em qualquer PC
        │      ├─ Padrão    ~1,6 GB   + Mel-RoFormer (CPU/GPU)    → voz de altíssima qualidade
        │      └─ Completo  ~2,5 GB   + htdemucs (4 stems)        → bateria, baixo, outros
        │
        ├── baixa Python embutido (só se o perfil exigir torch)
        ├── baixa cada peso com **SHA-256 verificado** (hoje não existe essa checagem!)
        ├── roda teste de fumaça: separa 2 s de senoide e confere que saiu áudio
        └── libera a separação
```

### 6.1 Três perfis, não um

O erro a evitar é "instalar tudo sempre". Um usuário de notebook sem GPU não deve
baixar 2,5 GB para descobrir que vai esperar 15 minutos por música.

| Perfil | Download | O que entrega | Para quem |
|---|---|---|---|
| **Leve** | ~250 MB | voz + instrumental (UVR-MDX ONNX, sem torch, sem Python extra) | qualquer PC; teste rápido |
| **Padrão** | ~1,6 GB | + voz Mel-RoFormer (SOTA) | quem tem GPU ou paciência |
| **Completo** | ~2,5 GB | + 4 stems (bateria/baixo/outros) | produção musical |

### 6.2 Verificação de integridade — hoje não existe

O instalador atual baixa o Python e o pip **sem conferir hash**. Para pesos de
modelo isso é inaceitável (são centenas de MB, de CDNs de terceiros). Proposta:
um `catalogo.json` versionado com `url + sha256 + tamanho + licença + crédito`
por peso; download vai para arquivo temporário, hash confere, só então move.

### 6.3 Empacotamento — decisão

O pedido pergunta "qual a melhor forma de empacotar". Pelos dados:

| Opção | Download | Complexidade | Veredito |
|---|---|---|---|
| **venv + pip** (`audio-separator`) | ~1,5 GB (torch vai junto) | baixa — **já funciona** | ✅ **escolhida** para o Padrão/Completo |
| ONNX Runtime puro | ~250 MB (sem torch) | média, mas precisa de export por modelo | ✅ **escolhida** para o Leve |
| PyInstaller/Nuitka com torch embutido | +2 GB no instalador principal | alta, frágil entre versões | ❌ rejeitada |
| MLX (só Apple) | ~460 MB | alta, específico de plataforma | ❌ por ora — caminho futuro |

**Por que não embutir tudo:** o pacote portátil passaria de ~60 MB para ~1,5 GB e
o usuário baixaria IA que talvez nunca use. A instalação sob demanda já é a
arquitetura do app e funciona.

---

## 7. Arquitetura modular proposta

O app já tem a espinha certa (`separator.py` com backends plugáveis, todos
chamados por **processo externo** — um torch quebrado não derruba a interface).
O que falta é tornar isso *dados*, não *código*:

```
src/mrqvs/motor/
├── __init__.py        API pública: separar(), modelos(), hardware()
├── catalogo.py        registro de modelos (nome, stems, licença, sha256, URL, crédito)
├── hardware.py        detecta CUDA / MPS / DirectML / CPU + RAM livre -> escolhe device
├── contrato.py        ModeloBase: carregar → preparar → processar_blocos → juntar → liberar
├── blocos.py          janela + sobreposição + crossfade (evita clique na emenda)
├── verificacao.py     sha256, teste de fumaça, duração/amostragem dos stems
└── adaptadores/
    ├── mel_roformer.py    (audio-separator)
    ├── mdx_onnx.py        (onnxruntime puro)
    ├── htdemucs.py        (já existente)
    └── dsp.py             (fallback atual, sempre disponível)
```

**Contrato único** — o mesmo para todos, o que responde ao item 7 do briefing:

```python
class ModeloBase:
    nome: str; stems: tuple[str, ...]; licenca: str
    def carregar(self, device: str) -> None: ...      # carrega pesos
    def separar(self, audio, sr) -> dict[str, np.ndarray]: ...  # em blocos
    def liberar(self) -> None: ...                    # devolve VRAM/RAM
```

Adicionar modelo novo = **uma entrada no catálogo + um adaptador**, sem tocar na
interface. É o que o pedido chama de "trocar o modelo sem modificar a interface".

---

## 8. Otimização de desempenho

| Técnica | Ganho publicado | Risco de qualidade | Decisão |
|---|---|---|---|
| **GPU (CUDA)** | **~18×** (172 s → 9,8 s) | nenhum | ✅ padrão quando disponível |
| **MPS no Mac** | 1,08× RT (base) | nenhum | ✅ padrão no Apple Silicon |
| **fp16 / autocast** | 1,35× no Mac | baixíssimo (66,7 dB vs fp32) | ✅ opcional, verificado |
| **RoPE/RMSNorm em fp16** | 1,35× → 2,19× | baixíssimo | ⏳ depende do upstream |
| **torch.compile** | ganho em execuções repetidas | precisa PyTorch 2.6+ | ✅ quando disponível |
| **Processamento em blocos** | viabiliza 8 GB de RAM | risco de emenda | ✅ **obrigatório**, com crossfade |
| **Quantização int8** | — | **alto em RoFormer** | ❌ rejeitada |
| **Ensemble de modelos** | +0,3 a +0,5 dB | 2–3× mais lento | ⏳ "modo caprichado" futuro |

**Regra que vou seguir:** nenhuma otimização que troque qualidade por velocidade
entra por padrão. fp16 é o único "atalho" aceitável, e só porque a perda medida é
inaudível.

---

## 9. Qualidade de áudio — o que a pesquisa mostrou

| Preocupação | Achado |
|---|---|
| **Vazamento entre instrumentos** | Mel-RoFormer melhor que BS-RoFormer em *bleedless* de voz no Multisong; o inverso no instrumental |
| **Artefatos metálicos** | Modelos Transformer (RoFormer) produzem espectrogramas "menos nebulosos" — produtores às vezes preferem o som mais "cheio" do Demucs |
| **Transientes da bateria** | HTDemucs é historicamente o melhor nisso; SCNet XL é o melhor SDR de bateria (11,81) |
| **Graves do baixo** | Mel-RoFormer é **notoriamente fraco em baixo** (o paper explica: a escala mel não modela bem baixo). Baixo pede BS-RoFormer ou SCNet |
| **Distorção vocal** | Mel-RoFormer foi descrito como "mais suave, com volume mais consistente" — é o ponto forte dele |
| **Duração e sincronia** | ⚠️ **Não é automático:** o modelo trabalha em blocos e devolve o mesmo número de amostras apenas se o pipeline recompuser o padding. **Precisa de verificação explícita** (hoje o app não valida isso) |

**Sobre "a soma dos stems é igual ao mix":** o pedido está certo em exigir
cautela. Modelos de máscara tendem a somar ~igual, mas **não é garantido** e não
deve ser afirmado na interface sem medição. A postura correta: calcular a soma e
**mostrar o desvio medido**, não prometer zero.

---

## 10. O que eu NÃO consegui verificar (honestidade sobre limites)

Esta seção existe porque o pedido diz "não inventar benchmarks" — e porque seria
fácil escrever uma tabela bonita de números que eu não medi.

| Item | Situação |
|---|---|
| **Teste com músicas reais + SDR medido por mim** | ❌ **Não executado.** Não houve download de pesos nem inferência nesta etapa |
| **RAM/tempo medidos nesta máquina** | ❌ Não. Os números das tabelas são de fontes públicas, cada um no seu hardware |
| **Comparação "olho no ouvido" (avaliação auditiva)** | ❌ Não feita |
| **Hash oficial dos pesos** | ⚠️ A maioria dos autores **não publica SHA-256**. Vou calcular e fixar no catálogo no momento do download |
| **Licença de `umxl`** | ✅ Verificado: **CC-BY-NC-SA 4.0**, não comercial (README do Open-Unmix) |

Ou seja: a recomendação abaixo é baseada em **documentação oficial, papers e
benchmarks publicados** — não em medição própria. O plano de validação está na
seção 12.

---

## 11. Riscos de integração

| Risco | Gravidade | Mitigação |
|---|---|---|
| **Licença de pesos** (Demucs "científico", BS-RoFormer SW sem licença) | 🔴 alta | Só Mel-RoFormer (MIT) e UVR (MIT+crédito) no download automático; o resto exige escolha explícita do usuário, com aviso |
| **MUSDB18 contamina quase tudo** | 🟠 média | Transparência no catálogo: cada modelo mostra a licença declarada, e a interface diz que a licença é do modelo, não do áudio do usuário |
| **`audio-separator` atualiza e quebra** | 🟠 média | Fixar versão (`==0.48.0`) no instalador, como já se faz com o Python |
| **AMD no Windows não acelera RoFormer** | 🟠 média | Detecção de hardware → sugere `Leve` (MDX/ONNX) e avisa o tempo estimado |
| **8 GB de RAM estoura com janela de 8 s** | 🟠 média | Blocos adaptativos: janela menor quando RAM livre < 4 GB |
| **PyTorch 2.13+ exigido no Apple Silicon** | 🟡 baixa | Python embutido já é 3.12/3.13; pinar torch compatível |
| **`umxl` é não comercial** (backend "leve" atual) | 🟡 baixa | Trocar o default do "leve" para `umxhq` ou para UVR-MDX |
| **Duração/sincronia dos stems** | 🟡 baixa | Verificação automática no fim do pipeline (item 9) |

---

## 12. Recomendação

### 12.1 Modelo recomendado: **Mel-Band RoFormer "Kim" (MIT)**

**Melhor equilíbrio entre qualidade, velocidade, recursos e licença** — e o único
que fecha as quatro pontas sem asterisco:

- **Qualidade:** voz no nível SOTA (11,0–13,3 dB SDR conforme o dataset), descrita
  na literatura como mais limpa e de volume mais consistente;
- **Licença:** **MIT nos pesos**, declarada pela autora, verificada na API do HF;
- **Tamanho:** 457 MB em fp16 — não é o modelo mais leve, mas cabe;
- **Portabilidade:** roda em CPU (lento), GPU NVIDIA (rápido) e Apple MPS.

### 12.2 Mas não sozinho — a arquitetura recomendada é em camadas

Nenhum modelo isolado atende ao pedido (2 stems ≠ 6 stems). A recomendação é
**um motor com quatro camadas**, escolhidas por licença e por capacidade:

| Camada | Modelo | Licença | Papel |
|---|---|---|---|
| **1. Sempre disponível** | DSP atual (HPSS) | — | fallback universal, funciona em qualquer máquina |
| **2. Base leve** | UVR-MDX-Net Inst HQ3 (ONNX) | ✅ MIT+crédito | voz/instrumental rápida, sem torch |
| **3. Qualidade (padrão)** | **Mel-RoFormer Kim** | ✅ MIT | voz SOTA — **nosso diferencial** |
| **4. Multi-stem** | HTDemucs (já instalado) | ⚠️ científico | bateria/baixo/outros + guitarra/piano (com aviso) |
| **5. Opcional/manual** | SCNet XL, BS-RoFormer SW | ❓/❌ | o usuário aponta o arquivo que já tem |

### 12.3 O que muda no app

| Hoje | Proposta |
|---|---|
| Demucs como "motor de qualidade", `audio-separator` como alternativa | **Mel-RoFormer como motor principal de voz**; Demucs vira a camada multi-stem |
| `umxl` (não comercial) é o "leve" | UVR-MDX (MIT) como leve; `umxl` sai do padrão |
| Download sem hash | `catalogo.json` com SHA-256 por peso |
| 2 perfis de instalação (completo/leve) | **3 perfis** + instalação de modelos individuais depois |
| Sem exibição de licença | Cada modelo mostra licença e crédito na interface |
| Sem detecção de GPU | `hardware.py` → device + estimativa de tempo |

### 12.4 Sequência sugerida (não iniciada — aguardando aprovação)

1. **Catálogo + hardware + verificação** (sem trocar motor): base segura, testável offline.
2. **UVR-MDX via ONNX** como novo "leve" — maior ganho por menor risco.
3. **Mel-RoFormer** como modelo de voz padrão, com blocos + crossfade.
4. **Perfil Completo** amarrando Demucs para os 4 stems.
5. **Medição própria** (ver 12.5) e só então ajustar default.

### 12.5 Plano de validação com música real

Para fechar a lacuna da seção 10, quando aprovado:

- 3 músicas com referência conhecida + 2 gravações do próprio usuário;
- métricas **SI-SDR** (mais robusta a permutação de escala que SDR) e SDR museval;
- medir tempo, pico de RAM e VRAM por perfil, no mesmo hardware, mesma sessão;
- conferir duração idêntica ao original amostra por amostra e desvio da soma;
- registrar tudo em `docs/BENCHMARK-MOTORES.md` com hardware e versões.

---

## 13. Referências

**Papers**
- Lu, Wang, Kong, Hung. *Music Source Separation with Band-Split RoPE Transformer* (BS-RoFormer) — arXiv:2309.02612, ICASSP 2024
- Wang, Lu, Won, Choi, Song. *Mel-Band RoFormer for Music Source Separation* — arXiv:2310.01809
- Rouard, Massa, Défossez. *Hybrid Transformers for Music Source Separation* — ICASSP 2023
- Solovyev et al. *Benchmarks and leaderboards for sound demixing tasks* — arXiv:2305.07489
- *Moises-Light: Resource-efficient Band-split U-Net* — arXiv:2510.06785
- *Music-Source-Separation-Training (MSST): a unified framework* — arXiv:2607.23395

**Código e pesos**
- Mel-Band RoFormer Kim (MIT): `huggingface.co/KimberleyJSN/melbandroformer` (verificado via API)
- MSST (MIT): `github.com/ZFTurbo/Music-Source-Separation-Training`
- `audio-separator` (MIT, v0.48.0): `github.com/nomadkaraoke/python-audio-separator`
- UVR / UVR-MDX-NET (MIT + crédito): `github.com/Anjok07/ultimatevocalremovergui`
- Demucs (código MIT / pesos restritos): `github.com/adefossez/demucs`, issue #327
- Open-Unmix (`umxl` CC-BY-NC-SA): `github.com/sigsep/open-unmix-pytorch`
- kuielab MDX-Net (MIT): `github.com/kuielab/mdx-net-submission`
- BS-RoFormer SW — disputa de licença: `github.com/ZFTurbo/Music-Source-Separation-Training/issues/248`

**Benchmarks públicos**
- MVSep algorithms e leaderboards: `mvsep.com/en/algorithms`
- StemSplit benchmark 2026: `huggingface.co/datasets/StemSplitio/stem-separation-benchmark-2026`

**Desempenho medido em hardware real (terceiros)**
- `github.com/LoggeL/turbo-roformer` (CPU AVX512-BF16)
- `github.com/aipdv/fast-melroformer` (Apple Silicon, Neural Engine)
- `github.com/nomadkaraoke/python-audio-separator/issues/314` (RoPE/RMSNorm no MPS)
