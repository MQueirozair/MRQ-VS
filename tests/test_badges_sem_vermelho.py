"""Nenhum badge vermelho: ausência de recurso opcional não é erro.

O usuário via "demucs — faltando" em vermelho e lia como defeito, mesmo
tendo o programa funcionando. Regra que fica valendo:

* instalado          -> verde (`.ok`)
* alternativa        -> cinza (`.opt`)
* formato sem ffmpeg -> cinza (`.opt`), é limitação conhecida
* IA não instalada   -> âmbar clicável (`.acao`), que leva ao botão
* vermelho (`.no`)   -> nunca
"""

from __future__ import annotations

from pathlib import Path

PASTA = Path(__file__).resolve().parents[1] / "src" / "mrqvs"
HTML = PASTA / "web" / "index.html"


def _js() -> str:
    texto = HTML.read_text(encoding="utf-8")
    return texto.split("<script>")[1].split("</script>")[0]


def test_css_tem_classe_de_acao_e_opcional():
    texto = HTML.read_text(encoding="utf-8")
    assert ".badge.acao" in texto
    assert ".badge.opt" in texto


def test_js_nao_marca_demucs_ausente_como_vermelho():
    js = _js()
    trecho = js[js.index("for (const b of STATUS.backends)") : js.index("for (const [f, ok]")]
    assert '"no"' not in trecho.replace(" ", ""), "badge de backend ainda usa a classe vermelha"
    assert "badge acao" in trecho
    assert "iaInstalar" in trecho, "o badge precisa levar ao botão de instalar"


def test_js_nao_marca_formato_sem_ffmpeg_como_vermelho():
    js = _js()
    inicio = js.index("for (const [f, ok]")
    fim = js.index("function selectedStems")
    trecho = js[inicio:fim]
    assert '"no"' not in trecho.replace(" ", "")
    assert "badge opt" in trecho


def test_nenhum_badge_no_restante_do_js():
    js = _js()
    assert 'badge " + (ok ? "ok" : "no")' not in js
    assert "badge no" not in js


def test_pagina_servida_nao_tem_texto_de_faltando():
    """A palavra 'faltando' saiu da interface (era o gatilho do alarme)."""
    texto = HTML.read_text(encoding="utf-8")
    assert "— faltando" not in texto
    assert "sem ffmpeg" not in texto


def test_doctor_nao_usa_marcador_de_falta():
    """`[falt]`/`FALTANDO` no terminal era o "vermelho" do doctor (0.1.8)."""
    fonte = (PASTA / "separator.py").read_text(encoding="utf-8")
    doctor = fonte[fonte.index("def doctor()") :]
    # procura o marcador em uso (dentro de string formatada), não em comentário
    assert "'falt'" not in doctor
    assert "FALTANDO" not in doctor
