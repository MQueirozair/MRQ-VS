"""Testes de acordes, compasso, guia e exportação estéreo L/R (0.1.18–0.1.21)."""

from __future__ import annotations

import sys
import types
import numpy as np
import soundfile as sf

from mrqvs import acordes, analysis, guia


def _acorde_sintetico(freqs: list[float], baixo_hz: float, sr: int = 44100, dur: float = 2.0) -> np.ndarray:
    t = np.arange(int(sr * dur)) / sr
    sinal = 0.35 * np.sin(2 * np.pi * baixo_hz * t)
    for f in freqs:
        sinal += 0.2 * np.sin(2 * np.pi * f * t)
    return sinal.astype(np.float32)


def test_grafia_bemol_vs_sustenido():
    """F maior e tons menores com bemóis devem escrever Bb/Eb, nunca A#/D#."""
    assert acordes.usar_bemol("F maior") is True
    assert acordes.usar_bemol("Bb maior") is True
    assert acordes.usar_bemol("D menor") is True
    assert acordes.usar_bemol("G menor") is True
    assert acordes.usar_bemol("G maior") is False
    assert acordes.usar_bemol("D maior") is False
    assert acordes.usar_bemol("A menor") is False
    assert acordes.usar_bemol("F# menor") is False

    assert acordes.nomes_do_acorde(10, "", bemol=True) == "Bb"
    assert acordes.nomes_do_acorde(10, "", bemol=False) == "A#"
    assert acordes.nomes_do_acorde(6, "m", bemol=False) == "F#m"


def test_por_compasso_respeita_tonalidade_em_bemol():
    sr = 44100
    # 2 compassos em 4/4 a 120 BPM (cada compasso = 2.0 s): F maior -> Bb maior
    f_maj = _acorde_sintetico([349.23, 440.00, 523.25], baixo_hz=87.31, sr=sr, dur=2.0)
    bb_maj = _acorde_sintetico([466.16, 293.66, 349.23], baixo_hz=116.54, sr=sr, dur=2.0)
    audio = np.concatenate([f_maj, bb_maj])
    batidas = [i * 0.5 for i in range(9)]

    estimados = acordes.por_compasso(audio, sr, batidas, compasso=4, tonalidade="F maior")
    assert len(estimados) == 2
    assert estimados[0]["acorde"].startswith("F")
    assert estimados[1]["acorde"].startswith("Bb"), f"esperava Bb em F maior, veio {estimados[1]}"


def test_estimativa_de_compasso_4_por_4_e_3_por_4():
    sr = 22050
    passo = 0.5  # 120 BPM
    dur = 12.0
    batidas = [round(i * passo, 4) for i in range(int(dur / passo))]

    for assinatura in (4, 3):
        sinal = np.zeros(int(sr * dur), dtype=np.float32)
        env = np.exp(-np.linspace(0, 8, int(0.04 * sr))).astype(np.float32)
        for idx, b in enumerate(batidas):
            ini = int(b * sr)
            freq = 120.0 if (idx % assinatura == 0) else 520.0
            amp = 0.9 if (idx % assinatura == 0) else 0.22
            pulso = amp * np.sin(2 * np.pi * freq * np.arange(env.size) / sr).astype(np.float32) * env
            fim = min(sinal.size, ini + pulso.size)
            sinal[ini:fim] += pulso[: fim - ini]
        comp, conf = acordes.compasso(sinal, sr, 120.0, batidas)
        assert comp == assinatura
        assert conf > 0.3


def test_compasso_com_modelo_sem_beat_this_devolve_none(tmp_path):
    wav = tmp_path / "x.wav"
    sf.write(wav, np.zeros(4410, dtype=np.float32), 44100)
    if "beat_this" not in sys.modules:
        assert acordes.compasso_com_modelo(wav) is None
        assert acordes.batidas_do_modelo(wav) == []


def test_compasso_com_modelo_mockado(tmp_path, monkeypatch):
    fake_pkg = types.ModuleType("beat_this")
    fake_inf = types.ModuleType("beat_this.inference")

    class FakeFile2Beats:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __call__(self, caminho):
            beats = np.array([i * 0.5 for i in range(16)], dtype=np.float64)
            downbeats = np.array([0.0, 1.5, 3.0, 4.5, 6.0], dtype=np.float64)  # 3/4
            return beats, downbeats

    fake_inf.File2Beats = FakeFile2Beats
    fake_pkg.inference = fake_inf
    monkeypatch.setitem(sys.modules, "beat_this", fake_pkg)
    monkeypatch.setitem(sys.modules, "beat_this.inference", fake_inf)

    wav = tmp_path / "valsa.wav"
    sf.write(wav, np.zeros(4410, dtype=np.float32), 44100)
    res = acordes.compasso_com_modelo(wav)
    assert res is not None
    comp, conf, down = res
    assert comp == 3
    assert conf >= 0.8
    assert len(down) == 5
    assert len(acordes.batidas_do_modelo(wav)) == 16


def test_guia_compor_e_escrever_audio(tmp_path):
    secoes = [
        analysis.Section(0.0, 4.0, "intro"),
        analysis.Section(4.0, 8.0, "refrao"),
    ]
    batidas = [i * 0.5 for i in range(16)]
    entradas = guia.compor(secoes, batidas, contagem=4)
    assert any(e.tipo == "anuncio" and e.valor == "Intro" for e in entradas)
    assert any(e.tipo == "anuncio" and e.valor == "Refrão" for e in entradas)
    contagens = [e.valor for e in entradas if e.tipo == "contagem"]
    assert contagens == [4, 3, 2, 1]

    destino = tmp_path / "guia.wav"
    guia.escrever_audio(destino, 44100, entradas, duracao=8.0)
    dados, sr = sf.read(destino, dtype="float32")
    assert sr == 44100
    assert dados.ndim == 1  # mono para o in-ear
    assert float(np.max(np.abs(dados))) > 0.05


def test_escrever_lr_separa_ensaio_na_esquerda_e_banda_na_direita(tmp_path):
    sr = 22050
    dur = 2.0
    n = int(sr * dur)
    ensaio = np.zeros(n, dtype=np.float32)
    ensaio[:2000] = 0.8  # só no começo (canal L)
    banda = np.zeros(n, dtype=np.float32)
    banda[n // 2 :] = 0.6  # só na segunda metade (canal R)

    lr_path = tmp_path / "ENSAIO_LR.wav"
    guia.escrever_lr(lr_path, sr, banda=banda, ensaio=ensaio, duracao=dur)
    lido, sr_out = sf.read(lr_path, dtype="float32", always_2d=True)
    assert sr_out == sr
    assert lido.shape == (n, 2)
    # No início: esquerda tem sinal, direita está em silêncio (zero vazamento do clique para o PA!)
    assert float(np.max(np.abs(lido[:2000, 0]))) > 0.5
    assert float(np.max(np.abs(lido[:2000, 1]))) < 1e-4
    # Na segunda metade: direita tem a banda, esquerda está em silêncio
    assert float(np.max(np.abs(lido[n // 2 :, 1]))) > 0.4
    assert float(np.max(np.abs(lido[n // 2 :, 0]))) < 1e-4
