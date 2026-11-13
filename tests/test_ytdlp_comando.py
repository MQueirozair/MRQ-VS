"""Ordem dos argumentos do yt-dlp.

Dois bugs reais no Windows, ambos por montar a linha de comando errado:

1. `find_tool("yt-dlp")` devolvia `ffmpeg.exe` -> "Unrecognized option
   'dump-single-json'".
2. as opções eram inseridas depois do executável, mas antes de `-m yt_dlp`
   -> o **Python** reclamava: "unknown option --extract-audio".

Com `python -m yt_dlp`, tudo o que vem antes de `-m yt_dlp` é do Python.
"""

from __future__ import annotations

import sys

from mrqvs import media


def test_opcoes_vem_depois_do_modulo(monkeypatch):
    monkeypatch.setattr(media, "find_tool", lambda *a, **k: None)
    monkeypatch.setattr(media.shutil, "which", lambda _n: None)
    monkeypatch.setattr(media, "_tem_modulo_ytdlp", lambda: True)

    cmd = media.ytdlp_command("--extract-audio", "--audio-format", "wav", "URL")
    assert cmd == [sys.executable, "-m", "yt_dlp", "--extract-audio", "--audio-format", "wav", "URL"]
    # a opção nunca pode aparecer antes do módulo
    assert cmd.index("--extract-audio") > cmd.index("yt_dlp")


def test_binario_tambem_e_lista(monkeypatch):
    monkeypatch.setattr(media, "find_tool", lambda *a, **k: r"C:\MRQ VS\lib\yt-dlp.exe")
    cmd = media.ytdlp_command("-f", "bestaudio")
    assert cmd == [r"C:\MRQ VS\lib\yt-dlp.exe", "-f", "bestaudio"], "caminho com espaço virou dois argumentos"


def test_download_monta_wav_na_ordem_certa(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "find_tool", lambda *a, **k: None)
    monkeypatch.setattr(media.shutil, "which", lambda _n: None)
    monkeypatch.setattr(media, "_tem_modulo_ytdlp", lambda: True)
    monkeypatch.setattr(media, "have_ffmpeg", lambda: True)

    capturado = {}

    class FakeProc:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        capturado["cmd"] = cmd
        (tmp_path / "source.wav").write_bytes(b"RIFF")
        return FakeProc()

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    info = media.MediaInfo(title="t")
    media.download_audio("http://x", tmp_path, info=info)

    cmd = capturado["cmd"]
    assert cmd[:3] == [sys.executable, "-m", "yt_dlp"]
    assert "--extract-audio" in cmd
    assert cmd.index("--extract-audio") > cmd.index("yt_dlp")
    assert "-f" in cmd and "bestaudio/best" in cmd


def test_env_do_filho_inclui_o_modulo_embutido(monkeypatch):
    """O filho não herda sys.path: PYTHONPATH precisa levar a pasta do yt_dlp."""
    monkeypatch.setenv("PYTHONPATH", "")
    env = media._env_ytdlp()
    assert env.get("PYTHONPATH"), "subprocesso ficaria sem o módulo yt_dlp"
    assert "PYTHONPATH" in env


def test_erro_explica_em_vez_de_so_despejar_traceback():
    texto = media._explicar_erro_ytdlp("ERROR: Sign in to confirm you are not a bot")
    assert "cookies" in texto.lower()
    # a mensagem original nunca é escondida
    assert "Sign in to confirm" in texto

    texto = media._explicar_erro_ytdlp("ERROR: Unsupported URL: xyz")
    assert "link" in texto.lower()
