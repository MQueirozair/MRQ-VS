import shutil

import numpy as np
import pytest

from mrqvs import demo, derive, dsp, export, separator


@pytest.fixture(scope="module")
def demo_data():
    return demo.build()


def _corr(a, b):
    n = min(len(a), len(b))
    a, b = np.asarray(a[:n], np.float64), np.asarray(b[:n], np.float64)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def _snr_db(reference, estimate):
    err = estimate - reference
    return 20 * np.log10(np.sqrt(np.mean(reference**2)) / np.sqrt(np.mean(err**2)))


def test_backend_dsp_sempre_disponivel():
    statuses = {s.name: s for s in separator.detect_backends()}
    assert statuses["dsp-fallback"].available
    assert "demucs" in statuses and "audio-separator" in statuses


def test_choose_backend_respeita_escolha_explicita():
    assert separator.choose_backend("dsp-fallback") == "dsp-fallback"
    with pytest.raises(ValueError):
        separator.choose_backend("modelo-magico")


def test_demo_tem_bpm_conhecido(demo_data):
    assert demo_data["mix"].shape[0] == int(demo.SAMPLE_RATE * demo.DURATION)
    assert np.abs(demo_data["mix"]).max() < 1.0  # sem clipping


def test_stems_dsp_reconstroem_o_mix(demo_data):
    mix = demo_data["mix"]
    stems = separator.separate_dsp(mix, demo.SAMPLE_RATE)
    assert set(stems) == {"vocals", "drums", "bass", "other"}
    total = sum(stems.values())
    assert total.shape == mix.shape
    # Partição por máscaras que somam 1: o mix tem que voltar quase igual.
    assert _snr_db(mix, total) > 30


def test_stems_dsp_acham_o_conteudo_certo(demo_data):
    """Cada stem gerado deve parecer mais com a sua fonte real do que com as outras."""
    mix = demo_data["mix"]
    truth = demo_data["stems"]
    stems = separator.separate_dsp(mix, demo.SAMPLE_RATE)
    for name, estimate in stems.items():
        # Correlação (e não SDR) porque basear a decisão na projeção ortogonal
        # premia qualquer coisa que "contenha" a referência — para decidir
        # *qual* fonte o stem representa, correlação é a métrica certa.
        scores = {other: _corr(reference, estimate) for other, reference in truth.items()}
        best = max(scores, key=scores.get)
        assert best == name, f"{name} ficou mais parecido com {best}: {scores}"


def test_drums_split_soma_aproximadamente_o_stem(demo_data):
    drums = demo_data["stems"]["drums"]
    parts = derive.split_drums(drums, demo.SAMPLE_RATE)
    assert set(parts) == {"kick", "snare", "hihat", "percussion"}
    total = sum(parts.values())
    assert total.shape == drums.shape
    assert _snr_db(drums, total) > 10  # aproximado, mas não pode ser aleatório


def test_instrumental_e_mix_menos_vocais(demo_data):
    mix, vocals = demo_data["mix"], demo_data["stems"]["vocals"]
    inst = derive.derive_instrumental(mix, vocals)
    esperado = mix - vocals
    # O instrumental leva fade curto nas pontas (evita clique), então a
    # comparação olha o miolo do arquivo.
    meio = slice(4410, len(esperado) - 4410)
    assert np.allclose(inst[meio], esperado[meio], atol=1e-5)
    assert np.abs(inst).max() < 1.5


def test_derive_stems_nao_inventa_stem_sem_pai(demo_data):
    stems, warnings = derive.derive_stems({"vocals": demo_data["stems"]["vocals"]}, demo.SAMPLE_RATE, ["kick", "fx"])
    assert stems == {}
    assert len(warnings) == 2


def test_extract_loops_encontra_repeticao():
    sr = 44100
    rng = np.random.default_rng(7)
    loop = (rng.standard_normal(int(0.5 * sr)) * 0.1).astype(np.float32)
    track = np.concatenate([loop, np.zeros(sr, np.float32), loop, np.zeros(sr, np.float32), loop])
    audio, spans = derive.extract_loops(track, sr)
    assert len(spans) >= 3
    assert audio.shape == track.shape
    assert np.abs(audio).max() > 0


def test_extract_loops_sem_repeticao_devolve_vazio():
    sr = 44100
    noise = np.random.default_rng(1).standard_normal(sr * 3).astype(np.float32) * 0.1
    _, spans = derive.extract_loops(noise, sr)
    assert spans == []


def test_formato_invalido_e_rejeitado():
    with pytest.raises(ValueError):
        export.ExportOptions(fmt="flac")


def test_bitrate_padrao_por_formato():
    assert export.ExportOptions(fmt="mp3").bitrate == "320k"
    assert export.ExportOptions(fmt="mp4").bitrate == "256k"
    assert export.ExportOptions(fmt="mp3", bitrate="128k").bitrate == "128k"


def test_export_wav_escreve_arquivo(tmp_path):
    data = (np.sin(np.arange(4410) / 44100 * 2 * np.pi * 440) * 0.5).astype(np.float32)
    path = export.export_audio(data, 44100, tmp_path / "teste", export.ExportOptions(fmt="wav", bits=16))
    assert path.exists() and path.suffix == ".wav"
    import soundfile as sf

    back, sr = sf.read(str(path), dtype="float32")
    assert sr == 44100
    assert back.shape[0] == data.shape[0]


def test_capacidade_de_export_sem_ffmpeg(monkeypatch):
    ok_wav, _ = export.check_export_capabilities("wav")
    assert ok_wav
    if not shutil.which("ffmpeg"):  # ambiente sem ffmpeg
        ok_mp3, motivo = export.check_export_capabilities("mp3")
        assert ok_mp3 is False
        assert "ffmpeg" in motivo
    monkeypatch.setattr(export.media, "have_ffmpeg", lambda: False)
    ok_mp3, motivo = export.check_export_capabilities("mp3")
    assert ok_mp3 is False
    assert "ffmpeg" in motivo


def _install_fake_ffmpeg(tmp_path, monkeypatch, supports=("libmp3lame", "libx264")):
    """Cria um `ffmpeg` falso no PATH e devolve a pasta de binários.

    Permite testar a montagem das linhas de comando e o caminho de exportação
    em MP3/MP4 numa máquina sem ffmpeg — que é justamente onde um argumento
    errado passaria batido até alguém tentar exportar.
    """
    import os
    import stat

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "ffmpeg"
    script.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  if [ "$a" = "-encoders" ]; then\n'
        + "".join(f"    echo '{name}'\n" for name in supports)
        + "    exit 0\n"
        "  fi\n"
        "done\n"
        'last=""\n'
        'for a in "$@"; do last="$a"; done\n'
        'case "$last" in\n'
        '  *.mp3|*.mp4|*.wav) : > "$last" ;;\n'
        "esac\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


def test_export_mp3_monta_o_comando(tmp_path, monkeypatch):
    data = (np.sin(np.arange(4410) / 44100 * 2 * np.pi * 440) * 0.4).astype(np.float32)
    _install_fake_ffmpeg(tmp_path, monkeypatch)
    ok, why = export.check_export_capabilities("mp3")
    assert ok, why
    out = export.export_audio(
        data, 44100, tmp_path / "faixa", export.ExportOptions(fmt="mp3", title="T", artist="A", bpm=96)
    )
    assert out.suffix == ".mp3" and out.exists()


def test_export_mp4_cai_para_fundo_solido_sem_showwaves(tmp_path, monkeypatch):
    """Sem o filtro `showwaves` a exportação não pode falhar."""
    data = np.zeros(4410, dtype=np.float32)
    bin_dir = _install_fake_ffmpeg(tmp_path, monkeypatch)
    # ffmpeg falso que falha quando vê showwaves (simula build sem o filtro)
    (bin_dir / "ffmpeg").write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do [ "$a" = "-encoders" ] && { echo libx264; exit 0; }; done\n'
        'for a in "$@"; do case "$a" in *showwaves*) exit 1;; esac; done\n'
        'last=""; for a in "$@"; do last="$a"; done\n'
        'case "$last" in *.mp3|*.mp4|*.wav) : > "$last" ;; esac\n'
        "exit 0\n"
    )
    out = export.export_audio(data, 44100, tmp_path / "clip", export.ExportOptions(fmt="mp4"))
    assert out.suffix == ".mp4" and out.exists()


def test_export_sem_ffmpeg_falha_cedo(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "vazio"))
    assert export.check_export_capabilities("mp3")[0] is False
    with pytest.raises(export.FFmpegMissing):
        export.export_audio(np.zeros(100, np.float32), 44100, tmp_path / "x", export.ExportOptions(fmt="mp3"))


def test_runtime_congelado_nao_chama_o_proprio_executavel(monkeypatch):
    """Num PyInstaller onefile, `sys.executable` é o mrq-vs.exe.

    Chamar `[sys.executable, "-m", "demucs"]` reiniciaria o app em laço; o
    `runtime` tem que resolver o Python do sistema nesse caso.
    """
    from mrqvs import runtime

    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "python3" else None)
    assert runtime.is_frozen() is True
    assert runtime.python_cmd() == "/usr/bin/python3"
    assert runtime.module_command("demucs", "x") == ["/usr/bin/python3", "-m", "demucs", "x"]

    monkeypatch.setattr(runtime.shutil, "which", lambda name: None)
    assert runtime.python_cmd() is None
    assert runtime.module_command("demucs") is None
    assert "nenhum Python" in runtime.interpreter_note()


def test_release_detecta_a_plataforma(tmp_path):
    from mrqvs import release

    tag = release._platform_tag()
    assert tag.split("-")[0] in {"linux", "macos", "windows"}
    assert tag.split("-")[1] in {"x64", "arm64"} or len(tag.split("-")[1]) > 0
    guide = release.guide_text(tag)
    assert release.VERSION in guide
    assert "ffmpeg" in guide and "demucs" in guide


# --- memória: o bug real do "Unable to allocate 7.87 GiB" ------------------


def test_hpss_em_blocos_e_igual_ao_calculo_de_uma_vez():
    """A versão em blocos (que cabe na memória) tem que ser idêntica."""
    rng = np.random.default_rng(7)
    for forma, largura in (((200, 80), 31), ((20, 8), 5), ((400, 300), 31)):
        spec = rng.random(forma, dtype=np.float32) + 0.05
        half = largura // 2
        harmonico = np.median(
            np.lib.stride_tricks.sliding_window_view(
                np.pad(spec, ((half, half), (0, 0)), mode="edge"), largura, axis=0
            ),
            axis=-1,
        )
        percussivo = np.median(
            np.lib.stride_tricks.sliding_window_view(
                np.pad(spec, ((0, 0), (half, half)), mode="edge"), largura, axis=1
            ),
            axis=-1,
        )
        esperado_h = dsp.soft_mask(harmonico, percussivo, power=1.0)
        esperado_p = 1.0 - esperado_h
        for bloco in (999, 512, 64, 7, 1):
            mask_h, mask_p = dsp.hpss_masks(spec, width=largura, bloco=bloco)
            assert np.allclose(mask_h, esperado_h, atol=1e-6), (forma, bloco)
            assert np.allclose(mask_p, esperado_p, atol=1e-6), (forma, bloco)


def test_hpss_mascara_unica_e_a_mesma_coisa():
    spec = np.random.default_rng(3).random((120, 40), dtype=np.float32) + 0.05
    so_h = dsp.hpss_masks(spec, width=15, apenas_harmonica=True)
    com_p = dsp.hpss_masks(spec, width=15)
    assert np.allclose(so_h, com_p[0], atol=1e-7)
    assert np.allclose(com_p[1], 1.0 - com_p[0], atol=1e-7)


def test_mediana_nao_copia_o_espectrograma_inteiro():
    """`np.median` na janela deslizante pedia 7,87 GiB; aqui não pode."""
    import tracemalloc

    spec = np.random.default_rng(5).random((600, 300), dtype=np.float32)
    tracemalloc.start()
    try:
        dsp.hpss_masks(spec, width=31, bloco=64)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # O `np.median` antigo materializava a janela deslizante inteira
    # (`(600, 300, 31)` = 22 MB aqui; 7,87 GiB na música do usuário). Aqui o
    # pico é de alguns blocos, não do espectrograma multiplicado pela janela.
    assert pico < spec.nbytes * 20, f"{pico / 2**20:.0f} MB"


def test_stft_e_istft_em_blocos_reconstroem_sinal_longo():
    sinal = np.random.default_rng(11).standard_normal(200003).astype(np.float32)
    spec = dsp.stft(sinal)
    volta = dsp.istft(spec, length=sinal.shape[0])
    # fora da primeira janela (onde a janela de Hann vale 0) o sinal volta
    assert np.abs(volta[4096:] - sinal[4096:]).max() < 1e-5


def test_separacao_em_trechos_bate_com_a_de_uma_passada():
    """O gerador por blocos (caminho do app) == cálculo todo em memória.

    Era o risco da mudança: blocos com normalização errada nas emendas
    produziam áudio com ganho 1e8. O teste comparara as duas rotas.
    """
    d = demo.build()
    mix = np.asarray(d["mix"], np.float32)
    inteiro = separator.separate_dsp(mix, demo.SAMPLE_RATE)
    pedacos = {nome: [] for nome in separator.NOMES_STEMS}
    for nomes, trechos in separator._separar_blocos(mix, demo.SAMPLE_RATE):
        for nome, trecho in zip(nomes, trechos):
            pedacos[nome].append(np.asarray(trecho)[:, 0])
    for nome in separator.NOMES_STEMS:
        em_blocos = np.concatenate(pedacos[nome])
        assert em_blocos.shape == inteiro[nome].shape
        assert np.abs(em_blocos - inteiro[nome]).max() < 1e-6, nome


def test_norm_por_bloco_inclui_o_pre_roll():
    """Sem os quadros anteriores, a normalização recomeça do zero e o áudio
    sai amplificado nas emendas (hop = n_fft/4 => 4 janelas por amostra)."""
    n_fft, hop, n = 4096, 1024, 64
    janela = dsp.hann(n_fft)
    norm = separator._norm_bloco(10, n, hop, n_fft, janela, np)
    # interior: soma de 4 janelas de Hann ao quadrado = 1.5
    assert abs(float(norm[4 * hop]) - 1.5) < 1e-3


def test_separacao_de_faixa_longa_nao_estoura_memoria(tmp_path):
    """710 s em estéreo era o caso que derrubava o app. Precisa terminar com
    pico limitado — não com `Unable to allocate 7.87 GiB`."""
    import tracemalloc

    sr = 8000  # mesmo problema, só menor para o teste rodar rápido
    dur = 120
    t = np.arange(sr * dur) / sr
    x = (0.3 * np.sin(2 * np.pi * 70 * t) + 0.2 * np.sin(2 * np.pi * 550 * t)).astype(
        np.float32
    )
    est = np.stack([x, x * 0.5], axis=1)
    tracemalloc.start()
    try:
        for _nomes, trechos in separator._separar_blocos(est, sr):
            for trecho in trechos:
                assert np.isfinite(trecho).all()
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # O pico é do tamanho do bloco, não da música: fica limitado e cresce
    # muito devagar com a duração (era isso que estourava em 710 s).
    assert pico < 400 * 2**20, f"{pico / 2**20:.0f} MB"
    assert pico < est.nbytes * 100, f"{pico / 2**20:.0f} MB para {est.nbytes / 2**20:.0f} MB de áudio"
