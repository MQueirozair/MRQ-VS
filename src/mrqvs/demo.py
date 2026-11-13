"""Faixa de demonstração sintética — para testar sem internet nem modelo.

`python -m mrqvs.demo` gera `out/_demo/demo_mix.wav`: 24 s em 96 BPM com
bumbo, caixa, chimbal, baixo, acordes e uma "voz" (senoide com vibrato e
formantes). Serve para três coisas:

* conferir o pipeline inteiro (análise -> stems -> relatório) numa máquina
  sem torch;
* validar a extração de BPM (o valor certo é 96) e de tonalidade;
* testar instrumentos *conhecidos*: se a "voz" sintética não cair no stem de
  vocais, a máscara está errada, e isso é um teste de regressão, não um gosto.

O mix é montado somando os stems "verdadeiros" — o arquivo ideal para medir
quanto de cada fonte o separador realmente recupera (`mrqvs.evaluate`).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

BPM = 96.0
DURATION = 24.0
SAMPLE_RATE = 44100
#: Progressão I–V–vi–IV em Dó (C, G, Am, F), um acorde por compasso. É um
#: loop **deliberadamente ambíguo** para detecção de tom (o mesmo material
#: também se lê como F maior ou Lá menor) — serve para exercitar o relatório
#: de confiança em vez de fingir que tonalidade é sempre trivial.
CHORDS = [
    [261.63, 329.63, 392.00],
    [196.00, 246.94, 392.00],
    [220.00, 261.63, 329.63],
    [174.61, 220.00, 349.23],
]
ROOT = [130.81, 98.00, 110.00, 87.31]  # fundamental do baixo por acorde


def _env(n: int, attack: float, decay: float, sample_rate: int) -> np.ndarray:
    t = np.arange(n) / sample_rate
    a = np.clip(t / max(attack, 1e-4), 0.0, 1.0)
    return (a * np.exp(-t / max(decay, 1e-4))).astype(np.float32)


def _place(track: np.ndarray, start: float, piece: np.ndarray, sample_rate: int) -> None:
    i = int(start * sample_rate)
    end = min(track.shape[0], i + piece.shape[0])
    if end > i:
        track[i:end] += piece[: end - i]


def build() -> dict[str, np.ndarray]:
    """Devolve os stems verdadeiros (mono, float32) e o mix somado."""
    sr = SAMPLE_RATE
    n = int(DURATION * sr)
    beat = 60.0 / BPM
    bar = 4 * beat
    rng = np.random.default_rng(20261109)

    kick = np.zeros(n, np.float32)
    snare = np.zeros(n, np.float32)
    hihat = np.zeros(n, np.float32)
    bass = np.zeros(n, np.float32)
    keys = np.zeros(n, np.float32)
    vocals = np.zeros(n, np.float32)

    t = np.arange(int(0.35 * sr)) / sr
    kick_piece = (np.sin(2 * np.pi * (55 + 60 * np.exp(-t * 40)) * t) * _env(t.size, 0.002, 0.09, sr)).astype(np.float32)
    snare_piece = (
        (rng.standard_normal(t.size).astype(np.float32) * 0.7 + np.sin(2 * np.pi * 190 * t).astype(np.float32) * 0.4)
        * _env(t.size, 0.001, 0.06, sr)
    ).astype(np.float32)
    hat_piece = (rng.standard_normal(int(0.06 * sr)).astype(np.float32) * _env(int(0.06 * sr), 0.0005, 0.012, sr)).astype(np.float32)

    bars = int(DURATION / bar)
    for b in range(bars):
        base = b * bar
        _place(kick, base, kick_piece * 0.9, sr)
        _place(kick, base + 1.5 * beat, kick_piece * 0.75, sr)
        _place(kick, base + 2.5 * beat, kick_piece * 0.7, sr)
        _place(snare, base + beat, snare_piece * 0.6, sr)
        _place(snare, base + 3 * beat, snare_piece * 0.6, sr)
        for eighth in range(8):
            _place(hihat, base + eighth * beat / 2, hat_piece * (0.25 if eighth % 2 else 0.15), sr)
        # baixo: fundamental em colcheias
        chord = b % len(CHORDS)
        for eighth in range(8):
            freq = ROOT[chord] * (2.0 if eighth in (3, 7) else 1.0)
            notes_n = int(beat / 2 * sr)
            tt = np.arange(notes_n) / sr
            tone = (np.sin(2 * np.pi * freq * tt) + 0.3 * np.sin(4 * np.pi * freq * tt)) * _env(notes_n, 0.01, 0.18, sr)
            _place(bass, base + eighth * beat / 2, tone.astype(np.float32) * 0.5, sr)
        # acordes no tempo 1 e 3
        for offset in (0.0, 2 * beat):
            notes_n = int(2 * beat * sr)
            tt = np.arange(notes_n) / sr
            chord_sig = np.zeros(notes_n, np.float32)
            for f in CHORDS[chord]:
                chord_sig += np.sin(2 * np.pi * f * tt).astype(np.float32)
                chord_sig += 0.25 * np.sin(2 * np.pi * 2 * f * tt).astype(np.float32)
            _place(keys, base + offset, chord_sig * _env(notes_n, 0.02, 0.5, sr) * 0.18, sr)
        # "voz": melodia em frases de 2 compassos, com vibrato
        if b % 2 == 0:
            melody = [440.0, 392.0, 349.23, 392.0]
            for i, f in enumerate(melody):
                notes_n = int(beat * 0.9 * sr)
                tt = np.arange(notes_n) / sr
                vib = 1.0 + 0.008 * np.sin(2 * np.pi * 5.5 * tt)
                sig = np.sin(2 * np.pi * f * vib * tt).astype(np.float32)
                sig += 0.45 * np.sin(2 * np.pi * 2 * f * vib * tt).astype(np.float32)
                sig += 0.15 * np.sin(2 * np.pi * 3 * f * vib * tt).astype(np.float32)
                _place(vocals, base + i * beat, sig * _env(notes_n, 0.04, 0.4, sr) * 0.22, sr)

    stems = {
        "vocals": vocals,
        "drums": kick + snare + hihat,
        "bass": bass,
        "other": keys,
    }
    # Escala única para todos os stems: o mix não pode clipar (clipping
    # destrói a soma das máscaras e faria o teste de reconstrução mentir).
    total = sum(stems.values())
    gain = 0.89 / max(float(np.abs(total).max()), 1e-9)
    stems = {name: (signal * gain).astype(np.float32) for name, signal in stems.items()}
    mix = sum(stems.values()).astype(np.float32)
    return {"stems": stems, "mix": mix, "sample_rate": sr}


def write(path: Path | None = None) -> Path:
    import soundfile as sf

    data = build()
    path = path or Path("out/_demo/demo_mix.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data["mix"], data["sample_rate"], subtype="PCM_16")
    truth = path.parent / "verdade"
    truth.mkdir(exist_ok=True)
    for name, signal in data["stems"].items():
        sf.write(truth / f"{name}.wav", signal, data["sample_rate"], subtype="FLOAT")
    return path


if __name__ == "__main__":
    out = write()
    print(f"demo gerada: {out} ({DURATION:.0f}s, {BPM:.0f} BPM, Dó maior)")
    print(f"stems de referência em {out.parent / 'verdade'}")
