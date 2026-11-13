"""Capa do vídeo: miniatura na interface e `capa.jpg` na pasta do projeto."""

from __future__ import annotations

import threading
import time
import urllib.request

from mrqvs import cover


def test_variantes_pedem_a_capa_grande_primeiro():
    urls = cover._variantes("https://i.ytimg.com/vi/abc/hqdefault.jpg")
    assert urls[0] == "https://i.ytimg.com/vi/abc/hqdefault.jpg"
    assert any("maxresdefault" in u for u in urls)
    # nunca inventa host: só troca o nome do arquivo no mesmo diretório
    assert all(u.startswith("https://i.ytimg.com/vi/abc/") for u in urls)


def test_sem_url_nao_falha(tmp_path):
    assert cover.download("", tmp_path / "capa.jpg") is None
    assert not (tmp_path / "capa.jpg").exists()


def test_falha_de_rede_vira_none(tmp_path):
    """Capa é opcional: erro de download não pode derrubar o projeto."""
    assert cover.download("http://127.0.0.1:9/nao-existe.jpg", tmp_path / "capa.jpg", timeout=2) is None


def test_para_media_url(tmp_path):
    arquivo = tmp_path / "proj" / "capa.jpg"
    arquivo.parent.mkdir()
    arquivo.write_bytes(b"x")
    assert cover.para_media_url(arquivo, tmp_path) == "/api/cover?p=proj/capa.jpg"
    # fora da pasta de saída não vira URL
    assert cover.para_media_url(tmp_path.parent / "fora.jpg", tmp_path) == ""


def _sobe_app():
    from mrqvs import app

    with __import__("socket").socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    threading.Thread(target=app.run, kwargs={"port": porta, "open_browser": False}, daemon=True).start()
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=0.5).close()
            return porta
        except OSError:
            time.sleep(0.1)
    raise AssertionError("servidor não subiu")


def test_interface_tem_capa_e_lightbox():
    porta = _sobe_app()
    html = urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=3).read().decode()
    assert 'id="capaImg"' in html
    assert 'id="lightbox"' in html
    assert "mostrarCapa" in html
    assert 'id="capaResultado"' in html


def test_rota_da_capa_serve_imagem(tmp_path, monkeypatch):
    from mrqvs import web

    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "capa.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 2000)
    monkeypatch.setattr(web, "_OUT_ROOT", tmp_path)

    porta = _sobe_app()
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/cover?p=demo/capa.jpg", timeout=3) as r:
        assert r.headers.get("Content-Type") == "image/jpeg"
        assert len(r.read()) > 1000

    # fora da pasta de saída: negado
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/cover?p=../../etc/passwd", timeout=3)
        raise AssertionError("deveria ter negado")
    except urllib.error.HTTPError as exc:
        assert exc.code in (403, 404)
