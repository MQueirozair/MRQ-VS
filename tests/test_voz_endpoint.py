"""Rota `/api/voz/<chave>` com o pacote completo.

Antes, com arquivos faltando, o teste só conseguia verificar o 404. Agora que
o pacote está fechado, dá para travar o contrato inteiro: 200 com WAV de
verdade para os 17 nomes, 404 para nome válido sem arquivo e 400 para chave
desconhecida.
"""
from __future__ import annotations

import io
import wave

import pytest

from mrqvs import voz
from mrqvs.web import Handler


class _Resposta(io.BytesIO):
    """wfile falso: guarda o corpo e finge o socket."""

    def __init__(self) -> None:
        super().__init__()
        self.status = None
        self.cabecalhos: dict[str, str] = {}

    def write(self, dados) -> int:  # noqa: D401
        return super().write(dados)

    def flush(self) -> None:
        pass


def _handler() -> tuple[Handler, _Resposta]:
    """Instancia o handler sem abrir socket."""
    h = Handler.__new__(Handler)
    resp = _Resposta()
    h.wfile = resp
    h.send_response = lambda codigo, *a, **k: setattr(resp, "status", codigo)  # type: ignore[method-assign]
    h.send_header = lambda k, v: resp.cabecalhos.__setitem__(k, v)  # type: ignore[method-assign]
    h.end_headers = lambda: None  # type: ignore[method-assign]
    return h, resp


@pytest.mark.parametrize("chave", voz.nomes_esperados())
def test_rota_devolve_wav_para_todas_as_palavras(chave):
    h, resp = _handler()
    h._serve_voz(chave)
    assert resp.status == 200, f"{chave}: status {resp.status}"
    corpo = resp.getvalue()
    assert len(corpo) > 8_000, f"{chave}: corpo de {len(corpo)} bytes"
    assert corpo[:4] == b"RIFF", f"{chave}: não é WAV"
    with wave.open(io.BytesIO(corpo)) as w:
        assert w.getframerate() == 44_100
        assert w.getnchannels() >= 1
        assert w.getnframes() > 0


def test_rota_aceita_maiuscula_e_espaco():
    h, resp = _handler()
    h._serve_voz(" REFRAO ")
    assert resp.status == 200


def test_rota_recusa_numero_fora_da_faixa():
    for n in ("0", "9", "42"):
        h, resp = _handler()
        h._serve_voz(n)
        assert resp.status == 404, f"{n} deveria ser 404"


def test_rota_devolve_404_para_nome_valido_sem_arquivo(monkeypatch):
    """Pacote sem o WAV é o caso 'instalação incompleta': 404, não 500.

    A leitura real passa por `_voz_bytes` (pkgutil/disco), então o jeito
    honesto de simular ausência é fazer ele devolver vazio — que é o que ele
    devolve quando o arquivo não existe.
    """
    import mrqvs.web as web

    monkeypatch.setattr(web, "_voz_bytes", lambda chave: b"")
    h, resp = _handler()
    h._serve_voz("refrao")
    assert resp.status == 404


def test_rota_recusa_chave_desconhecida():
    h, resp = _handler()
    h._serve_voz("banana")
    assert resp.status == 400


def test_rota_recusa_travessia_de_caminho():
    for ruim in ("../index", "..%2Findex", "voz/palavras/1"):
        h, resp = _handler()
        h._serve_voz(ruim)
        assert resp.status in (400, 404), f"{ruim}: status {resp.status}"
