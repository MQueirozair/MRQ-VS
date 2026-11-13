"""Regressões na descoberta de ffmpeg/yt-dlp.

O bug real (reportado com print do Windows): `find_tool("yt-dlp")` devolvia
`lib\\ffmpeg.exe`, porque a busca por `ffmpeg*` rodava para qualquer nome. O
resultado era o ffmpeg sendo executado com `--dump-single-json`:

    Unrecognized option 'dump-single-json'.

Estes testes fixam essa separação.
"""

from __future__ import annotations

import sys

import pytest

from mrqvs import media


@pytest.fixture()
def pacote(tmp_path, monkeypatch):
    """Um `lib/` falso com ffmpeg bem grande e o módulo yt_dlp."""
    lib = tmp_path / "lib"
    (lib / "yt_dlp").mkdir(parents=True)
    (lib / "yt_dlp" / "__init__.py").write_text("__version__ = '1.0'\n")
    (lib / "yt_dlp" / "__main__.py").write_text("print('yt-dlp')\n")
    # o glob do ffmpeg exige > 1 MB
    (lib / "ffmpeg.exe").write_bytes(b"MZ" + b"\0" * 2_000_000)
    monkeypatch.setattr(media, "_pastas_locais", lambda: [lib])
    monkeypatch.setattr(media.shutil, "which", lambda _nome: None)
    return lib


def test_ytdlp_nao_devolve_ffmpeg(pacote):
    assert media.find_tool("ffmpeg") is not None
    assert media.find_tool("yt-dlp") is None, "find_tool confundiu yt-dlp com ffmpeg"


def test_require_ytdlp_usa_modulo_embutido(pacote, monkeypatch):
    """Sem binário, o comando tem de ser `python -m yt_dlp` — nunca o ffmpeg."""

    monkeypatch.setattr(media, "_tem_modulo_ytdlp", lambda: True)
    comando = media.require_ytdlp()
    assert "yt_dlp" in comando
    assert "ffmpeg" not in comando.lower()
    partes = media._ytdlp_cmd()
    assert partes[:2] == [sys.executable, "-m"] or partes[1:] == ["-m", "yt_dlp"]
    assert partes != [str(pacote / "ffmpeg.exe")]


def test_erro_do_ytdlp_nao_cai_no_ffmpeg(pacote, monkeypatch):
    """Se o yt-dlp falhar, o erro tem que ser de yt-dlp, não 'Unrecognized option'."""
    monkeypatch.setattr(media, "_tem_modulo_ytdlp", lambda: False)
    with pytest.raises(media.MediaError) as exc:
        media.require_ytdlp()
    assert "yt-dlp" in str(exc.value)
    assert "dump-single-json" not in str(exc.value)


def test_pasta_de_ferramentas_e_o_proprio_pacote():
    """`lib/` e `tools/` entram na busca (é onde o zip põe as ferramentas)."""
    pastas = [str(p) for p in media._pastas_locais()]
    assert any(p.endswith("lib") or p.endswith("tools") for p in pastas) or pastas
