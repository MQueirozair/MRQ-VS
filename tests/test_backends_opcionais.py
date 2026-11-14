"""Badges de backend: alternativa ausente é neutra, não erro.

O usuário via três nomes em vermelho (demucs, audio-separator, spleeter) e
lia como "três erros". Só o demucs é o motor principal; os outros são
alternativas. Vermelho em item opcional é ruído que esconde o problema real.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import pytest

from mrqvs import separator


def test_demucs_e_o_unico_obrigatorio():
    status = {b.name: b for b in separator.detect_backends()}
    assert status["demucs"].opcional is False
    for nome in ("audio-separator", "spleeter"):
        assert status[nome].opcional is True, f"{nome} deveria ser opcional"
    assert status["dsp-fallback"].available is True


def test_as_dict_expoe_opcional():
    dados = [b.as_dict() for b in separator.detect_backends()]
    assert all("opcional" in d for d in dados)
    assert json.dumps(dados)  # serializável


def _porta():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_interface_nao_pinta_opcional_de_vermelho():
    """A classe `.no` (vermelha) só pode aparecer para o motor principal."""
    from mrqvs import app

    porta = _porta()
    threading.Thread(target=app.run, kwargs={"port": porta, "open_browser": False}, daemon=True).start()
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.1)

    status = json.load(urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=3))
    backend = {b["name"]: b for b in status["backends"]}

    html = urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=3).read().decode()
    # o JS precisa checar b.opcional antes de aplicar a classe vermelha
    assert "b.opcional" in html
    assert ".badge.opt" in html
    assert backend["audio-separator"]["opcional"] is True
    assert backend["spleeter"]["opcional"] is True


# --- MP3 sem ffmpeg, spleeter e a mensagem de erro que dizia a coisa errada ---


def test_mp3_sem_ffmpeg_usa_encoder_nativo(tmp_path, monkeypatch):
    """MP3 tem de sair mesmo sem ffmpeg: era o selo "MP3 indisponível".

    O `lameenc` é dependência obrigatória no Linux/macOS justamente por isto —
    uma tela que separa áudio não pode deixar de exportar o formato mais
    comum por falta de um binário do sistema.
    """
    import numpy as np
    import soundfile as sf

    pytest.importorskip("lameenc")
    from mrqvs import export, media

    monkeypatch.setattr(media, "have_ffmpeg", lambda: False)
    sr = 44100
    t = np.arange(sr) / sr  # 1 s
    audio = np.stack([(0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)] * 2, axis=1)

    destino = export.export_audio(
        audio, sr, tmp_path / "amostra", export.ExportOptions(fmt="mp3", title="Teste", bpm=96)
    )
    assert destino.suffix == ".mp3"
    dados = destino.read_bytes()
    assert dados[:3] in (b"ID3", b"\xff\xfb")
    assert len(dados) > 4000  # não é um arquivo vazio com cabeçalho

    # Continua sendo áudio válido: decodifica e confere a duração. No CI pode
    # não haver ffmpeg nenhum (é justamente o ambiente que motivou o encoder
    # nativo), então esta conferência é opcional — o que se exige sempre é o
    # cabeçalho e o tamanho acima.
    ffmpeg = media.find_tool("ffmpeg")
    if ffmpeg:
        wav = tmp_path / "volta.wav"
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(destino), str(wav)],
            check=False,
        )
        if wav.exists():
            info = sf.info(wav)
            assert 0.9 < info.duration < 1.15


def test_mp3_sem_encoder_avisa_em_vez_de_mentir(monkeypatch):
    """Sem ffmpeg E sem lameenc, a capability diz o que instalar."""
    from mrqvs import export, media

    monkeypatch.setattr(media, "have_ffmpeg", lambda: False)
    monkeypatch.setitem(sys.modules, "lameenc", None)  # força ImportError
    ok, motivo = export.check_export_capabilities("mp3")
    assert ok is False
    assert "lameenc" in motivo


def test_spleeter_nao_diz_mais_que_so_existe_ate_python_311():
    """O texto anterior mandava trocar de motor com uma premissa falsa.

    Testado de verdade: `pip install spleeter` instala e separa no Python 3.11
    (4 stems). O que falta numa máquina sem ffmpeg é o binário — e é isso que
    a mensagem tem de dizer.
    """
    from mrqvs import separator

    status = next(b for b in separator.detect_backends() if b.name == "spleeter")
    assert "só existe até o Python 3.11" not in status.detail
    assert "ffmpeg" in status.detail
    assert status.opcional is True


def test_spleeter_erro_de_ffmpeg_aponta_o_que_fazer(monkeypatch, tmp_path):
    """O Spleeter sai com código 0 mesmo sem ffmpeg; o erro vinha como
    "terminou sem gerar stems" (sintoma) em vez do motivo."""
    from mrqvs import separator, runtime

    class Falso:
        returncode = 0
        stdout = ""
        stderr = "ERROR:spleeter:ffmpeg binary not found"

    monkeypatch.setattr(runtime, "module_command", lambda *a, **k: ["python", "-m", "spleeter"])
    monkeypatch.setattr(separator, "_run", lambda *a, **k: Falso())
    with pytest.raises(separator.SeparationError) as exc:
        separator._separate_spleeter(tmp_path / "a.wav", tmp_path / "out", "spleeter:4stems", None)
    texto = str(exc.value).lower()
    assert "ffmpeg" in texto
    assert "winget" in texto or "apt install" in texto or "brew" in texto


def test_spleeter_recebe_o_ffmpeg_do_app_no_path(monkeypatch, tmp_path):
    """Se o app já achou o ffmpeg (inclusive o do wheel imageio-ffmpeg), a
    pasta dele entra no PATH do Spleeter — ele só procura por nome."""
    from mrqvs import separator, media

    pasta = tmp_path / "bin"
    pasta.mkdir()
    (pasta / "ffmpeg").write_text("#!/bin/sh\n")
    (pasta / "ffprobe").write_text("#!/bin/sh\n")
    monkeypatch.setattr(media, "find_tool", lambda *a, **k: str(pasta / "ffmpeg"))
    env = separator._ambiente_com_ffmpeg()
    assert env["PATH"].split(os.pathsep)[0] == str(pasta)
