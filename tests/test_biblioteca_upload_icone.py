"""Testes de biblioteca, upload em fatias, ícones puro-Python e motor leve."""

from __future__ import annotations

import struct
import numpy as np
import pytest
import soundfile as sf

from mrqvs import biblioteca, icone, leve, upload


def test_biblioteca_ciclo_completo_e_chaves_canonicas(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))

    pasta = tmp_path / "MinhaMusica-120BPM"
    apoio = tmp_path / "MinhaMusica-120BPM-apoio"
    pasta.mkdir()
    apoio.mkdir()

    sr = 22050
    onda = (0.2 * np.sin(2 * np.pi * 440 * np.arange(sr) / sr)).astype(np.float32)
    sf.write(pasta / "MinhaMusica-120BPM_00_mix.wav", onda, sr)
    sf.write(pasta / "MinhaMusica-120BPM_01_vocals.wav", onda, sr)
    sf.write(pasta / "MinhaMusica-120BPM_ENSAIO_LR.wav", np.stack([onda, onda], axis=1), sr)
    sf.write(apoio / "clique.wav", onda, sr)
    sf.write(apoio / "guia.wav", onda, sr)
    (apoio / "relatorio.md").write_text("# Relatório\n", encoding="utf-8")
    (apoio / "capa.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 1200)

    # Registrar pasta -apoio deve ser ignorado (evita duplicatas)
    assert biblioteca.registrar(apoio) == {}

    reg = biblioteca.registrar(pasta, titulo="Minha Música", bpm=120, tom="C maior", motor="dsp-fallback/dsp-fallback")
    assert reg["titulo"] == "Minha Música"
    lista = biblioteca.listar()
    assert len(lista) == 1

    aberto = biblioteca.abrir(str(pasta))
    assert aberto is not None
    # As chaves têm de ser os IDs canônicos (vocals, mix, ensaio_lr), não o nome longo do arquivo!
    assert set(aberto["arquivos"]) == {"mix", "vocals", "ensaio_lr"}
    assert aberto["lr"].startswith("/api/file?p=")
    assert aberto["clique"].startswith("/api/file?p=")
    assert aberto["guia"].startswith("/api/file?p=")
    assert aberto["capa"].startswith("/api/bib/capa?p=")

    assert biblioteca.remover(str(pasta)) is True
    assert biblioteca.listar() == []


def test_upload_em_fatias_e_validacao(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))

    with pytest.raises(upload.UploadError):
        upload.novo_envio("documento.pdf", 1024)
    with pytest.raises(upload.UploadError):
        upload.novo_envio("gigante.wav", upload.LIMITE_BYTES + 1)
    with pytest.raises(upload.UploadError):
        upload.ler_registro("../../etc")

    wav_src = tmp_path / "entrada.wav"
    sr = 22050
    onda = (0.3 * np.sin(2 * np.pi * 220 * np.arange(sr * 2) / sr)).astype(np.float32)
    sf.write(wav_src, onda, sr)
    bruto = wav_src.read_bytes()

    sessao = upload.novo_envio("Minha Faixa.wav", len(bruto))
    upload.gravar_registro(
        sessao["pasta"],
        {"nome": sessao["nome"], "tipo": sessao["tipo"], "titulo": "Minha Faixa"},
    )
    ident = sessao["id"]
    meio = len(bruto) // 2
    assert upload.receber_fatia(ident, 0, bruto[:meio]) == meio
    with pytest.raises(upload.UploadError):
        upload.receber_fatia(ident, -1, b"x")
    assert upload.receber_fatia(ident, meio, bruto[meio:]) == len(bruto)

    pronto = upload.preparar(ident)
    assert pronto["tipo"] == "audio"
    assert pronto["titulo"] == "Minha Faixa"
    assert pronto["duracao"] == pytest.approx(2.0, abs=0.1)
    assert pronto["audio"].is_file()
    upload.limpar(ident)
    assert not sessao["pasta"].exists()


def test_icone_redimensiona_em_python_puro_e_gera_ico_valido(tmp_path, monkeypatch):
    # Força o caminho puro-Python (sem Pillow e sem ImageMagick)
    monkeypatch.setattr(icone, "_tem_magick", lambda: "")
    import builtins

    real_import = builtins.__import__

    def sem_pil(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ModuleNotFoundError("PIL desativado no teste")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sem_pil)

    origem = icone.fonte()
    assert origem.is_file()

    p192 = tmp_path / "192.png"
    assert icone._redimensionar(origem, p192, 192) is True
    dados = p192.read_bytes()
    largura, altura = struct.unpack(">II", dados[16:24])
    assert (largura, altura) == (192, 192)

    ico_path = icone.gerar_ico(tmp_path / "teste.ico", origem)
    ico_bytes = ico_path.read_bytes()
    reservado, tipo, qtd = struct.unpack("<HHH", ico_bytes[:6])
    assert (reservado, tipo, qtd) == (0, 1, len(icone.TAMANHOS_ICO))


def test_leve_lista_os_dois_caminhos():
    cams = leve.caminhos(demucs_ok=True, openunmix_ok=False)
    assert {c.chave for c in cams} == {"rapido", "leve"}
    assert "Spleeter" in leve.resumo()
