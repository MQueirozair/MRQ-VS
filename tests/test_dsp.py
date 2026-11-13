import numpy as np
import pytest

from mrqvs import dsp


def _snr_db(reference, estimate):
    err = estimate - reference
    return 20 * np.log10(np.sqrt(np.mean(reference**2)) / np.sqrt(np.mean(err**2)))


def test_stft_roundtrip_reconstrói_o_sinal():
    rng = np.random.default_rng(1)
    signal = (rng.standard_normal(20000) * 0.1).astype(np.float32)
    spec = dsp.stft(signal, n_fft=2048, hop=512)
    back = dsp.istft(spec, n_fft=2048, hop=512, length=signal.shape[0])
    assert back.shape == signal.shape
    assert _snr_db(signal, back) > 30


def test_stft_cobre_o_final_do_sinal():
    """O último trecho precisa estar na análise (senão a soma das máscaras
    não reconstrói o arquivo inteiro)."""
    signal = np.ones(1000, dtype=np.float32)
    spec = dsp.stft(signal, n_fft=512, hop=128)
    frames = spec.shape[0]
    assert 512 + 128 * (frames - 1) >= len(signal)


def test_median_filters_shapes_preservados():
    spec = np.ones((50, 40), dtype=np.float32)
    assert dsp.median_filter_harmonic(spec, 9).shape == spec.shape
    assert dsp.median_filter_percussive(spec, 9).shape == spec.shape


def test_soft_mask_soma_um_e_vai_de_zero_a_um():
    a = np.array([1.0, 2.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 3.0], dtype=np.float32)
    m = dsp.soft_mask(a, b, power=1.0)
    assert np.allclose(dsp.soft_mask(a, b, 1.0) + dsp.soft_mask(b, a, 1.0), 1.0, atol=1e-5)
    assert m.min() >= 0.0 and m.max() <= 1.0


@pytest.mark.parametrize("bpm", [80.0, 96.0, 120.0, 140.0])
def test_tempo_recupera_bpm_de_pulsos_sinteticos(bpm):
    sr, hop = 44100, 512
    frames = int(sr / hop * 12)
    env = np.zeros(frames, dtype=np.float32)
    period = 60.0 / bpm * sr / hop
    for i in range(frames):
        phase = i % period
        env[i] = 1.0 if phase < 1.0 else 0.0
    got, conf = dsp.tempo_from_onset_envelope(env, hop, sr)
    assert conf > 0.1
    # aceita a mesma batida em outra oitava (dobro/metade)
    assert min(abs(got - bpm), abs(got - 2 * bpm), abs(got - bpm / 2)) < 3.0


def test_tempo_sem_pulso_devolve_desconhecido():
    env = np.zeros(500, dtype=np.float32)
    assert dsp.tempo_from_onset_envelope(env, 512, 44100) == (0.0, 0.0)


def test_beat_times_grade_regular():
    env = np.ones(4000, dtype=np.float32)
    beats = dsp.beat_times(env, 512, 44100, 120.0)
    assert len(beats) > 5
    diffs = np.diff(beats)
    assert np.allclose(diffs, 0.5, atol=1e-3)


def test_to_mono_e_to_stereo():
    stereo = np.stack([np.ones(10, np.float32), -np.ones(10, np.float32)], axis=1)
    assert np.allclose(dsp.to_mono(stereo), 0.0)
    assert dsp.to_stereo(np.ones(10, np.float32)).shape == (10, 2)


def test_resample_linear_muda_tamanho_e_preserva_tom_relativo():
    t = np.arange(44100) / 44100.0
    signal = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    out = dsp.resample_linear(signal, 44100, 22050)
    assert out.shape[0] == 22050
    # Energia preservada com erro pequeno
    assert abs(np.sqrt(np.mean(out**2)) - np.sqrt(np.mean(signal**2))) < 0.02


def test_normalize_peak_deixa_no_alvo():
    signal = (np.random.default_rng(0).standard_normal(1000) * 4).astype(np.float32)
    out = dsp.normalize_peak(signal, -1.0)
    assert abs(dsp.gain_to_db(dsp.peak(out)) + 1.0) < 0.01


def test_fade_nao_estoura_tamanho_curto():
    out = dsp.fade(np.ones(3, np.float32), 44100, 0.01, 0.01)
    assert out.shape == (3,)


def test_missing_dependency_tem_instrucao():
    exc = dsp.MissingDependency("soxr", "reamostrar")
    assert "pip install soxr" in str(exc)
