"""Testes de integração do pipeline completo, rotas HTTP novas e segurança."""

from __future__ import annotations

import json
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

from mrqvs import demo, export, project, separator, web


def _subir_servidor() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    httpd = web.ThreadingHTTPServer(("127.0.0.1", porta), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=0.5).close()
            return porta
        except OSError:
            time.sleep(0.05)
    raise AssertionError("servidor HTTP não iniciou")


def test_pipeline_completo_dois_stems_e_ensaio_lr(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))
    dados = demo.build()
    entrada = tmp_path / "Louvor Demo.wav"
    sf.write(entrada, dados["mix"], dados["sample_rate"])

    saida = tmp_path / "saida"
    opts = project.ProjectOptions(
        source=str(entrada),
        out_root=saida,
        out_dir=saida,
        dois_stems="vocals",
        exportar_lr=True,
    )
    res = project.run(opts)

    # Modo rápido (dois_stems="vocals") deve exportar voz + instrumental + mix + ensaio_lr
    assert {"vocals", "instrumental", "mix", "ensaio_lr"} <= set(res.stems_written)
    assert "drums" not in res.stems_written
    assert res.lr is not None and res.lr.is_file()

    # Playlist e CUE na pasta -apoio precisam apontar para caminhos relativos válidos
    apoio = saida / f"{res.folder.name}-apoio"
    m3u = (apoio / "projeto.m3u").read_text(encoding="utf-8").splitlines()
    caminhos_m3u = [ln for ln in m3u if ln and not ln.startswith("#")]
    assert caminhos_m3u
    for rel in caminhos_m3u:
        assert (apoio / rel).is_file(), f"caminho quebrado no projeto.m3u: {rel}"


def test_export_session_nao_duplica_energia_com_derivados(tmp_path):
    sr = 22050
    t = np.arange(sr) / sr
    vocals = (0.25 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    drums = (0.25 * np.sin(2 * np.pi * 110 * t)).astype(np.float32)
    kick = drums.copy()  # derivado do pai drums
    instrumental = drums.copy()  # derivado quando drums está presente

    stems = {"vocals": vocals, "instrumental": instrumental, "drums": drums, "kick": kick}
    written = export.export_session(stems, sr, tmp_path, "Teste-120BPM", export.ExportOptions(fmt="wav", bits=32))
    mix_lido, _ = sf.read(written["mix"], dtype="float32")
    esperado = vocals + drums
    assert np.allclose(mix_lido, esperado, atol=1e-5)


def test_choose_backend_respeita_modelo_especifico(monkeypatch):
    monkeypatch.setattr(
        separator,
        "detect_backends",
        lambda: [
            separator.BackendStatus("demucs", True, "ok"),
            separator.BackendStatus("audio-separator", True, "ok"),
            separator.BackendStatus("dsp-fallback", True, "ok"),
        ],
    )
    escolhido = separator.choose_backend(
        "auto", (), "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
    )
    assert escolhido == "audio-separator"


def test_rotas_web_range_upload_biblioteca_e_seguranca(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(web, "_OUT_ROOT", tmp_path / "out")
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    porta = _subir_servidor()
    base = f"http://127.0.0.1:{porta}"

    # 1. Ícones servidos de verdade
    for rota in ("/favicon.ico", "/icone-192.png", "/icone-512.png"):
        with urllib.request.urlopen(base + rota, timeout=3) as r:
            assert r.status == 200
            assert len(r.read()) > 100

    # 2. HTTP Range: 206 Partial Content e 416 quando fora do arquivo
    arq_teste = tmp_path / "out" / "amostra.wav"
    arq_teste.write_bytes(b"ABCDEFGHIJ0123456789")
    req_206 = urllib.request.Request(base + "/api/file?p=amostra.wav", headers={"Range": "bytes=2-5"})
    with urllib.request.urlopen(req_206, timeout=3) as r:
        assert r.status == 206
        assert r.read() == b"CDEF"
        assert r.headers.get("Content-Range") == "bytes 2-5/20"

    req_416 = urllib.request.Request(base + "/api/file?p=amostra.wav", headers={"Range": "bytes=999-"})
    try:
        urllib.request.urlopen(req_416, timeout=3)
        raise AssertionError("Range fora do arquivo deveria responder 416")
    except urllib.error.HTTPError as exc:
        assert exc.code == 416

    # 3. Segurança em /api/cover: pasta arbitrária `*-apoio` fora das raízes deve ser bloqueada (403)
    falso_apoio = tmp_path / "secreto-apoio"
    falso_apoio.mkdir()
    (falso_apoio / "capa.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 1500)
    try:
        urllib.request.urlopen(f"{base}/api/cover?p={falso_apoio.as_posix()}/capa.jpg", timeout=3)
        raise AssertionError("deveria negar pasta -apoio fora das raízes autorizadas")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403

    # E extensão não-imagem em /api/cover não pode dar erro 500 (KeyError)
    (tmp_path / "out" / "texto.txt").write_text("segredo", encoding="utf-8")
    try:
        urllib.request.urlopen(f"{base}/api/cover?p={(tmp_path / 'out' / 'texto.txt').as_posix()}", timeout=3)
        raise AssertionError("deveria negar extensão não-imagem em /api/cover")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403

    # 4. Upload HTTP -> /api/run -> /api/biblioteca -> /api/biblioteca/abrir
    sr = 22050
    onda = (0.25 * np.sin(2 * np.pi * 330 * np.arange(sr * 2) / sr)).astype(np.float32)
    wav_local = tmp_path / "envio.wav"
    sf.write(wav_local, onda, sr)
    payload_bytes = wav_local.read_bytes()

    def post_json(rota: str, corpo: dict) -> dict:
        req = urllib.request.Request(
            base + rota,
            data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)

    ini = post_json("/api/upload/iniciar", {"nome": "Teste Web.wav", "tamanho": len(payload_bytes)})
    req_fatia = urllib.request.Request(
        f"{base}/api/upload/fatia",
        data=payload_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Envio-Id": ini["id"],
            "X-Inicio": "0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req_fatia, timeout=10) as resp:
        assert json.load(resp)["ok"] is True

    prep = post_json("/api/upload/preparar", {"id": ini["id"]})
    assert prep["ok"] is True

    rodado = post_json("/api/run", {"envio": ini["id"], "dois_stems": True, "lr": False})
    assert {"vocals", "instrumental", "mix"} <= set(rodado["arquivos"])
    assert rodado["lr"] == ""

    with urllib.request.urlopen(base + "/api/biblioteca", timeout=5) as resp:
        bib = json.load(resp)
    itens = bib["versoes"] if isinstance(bib, dict) else bib
    assert len(itens) == 1
    reaberto = post_json("/api/biblioteca/abrir", {"id": itens[0]["id"]})
    assert reaberto["ok"] is True
    assert {"vocals", "instrumental", "mix"} <= set(reaberto["arquivos"])

    rem = post_json("/api/biblioteca/remover", {"id": itens[0]["id"]})
    assert rem["ok"] is True


def test_javascript_embutido_no_html_tem_sintaxe_valida():
    import shutil

    node = shutil.which("node")
    if not node:
        return
    html = (Path(__file__).resolve().parents[1] / "src" / "mrqvs" / "web" / "index.html").read_text(encoding="utf-8")
    blocos = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S)
    assert blocos, "nenhum bloco <script> encontrado no index.html"
    import tempfile

    for bloco in blocos:
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as fh:
            fh.write(bloco)
            caminho = Path(fh.name)
        try:
            proc = subprocess.run([node, "--check", str(caminho)], check=False, capture_output=True, text=True)
            assert proc.returncode == 0, f"erro de sintaxe JS no index.html:\n{proc.stderr}"
        finally:
            caminho.unlink(missing_ok=True)
