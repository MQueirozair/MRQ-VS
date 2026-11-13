import numpy as np
import pytest

from mrqvs import analysis, evaluate
from mrqvs.stems import MODEL_STEMS, STEM_ORDER, STEMS, native_stems, resolve_stems


def test_todo_stem_do_catalogo_tem_metadados():
    assert set(STEMS) == set(STEM_ORDER)
    for stem, info in STEMS.items():
        assert info.id == stem
        assert info.label and info.description
        assert info.color.startswith("#") and len(info.color) == 7


def test_todo_derivado_aponta_para_stem_que_existe():
    for info in STEMS.values():
        for parent in info.derived_from:
            assert parent in STEMS or parent == "mix"


def test_resolve_stems_auto_usa_nativos_do_modelo():
    native, derived, missing = resolve_stems([], "htdemucs_6s")
    assert set(native) == set(native_stems("htdemucs_6s"))
    assert derived == [] and missing == []


def test_resolve_stems_gera_derivados_transitivos():
    # `loops` vem de `other`; `other` é nativo de htdemucs.
    native, derived, missing = resolve_stems(["loops"], "htdemucs")
    assert native == ["other"] and derived == ["loops"] and missing == []
    # Já `kick` só existe derivado de `drums`: pedir o derivado traz o pai.
    native2, derived2, _ = resolve_stems(["kick"], "htdemucs")
    assert native2 == ["drums"] and derived2 == ["kick"]


def test_resolve_stems_reporta_o_que_nao_existe_no_modelo():
    native, derived, missing = resolve_stems(["vocals", "guitar", "piano"], "htdemucs")
    assert native == ["vocals"]
    assert missing == ["guitar", "piano"]


def test_modelo_de_6_stems_cobre_guitarra_e_piano():
    assert {"guitar", "piano"} <= set(MODEL_STEMS["htdemucs_6s"])
    assert "guitar" not in MODEL_STEMS["htdemucs"]


def test_native_stems_de_modelo_desconhecido_e_vazio():
    assert native_stems("modelo-que-nao-existe") == ()


def _tonal_signal(freqs, sr=44100, seconds=4.0):
    t = np.arange(int(sr * seconds)) / sr
    out = np.zeros_like(t, dtype=np.float32)
    for f in freqs:
        out += np.sin(2 * np.pi * f * t).astype(np.float32)
    return out / (len(freqs) + 1)


def test_analise_detecta_bpm_e_estrutura():
    sr = 44100
    beat = 0.5  # 120 BPM
    n = int(sr * 8)
    track = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(3)
    click = (rng.standard_normal(int(0.02 * sr)).astype(np.float32) * np.linspace(1, 0, int(0.02 * sr)))
    for i in range(int(8 / beat)):
        start = int(i * beat * sr)
        track[start : start + click.size] += click
    result = analysis.analyse(track, sr)
    assert 118 <= result.tempo.bpm <= 122
    assert result.tempo.beat_times
    assert result.duration == pytest.approx(8.0, abs=0.01)


def test_analise_devolve_tonalidade_do_acorde_de_dó():
    result = analysis.analyse(_tonal_signal([261.63, 329.63, 392.0]), 44100)
    assert result.key.tonic == "C"
    assert result.key.mode == "maior"
    assert 0.0 <= result.key.confidence <= 1.0


def test_analise_silencio_nao_explode():
    result = analysis.analyse(np.zeros(44100, dtype=np.float32), 44100)
    assert result.tempo.bpm == 0.0
    assert result.tempo.reliable is False
    assert result.notes  # avisa que não deu para medir


def test_secoes_cobrem_a_duracao_sem_buraco():
    sr = 44100
    signal = _tonal_signal([220.0, 277.18], seconds=6)
    result = analysis.analyse(signal, sr)
    assert result.sections
    assert result.sections[0].start == 0.0
    assert result.sections[-1].end == pytest.approx(result.duration, abs=0.05)
    for a, b in zip(result.sections, result.sections[1:]):
        assert b.start >= a.end - 1e-6


def test_camelot_mapeia_tons_conhecidos():
    assert analysis.KeyInfo("C", "maior", 0.9).camelot() == "8B"
    assert analysis.KeyInfo("A", "menor", 0.9).camelot() == "8A"
    assert analysis.KeyInfo("C", "maior", 0.0).label() == "C maior"


def test_sdr_perfeito_e_ruim():
    rng = np.random.default_rng(0)
    ref = rng.standard_normal(2000).astype(np.float32)
    assert evaluate.sdr(ref, ref) > 90
    # Ruído não correlacionado fica no piso da escala (~0 dB), não "menos".
    assert evaluate.sdr(ref, rng.standard_normal(2000).astype(np.float32)) < 3.0


def test_sdr_ignora_diferenca_de_ganho():
    rng = np.random.default_rng(0)
    ref = rng.standard_normal(2000).astype(np.float32)
    assert evaluate.sdr(ref, ref * 3.0) > 5.0
