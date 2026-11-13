"""Instalador do motor de IA (demucs).

O que estes testes protegem:

* a pasta `mrq-ai/` é encontrada e usada como interpretador dos backends;
* `._pth` do Python baixado é ajustado (senão `pip install` "funciona" e o
  import não acha nada — o mesmo tipo de armadilha do pacote portátil);
* falha na instalação **não deixa meia instalação** para trás;
* a interface mostra o painel e o botão quando a IA falta.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.request

import pytest

from mrqvs import ai, runtime


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_AI_DIR", str(tmp_path / "mrq-ai"))
    return tmp_path / "mrq-ai"


def test_ai_dir_respeita_variavel_de_ambiente(ambiente):
    assert runtime.ai_dir() == ambiente


def test_ai_python_encontra_interpretador(ambiente):
    assert runtime.ai_python() is None
    (ambiente / "Scripts").mkdir(parents=True)
    (ambiente / "Scripts" / "python.exe").write_bytes(b"MZ")
    assert runtime.ai_python() == ambiente / "Scripts" / "python.exe"


def test_pth_do_python_baixado_recebe_site_packages(ambiente):
    """Sem isso o pip instala em um lugar que o interpretador não lê."""
    ambiente.mkdir(parents=True)
    pth = ambiente / "python313._pth"
    pth.write_text("python313.zip\r\n.\r\n#import site\r\n")

    ai._habilitar_site_packages(ambiente)
    conteudo = pth.read_text()
    assert "Lib\\site-packages" in conteudo
    assert "import site" in conteudo

    # idempotente: rodar de novo não duplica linhas
    ai._habilitar_site_packages(ambiente)
    assert pth.read_text().count("Lib\\site-packages") == 1


def test_falha_nao_deixa_meia_instalacao(ambiente, monkeypatch):
    """Se o download do Python falhar, a pasta é limpa."""

    def falhar(*a, **k):
        raise ai.IAError("sem rede")

    monkeypatch.setattr(ai, "python_do_sistema", lambda: None)
    monkeypatch.setattr(ai, "_baixar", falhar)
    with pytest.raises(ai.IAError):
        ai.instalar()
    assert not ambiente.exists(), "sobrou uma pasta de IA incompleta"


def test_falha_no_venv_nao_deixa_meia_instalacao(ambiente, monkeypatch):
    """Se o venv/pip falhar e o fallback de download também, a pasta é limpa."""

    def falhar_rodar(cmd, cwd, acao, timeout=900):
        (cwd / "lixo_parcial").write_text("x")
        raise ai.IAError("pip falhou")

    def falhar_baixar(*a, **k):
        raise ai.IAError("sem rede")

    monkeypatch.setattr(ai, "python_do_sistema", lambda: "/usr/bin/python3")
    monkeypatch.setattr(ai, "_rodar", falhar_rodar)
    monkeypatch.setattr(ai, "_baixar", falhar_baixar)
    with pytest.raises(ai.IAError):
        ai.instalar()
    assert not ambiente.exists(), "sobrou uma pasta de IA incompleta após falha do venv"


def test_status_do_backend_reflete_o_ambiente(ambiente, monkeypatch):
    """`interpreter_note` e `python_cmd` passam a apontar para o mrq-ai."""
    ambiente.mkdir(parents=True, exist_ok=True)
    (ambiente / "python.exe").write_bytes(b"MZ")
    assert "ambiente de IA" in runtime.interpreter_note()
    assert runtime.python_cmd() == str(ambiente / "python.exe")


def _porta():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_interface_tem_painel_de_ia(ambiente):
    from mrqvs import app

    porta = _porta()
    threading.Thread(target=app.run, kwargs={"port": porta, "open_browser": False}, daemon=True).start()
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.1)

    import json

    status = json.load(urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=3))
    assert status["ia"]["instalado"] is False
    assert "winget" in status["ia"]["manual"]

    html = urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=3).read().decode()
    for elemento in ('id="iaBox"', 'id="iaInstalar"', "carregarIA"):
        assert elemento in html


def test_python_do_sistema_e_detectado():
    """O atalho por venv evita baixar interpretador quando já existe um."""
    achado = ai.python_do_sistema()
    assert achado is not None, "deveria achar o python deste ambiente"
    assert "python" in achado.lower()


def test_versoes_de_python_tem_fallback():
    """python.org remove builds antigas: uma lista só com um item é frágil."""
    assert len(ai.PYTHON_VERSOES) >= 3
    assert all(v.startswith("3.") for v in ai.PYTHON_VERSOES)
    assert "{v}" in ai.PYTHON_URL


# --- o bug real: "não sai de Instalando…" ----------------------------------


def test_estado_da_ia_tem_os_campos_que_a_tela_usa():
    """A tela lê `rodando`, `fracao`, `texto`, `erro` e `instalado`.

    (Não dá para exigir `erro == ""` sem reiniciar o estado: outro teste
    desta mesma sessão deixa um erro proposital, e isso é o comportamento
    real — o último resultado fica lá para quem abrir a página ver.)
    """
    from mrqvs import ai

    e = ai.estado()
    assert set(e) >= {"rodando", "fracao", "texto", "erro", "instalado"}
    assert e["rodando"] is False
    assert 0.0 <= float(e["fracao"]) <= 1.0


def test_instalar_publica_progresso_e_termina_mesmo_falhando(monkeypatch):
    """O que travava a tela: a instalação nunca deixava um estado final.

    Com o estado explícito, uma falha deixa `rodando=False`, `terminado=True`
    e o motivo real em `erro` — a interface consegue sair de "Instalando…".
    """
    import threading
    import time

    from mrqvs import ai

    vistos = []

    def falso(alvo, dizer, forcar):
        # o passo do meio é lento de propósito: dá tempo de a tela amostrar
        # mais de um valor (antes o teste podia ver só o primeiro e falhar)
        dizer(0.1, "baixando…")
        time.sleep(0.2)
        dizer(0.5, "instalando demucs…")
        time.sleep(0.2)
        raise ai.IAError("falha simulada de rede")

    monkeypatch.setattr(ai, "_instalar_de_verdade", falso)
    erro = {}

    def alvo():
        try:
            ai.instalar()
        except Exception as exc:  # noqa: BLE001
            erro["msg"] = str(exc)

    t = threading.Thread(target=alvo)
    t.start()
    # espera a instalação começar antes de amostrar: máquina rápida podia
    # terminar antes da primeira leitura e o teste falhava sem defeito nenhum
    for _ in range(200):
        if ai.estado().get("rodando"):
            break
        time.sleep(0.005)
    while t.is_alive():
        vistos.append(ai.estado()["fracao"])
        time.sleep(0.01)
    t.join()

    e = ai.estado()
    assert len(set(round(v, 2) for v in vistos)) > 1, "o progresso não pode ser fixo"
    assert e["rodando"] is False, "não pode ficar 'rodando' para sempre"
    assert e["terminado"] is True
    assert "simulada" in e["erro"], "o motivo real precisa chegar à tela"
    assert "simulada" in erro["msg"]


def test_cancelar_para_a_instalacao(monkeypatch):
    import threading
    import time

    from mrqvs import ai

    def lento(alvo, dizer, forcar):
        for i in range(100):
            dizer(i / 100, f"passo {i}")
            time.sleep(0.01)

    monkeypatch.setattr(ai, "_instalar_de_verdade", lento)
    t = threading.Thread(target=lambda: _engolir(ai.instalar))
    t.start()
    time.sleep(0.15)
    ai.cancelar()
    t.join(timeout=5)
    assert not t.is_alive(), "cancelar precisa parar de verdade"
    assert "cancelada" in ai.estado()["erro"]


def _engolir(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass


def test_rota_de_estado_responde_na_hora_mesmo_instalando():
    """A rota antiga segurava a requisição por 10–20 min e o navegador
    desistia; a interface ficava com a barra decorativa para sempre."""
    from pathlib import Path

    fonte = Path(__file__).resolve().parents[1] / "src" / "mrqvs" / "web" / "__init__.py"
    texto = fonte.read_text(encoding="utf-8")
    trecho = texto[texto.index("def _instalar_ia") : texto.index("def _estado_ia")]
    assert "Thread(" in trecho, "a instalação precisa rodar em segundo plano"
    assert "ai_mod.instalar()" in trecho


def test_interface_consulta_o_estado_e_permite_cancelar():
    from pathlib import Path

    html = Path(__file__).resolve().parents[1] / "src" / "mrqvs" / "web" / "index.html"
    texto = html.read_text(encoding="utf-8")
    assert "/api/ia/estado" in texto
    assert "/api/ia/cancelar" in texto
    # a barra decorativa com setInterval fixo era o sintoma do bug
    assert "passo = Math.min(94" not in texto
