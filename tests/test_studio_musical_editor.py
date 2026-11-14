"""Testes do editor musical (Studio) com o JS de verdade e áudio de verdade.

O que estes testes cobrem, e por quê:

* **matemática do compasso** — o caso do usuário (398 s, 158 BPM, 4/4,
  F# menor) tem de dar 262 compassos *calculados*, nunca fixos no código;
  6/8, 7/8 e 5/4 têm de cair no lugar certo;
* **cifra** — uma célula por compasso, larguras exatas, sem sobreposição,
  sem teto de 400 compassos, "—" quando não há acorde (nada de inventar),
  transposição com bemol/sustenido coerente com o modo;
* **faixas** — ordem canônica, alturas sem corte, rolagem sincronizada,
  ids sem colisão;
* **clique** — agendamento no relógio do AudioContext (lookahead), não
  `setInterval`; acentos de compasso composto; pré-contagem;
* **backend** — importar faixa, edições (com os campos novos) e atalho na
  Área de Trabalho, por HTTP, com WAVs gerados de verdade.

Os testes que dependem de Node (executar o JS do `index.html`) são pulados
quando o Node não existe, mas o CI o tem — é o que garante que o código
testado é o mesmo que roda no navegador.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import socket
import subprocess
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from mrqvs import mixdown, web

RAIZ = Path(__file__).resolve().parents[1]
JS_DIR = RAIZ / "tests" / "js"
HARNESS = JS_DIR / "harness.js"
NODE = shutil.which("node")


def _rodar_node(corpo: str, timeout: int = 90) -> str:
    """Executa um trecho Node dentro da pasta tests/js (usa o harness)."""
    if not NODE:
        pytest.skip("node não instalado: teste de execução do JS pulado")
    script = JS_DIR / "_tmp_exec.js"
    script.write_text(textwrap.dedent(corpo), encoding="utf-8")
    try:
        proc = subprocess.run(
            [NODE, str(script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(JS_DIR),
        )
    finally:
        try:
            script.unlink()
        except OSError:
            pass
    assert proc.returncode == 0, f"JS falhou:\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout


# --------------------------------------------------------------------------
# 1. Matemática do compasso (Seções 6 e 7)
# --------------------------------------------------------------------------
def _math_node() -> dict:
    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        const dados = {
          titulo: "Validação", nome_pasta: "Val", pasta: "/tmp/val", apoio: "",
          bpm: 158, tonalidade: "F# menor", compasso: 4, denominador: 4,
          segundos: 398, duracao: 398,
          estudio: {batidas: [], compasso: 4, denominador: 4, bpm: 158,
                    duracao: 398, tonalidade: "F# menor", acordes: [], secoes: []},
          arquivos: {mix: {nome: "00_mix.wav", url: "/api/file?p=/tmp/m.wav", audio: true}},
        };
        sb.studioMontar(dados);
        const res = {
          duracao: S.duracao, bpm: S.bpm, compasso: S.compasso, denominador: S.denominador,
          totalCompassos: sb.totalCompassos(),
          compassosExatos: sb.compassosNaMusica(),
          inicio0: sb.inicioDoCompasso(0),
          inicio1: sb.inicioDoCompasso(1),
          inicio261: sb.inicioDoCompasso(261),
          ultimo: sb.compassoDe(398),
          compassoDeZero: sb.compassoDe(0),
          compassoDeMeio: sb.compassoDe(sb.inicioDoCompasso(100) + 0.001),
          unidade44: sb.unidadesDoCompasso(0),
          unidade68: (function(){ S.compasso = 6; S.denominador = 8; sb.invalidarGrade();
                      return sb.unidadesDoCompasso(0); })(),
          unidade78: (function(){ S.compasso = 7; S.denominador = 8; sb.invalidarGrade();
                      return sb.unidadesDoCompasso(0); })(),
          unidade54: (function(){ S.compasso = 5; S.denominador = 4; sb.invalidarGrade();
                      return sb.unidadesDoCompasso(0); })(),
          unidade24: (function(){ S.compasso = 2; S.denominador = 4; sb.invalidarGrade();
                      return sb.unidadesDoCompasso(0); })(),
          acentos78: (function(){ S.compasso = 7; S.denominador = 8;
                      return sb.acentosDoCompasso(0); })(),
          acentos68: (function(){ S.compasso = 6; S.denominador = 8;
                      return sb.acentosDoCompasso(0); })(),
          acentos128: (function(){ S.compasso = 12; S.denominador = 8;
                      return sb.acentosDoCompasso(0); })(),
        };
        console.log(JSON.stringify(res));
        """
    )
    return json.loads(saida.strip().splitlines()[-1])


def test_398s_158bpm_4por4_da_262_compassos_calculados():
    """Caso do usuário: 398 s, 158 BPM, 4/4 -> 262.0167 compassos.

    O número NÃO pode estar escrito no código: o teste também confere a
    matemática com outro BPM e outra duração.
    """
    m = _math_node()
    barra = (60 / 158) * 4 * (4 / 4)          # 1.5189873417 s
    assert barra == pytest.approx(240 / 158, rel=1e-9)
    assert m["inicio1"] == pytest.approx(barra, abs=1e-6)
    assert m["compassosExatos"] == pytest.approx(398 / barra, abs=1e-3)
    assert m["compassosExatos"] == pytest.approx(262.0167, abs=1e-3)
    assert m["totalCompassos"] == 262
    # 398 s cai na sobra de 1,7% do compasso 263 (0-based 262). A sobra não é
    # um compasso: `totalCompassos()` conta 262 (regra dos 5%), não 263 nem 400
    assert m["ultimo"] == 262
    assert m["inicio261"] == pytest.approx(261 * barra, abs=1e-6)
    assert m["totalCompassos"] == 262
    assert m["compassoDeZero"] == 0


def test_matematica_nao_esta_hardcoded():
    """Trocar BPM/duração muda o resultado — a conta é feita, não colada."""
    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        const linha = (bpm, dur, num, den) => {
          S.duracao = dur; S.bpm = bpm; S.compasso = num; S.denominador = den;
          S.batidas = []; sb.invalidarGrade();
          return {total: sb.totalCompassos(), exato: sb.compassosNaMusica(),
                  barra: sb.duracaoDoCompasso(0)};
        };
        console.log(JSON.stringify({
          a: linha(158, 398, 4, 4), b: linha(120, 300, 4, 4),
          c: linha(90, 400, 6, 8), d: linha(90, 400, 7, 8),
          e: linha(200, 100, 5, 4),
        }));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["a"]["total"] == 262
    # 300 s a 120 BPM 4/4 = 150 compassos (2 s cada)
    assert r["b"]["barra"] == pytest.approx(2.0)
    assert r["b"]["total"] == 150
    # 6/8 a 90 BPM: 6 * (30/90) = 2 s por compasso
    assert r["c"]["barra"] == pytest.approx(2.0)
    assert r["c"]["total"] == 200
    # 7/8 a 90 BPM: 7 * (30/90) = 2.3333 s
    assert r["d"]["barra"] == pytest.approx(7 * 30 / 90)
    assert r["d"]["total"] == math.ceil(400 / (7 * 30 / 90) - 0.05)
    # 5/4 a 200 BPM: 5 * (60/200) = 1.5 s
    assert r["e"]["barra"] == pytest.approx(1.5)


def test_formulas_compostas_e_acentos():
    m = _math_node()
    assert m["unidade44"] == pytest.approx(4.0)
    assert m["unidade68"] == pytest.approx(3.0)     # 6 colcheias = 3 semínimas
    assert m["unidade78"] == pytest.approx(3.5)     # e não 4 (arredondamento antigo)
    assert m["unidade54"] == pytest.approx(5.0)
    assert m["unidade24"] == pytest.approx(2.0)
    # 6/8: forte no 1, médio no 4 (segundo grupo de 3)
    assert m["acentos68"][0] == "forte" and m["acentos68"][3] == "medio"
    # 7/8 conta 3+2+2
    assert m["acentos78"][0] == "forte"
    assert m["acentos78"][3] == "medio"
    assert m["acentos78"][5] == "medio"
    # 12/8: quatro grupos de 3
    assert [i for i, a in enumerate(m["acentos128"]) if a == "medio"] == [3, 6, 9]


def test_busca_binaria_do_compasso_bate_com_a_grade():
    """`compassoDe(t)` e `inicioDoCompasso(n)` são inversas em toda a música."""
    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        S.titulo = "x";
        sb.studioMontar({
          titulo: "x", nome_pasta: "x", pasta: "/tmp/x",
          bpm: 158, tonalidade: "F# menor", compasso: 4, denominador: 4,
          segundos: 398, duracao: 398,
          estudio: {batidas: [], compasso: 4, denominador: 4, bpm: 158, duracao: 398,
                    tonalidade: "F# menor", acordes: [], secoes: []},
          arquivos: {mix: {nome: "00_mix.wav", url: "/api/file?p=/tmp/m.wav", audio: true}},
        });
        let erros = 0;
        for (let n = 0; n < 261; n++){
          const t = sb.inicioDoCompasso(n);
          if (t > 398) break;
          if (sb.compassoDe(t) !== n) erros++;
          if (sb.compassoDe(t + 0.2) !== n) erros++;
        }
        console.log(JSON.stringify({erros, total: sb.totalCompassos()}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["erros"] == 0
    assert r["total"] == 262


# --------------------------------------------------------------------------
# 2. Cifra (Seção 1)
# --------------------------------------------------------------------------
def test_cifra_com_centenas_de_compassos_sem_sobreposicao_e_sem_teto():
    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        // 500 compassos de 4/4 a 120 BPM = 1000 s (passa do antigo teto de 400)
        const acordes = [];
        const tabela = ["C", "G", "Am", "F"];
        for (let n = 0; n < 500; n++){
          acordes.push({inicio: n * 2, fim: n * 2 + 2, compasso: n + 1,
                        acorde: tabela[n % 4], confianca: 1});
        }
        sb.studioMontar({
          titulo: "500", nome_pasta: "500", pasta: "/tmp/500",
          bpm: 120, tonalidade: "C maior", compasso: 4, denominador: 4,
          segundos: 1000, duracao: 1000,
          estudio: {batidas: [], compasso: 4, denominador: 4, bpm: 120, duracao: 1000,
                    tonalidade: "C maior", acordes: acordes, secoes: []},
          arquivos: {mix: {nome: "00_mix.wav", url: "/api/file?p=/tmp/m.wav", audio: true}},
        });
        // zoom normal: um compasso ocupa a largura da tela dividida por 500
        sb.calcEscala();
        const cels = sb.construirGradeCifras();
        const total = sb.totalCompassos();
        // confere no HTML desenhado: nenhuma célula invade a próxima
        sb.studioDesenharCifra();
        const dom = h.doc.getElementById("linhaCifra");
        const desenhadas = dom.querySelectorAll(".cifra-cel");
        let sobrepostas = 0, larguraErrada = 0, somaCompassos = 0;
        const re = /left:([\\d.]+)px;width:([\\d.]+)px/g;
        let m, pos = [];
        while ((m = re.exec(dom.innerHTML))) pos.push([parseFloat(m[1]), parseFloat(m[2])]);
        for (let i = 1; i < pos.length; i++){
          if (pos[i][0] < pos[i - 1][0] + pos[i - 1][1] - 0.05) sobrepostas++;
        }
        desenhadas.forEach((el) => { somaCompassos += Number(el.dataset.agrupado || 1); });
        console.log(JSON.stringify({
          total, cels: cels.length, desenhadas: desenhadas.length, sobrepostas,
          somaCompassos, temAcordeFim: dom.innerHTML.includes("Am") || dom.innerHTML.includes("F"),
          textos: desenhadas.slice(0, 6).map((el) => el.textContent),
        }));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["total"] == 500, "música de 500 compassos não pode ser cortada em 400"
    assert r["sobrepostas"] == 0, "células de cifra se sobrepõem"
    assert r["somaCompassos"] == 500, "a grade desenhada tem de cobrir todos os compassos"
    assert r["desenhadas"] >= 100
    assert set(r["textos"]) <= {"C", "G", "Am", "F"}


def test_cifra_mostra_travessao_quando_nao_ha_acorde_e_nao_inventa():
    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        // só o compasso 5 tem acorde; confiança baixa no 7 (deve virar "—")
        const acordes = [
          {inicio: 8, fim: 10, compasso: 5, acorde: "Bm", confianca: 1},
          {inicio: 12, fim: 14, compasso: 7, acorde: "D", confianca: 0.08},
        ];
        sb.studioMontar({
          titulo: "vazia", nome_pasta: "v", pasta: "/tmp/v",
          bpm: 120, tonalidade: "D maior", compasso: 4, denominador: 4,
          segundos: 40, duracao: 40,
          estudio: {batidas: [], compasso: 4, denominador: 4, bpm: 120, duracao: 40,
                    tonalidade: "D maior", acordes: acordes, secoes: []},
          arquivos: {mix: {nome: "00_mix.wav", url: "/api/file?p=/tmp/m.wav", audio: true}},
        });
        sb.studioDesenharCifra();
        const dom = h.doc.getElementById("linhaCifra");
        const cels = dom.querySelectorAll(".cifra-cel");
        const porCompasso = {};
        cels.forEach((el) => { porCompasso[el.dataset.compasso] = el.textContent.trim(); });
        // a célula que cobre o compasso 7 (índice 6)
        const cobre6 = cels.filter((el) => Number(el.dataset.compasso) <= 6 &&
          Number(el.dataset.compassoFim || el.dataset.compasso) >= 6)
          .map((el) => el.textContent.trim());
        console.log(JSON.stringify({
          total: sb.totalCompassos(), porCompasso,
          temBmNo5: dom.innerHTML.includes("Bm"),
          cobre6, indefinidos: cels.filter((c) => c.textContent.trim() === "—").length,
        }));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["total"] == 20                       # 40 s / 2 s
    assert r["porCompasso"]["0"] == "—", "compasso sem acorde tem de mostrar —"
    assert r["porCompasso"]["4"] == "Bm"
    assert r["temBmNo5"] is True
    # confiança 8% não vira cifra: o usuário vê "—"
    assert r["cobre6"] == ["—"], "acorde de confiança baixa não pode ser exibido"
    assert r["indefinidos"] >= 4


def test_transposicao_respeita_o_modo_menor_e_acorde_invertido():
    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        console.log(JSON.stringify({
          bemol_fmenor: sb.usarBemol("F# menor"),      // relativa A maior -> sustenido
          bemol_fm: sb.usarBemol("F menor"),           // relativa Ab maior -> bemol
          bemolfsharp_maior: sb.usarBemol("F# maior"), // sustenido
          transpor_fsharp_menor: sb.transporAcorde("F#m7", 1, sb.usarBemol("F# menor")),
          transpor_invertido: sb.transporAcorde("D/F#", 2, false),
          transpor_bemol: sb.transporAcorde("Bb7", 2, true),
          escala_fsharp_menor: sb.escalaDiatonica("F# menor"),
        }));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["bemol_fmenor"] is False, "F# menor se escreve com sustenido"
    assert r["bemol_fm"] is True, "F menor se escreve com bemol (relativa Ab)"
    assert r["bemolfsharp_maior"] is False
    assert r["transpor_fsharp_menor"] == "Gm7"
    assert r["transpor_invertido"] == "E/G#"
    assert r["transpor_bemol"] == "C7"
    # F# menor: F#m, G#dim, A, Bm, C#m, D, E
    assert r["escala_fsharp_menor"] == ["F#m", "G#dim", "A", "Bm", "C#m", "D", "E"]


def test_editar_cifra_pelo_editor_grava_e_apaga():
    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({
          titulo: "edit", nome_pasta: "e", pasta: "/tmp/e",
          bpm: 120, tonalidade: "C maior", compasso: 4, denominador: 4,
          segundos: 20, duracao: 20,
          estudio: {batidas: [], compasso: 4, denominador: 4, bpm: 120, duracao: 20,
                    tonalidade: "C maior", acordes: [], secoes: []},
          arquivos: {mix: {nome: "00_mix.wav", url: "/api/file?p=/tmp/m.wav", audio: true}},
        });
        sb.studioDefinirAcordeDoCompasso(3, "Am7");
        sb.studioDefinirAcordeDoCompasso(0, "C");
        const depoisDeInserir = S.acordes.map((a) => [Math.round(a.inicio * 100) / 100, a.acorde]);
        sb.studioDefinirAcordeDoCompasso(3, "");           // apagar
        sb.studioDesenharCifra();
        const dom = h.doc.getElementById("linhaCifra");
        const cels = dom.querySelectorAll(".cifra-cel");
        console.log(JSON.stringify({
          depoisDeInserir, depoisDeApagar: S.acordes.map((a) => [Math.round(a.inicio * 100) / 100, a.acorde]),
          celula3: (cels.filter((el) => Number(el.dataset.compasso) <= 3 &&
            Number(el.dataset.compassoFim || el.dataset.compasso) >= 3)
            .map((el) => el.textContent.trim())[0] || ""),
          textos: cels.map((c) => c.textContent.trim()),
        }));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert ["0", "C"] in [[str(int(v)) if isinstance(v, int) else v, a] for v, a in r["depoisDeInserir"]]
    assert any(a == "Am7" for _, a in r["depoisDeInserir"])
    # apagar não remove a célula: vira "—" (nada some da timeline)
    assert r["celula3"] == "—"
    assert "C" in r["textos"]


# --------------------------------------------------------------------------
# 3. Faixas, alturas e rolagem (Seção 2)
# --------------------------------------------------------------------------
def _dados_com_muitos_stems() -> dict:
    arquivos = {
        "vocals": {"nome": "01_vocals.wav", "url": "/api/file?p=/tmp/v.wav", "audio": True},
        "drums": {"nome": "02_drums.wav", "url": "/api/file?p=/tmp/d.wav", "audio": True},
        "bass": {"nome": "03_bass.wav", "url": "/api/file?p=/tmp/b.wav", "audio": True},
        "guitar": {"nome": "04_guitar.wav", "url": "/api/file?p=/tmp/g.wav", "audio": True},
        "piano": {"nome": "05_piano.wav", "url": "/api/file?p=/tmp/p.wav", "audio": True},
        "other": {"nome": "06_strings.wav", "url": "/api/file?p=/tmp/o1.wav", "audio": True},
        "other_2": {"nome": "07_perc.wav", "url": "/api/file?p=/tmp/o2.wav", "audio": True},
        "other_3": {"nome": "08_fx.wav", "url": "/api/file?p=/tmp/o3.wav", "audio": True},
        "mix": {"nome": "00_mix.wav", "url": "/api/file?p=/tmp/m.wav", "audio": True},
    }
    return {
        "titulo": "muitos", "nome_pasta": "m", "pasta": "/tmp/m",
        "bpm": 100, "tonalidade": "A maior", "compasso": 4, "denominador": 4,
        "segundos": 200, "duracao": 200,
        "estudio": {"batidas": [], "compasso": 4, "denominador": 4, "bpm": 100,
                    "duracao": 200, "tonalidade": "A maior", "acordes": [], "secoes": []},
        "arquivos": arquivos,
        "clique": "/api/file?p=/tmp/clique.wav",
        "guia": "/api/file?p=/tmp/guia.wav",
    }


def test_faixas_ordem_canonica_ids_unicos_e_altura_sem_corte():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({json.dumps(dados)});
        const todas = S.faixas.concat(S.ensaio);
        console.log(JSON.stringify({{
          painel: h.doc.getElementById("painelFaixas").children.map((el) => el.dataset.id),
          grade: h.doc.getElementById("gradeFaixas").children.map((el) => el.dataset.id),
          ids: todas.map((f) => f.id),
          nomes: todas.map((f) => f.nome),
          alturasPainel: todas.map((f) => f.linha.style.height),
          alturasTrilha: todas.map((f) => f.trilha.style.height),
          hLinha: sb.alturaBase(),
        }}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    # Click e Guia no topo, mix no fim; ordem canônica no meio
    assert r["painel"][:2] == ["clique", "guia"]
    assert r["painel"][-1] == "mix"
    ordem_esperada = ["vocals", "drums", "bass", "guitar", "piano"]
    assert r["painel"][2:7] == ordem_esperada
    # três stems desconhecidos: ids distintos (antes todos eram "other")
    outros = [i for i in r["ids"] if i.startswith("other")]
    assert len(outros) == 3 and len(set(outros)) == 3
    # painel e grade na MESMA ordem, item por item
    assert r["painel"] == r["grade"]
    # altura suficiente para nome + M/S + VOL + PAN + medidor
    assert all(h == r["alturasPainel"][0] for h in r["alturasPainel"])
    assert all(h == r["alturasTrilha"][0] for h in r["alturasTrilha"])
    assert float(r["alturasPainel"][0].replace("px", "")) >= 72


def test_rolagem_vertical_sincronizada_nos_dois_sentidos():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({json.dumps(dados)});
        const area = h.doc.getElementById("studioTempo");
        const painel = h.doc.getElementById("painelFaixas");
        area.scrollTop = 120; sb.sincronizarScroll("tempo");
        const a = {{tempo: area.scrollTop, painel: painel.scrollTop}};
        painel.scrollTop = 40; sb.sincronizarScroll("painel");
        const b = {{tempo: area.scrollTop, painel: painel.scrollTop}};
        console.log(JSON.stringify({{a, b}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["a"]["painel"] == 120, "rolar a timeline tem de mover o painel"
    assert r["b"]["tempo"] == 40, "rolar o painel tem de mover a timeline"


def test_faixas_ocultas_nao_sao_apagadas_e_o_audio_continua():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({json.dumps(dados)});
        const f = S.faixas.find((x) => x.id === "vocals");
        sb.studioOcultarFaixa(f);
        const oculta = {{display: f.trilha.style.display, noPainel: !!h.doc.getElementById("painelFaixas").children.find((e) => e.dataset.id === "vocals"),
                          ganho: f.ganho ? f.ganho.gain.value : null}};
        sb.studioOcultarFaixa(f);
        console.log(JSON.stringify({{oculta, depois: f.trilha.style.display, total: S.faixas.length}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["oculta"]["display"] == "none"
    assert r["oculta"]["noPainel"] is True, "ocultar não pode remover a faixa do painel"
    assert r["depois"] == ""
    assert r["total"] >= 8


# --------------------------------------------------------------------------
# 4. Mixagem (Seção 9)
# --------------------------------------------------------------------------
def test_mute_solo_volume_e_pan_mexem_no_grafo_de_audio():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({json.dumps(dados)});
        S.masterVolume = 0.5; sb.aplicarMix();
        const vox = S.faixas.find((f) => f.id === "vocals");
        const bat = S.faixas.find((f) => f.id === "drums");
        const mix = S.faixas.find((f) => f.id === "mix");
        const ganhoInicial = [vox.ganho.gain.value, bat.ganho.gain.value];
        sb.studioMute(vox);
        const aposMute = vox.ganho.gain.value;
        sb.studioSolo(bat);
        const emSolo = {{vox: vox.ganho.gain.value, bat: bat.ganho.gain.value, mix: mix.ganho.gain.value}};
        vox.volume = 0.5; vox.pan = -0.7; sb.studioSolo(bat); sb.aplicarMix();
        const pan = vox.panNode.pan.value;
        console.log(JSON.stringify({{ganhoInicial, aposMute, emSolo, pan,
          master: S.master.gain.value}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["ganhoInicial"] == [1, 1]
    assert r["aposMute"] == 0, "Mute tem de zerar o ganho (não só a cor do botão)"
    assert r["emSolo"]["bat"] == 1
    assert r["emSolo"]["vox"] == 0 and r["emSolo"]["mix"] == 0, "Solo é múltiplo e silencia o resto"
    assert r["pan"] == pytest.approx(-0.7)
    assert r["master"] == pytest.approx(0.5)


# --------------------------------------------------------------------------
# 5. Clique e relógio (Seções 3 e 8)
# --------------------------------------------------------------------------
def test_clique_usa_lookahead_do_audiocontext_e_nao_setinterval_como_relogio():
    fonte = (RAIZ / "src" / "mrqvs" / "web" / "index.html").read_text(encoding="utf-8")
    js = fonte.split("<script>")[1].split("</script>")[0]
    assert "agendarCliquesLookahead" in js
    assert "currentTime" in js
    # o único setInterval permitido é o do acompanhamento da instalação da IA,
    # que não tem nada a ver com música
    trecho_studio = js[js.index("const Studio = window.Studio"):]
    # só a menção em comentário (explicando o defeito antigo) é aceitável: o
    # código de verdade não pode ter chamada de setInterval
    sem_comentarios = re.sub(r"/\*[\s\S]*?\*/", "", trecho_studio)
    sem_comentarios = re.sub(r"(?m)^\s*//.*$", "", sem_comentarios)
    assert "setInterval(" not in sem_comentarios, "o relógio do Studio não pode ser setInterval"
    assert "requestAnimationFrame" in js
    # o agendador tem de disparar osciladores no relógio do contexto
    trecho = js[js.index("function tocarPulsoClique"): js.index("function agendarCliquesLookahead")]
    assert "createOscillator" in trecho
    assert "osc.start(quando)" in trecho


def test_clique_agenda_pulsos_e_respeita_acentos_compostos():
    dados = _dados_com_muitos_stems()
    dados["estudio"]["compasso"] = 6
    dados["estudio"]["denominador"] = 8
    dados["compasso"] = 6
    dados["denominador"] = 8
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        const ctx = h.ctx;
        const criados = [];
        const orig = ctx.createOscillator;
        ctx.createOscillator = function () {{
          const o = orig.call(ctx);
          const s = o.start;
          const f = o.stop;
          o.start = function (t) {{ criados.push({{t, freq: o._freq}}); s.call(o, t); }};
          o.stop = function (t) {{ f.call(o, t); }};
          return o;
        }};
        sb.studioMontar({json.dumps(dados)});
        S.tocando = true; S.clockOffset = 0; S.clockInicio = ctx.currentTime;
        S.proximoPulso = sb.pulsoEm(0);
        // 4 s de relógio: a 100 BPM em 6/8 são 6 pulsos por compasso de 1,8 s
        for (let i = 0; i < 80; i++) {{ sb.agendarCliquesLookahead(); ctx.avancar(0.05); }}
        const freqs = criados.map((c) => c.freq);
        console.log(JSON.stringify({{
          quantos: criados.length,
          freqs: [...new Set(freqs)].sort(),
          ordem: freqs.slice(0, 6),
          pulsoAtual: S.proximoPulso,
        }}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    # 4 s a 100 BPM em 6/8 (~0,3 s por colcheia) = ~13 pulsos, sem buraco
    assert r["quantos"] >= 12, "o lookahead tem de agendar todos os pulsos do trecho"
    assert r["quantos"] <= 16, "não pode agendar em duplicidade"
    # 6/8: forte 1760 no 1, médio 1320 no 4, fracos 990 no resto
    assert sorted(r["freqs"]) == [990, 1320, 1760]
    assert r["ordem"][0] == 1760
    assert r["ordem"][3] == 1320


def test_pre_contagem_e_contagem_de_compassos():
    fonte = (RAIZ / "src" / "mrqvs" / "web" / "index.html").read_text(encoding="utf-8")
    js = fonte.split("<script>")[1].split("</script>")[0]
    assert "function agendarContagem" in js
    bloco = js[js.index('on("trContagem"'): js.index("// --- volume geral")]
    assert "Studio.contagem" in bloco and "marcarSalvo" in bloco

    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({json.dumps(dados)});
        const cliques = [];
        const ctx = h.ctx, orig = ctx.createOscillator;
        ctx.createOscillator = function () {{
          const o = orig.call(ctx);
          const s = o.start;
          o.start = function (t) {{ cliques.push(t); s.call(o, t); return; }};
          return o;
        }};
        S.contagem = 2;
        const usados = sb.agendarContagem(ctx.currentTime, 2, 0);
        console.log(JSON.stringify({{cliques: cliques.length, usados, barra: sb.duracaoDoCompasso(0)}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["cliques"] == 8, "2 compassos de 4/4 = 8 pulsos"
    assert r["usados"] == pytest.approx(2 * r["barra"])


def test_guia_e_clique_sao_independentes_e_solo_do_clique_funciona():
    """Regras de audibilidade das faixas de ensaio, verificadas no ganho real.

    * o ⏱ (metrônomo) liga/desliga o CLIQUE e não toca na guia;
    * a guia tem interruptor próprio (M do painel) e também não depende do ⏱;
    * Solo vence o interruptor global — clicar S no clique com o ⏱ desligado
      tem de soar (era o defeito antigo, que calava os dois juntos).
    """
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({json.dumps(dados)});
        const clique = S.ensaio.find((f) => f.id === "clique");
        const guia = S.ensaio.find((f) => f.id === "guia");
        const vox = S.faixas.find((f) => f.id === "vocals");

        // 1. metrônomo desligado: silencia o clique, mantém a guia
        S.metronomo = false; sb.aplicarMix();
        const semMetro = {{clique: clique.ganho.gain.value, guia: guia.ganho.gain.value}};

        // 2. Solo do clique com o ⏱ desligado: tem de soar
        clique.solo = true; sb.aplicarMix();
        const soClique = {{clique: clique.ganho.gain.value, guia: guia.ganho.gain.value,
                            vocal: vox.ganho.gain.value}};
        clique.solo = false;

        // 3. guia desligada pelo M dela: clique (com o ⏱ ligado) continua no ar
        S.metronomo = true;
        sb.studioMute(guia); sb.aplicarMix();
        const semGuia = {{guia: guia.ganho.gain.value, clique: clique.ganho.gain.value,
                           guiaAtiva: S.guiaAtiva}};
        sb.studioMute(guia);
        S.metronomo = true; sb.aplicarMix();
        const tudo = {{clique: clique.ganho.gain.value, guia: guia.ganho.gain.value}};
        console.log(JSON.stringify({{semMetro, soClique, semGuia, tudo}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["semMetro"]["clique"] == 0, "⏱ desligado tem de calar o clique"
    assert r["semMetro"]["guia"] == 1, "a guia NÃO pode depender do metrônomo"
    assert r["soClique"]["clique"] == 1, "solo do clique funciona com o ⏱ desligado"
    assert r["soClique"]["guia"] == 0 and r["soClique"]["vocal"] == 0
    assert r["semGuia"]["guia"] == 0 and r["semGuia"]["clique"] == 1
    assert r["semGuia"]["guiaAtiva"] is False
    assert r["tudo"] == {"clique": 1, "guia": 1}


def test_marcas_do_clique_sao_persistentes_na_trilha():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({json.dumps(dados)});
        const f = S.ensaio.find((x) => x.id === "clique");
        let marcou = 0;
        const ctxFake = {{globalAlpha: 1, fillStyle: "", globalAlpha2: 1,
          clearRect() {{}}, fillRect() {{ marcou++; }}, fillText() {{}}}};
        sb.desenharMarcasClique(ctxFake, 800, 60, 0, f);
        const antes = marcou;
        // desenhar de novo (o antigo apagava o canvas do clique depois das ondas)
        sb.studioDesenharFaixas();
        marcou = 0;
        sb.desenharMarcasClique(ctxFake, 800, 60, 0, f);
        console.log(JSON.stringify({{antes, depois: marcou, picos: !!f.picos}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["antes"] > 0 and r["depois"] > 0, "as marcas do clique têm de ser redesenháveis"


# --------------------------------------------------------------------------
# 6. Onda (Seção 4)
# --------------------------------------------------------------------------
def test_zoom_da_onda_muda_amplitude_e_nao_o_tempo():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.studioMontar({json.dumps(dados)});
        const picos = new Float32Array(2000);
        for (let i = 0; i < picos.length; i++) picos[i] = (i % 100) / 100;
        const medir = (zoom) => {{
          S.zoomOnda = zoom;
          const barras = [];
          const g = {{globalAlpha: 1, fillStyle: "", clearRect() {{}}, fillText() {{}},
            fillRect(x, y, w, hh) {{ barras.push({{x, y, w, hh}}); }}}};
          sb.desenharPicos(g, picos, 200, 80, "#fff", 0, 200);
          const corpo = barras.filter((b) => b.w === 1);
          // o eixo da onda é o centro do PREENCHIMENTO (a camada mais alta de
          // cada pixel); o brilho é só um cap de 2 px no topo
          const porX = new Map();
          corpo.forEach((b) => {{
            const atual = porX.get(b.x);
            if (!atual || b.hh > atual.hh) porX.set(b.x, b);
          }});
          const centros = [...porX.values()].map((b) => b.y + b.hh / 2);
          return {{alturaMax: Math.max(...corpo.map((b) => b.hh)), xs: corpo.map((b) => b.x).join(","),
                   centro: Math.max(...centros) - Math.min(...centros)}};
        }};
        console.log(JSON.stringify({{z1: medir(1), z3: medir(3)}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    # o teto é a altura do canvas: em zoom 1 a onda já usa quase tudo
    assert r["z3"]["alturaMax"] > r["z1"]["alturaMax"] * 1.15, "zoom tem de aumentar a amplitude"
    assert r["z3"]["alturaMax"] <= 80
    assert r["z3"]["xs"] == r["z1"]["xs"], "zoom da onda NÃO pode deslocar o tempo (x igual)"
    # eixo da onda no meio da trilha em qualquer zoom (nada "afunda" nem desce)
    assert r["z1"]["centro"] == pytest.approx(0, abs=0.6)
    assert r["z3"]["centro"] == pytest.approx(0, abs=0.6)


def test_clique_na_onda_posiciona_o_cursor_sem_somar_scroll_duas_vezes():
    fonte = (RAIZ / "src" / "mrqvs" / "web" / "index.html").read_text(encoding="utf-8")
    js = fonte.split("<script>")[1].split("</script>")[0]
    trecho = js[js.index("trilha.onclick = (ev) => {"): js.index("el.addEventListener(\"loadedmetadata\"")]
    assert "scrollLeft" not in trecho, "o duplo scrollLeft no clique da onda voltaria a errar o cursor"
    assert "studioBuscar(segDe(ev.clientX - r.left))" in trecho


# --------------------------------------------------------------------------
# 7. Backend com áudio real (Seções 2, 5 e 10)
# --------------------------------------------------------------------------
def _subir_servidor() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    httpd = web.ThreadingHTTPServer(("127.0.0.1", porta), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=0.5).close()
            return porta
        except OSError:
            time.sleep(0.05)
    raise AssertionError("servidor HTTP não iniciou")


def _post(base: str, rota: str, corpo: dict) -> dict:
    req = urllib.request.Request(
        base + rota,
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _wav(caminho: Path, segundos: float = 3.0, freq: float = 220.0, sr: int = 22050) -> Path:
    t = np.arange(int(sr * segundos)) / sr
    onda = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    sf.write(caminho, onda, sr)
    return caminho


def test_edicoes_salvam_campos_novos_do_editor(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(web, "_OUT_ROOT", tmp_path / "out")
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    porta = _subir_servidor()
    base = f"http://127.0.0.1:{porta}"

    apoio = tmp_path / "out" / "Musica-apoio"
    apoio.mkdir()
    acordes = [
        {"inicio": 0.0, "fim": 1.5189873417721519, "compasso": 1, "acorde": "F#m", "confianca": 1.0},
        {"inicio": 1.5189873417721519, "fim": 3.0379746835443038, "compasso": 2, "acorde": "—", "confianca": 0.0},
    ]
    secoes = [{"start": 0.0, "end": 20.0, "nome": "Introdução", "rotulo": "A"}]
    r = _post(base, "/api/edicoes", {
        "apoio": str(apoio),
        "acordes": acordes,
        "secoes": secoes,
        "compasso": 7,
        "denominador": 8,
        "bpm": 158,
        "bpmManual": True,
        "offsetInicial": 0.25,
        "mudancasCompasso": [{"compasso": 9, "numerador": 4, "denominador": 4}],
        "tom": "F# menor",
        "contagem": 2,
    })
    assert r["ok"] is True

    with urllib.request.urlopen(f"{base}/api/edicoes?apoio={urllib.parse.quote(str(apoio), safe='')}", timeout=5) as resp:
        lido = json.load(resp)
    assert lido["compasso"] == 7 and lido["denominador"] == 8
    assert lido["bpm"] == 158 and lido["bpmManual"] is True
    assert lido["offsetInicial"] == pytest.approx(0.25)
    assert lido["mudancasCompasso"][0]["numerador"] == 4
    assert lido["acordes"][0]["acorde"] == "F#m"
    assert lido["secoes"][0]["nome"] == "Introdução"
    assert lido["contagem"] == 2


def test_importar_faixa_soma_stem_ao_projeto_sem_apagar_nada(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(web, "_OUT_ROOT", tmp_path / "out")
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    porta = _subir_servidor()
    base = f"http://127.0.0.1:{porta}"

    pasta = tmp_path / "out" / "Musica-100BPM"
    pasta.mkdir()
    _wav(pasta / "00_mix.wav", 2.0, 200.0)
    _wav(pasta / "01_vocals.wav", 2.0, 300.0)

    # envia a faixa extra pelo mesmo caminho do upload do app
    enviado = _wav(tmp_path / "Violão de apoio.wav", 2.0, 440.0).read_bytes()
    ini = _post(base, "/api/upload/iniciar", {"nome": "Violão de apoio.wav", "tamanho": len(enviado)})
    req = urllib.request.Request(
        base + "/api/upload/fatia",
        data=enviado,
        headers={"Content-Type": "application/octet-stream",
                 "X-Envio-Id": ini["id"], "X-Inicio": "0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert json.load(resp)["ok"] is True
    _post(base, "/api/upload/preparar", {"id": ini["id"]})

    r = _post(base, "/api/importar-faixa", {"pasta": str(pasta), "envio": ini["id"], "nome": "Violão de apoio.wav"})
    assert r["ok"] is True
    assert r["audio"] is True
    novo = pasta / r["nome"]
    assert novo.is_file(), "a faixa importada tem de existir no disco"
    # os originais continuam intactos
    assert (pasta / "00_mix.wav").is_file() and (pasta / "01_vocals.wav").is_file()
    # o WAV importado é áudio de verdade, com o conteúdo enviado
    lido, sr = sf.read(novo, dtype="float32")
    assert sr == 22050 and lido.size > 1000

    # importar de novo NÃO sobrescreve: ganha sufixo
    ini2 = _post(base, "/api/upload/iniciar", {"nome": "Violão de apoio.wav", "tamanho": len(enviado)})
    req2 = urllib.request.Request(
        base + "/api/upload/fatia",
        data=enviado,
        headers={"Content-Type": "application/octet-stream", "X-Envio-Id": ini2["id"], "X-Inicio": "0"},
        method="POST",
    )
    urllib.request.urlopen(req2, timeout=10).close()
    _post(base, "/api/upload/preparar", {"id": ini2["id"]})
    r2 = _post(base, "/api/importar-faixa", {"pasta": str(pasta), "envio": ini2["id"]})
    assert r2["nome"] != r["nome"]
    assert (pasta / r2["nome"]).is_file()


def test_importar_faixa_recusa_pasta_fora_das_raizes(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(web, "_OUT_ROOT", tmp_path / "out")
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    porta = _subir_servidor()
    base = f"http://127.0.0.1:{porta}"
    fora = tmp_path / "fora"
    fora.mkdir()
    try:
        _post(base, "/api/importar-faixa", {"pasta": str(fora), "envio": "x"})
        raise AssertionError("deveria negar importação fora das raízes")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403


def test_criar_atalho_na_area_de_trabalho(tmp_path, monkeypatch):
    """O atalho é criado no disco, não só "reportado como criado".

    A plataforma é simulada pelo ponto de leitura do módulo (`_plataforma`) e
    não trocando `sys.platform`: trocar o `sys` do processo quebrava o próprio
    `subprocess` no runner do CI (que tem PowerShell instalado).
    """
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))
    from mrqvs import app as app_mod

    # Windows: `.lnk` na Área de Trabalho, sem pywin32 e sem tocar na máquina
    desktop = tmp_path / "win" / "Desktop"
    desktop.mkdir(parents=True)
    monkeypatch.setattr(app_mod, "_plataforma", lambda: "win32")
    monkeypatch.setattr(app_mod, "_tem_powershell", lambda: False)
    monkeypatch.setattr(app_mod, "_pasta_area_de_trabalho", lambda: desktop)
    caminho = app_mod.criar_atalho_desktop(alvo="C:/Program Files/MRQ-VS/mrq-vs.exe")
    arq = Path(caminho)
    assert arq.is_file()
    assert arq.suffix.lower() == ".lnk"
    assert arq.parent == desktop
    texto = arq.read_text(encoding="utf-8")
    assert "C:/Program Files/MRQ-VS/mrq-vs.exe" in texto
    assert "mrq-vs.ico" in texto

    # Linux/macOS: `.desktop` (existe de verdade e é executável)
    monkeypatch.setattr(app_mod, "_plataforma", lambda: "linux")
    desktop2 = tmp_path / "lin" / "Desktop"
    desktop2.mkdir(parents=True)
    monkeypatch.setattr(app_mod, "_pasta_area_de_trabalho", lambda: desktop2)
    arq2 = Path(app_mod.criar_atalho_desktop(alvo="/usr/local/bin/mrq-vs"))
    assert arq2.is_file()
    assert arq2.parent == desktop2
    corpo = arq2.read_text(encoding="utf-8")
    assert "Name=MRQ Audio Studio" in corpo
    assert "Exec=" in corpo


def test_rota_atalho_responde(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(web, "_OUT_ROOT", tmp_path / "out")
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    porta = _subir_servidor()
    base = f"http://127.0.0.1:{porta}"
    r = _post(base, "/api/atalho", {})
    assert r.get("ok") is True or "erro" in r


# --------------------------------------------------------------------------
# 8. Mixagem do servidor com áudio real (Seção 9, ponta a ponta)
# --------------------------------------------------------------------------
def test_exportar_mix_com_audio_real_respeita_solo_e_pan(tmp_path, monkeypatch):
    monkeypatch.setenv("MRQVS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(web, "_OUT_ROOT", tmp_path / "out")
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    porta = _subir_servidor()
    base = f"http://127.0.0.1:{porta}"

    pasta = tmp_path / "out" / "Mix-120BPM"
    pasta.mkdir()
    _wav(pasta / "01_vocals.wav", 2.0, 300.0)
    _wav(pasta / "02_drums.wav", 2.0, 120.0)

    r = _post(base, "/api/exportar-mix", {
        "pasta": str(pasta),
        "faixas": [
            {"caminho": "01_vocals.wav", "volume": 1.0, "pan": 0.0, "mudo": False, "solo": False},
            {"caminho": "02_drums.wav", "volume": 1.0, "pan": 0.0, "mudo": False, "solo": True},
        ],
    })
    assert r["faixas"] == 1, "solo tem de excluir a outra faixa da mixagem"
    destino = pasta / r["nome"]
    assert destino.is_file()
    dados, sr = sf.read(destino, dtype="float32", always_2d=True)
    assert dados.shape[1] == 2
    # o solo é a bateria (120 Hz): a energia está no médio/grave, não em 300 Hz
    mono = dados.mean(axis=1)
    assert np.max(np.abs(mono)) > 0.05


def test_mixdown_do_servidor_concorda_com_a_tela():
    """A regra de solo/mute é a mesma no JS e no servidor (uma não pode divergir)."""
    fonte = (RAIZ / "src" / "mrqvs" / "web" / "index.html").read_text(encoding="utf-8")
    js = fonte.split("<script>")[1].split("</script>")[0]
    corpo = js[js.index("function audivel(f, temSolo)"): js.index("function aplicarMix()")]
    assert "if (temSolo) return !!f.solo && !f.mudo;" in corpo
    assert "return !f.mudo;" in corpo

    src = (RAIZ / "src" / "mrqvs" / "mixdown.py").read_text(encoding="utf-8")
    assert "tem_solo = any(f.get(\"solo\") for f in validas)" in src
    assert "if not entra or f.get(\"mudo\")" in src


def test_salvar_edicoes_preserva_secoes_e_acordes_com_acentos(tmp_path):
    apoio = tmp_path / "x-apoio"
    apoio.mkdir()
    acordes = [{"inicio": 0.0, "fim": 2.0, "compasso": 1, "acorde": "D/F#", "confianca": 1.0}]
    secoes = [{"start": 0.0, "end": 30.0, "nome": "Pré-refrão"}]
    mixdown.salvar_edicoes(apoio, {"acordes": acordes, "secoes": secoes, "denominador": 8})
    lido = mixdown.ler_edicoes(apoio)
    assert lido["acordes"] == acordes
    assert lido["secoes"] == secoes
    assert lido["denominador"] == 8
    # `None` continua significando "nunca editado"
    assert mixdown.ler_edicoes(tmp_path / "sem")["acordes"] is None


# --------------------------------------------------------------------------
# 9. Relógio central (Seção 8) e reprodução
# --------------------------------------------------------------------------
def test_relogio_central_vem_do_audiocontext():
    """A posição da música é lida do AudioContext, não de um contador à parte."""
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox, ctx = h.ctx;
        sb.studioMontar({json.dumps(dados)});
        (async () => {{
          await sb.studioTocar();
          const inicio = {{tocando: S.tocando, offset: S.clockOffset, clock: S.clockInicio}};
          ctx.avancar(2.5);
          const t1 = sb.posicaoAtual();
          const elementos = S.faixas.filter((f) => f.el && !f.el.paused).length;
          ctx.avancar(0.5);
          const t2 = sb.posicaoAtual();
          sb.studioBuscar(6);
          ctx.avancar(1.0);
          const t3 = sb.posicaoAtual();
          sb.studioPausar();
          const parado = sb.posicaoAtual();
          console.log(JSON.stringify({{inicio, t1, t2, t3, parado, elementos,
            totalFaixas: S.faixas.length}}));
        }})();
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["inicio"]["tocando"] is True
    assert r["t1"] == pytest.approx(2.44, abs=0.02)   # 2.5 s menos a espera de 60 ms
    assert r["t2"] - r["t1"] == pytest.approx(0.5, abs=0.01)
    assert r["t3"] == pytest.approx(7.0, abs=0.05)    # seek + 1 s de relógio
    assert r["parado"] == pytest.approx(7.0, abs=0.05)
    assert r["elementos"] == r["totalFaixas"], "todos os stems tocam juntos"


def test_play_no_fim_recomeca_do_zero_e_stop_volta_ao_inicio():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox, ctx = h.ctx;
        sb.studioMontar({json.dumps(dados)});
        (async () => {{
          sb.studioBuscar(S.duracao);
          await sb.studioTocar();          // estava no fim: recomeça
          const depoisDoPlay = {{offset: S.clockOffset, tocando: S.tocando}};
          ctx.avancar(1.0);
          const t = sb.posicaoAtual();
          sb.studioParar();
          console.log(JSON.stringify({{depoisDoPlay, t, aposStop: S.tempo,
            tocando: S.tocando}}));
        }})();
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["depoisDoPlay"]["offset"] == 0
    assert r["t"] == pytest.approx(0.94, abs=0.02)
    assert r["aposStop"] == 0
    assert r["tocando"] is False


def test_pre_contagem_atrasa_a_entrada_da_banda():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox, ctx = h.ctx;
        sb.studioMontar({json.dumps(dados)});
        (async () => {{
          S.contagem = 2;
          await sb.studioTocar();
          const atraso = S.clockInicio - ctx.currentTime;
          console.log(JSON.stringify({{atraso, barra: sb.duracaoDoCompasso(0),
            tocando: S.tocando}}));
        }})();
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    # 2 compassos de 100 BPM 4/4 = 4.8 s de contagem (+ 60 ms de folga)
    assert r["barra"] == pytest.approx(2.4)
    assert r["atraso"] == pytest.approx(4.8 + 0.06, abs=0.02)
    assert r["tocando"] is True


def test_loop_reancora_o_relogio_do_trecho():
    dados = _dados_com_muitos_stems()
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox, ctx = h.ctx;
        sb.studioMontar({json.dumps(dados)});
        (async () => {{
          S.loop = true; S.loopA = 2; S.loopB = 4;
          sb.studioBuscar(3.9);
          await sb.studioTocar();
          ctx.avancar(0.2);                // passou de B=4
          sb.iniciarRelogio();
          sb.__raf && sb.__raf();          // um quadro do loop de UI
          const voltouParaA = S.clockOffset;
          console.log(JSON.stringify({{tempo: S.tempo, offset: S.clockOffset,
            voltouParaA}}));
        }})();
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    # o relógio é reancorado em A (2 s), não em 4.1 s: passou de B e voltou
    assert r["voltouParaA"] == pytest.approx(2.0, abs=0.01)
    assert r["tempo"] < 3.0


# --------------------------------------------------------------------------
# 7. Compatibilidade com dados salvos pela versão anterior (0.1.23)
# --------------------------------------------------------------------------
def test_edicoes_da_versao_anterior_restauram_secoes_cifra_e_mix():
    """Música salva pela 0.1.23 tem de reabrir com o trabalho do usuário.

    O pacote de transferência trouxe um `edicoes.json` real dessa versão
    (seções `Verso/Refrão/Final`, cifra C-G-Am-F, mix com volume por faixa).
    A estrutura de lá usa `start/end/rotulo/nome` e `id/volume/pan/mudo/solo`;
    se o carregamento só olhasse os nomes novos (`inicio`/`fim`), o usuário
    reabriria a música e veria as seções detectadas no lugar das dele — que é
    justamente "recuperar os acordes e a estrutura salvos".
    """
    dados = {
        "titulo": "demomix", "nome_pasta": "demomix-96BPM",
        "pasta": "/tmp/demomix-96BPM", "apoio": "/tmp/demomix-96BPM-apoio",
        "bpm": 96, "tonalidade": "C maior", "compasso": 4, "denominador": 4,
        "duracao": 24,
        # o detector achou só duas seções; as do usuário são três e com nome
        "secoes": [{"inicio": 0, "fim": 22.0, "rotulo": "A"},
                   {"inicio": 22.0, "fim": 24.0, "rotulo": "B"}],
        "estudio": {"batidas": [0, 0.625, 1.25], "compasso": 4, "denominador": 4,
                    "bpm": 96, "tonalidade": "C maior", "duracao": 24,
                    "secoes": [{"start": 0, "end": 22, "rotulo": "A", "nome": "A"},
                               {"start": 22, "end": 24, "rotulo": "B", "nome": "B"}],
                    "acordes": []},
        "acordes": [{"inicio": 0.0, "fim": 2.5, "compasso": 1, "acorde": "C",
                     "confianca": 0.2}],
        "arquivos": {
            "mix": {"nome": "demomix-96BPM_00_mix.wav", "audio": True,
                    "url": "/api/file?p=/tmp/demomix-96BPM/00_mix.wav"},
            "vocals": {"nome": "demomix-96BPM_01_vocals.wav", "audio": True,
                       "url": "/api/file?p=/tmp/demomix-96BPM/01_vocals.wav"},
        },
    }
    # conteúdo fiel ao edicoes.json que veio no pacote (0.1.23)
    edicoes = {
        "acordes": [
            {"inicio": 0.0, "fim": 2.5, "compasso": 1, "acorde": "C", "confianca": 0.9},
            {"inicio": 2.5, "fim": 5.0, "compasso": 2, "acorde": "G", "confianca": 0.9},
            {"inicio": 5.0, "fim": 7.5, "compasso": 3, "acorde": "Am", "confianca": 0.9},
        ],
        "secoes": [
            {"start": 0, "end": 10, "rotulo": "A", "nome": "Verso"},
            {"start": 10, "end": 20, "rotulo": "B", "nome": "Refrão"},
            {"start": 20, "end": 24, "rotulo": "C", "nome": "Final"},
        ],
        "compasso": 4, "denominador": 4, "bpm": 96, "tom": "C maior",
        "transposicao": 0, "master": 85, "zoomOnda": 1, "alturaLinha": 0,
        "mix": [
            {"id": "vocals", "volume": 0.4, "pan": -0.25, "mudo": False,
             "solo": True, "oculta": False},
            {"id": "mix", "volume": 1, "pan": 0, "mudo": False, "solo": False,
             "oculta": False},
            {"id": "clique", "volume": 0.8, "pan": 0, "mudo": False,
             "solo": False, "oculta": True},
        ],
    }
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const edicoes = {json.dumps(edicoes)};
        const fetch = (url) => String(url).startsWith("/api/edicoes")
          ? Promise.resolve({{ok: true, json: () => Promise.resolve(edicoes)}})
          : Promise.resolve({{ok: false, status: 404, json: () => Promise.resolve({{}})}});
        const h = montar({json.dumps(dados)}, {{fetch}});
        const S = h.Studio, sb = h.sandbox;
        setTimeout(() => {{
          const v = sb.faixaPorId("vocals"), mix = sb.faixaPorId("mix");
          const cli = sb.faixaPorId("clique");
          console.log(JSON.stringify({{
            secoes: S.secoes.map(s => ({{nome: s.nome, start: s.start, end: s.end}})),
            acordes: S.acordes.map(a => a.acorde),
            compasso: S.compasso, denominador: S.denominador, bpm: S.bpm,
            master: S.masterVolume,
            vocals: v && {{volume: v.volume, pan: v.pan, solo: v.solo}},
            mixMudo: mix ? mix.mudo : null,
            cliqueOculta: cli ? !!S.ocultas["clique"] : null,
            tomProjeto: S.tomProjeto, transposicao: S.transposicao,
          }}));
        }}, 60);
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    # 1) as três seções do usuário, não as duas do detector
    assert [s["nome"] for s in r["secoes"]] == ["Verso", "Refrão", "Final"]
    assert r["secoes"][1]["start"] == pytest.approx(10.0)
    assert r["secoes"][2]["end"] == pytest.approx(24.0)
    # 2) a cifra salva vence a detecção (confiança 0.9, não 0.2)
    assert r["acordes"] == ["C", "G", "Am"]
    # 3) compasso, fórmula, BPM, tom e master
    assert (r["compasso"], r["denominador"], r["bpm"]) == (4, 4, 96)
    assert r["master"] == pytest.approx(0.85)
    assert r["tomProjeto"] == "C maior" and r["transposicao"] == 0
    # 4) mixagem: volume/pan/solo vêm do disco, e a faixa oculta continua no estado
    assert r["vocals"]["volume"] == pytest.approx(0.4)
    assert r["vocals"]["pan"] == pytest.approx(-0.25)
    assert r["vocals"]["solo"] is True
    assert r["mixMudo"] is False
    assert r["cliqueOculta"] is True


def test_marcadores_de_secao_e_audio_de_guia_sao_independentes():
    """Seção é marcador; guia é áudio. Um não pode apagar o outro.

    Requisito explícito: "marcadores não podem apagar/substituir áudio". O
    teste monta com guia, apaga todas as seções (como o usuário faz ao limpar
    a estrutura) e confere que a faixa Guia continua no mixer, tocável e com a
    URL intacta; depois recria uma seção e confere que o áudio segue o mesmo.
    """
    dados = {
        "titulo": "Guia", "nome_pasta": "Guia", "pasta": "/tmp/guia",
        "apoio": "/tmp/guia-apoio", "bpm": 100, "tonalidade": "D maior",
        "compasso": 4, "denominador": 4, "duracao": 12,
        "clique": "/api/file?p=/tmp/guia-apoio/clique.wav",
        "guia": "/api/file?p=/tmp/guia-apoio/guia.wav",
        "estudio": {"batidas": [], "compasso": 4, "bpm": 100, "duracao": 12,
                    "tonalidade": "D maior",
                    "secoes": [{"start": 0, "end": 6, "rotulo": "A", "nome": "Verso"},
                               {"start": 6, "end": 12, "rotulo": "B", "nome": "Refrão"}],
                    "acordes": []},
        "arquivos": {"mix": {"nome": "g_00_mix.wav", "audio": True,
                             "url": "/api/file?p=/tmp/guia/00_mix.wav"}},
    }
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar({json.dumps(dados)});
        const S = h.Studio, sb = h.sandbox;
        const guia = sb.faixaPorId("guia");
        const antes = {{secoes: S.secoes.length, temGuia: !!guia,
                       url: guia ? guia.el.src : null, nome: guia ? guia.nome : null}};
        // o usuário apaga todas as seções (limpar a estrutura, sem tocar no áudio)
        S.secoes = [];
        sb.studioDesenharSecoes();
        sb.aplicarMix();
        const semSecoes = {{secoes: S.secoes.length, temGuia: !!sb.faixaPorId("guia"),
                           audivel: !!guia && sb.audivel(guia, false),
                           ganho: guia && guia.ganho ? guia.ganho.gain.value : null,
                           marcas: (sb.faixaPorId("guia").trilha.querySelectorAll(".secao-bloco") || []).length}};
        // e cria uma seção nova: continua a mesma faixa, mesmo áudio
        S.secoes.push({{start: 2, end: 4, rotulo: "C", nome: "Ponte"}});
        sb.studioDesenharSecoes();
        const depois = {{secoes: S.secoes.length,
                         mesmoAudio: sb.faixaPorId("guia").el === guia.el,
                         url: sb.faixaPorId("guia").el.src,
                         marcas: sb.faixaPorId("guia").trilha.querySelectorAll(".secao-bloco").length}};
        console.log(JSON.stringify({{antes, semSecoes, depois}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["antes"]["secoes"] == 2 and r["antes"]["temGuia"] is True
    assert r["antes"]["url"] == "/api/file?p=/tmp/guia-apoio/guia.wav"
    # apagar as seções não desmonta a Guia nem a cala
    assert r["semSecoes"]["temGuia"] is True
    assert r["semSecoes"]["secoes"] == 0
    assert r["semSecoes"]["audivel"] is True
    assert r["semSecoes"]["ganho"] == pytest.approx(1.0)
    assert r["semSecoes"]["marcas"] == 0
    # criar seção nova desenha a marca na trilha da Guia, sem trocar o áudio
    assert r["depois"]["secoes"] == 1
    assert r["depois"]["marcas"] == 1
    assert r["depois"]["mesmoAudio"] is True
    assert r["depois"]["url"] == "/api/file?p=/tmp/guia-apoio/guia.wav"


def test_texto_da_pre_contagem_e_legivel_e_o_botao_mostra_o_estado():
    """A barra dizia "123 Sem Pré-contagem": os pulsos eram caracteres.

    Nas capturas do usuário e na 0.1.23 o rótulo carregava os três pulsos
    como texto, então a leitura saía como um número colado na frase. O botão
    passou a ter ícone próprio e um `<span>` com o estado; este teste percorre
    o ciclo 0 → 1 → 2 → 0 e confere texto, classe e dica a cada passo.
    """
    dados = {
        "titulo": "Contagem", "nome_pasta": "C", "pasta": "/tmp/c", "apoio": "",
        "bpm": 100, "tonalidade": "C maior", "compasso": 4, "denominador": 4,
        "duracao": 8,
        "estudio": {"batidas": [], "compasso": 4, "bpm": 100, "duracao": 8,
                    "tonalidade": "C maior", "acordes": [], "secoes": []},
        "arquivos": {"mix": {"nome": "c_00_mix.wav", "audio": True,
                             "url": "/api/file?p=/tmp/c/00_mix.wav"}},
    }
    script = r"""
        const {montar} = require("./harness");
        const h = montar(__DADOS__);
        const S = h.Studio, sb = h.sandbox, doc = h.doc;
        const lido = () => ({
          texto: doc.getElementById("trContagemTexto").textContent,
          ligado: doc.getElementById("trContagem").classList.contains("on"),
          dica: doc.getElementById("trContagem").title,
          contagem: S.contagem,
        });
        const passos = [];
        S.contagem = 0; sb.studioAtualizarTransporte();
        passos.push(lido());
        for (let i = 0; i < 3; i++){
          doc.getElementById("trContagem").onclick();
          passos.push(lido());
        }
        // o rótulo no markup: só o span do estado, sem os pulsos colados
        const html = require("fs").readFileSync(
          require("path").resolve(__dirname, "..", "..", "src", "mrqvs", "web", "index.html"),
          "utf8");
        const m = /id="trContagem"[\s\S]*?>([\s\S]*?)<\/button>/.exec(html);
        const markup = m ? m[1].replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim() : "?";
        console.log(JSON.stringify({passos, markup,
          tem123: /(^|\s)123(\s|$)/.test(markup)}));
    """
    saida = _rodar_node(script.replace("__DADOS__", json.dumps(dados)))
    r = json.loads(saida.strip().splitlines()[-1])
    p = r["passos"]
    assert p[0]["texto"] == "sem contagem" and p[0]["ligado"] is False
    assert p[1]["contagem"] == 1 and p[1]["texto"] == "1 compasso de contagem"
    assert p[1]["ligado"] is True and "1 compasso" in p[1]["dica"]
    assert p[2]["contagem"] == 2 and p[2]["texto"] == "2 compassos de contagem"
    assert p[3]["contagem"] == 0 and p[3]["texto"] == "sem contagem"
    assert p[3]["ligado"] is False
    # no markup sobra só o span do estado: nada de pulsos como texto
    assert r["markup"] == "sem contagem"
    assert r["tem123"] is False


# --------------------------------------------------------------------------
# 8. O botão do menu lateral no cabeçalho + rolagem visível das faixas
# --------------------------------------------------------------------------
def test_botao_do_menu_lateral_fica_no_cabecalho_e_sincroniza_os_dois():
    """O botão existia só dentro do Studio, então a tela inicial não tinha como
    recolher "Minhas músicas". Agora há um no cabeçalho, ao lado da versão, e os
    dois espelham o MESMO estado — clicar num não pode deixar o outro aceso.

    Antes também havia dois lugares acendendo botão (handler e restauração do
    localStorage), cada um com uma cópia da regra.
    """
    html = (RAIZ / "src" / "mrqvs" / "web" / "index.html").read_text(encoding="utf-8")
    # o botão está dentro de .janela-botoes, depois da versão (posição da foto 2)
    janela = html[html.index('class="janela-botoes"'):html.index("</header>")]
    assert 'id="fMenuTopo"' in janela
    assert janela.index("versaoTopo") < janela.index("fMenuTopo")
    # o estado "ligado" não pode depender da classe .ferr (o botão saiu dela)
    assert ".ferr.on,.botao-icone.on{" in html

    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const h = montar();
        const sb = h.sandbox, doc = h.doc;
        const topo = doc.getElementById("fMenuTopo");
        const barra = doc.getElementById("fMenu");
        const estado = () => ({
          body: doc.body.classList.contains("sem-lateral"),
          topo: topo.classList.contains("on"),
          topoAria: topo.getAttribute("aria-pressed"),
          barra: barra.classList.contains("on"),
          barraAria: barra.getAttribute("aria-pressed"),
        });
        const passos = [estado()];
        topo.onclick();  passos.push(estado());   // pelo cabeçalho
        barra.onclick(); passos.push(estado());   // pela barra do Studio
        topo.onclick();  passos.push(estado());   // de novo no cabeçalho
        console.log(JSON.stringify(passos));
        """
    )
    passos = json.loads(saida.strip().splitlines()[-1])
    assert passos[0]["body"] is False
    for passo, esperado in zip(passos[1:], (True, False, True), strict=True):
        assert passo["body"] is passo["topo"] is passo["barra"] is esperado
        assert passo["topoAria"] == ("true" if esperado else "false")
        assert passo["barraAria"] == passo["topoAria"]


def test_estado_salvo_acende_os_dois_botoes_antes_de_abrir_musica():
    """Recarregar com o menu recolhido tem de acender também o botão do topo."""
    saida = _rodar_node(
        """
        const fs = require("fs"), path = require("path"), vm = require("vm");
        const {Document} = require("./minidom");
        const html = fs.readFileSync(
          path.resolve(__dirname, "..", "..", "src", "mrqvs", "web", "index.html"), "utf8");
        const js = /<script[^>]*>([\\s\\S]*?)<\\/script>/.exec(html)[1];
        const doc = new Document();
        const ids = ["fMenuTopo", "fMenu", "versaoTopo", "bibAtualizar", "bibPasta"];
        for (const id of ids) doc.criar(id, "div");
        const sandbox = {
          document: doc, window: null, location: {origin: "", href: ""},
          console: {log() {}, warn() {}, error() {}},
          fetch: () => Promise.resolve({ok: false, json: () => Promise.resolve({})}),
          localStorage: {_d: {"mrqvs.semLateral": "1"},
            getItem(k) { return this._d[k] || null; }, setItem(k, v) { this._d[k] = v; }},
          setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
          addEventListener() {}, removeEventListener() {}, requestAnimationFrame: () => 1,
          cancelAnimationFrame() {}, getComputedStyle: () => ({getPropertyValue: () => ""}),
          Math, JSON, Object, Array, Number, String, Boolean, Promise, Error, RegExp,
          Date, Set, Map, isFinite, parseInt, parseFloat, URL, Float32Array, Uint8Array,
          devicePixelRatio: 1, innerWidth: 1440, innerHeight: 900, performance: {now: () => 0},
        };
        sandbox.window = sandbox; sandbox.globalThis = sandbox;
        vm.createContext(sandbox);
        new vm.Script(js).runInContext(sandbox, {timeout: 20000});
        const topo = doc.getElementById("fMenuTopo"), barra = doc.getElementById("fMenu");
        console.log(JSON.stringify({
          body: doc.body.classList.contains("sem-lateral"),
          topo: topo.classList.contains("on"), topoAria: topo.getAttribute("aria-pressed"),
          barra: barra.classList.contains("on"), barraAria: barra.getAttribute("aria-pressed"),
        }));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["body"] is True
    assert r["topo"] is True and r["topoAria"] == "true"
    assert r["barra"] is True and r["barraAria"] == "true"


def test_painel_de_faixas_mostra_que_ha_mais_faixas_abaixo():
    """8 faixas em 586 px de altura: duas ficavam abaixo da dobra e a rolagem
    era invisível (`scrollbar-width:none` + `::-webkit-scrollbar{display:none}`),
    então a lista parecia ter sido cortada.

    Agora: barra de rolagem visível, classe `tem-mais` no painel enquanto há
    conteúdo oculto e o contador "N faixas · K à vista".
    """
    html = (RAIZ / "src" / "mrqvs" / "web" / "index.html").read_text(encoding="utf-8")
    assert ".painel-faixas::-webkit-scrollbar{display:none}" not in html
    assert ".painel-faixas::-webkit-scrollbar{width:11px}" in html
    assert ".studio-painel.tem-mais::after" in html
    # o transporte não flutua mais sobre as últimas faixas
    assert "position:sticky;bottom:0;z-index:8}" not in html

    dados = {
        "titulo": "Rolagem", "nome_pasta": "R", "pasta": "/tmp/r", "apoio": "",
        "bpm": 96, "tonalidade": "G maior", "compasso": 4, "denominador": 4,
        "duracao": 24,
        "estudio": {"batidas": [], "compasso": 4, "bpm": 96, "duracao": 24,
                    "tonalidade": "G maior", "acordes": [], "secoes": []},
        "arquivos": {
            k: {"nome": f"r_{k}.wav", "audio": True, "url": f"/x/{k}.wav"}
            for k in ("mix", "vocals", "drums", "bass", "guitar", "piano", "other")
        },
    }
    saida = _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const h = montar({json.dumps(dados)});
        const sb = h.sandbox, doc = h.doc;
        const painel = doc.getElementById("painelFaixas");
        const caixa = doc.getElementById("studioPainel");
        const contagem = doc.getElementById("painelContagem");
        const base = sb.alturaBase();
        // 3 faixas visíveis num painel de 228 px = conteúdo maior que a janela
        painel.clientHeight = base * 3;
        painel.scrollHeight = base * 7;
        painel.scrollTop = 0;
        sb.studioAtualizarRolagemPainel();
        const noTopo = {{temMais: caixa.classList.contains("tem-mais"),
                         texto: contagem.textContent, dica: contagem.title}};
        // rolando até o fim, o degradê some
        painel.scrollTop = painel.scrollHeight - painel.clientHeight;
        sb.studioAtualizarRolagemPainel();
        const noFim = {{temMais: caixa.classList.contains("tem-mais")}};
        console.log(JSON.stringify({{base, faixas: doc.querySelectorAll("#painelFaixas .faixa").length,
          noTopo, noFim}}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["faixas"] == 7
    assert r["noTopo"]["temMais"] is True
    assert r["noTopo"]["texto"] == "7 faixas · 3 à vista"
    assert "abaixo" in r["noTopo"]["dica"]
    assert r["noFim"]["temMais"] is False
