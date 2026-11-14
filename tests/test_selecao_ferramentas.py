"""Trava o documento das 30 ferramentas: dados, contagens e sincronia.

A página de seleção é um artefato estático: se alguém editar o relatório e
esquecer a página (ou o contrário), a contagem de categorias e as notas
divergem e o usuário marca uma coisa achando que marcou outra. Este teste
não instala nada, só lê os dois arquivos.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HTML = RAIZ / "docs" / "selecao-30-ferramentas.html"
RELATORIO = RAIZ / "docs" / "PESQUISA-30-FERRAMENTAS.md"

# o pedido do usuário: 6/5/4/5/3/3/4 = 30
POR_CATEGORIA = {"A": 6, "B": 5, "C": 4, "D": 5, "E": 3, "F": 3, "G": 4}


def _dados() -> list[dict]:
    texto = HTML.read_text(encoding="utf-8")
    m = re.search(r"const DADOS = (\[.*?\n\]);", texto, re.S)
    assert m, "a página não tem o bloco const DADOS"
    return json.loads(m.group(1))


def test_pagina_de_selecao_tem_as_30_ferramentas():
    assert len(_dados()) == 30


def test_categorias_respeitam_o_pedido():
    contagem: dict[str, int] = {}
    for d in _dados():
        contagem[d["cat"]] = contagem.get(d["cat"], 0) + 1
    assert contagem == POR_CATEGORIA


def test_numeracao_e_unica_e_sequencial():
    numeros = sorted(d["n"] for d in _dados())
    assert numeros == list(range(1, 31))


def test_nada_vem_pre_selecionado():
    """A recomendação do relatório não é autorização para implementar."""
    texto = HTML.read_text(encoding="utf-8")
    # nenhuma caixa nasce marcada no HTML (o CSS usa :checked, isso é estilo)
    assert not re.search(r"<input[^>]*\bchecked\b", texto)
    # e a renderização não marca nada: marcar só acontece no clique
    corpo = texto.split("function render()")[1].split("function setAll")[0]
    assert "setAll(true)" not in corpo.split("document.getElementById")[0]
    assert "checked = true" not in corpo and ".checked=true" not in corpo
    assert 'id="bAll"' in texto


def test_campos_obrigatorios_em_cada_ferramenta():
    obrigatorios = {
        "n", "nome", "cat", "desc", "ben", "dif", "custo",
        "compat", "nota", "dias", "lic", "tipo",
    }
    for d in _dados():
        faltando = obrigatorios - set(d)
        assert not faltando, f"#{d.get('n')} sem {faltando}"
        assert d["dif"] in {"Fácil", "Médio", "Avançado", "Muito avançado"}
        assert 0 <= d["nota"] <= 10
        assert d["dias"] > 0
        assert d["custo"].startswith("R$")


def _normalizar(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def test_toda_ferramenta_tem_ficha_no_relatorio():
    """O número na página tem de existir como ficha no relatório."""
    texto = RELATORIO.read_text(encoding="utf-8")
    plano = _normalizar(texto)
    for d in _dados():
        assert re.search(rf"^### {d['n']}\. ", texto, re.M), f"ficha #{d['n']} ausente"
        chave = _normalizar(d["nome"].split(" (")[0])[:12]
        assert chave in plano, f"nome #{d['n']} ({d['nome']}) ausente no relatório"


def test_relatorio_declara_que_nada_foi_implementado():
    texto = RELATORIO.read_text(encoding="utf-8")
    assert "não instalei nada" in texto
    assert "Nada foi instalado, alterado, trocado ou removido" in texto


def test_licencas_gpl_estao_marcadas_como_tal():
    """Quem tem GPL/AGPL não pode aparecer como se fosse permissiva."""
    gpl = [d for d in _dados() if "GPL" in d["lic"]]
    assert gpl, "esperava ao menos uma licença GPL na lista"
    for d in gpl:
        assert "❌" in d["lic"], f"#{d['n']} tem GPL sem a marca de restrição"


def test_contagem_de_dias_bate_com_a_soma_das_fichas():
    texto = RELATORIO.read_text(encoding="utf-8")
    total = sum(d["dias"] for d in _dados())
    assert f"~{total} dias-dev" in texto, f"relatório não diz ~{total} dias-dev"
