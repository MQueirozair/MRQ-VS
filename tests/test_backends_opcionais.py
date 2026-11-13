"""Badges de backend: alternativa ausente é neutra, não erro.

O usuário via três nomes em vermelho (demucs, audio-separator, spleeter) e
lia como "três erros". Só o demucs é o motor principal; os outros são
alternativas. Vermelho em item opcional é ruído que esconde o problema real.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request

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
