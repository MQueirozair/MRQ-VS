"""Avaliação objetiva da separação contra stems de referência (SDR).

Sem referência ("verdade") não dá para afirmar que um separador é bom — só
"parece bom". Este módulo calcula o SDR (signal-to-distortion ratio) entre
cada stem gerado e o stem verdadeiro, com a mesma definição usada na
literatura (BSS Eval, Vincent 2006), na forma simplificada:

    SDR = 10 log10( ||s||² / ||ŝ - s||² )

Não faz o desdobramento em SIR/SAR (exigiria projeções ortogonais); para
escolher modelo/parâmetro, o SDR já ordena corretamente — e é o que os
benchmarks públicos (MUSDB18, StemSplit) reportam.

Uso:
    python -m mrqvs.evaluate out/_demo/verdade out/_demo/projeto/stems
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from . import dsp


def sdr(reference: np.ndarray, estimate: np.ndarray) -> float:
    """SDR em dB (BSS Eval simplificado) entre referência e estimativa."""
    n = min(reference.shape[0], estimate.shape[0])
    reference = np.asarray(reference)
    estimate = np.asarray(estimate)
    ref = reference[:n].astype(np.float64)
    est = estimate[:n].astype(np.float64)
    if ref.ndim > 1 or est.ndim > 1:
        ref, est = dsp.to_mono(ref.astype(np.float32)), dsp.to_mono(est.astype(np.float32))
        n = min(ref.shape[0], est.shape[0])
        ref, est = ref[:n], est[:n]
    noise = est - ref
    num = float(np.sum(ref**2))
    den = float(np.sum(noise**2))
    if den <= 1e-12:
        return 99.0
    if num <= 1e-12:
        return -99.0
    # Traduz para a convenção da literatura (BSS Eval): SDR = SIR + SAR, com
    # a estimativa decomposta em parte "que é o alvo" (projeção s_target) e
    # erro. Sem isso, ruído não correlacionado sempre daria 0 dB — que é o
    # piso da escala, não uma medida.
    target = float(np.dot(est, ref) / num) * ref
    err = est - target
    den = float(np.sum(err**2))
    if den <= 1e-12:
        return 99.0
    return round(10.0 * np.log10(num / den), 2)


def evaluate_dir(reference_dir: Path, estimate_dir: Path) -> dict[str, float]:
    """Compara dois diretórios de WAV pelo nome do stem (ignora prefixos)."""
    import soundfile as sf

    results: dict[str, float] = {}
    refs = {_stem_key(p): p for p in Path(reference_dir).glob("*.wav")}
    ests = {_stem_key(p): p for p in Path(estimate_dir).glob("*.wav")}
    for stem, ref_path in sorted(refs.items()):
        est_path = ests.get(stem)
        if est_path is None:
            continue
        ref, _ = sf.read(str(ref_path), dtype="float32", always_2d=False)
        est, _ = sf.read(str(est_path), dtype="float32", always_2d=False)
        results[stem] = sdr(np.asarray(ref), np.asarray(est))
    if results:
        results["media"] = round(sum(v for k, v in results.items() if k != "media") / (len(results)), 2)
    return results


def _stem_key(path: Path) -> str:
    """`01_vocals.wav` / `vocals.wav` / `mix_(Vocals)_htdemucs.wav` -> `vocals`."""
    name = path.stem.lower()
    for stem in ("vocals", "instrumental", "drums", "bass", "other", "guitar", "piano", "keys"):
        if stem in name:
            return stem
    return name


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("uso: python -m mrqvs.evaluate <pasta_referencia> <pasta_stems>")
        return 2
    scores = evaluate_dir(Path(argv[0]), Path(argv[1]))
    if not scores:
        print("nenhum stem em comum entre as pastas")
        return 1
    print("SDR (dB, maior é melhor)\n")
    for stem, value in scores.items():
        bar = "#" * max(0, int((value + 5) * 2))
        print(f"  {stem:<14} {value:>7.2f}  {bar}")
    print("\nReferência de leitura: SDR < 0 dB = o stem está pior que silêncio;")
    print("3–6 dB = separação audível com vazamento; 8+ dB = boa; 10+ = muito boa.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
