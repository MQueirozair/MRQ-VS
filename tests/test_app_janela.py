"""Modo janela: duplo clique tem de abrir a interface, não a ajuda do argparse.

O bug que estes testes impedem: `mrq-vs` sem argumentos imprimia o `--help`.
Para quem clica duas vezes no ícone, isso é indistinguível de "não abriu".
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request

from mrqvs import app, cli


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_sem_argumentos_nao_imprime_ajuda(capsys, monkeypatch):
    """`main([])` deve cair no modo janela (e não no print_help)."""
    chamado = {}

    def fake_run(port=8765, host="127.0.0.1", open_browser=True):
        chamado["port"] = port
        chamado["browser"] = open_browser
        return 0

    monkeypatch.setattr(app, "run", fake_run)
    assert cli.main([]) == 0
    assert chamado, "main([]) não abriu o modo janela"
    out = capsys.readouterr().out
    assert "usage:" not in out, "ainda imprimiu a ajuda do argparse"


def test_subcomando_app_aceita_no_browser(monkeypatch):
    chamado = {}

    def fake_run(port=8765, host="127.0.0.1", open_browser=True):
        chamado.update(port=port, browser=open_browser)
        return 0

    monkeypatch.setattr(app, "run", fake_run)
    assert cli.main(["app", "--port", "9123", "--no-browser"]) == 0
    assert chamado == {"port": 9123, "browser": False}


def test_porta_livre_desvia_de_porta_ocupada():
    """Duas instâncias abertas não podem derrubar a segunda com OSError."""
    ocupada = _porta_livre()
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", ocupada))
        s.listen(1)
        assert app._porta_livre(ocupada) != ocupada


def test_servidor_responde_e_a_pagina_tem_a_interface():
    porta = _porta_livre()
    t = threading.Thread(target=app.run, kwargs={"port": porta, "open_browser": False}, daemon=True)
    t.start()
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=0.5) as r:
                dados = json.load(r)
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise AssertionError("o servidor do modo janela não subiu")

    assert "stems" in dados and "backends" in dados

    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=2) as r:
        html = r.read().decode("utf-8")
    # a página precisa ser o app de verdade, não uma tela de erro
    assert "Separar" in html
    assert len(html) > 5000
