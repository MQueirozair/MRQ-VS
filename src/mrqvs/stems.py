"""Catálogo de stems: o que existe, o que cada backend consegue entregar.

O usuário pediu "até o máximo de faixas: vocais, bateria, contrabaixo,
guitarra, teclado, piano, percussão, loops, fx...". Nenhum modelo aberto
entrega isso tudo de uma vez — e é importante ser honesto sobre isso em vez
de inventar stems vazios:

| stem        | quem entrega de verdade                                     |
|-------------|-------------------------------------------------------------|
| vocals      | htdemucs, htdemucs_ft, htdemucs_6s, MDX                      |
| instrumental| derivado (mix - vocals), não é um modelo separado            |
| drums       | htdemucs, htdemucs_ft, htdemucs_6s, MDX                      |
| bass        | htdemucs, htdemucs_ft, htdemucs_6s, MDX                      |
| guitar      | htdemucs_6s (e só ele entre os abertos)                       |
| piano       | htdemucs_6s (o próprio Demucs avisa que é o elo fraco)       |
| other       | htdemucs, htdemucs_ft, htdemucs_6s, MDX                      |
| percussion  | derivado de `drums` (HPSS: ataque vs. corpo)                 |
| kick/snare/hihat | derivados de `drums` (bandas + onsets) — aproximação     |
| fx/loops    | derivado de `other` só quando o resto não explica o sinal     |

Os "derivados" são marcados como aproximados no relatório do projeto; só os
stems nativos contam como separação de verdade. Ver `report.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StemInfo:
    id: str
    label: str
    description: str
    #: stems "pai" dos quais este pode ser derivado (vazio = nativo de IA)
    derived_from: tuple[str, ...] = field(default_factory=tuple)
    #: cor do fader/faixa na interface (hex) — mesma paleta em toda a UI
    color: str = "#888888"


STEM_ORDER: tuple[str, ...] = (
    "vocals",
    "instrumental",
    "drums",
    "kick",
    "snare",
    "hihat",
    "percussion",
    "bass",
    "guitar",
    "piano",
    "keys",
    "other",
    "fx",
    "loops",
)

STEMS: dict[str, StemInfo] = {
    "vocals": StemInfo("vocals", "Vocais", "Voz principal + backing vocals", color="#e05c5c"),
    "instrumental": StemInfo(
        "instrumental",
        "Instrumental",
        "O mix inteiro sem os vocais (karaokê)",
        derived_from=("mix", "vocals"),
        color="#c98b3a",
    ),
    "drums": StemInfo("drums", "Bateria", "Kit completo (bumbo, caixa, pratos)", color="#4f9dde"),
    "kick": StemInfo("kick", "Bumbo", "Derivado da bateria (ataque grave)", derived_from=("drums",), color="#3f7fb5"),
    "snare": StemInfo("snare", "Caixa", "Derivado da bateria (ataque médio)", derived_from=("drums",), color="#5aa9c9"),
    "hihat": StemInfo("hihat", "Pratos", "Derivado da bateria (ataque agudo)", derived_from=("drums",), color="#7ec8d8"),
    "percussion": StemInfo(
        "percussion",
        "Percussão",
        "Derivado da bateria: o que é ataque/transiente (shakers, congas, tamborim)",
        derived_from=("drums",),
        color="#8f7fd0",
    ),
    "bass": StemInfo("bass", "Contrabaixo", "Baixo elétrico/acústico + sub", color="#5fb96b"),
    "guitar": StemInfo("guitar", "Guitarra", "Só com modelo de 6 stems (htdemucs_6s)", color="#d9a441"),
    "piano": StemInfo("piano", "Piano", "Só com modelo de 6 stems (é o stem mais fraco do Demucs)", color="#c4756b"),
    "keys": StemInfo(
        "keys",
        "Teclados",
        "Órgão, sintetizadores e teclados que não são piano",
        derived_from=("other", "piano"),
        color="#b07fc9",
    ),
    "other": StemInfo("other", "Outros", "Tudo que não é voz/bateria/baixo (cordas, metais, texturas)", color="#9a9a9a"),
    "fx": StemInfo(
        "fx",
        "Efeitos",
        "Sobe/riser, impactos, ruídos e ambiências isoladas",
        derived_from=("other",),
        color="#7f9a9a",
    ),
    "loops": StemInfo(
        "loops",
        "Loops",
        "Trechos repetidos identificados na faixa 'Outros' (aproximação)",
        derived_from=("other",),
        color="#a3a37f",
    ),
}

#: O que cada modelo de separação realmente entrega.
MODEL_STEMS: dict[str, tuple[str, ...]] = {
    "htdemucs": ("drums", "bass", "other", "vocals"),
    "htdemucs_ft": ("drums", "bass", "other", "vocals"),
    "htdemucs_6s": ("drums", "bass", "other", "vocals", "guitar", "piano"),
    "mdx_extra_q": ("drums", "bass", "other", "vocals"),
    "mdx_extra": ("drums", "bass", "other", "vocals"),
    # BS-RoFormer / UVR-MDX via audio-separator. Ajusta-se à música inteira
    # (não é multi-stem): entrega voz e instrumental nativamente.
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt": ("vocals", "instrumental"),
    "UVR-MDX-NET-Inst_HQ_3.onnx": ("vocals", "instrumental"),
    # Spleeter fica no mapa só para ler projetos antigos: o backend não roda no
    # Python 3.13 e foi substituído pelo "leve" (open-unmix).
    "spleeter:4stems": ("drums", "bass", "other", "vocals"),
    "spleeter:5stems": ("drums", "bass", "other", "vocals", "piano"),
    # open-unmix: o substituto do Spleeter. 4 stems, roda em CPU, sem
    # TensorFlow. `umxl` é o modelo grande (qualidade melhor), `umxhq` o
    # treinado só no MUSDB18-HQ.
    "umxl": ("drums", "bass", "other", "vocals"),
    "umxhq": ("drums", "bass", "other", "vocals"),
    "dsp-fallback": ("vocals", "drums", "bass", "other"),
}

DEFAULT_MODEL = "htdemucs_6s"

#: Qualidade publicada de cada modelo, em SDR médio (dB) no MUSDB18-HQ.
#: Fonte: papers do Demucs v4 e do BS-RoFormer (SDX23), e as tabelas do
#: Music-Source-Separation-Training. Serve para a tela recomendar com número,
#: não com opinião:
#:
#:   htdemucs_6s   6 stems, mas guitarra/piano são o elo fraco do Demucs
#:   htdemucs_ft   +0.5 dB sobre o htdemucs, 4× mais lento (só 4 stems)
#:   BS-RoFormer   9.8 dB, o estado da arte — vocals 12.9 dB contra 8.3 dB
#:
#: O número que mais importa para quem monta playback de igreja: voz. Ali o
#: RoFormer ganha do Demucs por ~4 dB, que é a diferença entre "dá para usar"
#: e "não dá".
SDR_MEDIO: dict[str, float] = {
    "htdemucs": 7.7,
    "htdemucs_ft": 8.5,
    "htdemucs_6s": 7.7,      # mesma base; os 2 stems extras são os mais fracos
    "mdx_extra": 7.0,
    "mdx_extra_q": 7.0,
    "spleeter:4stems": 5.4,
    "spleeter:5stems": 5.4,
    # Open-Unmix: 5.3 dB é o valor do próprio paper (MUSDB18). Fica abaixo do
    # Demucs de propósito na tabela — a vantagem dele não é qualidade, é peso
    # e velocidade num PC sem placa de vídeo.
    "umxl": 5.9,
    "umxhq": 5.3,
}

#: SDR de voz isolada — é o stem que decide a maior parte dos usos.
SDR_VOZ: dict[str, float] = {
    "htdemucs": 8.1,
    "htdemucs_ft": 8.9,
    "htdemucs_6s": 8.1,
    "spleeter:4stems": 6.3,
    "umxl": 6.2,
    "umxhq": 5.6,
}


#: Qualidade dos modelos RoFormer/MDX que vêm pelo audio-separator.
#: O número é o SDR de voz publicado pelo próprio pacote, não estimativa.
SDR_VOZ_ROFORMER: dict[str, float] = {
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt": 12.9,
    "UVR-MDX-NET-Inst_HQ_3.onnx": 10.4,
}


def recomendacao(modelo: str) -> str:
    """Frase curta e honesta sobre o modelo escolhido."""
    if modelo in SDR_VOZ_ROFORMER:
        nota = f"voz ≈ {SDR_VOZ_ROFORMER[modelo]:.1f} dB"
        if modelo.endswith(".onnx"):
            return nota + " — roda em CPU sem torch; voz + instrumental"
        return nota + " — o melhor que existe para voz; voz + instrumental"
    if modelo in SDR_VOZ:
        base = f"voz ≈ {SDR_VOZ[modelo]:.1f} dB"
    elif modelo in SDR_MEDIO:
        base = f"média ≈ {SDR_MEDIO[modelo]:.1f} dB"
    else:
        base = ""
    if modelo == "htdemucs_6s":
        return (
            base + " — 6 stems, mas guitarra e piano são o elo fraco do Demucs"
        )
    if modelo == "htdemucs_ft":
        return base + " — melhor voz do Demucs, ~4× mais lento e só 4 stems"
    return base


def native_stems(model: str) -> tuple[str, ...]:
    return MODEL_STEMS.get(model, ())


def resolve_stems(requested: list[str], model: str, derive: bool = True) -> tuple[list[str], list[str], list[str]]:
    """Resolve o que será gerado de fato.

    Devolve `(nativos, derivados, sem_suporte)`, na ordem canônica de
    `STEM_ORDER`. Pedir um derivado traz junto o **pai** (ex.: `kick` implica
    `drums`), porque o pai é separado pelo modelo de qualquer forma — quem
    chamou nunca precisa lembrar dessa dependência.
    """
    native_available = set(native_stems(model))
    available = set(native_available)
    if derive:
        changed = True
        while changed:
            changed = False
            for stem, info in STEMS.items():
                if stem in available or not info.derived_from:
                    continue
                if any(parent in available for parent in info.derived_from):
                    available.add(stem)
                    changed = True
    if not requested:
        requested = [s for s in STEM_ORDER if s in native_available]
    wanted = set(requested)
    # Fecha a dependência: pai de derivado pedido entra na conta.
    pending = [s for s in wanted if s in STEMS and STEMS[s].derived_from and s not in native_available]
    while pending:
        stem = pending.pop()
        for parent in STEMS[stem].derived_from:
            if parent == "mix" or parent in wanted:
                continue
            wanted.add(parent)
            if parent in STEMS and STEMS[parent].derived_from and parent not in native_available:
                pending.append(parent)
    native = [s for s in STEM_ORDER if s in wanted and s in native_available]
    derived = [s for s in STEM_ORDER if s in wanted and s in available and s not in native_available]
    missing = [s for s in requested if s not in available]
    return native, derived, missing
