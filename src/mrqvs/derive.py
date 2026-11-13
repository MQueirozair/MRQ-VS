"""Stems derivados: o que dá para tirar de um stem já separado.

Três famílias, todas marcadas como **aproximadas** no relatório:

1. **instrumental** — mix − vocais. Exato na prática (é subtração de amostras),
   é o "karaokê" que o Moises oferece como stem de 2 faixas.
2. **bateria desmontada** — kick / snare / hihat / percussion a partir do stem
   `drums`, por banda de frequência:
   * bumbo: 30–120 Hz;
   * caixa: 150–600 Hz (corpo; o chiado fica nos pratos por simplicidade);
   * pratos: 6–16 kHz;
   * percussão: todo o resto do espectro (shaker, tamborim, congas).
   As máscaras têm bordas suaves e formam uma partição (somam 1), então
   "kick + snare + hihat + percussion = drums" — dá para conferir a soma.
3. **keys / fx / loops** — `keys` = `other` com máscara de banda de teclado e
   remoção do que já está no piano; `fx` = `other` com o conteúdo harmônico
   removido (sobra o ruidoso: risers, impactos, texturas); `loops` = os trechos
   de `other` que se repetem (autocorrelação de curto alcance), o resto vira
   silêncio — é mais um mapa do que um stem.
"""

from __future__ import annotations

from pathlib import Path

from . import dsp

#: banda (Hz) e largura de transição (em semitons de oitava) de cada peça
_BANDS: dict[str, tuple[float, float]] = {
    "kick": (30.0, 120.0),
    "snare": (150.0, 600.0),
    "hihat": (6000.0, 16000.0),
    "percussion": (120.0, 16000.0),
}


def _band_weight(freqs, lo: float, hi: float, knee: float = 0.35):
    """Peso 1 dentro de [lo, hi], caindo suavemente nas bordas (em oitavas)."""
    import numpy as np

    f = np.maximum(freqs, 1e-3)
    low_edge = np.clip(np.log2(f / max(lo, 1e-3)) / knee, 0.0, 1.0)
    high_edge = np.clip(np.log2(max(hi, lo * 2) / f) / knee, 0.0, 1.0)
    return (low_edge * high_edge).astype(np.float32)


def split_drums(drums, sample_rate: int, n_fft: int = 2048) -> dict[str, "object"]:
    """Divide um stem de bateria em kick/snare/hihat/percussion.

    Separação **espectral**: o bumbo vive em 30–120 Hz, o corpo da caixa em
    150–600 Hz, o chiado dos pratos acima de 6 kHz; `percussion` fica com
    todo o resto do espectro (shakers, tamborim, congas, e o que sobra das
    bordas). As quatro máscaras formam uma **partição** (somam 1 em todo bin),
    então `kick + snare + hihat + percussion` reconstitui o stem de bateria —
    o que permite ao usuário conferir a soma na DAW.

    Limite honesto: por frequência dá para separar bumbo/caixa/pratos de
    forma convincente, mas não "caixa de verdade" de "palmas" — isso exige
    modelo treinado. O relatório marca estes stems como derivados.
    """
    dsp.require_numpy("desmontar a bateria")
    import numpy as np

    hop = n_fft // 4
    freqs = dsp.stft_freqs(n_fft, sample_rate)
    channels = 1 if drums.ndim == 1 else drums.shape[1]
    out = {name: np.zeros_like(drums) for name in _BANDS}

    kick = _band_weight(freqs, 30.0, 120.0)
    snare = _band_weight(freqs, 150.0, 600.0)
    hihat = _band_weight(freqs, 6000.0, 16000.0)
    # O resto (600 Hz–6 kHz e bordas) é percussão — garante cobertura total.
    percussion = np.clip(1.0 - (kick + snare + hihat), 0.0, 1.0).astype(np.float32)
    masks = {"kick": kick, "snare": snare, "hihat": hihat, "percussion": percussion}
    total_mask = sum(masks.values())
    masks = {name: (mask / np.maximum(total_mask, 1e-6)).astype(np.float32) for name, mask in masks.items()}

    for ch in range(channels):
        signal = drums if drums.ndim == 1 else drums[:, ch]
        spec = dsp.stft(signal, n_fft=n_fft, hop=hop)
        for name, mask in masks.items():
            piece = dsp.istft(spec * mask[None, :], n_fft=n_fft, hop=hop, length=signal.shape[0])
            if drums.ndim == 1:
                out[name] = piece
            else:
                out[name][:, ch] = piece
    return out


def derive_instrumental(mix, vocals):
    """`mix − vocais`: subtração literal. Nunca cancela completamente (o
    modelo não reconstrói o mix perfeitamente), por isso é o stem derivado
    mais confiável de todos."""
    dsp.require_numpy("gerar o instrumental")
    import numpy as np

    m = np.asarray(mix, dtype=np.float32)
    v = np.asarray(vocals, dtype=np.float32)
    n = min(m.shape[0], v.shape[0])
    out = m[:n].copy()
    out -= v[:n]
    return dsp.fade(out, 44100)


def isolate_band(source, sample_rate: int, lo: float, hi: float, n_fft: int = 4096):
    """Filtro de banda suave no domínio espectral (usado por keys e fx)."""
    dsp.require_numpy("filtrar uma faixa de frequência")
    import numpy as np

    hop = n_fft // 4
    freqs = dsp.stft_freqs(n_fft, sample_rate)
    weight = _band_weight(freqs, lo, hi, knee=0.5)
    channels = 1 if source.ndim == 1 else source.shape[1]
    out = np.zeros_like(source)
    for ch in range(channels):
        signal = source if source.ndim == 1 else source[:, ch]
        spec = dsp.stft(signal, n_fft=n_fft, hop=hop)
        piece = dsp.istft(spec * weight[None, :], n_fft=n_fft, hop=hop, length=signal.shape[0])
        if source.ndim == 1:
            out = piece
        else:
            out[:, ch] = piece
    return out


def separate_tonal_noise(source, sample_rate: int, n_fft: int = 4096):
    """Separa (tonal, ruidoso) — usado para tirar `fx` de `other`.

    Mediana ao longo do tempo deixa o que é **sustentado/tonal** (acordes,
    notas); o resíduo é o que aparece e desaparece (risers, impactos, ruído).
    """
    dsp.require_numpy("separar conteúdo tonal de ruído")
    import numpy as np

    hop = n_fft // 4
    mono = dsp.to_mono(source)
    spec = dsp.stft(mono, n_fft=n_fft, hop=hop)
    mag = np.abs(spec).astype(np.float32)
    tonal = dsp.median_filter_harmonic(mag, width=9)
    mask = dsp.soft_mask(tonal, mag - tonal, power=1.0)
    return mask


def extract_loops(source, sample_rate: int, n_fft: int = 2048, min_repeats: int = 2):
    """Devolve (áudio dos trechos repetidos, lista de (início, fim) em s).

    Estratégia barata e explicável: divide em blocos de 0,5 s, calcula a
    "impressão digital" espectral de cada bloco e agrupa os blocos com
    similaridade de cosseno ≥ 0,97. Grupos com `min_repeats` ou mais
    ocorrências são loops; o áudio devolvido mantém só as ocorrências (com
    crossfade curto para não cortar no meio de um ataque).
    """
    dsp.require_numpy("detectar loops")
    import numpy as np

    hop = n_fft // 4
    mono = dsp.to_mono(source)
    spec = dsp.stft(mono, n_fft=n_fft, hop=hop)
    mag = np.abs(spec).astype(np.float32)
    block = max(1, int(round(0.5 * sample_rate / hop)))
    n_blocks = mag.shape[0] // block
    mask = np.zeros(mag.shape, dtype=np.float32)
    spans: list[tuple[float, float]] = []
    if n_blocks >= 2:
        prints = np.log1p(mag[: n_blocks * block].reshape(n_blocks, block, -1).mean(axis=1))
        # Centralizar é essencial: sem isso, dois trechos de ruído (espectro
        # plano) ficam com cosseno ≈ 1 e o detector "acha" loops no caos.
        prints = prints - prints.mean(axis=1, keepdims=True)
        prints = prints / (np.linalg.norm(prints, axis=1, keepdims=True) + 1e-9)
        sim = prints @ prints.T
        used = np.zeros(n_blocks, dtype=bool)
        for i in range(n_blocks):
            if used[i]:
                continue
            group = np.where((sim[i] >= 0.90) & ~used)[0]
            if group.size >= min_repeats:
                used[group] = True
                for b in group:
                    mask[b * block : (b + 1) * block] = 1.0
                    spans.append((round(b * block * hop / sample_rate, 2),
                                  round((b + 1) * block * hop / sample_rate, 2)))
    if not spans:
        return np.zeros_like(mono), []
    audio = dsp.istft(spec * mask, n_fft=n_fft, hop=hop, length=mono.shape[0])
    return dsp.fade(audio, sample_rate, 0.01, 0.01), sorted(spans)


def derive_stems(
    native: dict[str, "object"],
    sample_rate: int,
    wanted: list[str],
    mix=None,
) -> tuple[dict[str, "object"], list[str]]:
    """Gera os derivados pedidos a partir dos nativos.

    Devolve `(novos_stems, avisos)`. Nunca devolve um stem que não pôde ser
    calculado — nesse caso ele entra em `avisos` e não é gravado.
    """
    dsp.require_numpy("gerar stems derivados")
    import numpy as np

    new: dict[str, object] = {}
    warnings: list[str] = []

    def has(name: str) -> bool:
        return name in native or name in new

    if "instrumental" in wanted and "instrumental" not in native and mix is not None and has("vocals"):
        new["instrumental"] = derive_instrumental(mix, native["vocals"])

    drum_parts = [s for s in ("kick", "snare", "hihat", "percussion") if s in wanted]
    if drum_parts:
        if has("drums"):
            pieces = split_drums(native["drums"], sample_rate)
            for name in drum_parts:
                new[name] = pieces[name]
        else:
            warnings.append("kick/snare/hihat/percussion precisam do stem 'drums' — não gerados")

    if "keys" in wanted:
        if has("other"):
            keys = isolate_band(native["other"], sample_rate, 200.0, 4000.0)
            if has("piano"):
                # Tira do `keys` a energia que já está no piano (evita dobrado).
                spec_keys = keys
                spec_piano = native["piano"][: keys.shape[0]]
                ratio = np.abs(spec_piano) > np.abs(keys) * 0.5
                spec_keys = np.where(ratio, 0.0, keys).astype(np.float32)
                keys = spec_keys
            new["keys"] = keys
        else:
            warnings.append("'keys' precisa do stem 'other' — não gerado")

    if "fx" in wanted:
        if has("other"):
            other = native["other"]
            mask = separate_tonal_noise(other, sample_rate)
            # O que NÃO é tonal é o efeito/ambiente.
            new["fx"] = np.asarray(non_tonal(other, mask), dtype=np.float32)
        else:
            warnings.append("'fx' precisa do stem 'other' — não gerado")

    if "loops" in wanted:
        if has("other"):
            audio, spans = extract_loops(native["other"], sample_rate)
            if spans:
                new["loops"] = audio
            else:
                warnings.append("nenhum loop repetido encontrado em 'other' — stem não gerado")
        else:
            warnings.append("'loops' precisa do stem 'other' — não gerado")

    return new, warnings


def non_tonal(source, mask):
    """Reconstrói o resíduo (1 − máscara tonal) no domínio do tempo."""
    import numpy as np

    n_fft = 4096
    hop = n_fft // 4
    channels = 1 if source.ndim == 1 else source.shape[1]
    out = np.zeros_like(source)
    for ch in range(channels):
        signal = source if source.ndim == 1 else source[:, ch]
        spec = dsp.stft(signal, n_fft=n_fft, hop=hop)
        residual = dsp.istft(spec * (1.0 - mask), n_fft=n_fft, hop=hop, length=signal.shape[0])
        if source.ndim == 1:
            out = residual
        else:
            out[:, ch] = residual
    return out


def write_stems(stems: dict[str, object], sample_rate: int, out_dir: Path, prefix: str) -> dict[str, Path]:
    """Grava cada stem como WAV float32 (mantém headroom, sem clipping)."""
    from .naming import stem_filename

    try:
        import soundfile as sf
    except ModuleNotFoundError:
        raise dsp.MissingDependency("soundfile", "gravar os stems") from None
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for stem, data in stems.items():
        path = out_dir / stem_filename(prefix, stem, "wav")
        sf.write(path, data, sample_rate, subtype="FLOAT")
        paths[stem] = path
    return paths
