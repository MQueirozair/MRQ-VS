"""Análise musical: BPM, grade de batidas, tonalidade, seções e dinâmica.

Tudo aqui roda em numpy puro (ver `dsp.py`), de propósito: a análise é a
parte que precisa funcionar **mesmo sem o modelo de IA instalado**, para o
projeto já nascer com nome/bpm corretos mesmo quando a separação vai ser
feita noutra máquina (ou só com o fallback).

Referências usadas no desenho:
- onsets por fluxo espectral + autocorrelação: abordagem clássica
  (Ellis 2007, "Beat Tracking by Dynamic Programming"; librosa usa a mesma
  ideia). A grade estrita (BPM fixo) é preferida a "beat tracking" completo
  porque aqui o destino é cortar faixas em compasso, não seguir rubato.
- tonalidade: perfil de cromagrama de Krumhansl-Kessler (pitch-class
  profiles de maior/menor) correlacionado com os 24 tons.
- seções: novidade espectral (Foote 2000) — autocorrelação da matriz de
  similaridade em diagonal, picos = mudança de seção.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import dsp

# Perfis de Krumhansl-Kessler (1967), um dos mais usados em estimativa de tom.
_MAJOR_PROFILE = [
    6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88,
]
_MINOR_PROFILE = [
    6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17,
]
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class TempoInfo:
    bpm: float
    confidence: float
    beat_times: list[float] = field(default_factory=list)
    #: quantos frames de análise entraram — usado para avisar material curto
    frames: int = 0

    @property
    def reliable(self) -> bool:
        # 0.15 é o piso empírico: abaixo disso o pulso não é claro o bastante
        # para prometer um BPM (textura, pad, música com rubato livre).
        return self.confidence >= 0.15 and self.bpm > 0

    def grid_note(self) -> str:
        return "pulso claro" if self.confidence >= 0.35 else "pulso fraco (confira)"


@dataclass
class KeyInfo:
    tonic: str
    mode: str  # "maior" | "menor"
    confidence: float
    #: correlações dos 24 tons, ordenadas — útil para diagnóstico na UI
    ranking: list[tuple[str, float]] = field(default_factory=list)

    def label(self) -> str:
        return f"{self.tonic} {self.mode}"

    def camelot(self) -> str:
        """Roda de Camelot (padrão de DJ) — bônus barato de calcular.

        Mapa fixo e conferível: 8B = Dó maior, 8A = Lá menor; cada passo
        sobe uma quinta no lado B e mantém a relativa no lado A.
        """
        major = {
            "B": 1, "F#": 2, "Db": 3, "Ab": 4, "Eb": 5, "Bb": 6,
            "F": 7, "C": 8, "G": 9, "D": 10, "A": 11, "E": 12,
        }
        minor = {
            "Ab": 1, "Eb": 2, "Bb": 3, "F": 4, "C": 5, "G": 6,
            "D": 7, "A": 8, "E": 9, "B": 10, "F#": 11, "C#": 12,
        }
        table = major if self.mode == "maior" else minor
        # Enarmônicos que a estimativa pode devolver com sustenido.
        equivalent = {"C#": "Db", "D#": "Eb", "G#": "Ab", "A#": "Bb", "Gb": "F#"}
        note = table.get(self.tonic) or table.get(equivalent.get(self.tonic, ""), 0)
        if not note:
            return "?"
        return f"{note}{'B' if self.mode == 'maior' else 'A'}"


@dataclass
class Section:
    start: float
    end: float
    #: "A", "B", "C"... por ordem de primeira aparição (rótulo de estrutura)
    label: str
    loudness_db: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Analysis:
    sample_rate: int
    duration: float
    tempo: TempoInfo
    key: KeyInfo
    sections: list[Section]
    loudness_db: float
    peak_db: float
    #: anotações honestas sobre o que não deu para medir
    notes: list[str] = field(default_factory=list)


def _chroma(spec, freqs, sample_rate: int):
    """Cromagrama de 12 classes por frame (afinação A440, temperamento igual)."""
    import numpy as np

    mag = np.abs(spec).astype(np.float32)
    # Descarta DC e o extremo agudo: sopra e ruído só atrapalham o tom.
    band = (freqs >= 55.0) & (freqs <= 2500.0)
    freqs = freqs[band]
    mag = mag[:, band]
    if freqs.size == 0:
        return np.zeros((spec.shape[0], 12), dtype=np.float32)
    midi = 69.0 + 12.0 * np.log2(freqs.astype(np.float64) / 440.0)
    classes = np.mod(np.round(midi).astype(int), 12)
    chroma = np.zeros((mag.shape[0], 12), dtype=np.float32)
    for pc in range(12):
        chroma[:, pc] = mag[:, classes == pc].sum(axis=1)
    total = chroma.sum(axis=1, keepdims=True)
    return chroma / np.maximum(total, 1e-9)


def estimate_key(chroma) -> KeyInfo:
    import numpy as np

    profile_mean = np.asarray(chroma, dtype=np.float32).mean(axis=0)
    if not profile_mean.any():
        return KeyInfo("C", "maior", 0.0, [])
    profile_mean = profile_mean - profile_mean.mean()

    def corr(profile, tonic: int) -> float:
        rotated = np.roll(np.asarray(profile, dtype=np.float32), tonic)
        rotated = rotated - rotated.mean()
        denom = np.linalg.norm(rotated) * np.linalg.norm(profile_mean)
        return float(np.dot(rotated, profile_mean) / denom) if denom > 1e-9 else 0.0

    candidates: list[tuple[str, float]] = []
    for tonic in range(12):
        for profile, mode in ((_MAJOR_PROFILE, "maior"), (_MINOR_PROFILE, "menor")):
            candidates.append((f"{_NOTE_NAMES[tonic]} {mode}", corr(profile, tonic)))
    candidates.sort(key=lambda c: c[1], reverse=True)
    best_name, best_score = candidates[0]
    tonic, _, mode = best_name.partition(" ")
    # A correlação vai de -1 a 1; 0.5+- é um tom bem definido, 0.2 é vago.
    confidence = float(max(0.0, min(1.0, best_score)))
    return KeyInfo(tonic, mode, confidence, candidates[:5])


def _novelty(spec, hop: int, sample_rate: int):
    """Curva de novidade (Foote): quão diferente é o futuro do passado."""
    import numpy as np

    mag = np.abs(spec).astype(np.float32)
    # Reduz para ~1 feature por 0.5 s: novidade de seção é lenta.
    frames_per_block = max(1, int(round(0.5 * sample_rate / hop)))
    blocks = mag.shape[0] // frames_per_block
    if blocks < 4:
        return np.zeros(max(blocks, 0), dtype=np.float32)
    feats = mag[: blocks * frames_per_block].reshape(blocks, frames_per_block, -1).mean(axis=1)
    feats = np.log1p(feats)
    feats = feats - feats.mean(axis=0)
    feats = feats / (np.linalg.norm(feats, axis=1, keepdims=True) + 1e-9)
    sim = feats @ feats.T
    # Kernel em "xadrez" (gaussiana de janela) realça mudanças, não repetições.
    size = 4
    kernel = -np.ones((size * 2, size * 2), dtype=np.float32)
    kernel[:size, :size] = 1.0
    kernel[size:, size:] = 1.0
    novelty = np.zeros(blocks, dtype=np.float32)
    for i in range(blocks):
        lo = max(0, i - size)
        hi = min(blocks, i + size)
        sub = sim[lo:hi, lo:hi]
        k = kernel[: sub.shape[0], : sub.shape[1]]
        novelty[i] = float((sub * k).sum())
    novelty = np.maximum(novelty, 0.0)
    return novelty / (novelty.max() + 1e-9)


def estimate_sections(
    spec,
    hop: int,
    sample_rate: int,
    duration: float,
    max_sections: int = 12,
    energy=None,
) -> list[Section]:
    import numpy as np

    novelty = _novelty(spec, hop, sample_rate)
    block_seconds = 0.5
    if novelty.size < 4 or duration < 6:
        return [Section(0.0, duration, "A")] if duration > 0 else []

    # Picos de novidade separados por pelo menos ~8 s (nada de micro-cortes).
    min_gap = max(1, int(round(8.0 / block_seconds)))
    order = np.argsort(novelty)[::-1]
    picks: list[int] = []
    for idx in order:
        if novelty[idx] < 0.15:  # ruído de fundo da curva
            break
        if all(abs(int(idx) - p) >= min_gap for p in picks):
            picks.append(int(idx))
        if len(picks) >= max_sections - 1:
            break
    boundaries = [0] + sorted(p * block_seconds for p in picks) + [duration]
    boundaries = [b for i, b in enumerate(boundaries) if i == 0 or b > boundaries[i - 1] + 1.0]

    sections: list[Section] = []
    labels: list[str] = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        if end - start < 1.0:
            continue
        # Rótulo por similaridade de conteúdo: seções com a mesma "cara"
        # espectral dividem a letra (verso/refrão ficam com o mesmo nome,
        # que é o que interessa para leitura da estrutura).
        label = "A"
        if sections:
            label = _match_label(spec, hop, sample_rate, sections, start, end, labels)
        sections.append(Section(round(start, 2), round(min(end, duration), 2), label))
        if label not in labels:
            labels.append(label)
    sections = _merge_sections(sections)
    if energy is not None:
        for s in sections:
            s.loudness_db = _loudness_in(energy, sample_rate, s.start, s.end)
    return sections


def _merge_sections(sections: list[Section], min_len: float = 2.0) -> list[Section]:
    """Junta vizinhas de mesmo rótulo e absorve trechos curtos demais.

    Sem isso o relatório sai com "A | A | A" (o kernel de novidade reage a
    dois lados de uma fronteira) e com uma seção de 0,5 s na borda, que não
    é estrutura musical — é efeito do detector.
    """
    merged: list[Section] = []
    for section in sections:
        if merged and (section.label == merged[-1].label or section.duration < min_len):
            merged[-1].end = section.end
        else:
            merged.append(section)
    # Depois de absorver, uma primeira seção pode ter ficado grande demais
    # por causa de um rótulo repetido: nada a fazer, o rótulo é aproximado.
    return [Section(s.start, s.end, s.label, s.loudness_db) for s in merged]


def _fingerprint(spec, hop: int, sample_rate: int, start: float, end: float):
    import numpy as np

    a = int(start * sample_rate / hop)
    b = max(a + 1, int(end * sample_rate / hop))
    mag = np.abs(spec[a:b]).astype(np.float32)
    if mag.size == 0:
        return np.zeros(spec.shape[1], dtype=np.float32)
    v = np.log1p(mag.mean(axis=0))
    return v / (np.linalg.norm(v) + 1e-9)


def _match_label(spec, hop, sample_rate, sections, start, end, labels) -> str:
    import numpy as np

    fp = _fingerprint(spec, hop, sample_rate, start, end)
    best, best_score = "A", -1.0
    for s, label in zip(sections, labels):
        other = _fingerprint(spec, hop, sample_rate, s.start, s.end)
        score = float(np.dot(fp, other))
        if score > best_score:
            best, best_score = label, score
    if best_score >= 0.85:  # mesmo material
        return best
    alphabet = "ABCDEFGHIJKL"
    return alphabet[min(len(set(labels)), len(alphabet) - 1)]


def _loudness_in(energy, sample_rate: int, start: float, end: float) -> float:

    a = max(0, int(start * sample_rate))
    b = min(energy.shape[0], int(end * sample_rate))
    seg = energy[a:b]
    return round(dsp.db_rms(seg), 1) if seg.size else 0.0


def analyse(mix, sample_rate: int, n_fft: int = 2048, hop: int | None = None) -> Analysis:
    """Pipeline completo de análise de um mix mono (ou estéreo -> mono)."""
    require = dsp.require_numpy
    require("analisar o áudio")
    import numpy as np

    mono = dsp.to_mono(np.asarray(mix, dtype=np.float32))
    hop = hop or n_fft // 4
    spec = dsp.stft(mono, n_fft=n_fft, hop=hop)
    freqs = dsp.stft_freqs(n_fft, sample_rate)

    env = dsp.onset_envelope(spec, sample_rate, hop)
    bpm, confidence = dsp.tempo_from_onset_envelope(env, hop, sample_rate)
    beats = dsp.beat_grid(sample_rate, bpm, mono.shape[0] / sample_rate) if bpm > 0 else []
    duration = mono.shape[0] / sample_rate

    chroma = _chroma(spec, freqs, sample_rate)
    key = estimate_key(chroma)
    sections = estimate_sections(spec, hop, sample_rate, duration, energy=mono)
    notes: list[str] = []
    if duration < 10:
        notes.append("áudio com menos de 10 s: BPM e seções podem sair imprecisos")
    if bpm <= 0 or confidence < 0.15:
        notes.append("não foi possível determinar um pulso estável — BPM marcado como desconhecido")
    if key.confidence < 0.25:
        notes.append("tonalidade pouco definida (material muito percussivo ou ruidoso)")
    return Analysis(
        sample_rate=sample_rate,
        duration=round(duration, 3),
        tempo=TempoInfo(round(bpm, 1), round(confidence, 3), beats, env.size),
        key=key,
        sections=sections,
        loudness_db=round(dsp.db_rms(mono), 1),
        peak_db=round(dsp.gain_to_db(dsp.peak(mono)), 1),
        notes=notes,
    )
