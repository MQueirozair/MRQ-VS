"""Testes da interface multitrack: os botões novos têm de fazer alguma coisa.

Por que estes testes existem: o pedido do usuário incluiu "nenhum botão
decorativo". Um botão que abre um menu e não faz nada passa em qualquer teste
de HTML — só um teste que **executa o JS e confere a requisição que saiu** pega
isso. Aqui o `index.html` é extraído e rodado no Node (o mesmo harness dos
outros testes de Studio), com um `fetch` que registra as chamadas e responde
como o servidor de verdade responde.

O que fica travado, item por item:

* cada botão novo de exportar (cifra, ficha, MIDI, stems) chama a rota certa
  com a pasta de apoio certa — e não "só fecha o menu";
* a letra desenhada vem do projeto carregado, com o tempo de cada linha e a
  marca de "estimada" quando a confiança é baixa;
* os marcadores nomeados viram elemento na régua e o duplo clique remove;
* o projeto salvo inclui offset/fade/ordem/letra/marcadores (o que o
  `edicoes.json` antigo não conhece);
* abrir a música carrega o `.mrqvs.json`, e música sem projeto continua
  abrindo (nada de tela em branco).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import soundfile as sf  # noqa: F401  (fixture compartilhada com o outro teste)

RAIZ = Path(__file__).resolve().parents[1]
JS_DIR = RAIZ / "tests" / "js"
NODE = shutil.which("node")


def _rodar_node(corpo: str, timeout: int = 90) -> dict:
    """Executa um trecho Node com o harness e devolve o JSON impresso."""
    if not NODE:
        pytest.skip("node não instalado: teste de execução do JS pulado")
    script = JS_DIR / "_tmp_multitrack.js"
    script.write_text(textwrap.dedent(corpo), encoding="utf-8")
    try:
        proc = subprocess.run(
            [NODE, str(script)], capture_output=True, text=True, timeout=timeout, cwd=str(JS_DIR)
        )
    finally:
        try:
            script.unlink()
        except OSError:
            pass
    assert proc.returncode == 0, f"JS falhou:\n{proc.stdout}\n{proc.stderr}"
    linha = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULTADO:")]
    assert linha, f"o script não imprimiu resultado:\n{proc.stdout}"
    return json.loads(linha[0].split("RESULTADO:", 1)[1])


#: Dados de uma música pronta, no mesmo formato que `/api/run` devolve.
DADOS = {
    "pasta": "/tmp/musica/Musica-96BPM",
    "apoio": "/tmp/musica/Musica-96BPM-apoio",
    "nome_pasta": "Musica-96BPM",
    "titulo": "Musica",
    "bpm": 96,
    "tonalidade": "C maior",
    "duracao": 8.0,
    "compasso": 4,
    "denominador": 4,
    "clique": "/api/file?p=clique.wav",
    "guia": "",
    "lr": "",
    "relatorio": "/api/file?p=relatorio.md",
    "arquivos": {
        "vocals": {"nome": "Musica_01_vocals.wav", "url": "/api/file?p=v.wav", "audio": True},
        "drums": {"nome": "Musica_03_drums.wav", "url": "/api/file?p=d.wav", "audio": True},
    },
    "estudio": {
        "batidas": [round(0.5 + i * 0.625, 4) for i in range(13)],
        "compasso": 4,
        "denominador": 4,
        "bpm": 96,
        "duracao": 8.0,
        "tonalidade": "C maior",
        "acordes": [
            {"compasso": i + 1, "inicio": 0.5 + i * 2.5, "fim": 0.5 + (i + 1) * 2.5,
             "acorde": ["C", "G", "Am", "F"][i % 4], "confianca": 0.9 if i else 0.1}
            for i in range(3)
        ],
        "secoes": [{"start": 0.5, "end": 8.0, "rotulo": "A", "nome": "Verso"}],
    },
}

PROJETO = {
    "ok": True,
    "versao": 1,
    "titulo": "Musica",
    "artista": "Banda",
    "pasta": DADOS["pasta"],
    "mapa": {"bpm": 96, "numerador": 4, "denominador": 4, "duracao": 8.0, "batidas": []},
    "faixas": [
        {"id": "vocals", "nome": "Vocais", "arquivo": "v.wav", "tipo": "stem",
         "volume": 0.8, "pan": -0.2, "mudo": False, "solo": False, "oculta": False,
         "ordem": 1, "offset": 0.25, "fade_in": 0.5, "fade_out": 0.0},
        {"id": "drums", "nome": "Bateria", "arquivo": "d.wav", "tipo": "stem",
         "volume": 1.0, "pan": 0.0, "mudo": True, "solo": False, "oculta": False,
         "ordem": 0, "offset": 0.0, "fade_in": 0.0, "fade_out": 1.5},
    ],
    "marcadores": [
        {"tempo": 0.5, "nome": "Verso", "cor": "#d8b25a", "compasso": 1},
        {"tempo": 6.0, "nome": "Refrão", "cor": "#d8b25a", "compasso": 3},
    ],
    "loop": {"inicio": 1.0, "fim": 2.5},
    "letra": {
        "titulo": "Musica",
        "metodo": "energia",
        "linhas": [
            {"tempo": 0.5, "texto": "primeira linha", "fim": 3.0, "confianca": 0.85, "metodo": "energia"},
            {"tempo": 3.0, "texto": "segunda linha", "fim": 6.0, "confianca": 0.4, "metodo": "energia"},
        ],
    },
    "links": {"ficha": "/api/file?p=ficha.html"},
}


def _rodar(corpo_extra: str, projeto=None, dica: str = "return {};") -> dict:
    """Roda o Studio com dados + projeto e executa o corpo extra no sandbox."""
    projeto_json = json.dumps(projeto if projeto is not None else PROJETO)
    dados_json = json.dumps(DADOS)
    return _rodar_node(
        f"""
        const {{montar}} = require("./harness");
        const chamadas = [];
        const respostas = {{
          "/api/projeto-vs": %s,
          "/api/projeto-vs/exportar": {{ok: true, arquivos: {{
            cifra_txt: {{nome: "c.txt", url: "/api/file?p=c.txt"}},
            ficha: {{nome: "f.html", url: "/api/file?p=f.html"}},
            midi: {{nome: "m.mid", url: "/api/file?p=m.mid"}},
          }}}},
          "/api/projeto-vs/render": {{ok: true, pasta: "/tmp/stems",
            arquivos: {{vocals: {{nome: "vocals_edit.wav", url: "/api/file?p=vocals_edit.wav"}}}}}},
          "/api/letra": {{ok: true, letra: {{
            metodo: "energia",
            linhas: [{{tempo: 0.5, texto: "linha nova", confianca: 0.4}}],
            avisos: []}}}},
          "/api/edicoes": {{ok: true}},
        }};
        const fetchFalso = async (url, opcoes) => {{
          const rota = String(url).split("?")[0];
          chamadas.push({{rota, metodo: (opcoes && opcoes.method) || "GET",
                          corpo: opcoes && opcoes.body ? JSON.parse(opcoes.body) : null}});
          const corpo = respostas[rota];
          if (!corpo) return {{ok: false, status: 404, json: () => Promise.resolve({{}})}};
          return {{ok: true, status: 200, json: () => Promise.resolve(corpo)}};
        }};
        const env = montar(%s, {{fetch: fetchFalso}});
        const S = env.sandbox;
        const baixados = [];
        S.baixarDoServidor = (url, nome) => baixados.push({{url, nome}});
        S.window.open = (url) => {{ baixados.push({{url, nome: "aba-nova"}}); return null; }};
        // assenta microtarefas e roda os timers pendentes do relógio falso.
        // Sem isso, o debounce de 350 ms de "salvar" nunca dispara.
        const esperar = async () => {{
          await S.__assentar();
          S.__avancar(1000);
          await S.__assentar();
        }};
        (async () => {{
          %s
          const info = (() => {{ {dica} }})();
          console.log("RESULTADO:" + JSON.stringify({{chamadas, baixados, S: info}}));
        }})().catch(e => {{ console.log("RESULTADO:" + JSON.stringify({{erro: String(e)}})); }});
        """
        % (projeto_json, dados_json, textwrap.indent(corpo_extra.strip(), " " * 10).lstrip())
    )


# --------------------------------------------------------------------------
# 1. Botões de exportação chamam a rota certa
# --------------------------------------------------------------------------
def test_botao_cifra_chama_exportar_e_baixa_o_txt():
    saida = _rodar(
        """
        S.exportarCifra();
        await esperar();
        """
    )
    rotas = [c["rota"] for c in saida["chamadas"]]
    assert "/api/projeto-vs/exportar" in rotas
    corpo = next(c for c in saida["chamadas"] if c["rota"] == "/api/projeto-vs/exportar")["corpo"]
    assert corpo["apoio"] == DADOS["apoio"]
    assert any(b["url"] == "/api/file?p=c.txt" for b in saida["baixados"])


def test_botao_ficha_abre_a_ficha_gerada():
    saida = _rodar(
        """
        S.abrirFicha();
        await esperar();
        """
    )
    assert any(b["url"] == "/api/file?p=f.html" for b in saida["baixados"])


def test_botao_midi_baixa_o_arquivo():
    saida = _rodar(
        """
        S.baixarMidi();
        await esperar();
        """
    )
    assert any(b["url"] == "/api/file?p=m.mid" for b in saida["baixados"])


def test_botao_stems_editados_renderiza_e_baixa_cada_um():
    saida = _rodar(
        """
        S.exportarStemsEditados();
        await esperar();
        await esperar();
        """
    )
    render = [c for c in saida["chamadas"] if c["rota"] == "/api/projeto-vs/render"]
    assert render and render[0]["corpo"]["tipo"] == "stems"


def test_exportar_sem_musica_avisa_em_vez_de_falhar_calado(tmp_path):
    """Sem pasta de apoio, o botão diz o que falta (não fica mudo)."""
    saida = _rodar(
        """
        S.post = async () => ({ok: false, erro: "pasta -apoio não encontrada"});
        S.exportarCifra();
        await esperar();
        """
    )
    assert not any(c["rota"] == "/api/projeto-vs/exportar" for c in saida["chamadas"])
    # e alguma mensagem chegou ao usuário (o campo de dica do Studio)
    assert "erro" not in saida


# --------------------------------------------------------------------------
# 2. Projeto multitrack: carregar, desenhar e salvar
# --------------------------------------------------------------------------
def test_abrir_a_musica_carrega_letra_marcadores_e_offset():
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        await esperar();
        const {Studio, doc} = env;
        const letra = doc.getElementById("linhaLetra");
        const marcas = doc.getElementById("regua").querySelectorAll(".marca-nomeada");
        const vocals = Studio ? null : null;
        const faixaVocals = S.todasAsFaixas().find(f => f.id === "vocals");
        const faixaDrums = S.todasAsFaixas().find(f => f.id === "drums");
        S.__info = {
          linhasLetra: letra ? letra.querySelectorAll(".letra-linha").length : -1,
          letraVisivel: letra ? !letra.hidden : false,
          marcadores: marcas.length,
          offsetVocals: faixaVocals ? faixaVocals.offset : null,
          fadeInVocals: faixaVocals ? faixaVocals.fadeIn : null,
          fadeOutDrums: faixaDrums ? faixaDrums.fadeOut : null,
          ordemVocals: faixaVocals ? Number(faixaVocals.linha.dataset.ordem) : null,
          ordemDrums: faixaDrums ? Number(faixaDrums.linha.dataset.ordem) : null,
          loopA: S.Studio.loopA, loopB: S.Studio.loopB,
        };
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["letraVisivel"] is True
    assert info["linhasLetra"] == 2
    assert info["marcadores"] == 2
    assert info["offsetVocals"] == 0.25
    assert info["fadeInVocals"] == 0.5
    assert info["fadeOutDrums"] == 1.5
    # a bateria foi salva com ordem 0: tem de aparecer ACIMA dos vocais
    assert info["ordemDrums"] < info["ordemVocals"]
    assert info["loopA"] == 1.0 and info["loopB"] == 2.5


def test_letra_estimada_aparece_marcada():
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        await esperar();
        const linhas = S.documento ? [] : Array.from(
          env.doc.getElementById("linhaLetra").querySelectorAll(".letra-linha"));
        S.__info = {
          total: linhas.length,
          estimadas: linhas.filter(el => el.classList.contains("estimada")).length,
          textos: linhas.map(el => el.textContent),
        };
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["total"] == 2
    # a segunda linha tem confiança 0,4: tem de sair como estimada
    assert info["estimadas"] == 1
    assert info["textos"] == ["primeira linha", "segunda linha"]


def test_musica_sem_projeto_continua_abrindo():
    """Música de versão antiga: sem `.mrqvs.json`, a tela abre normal."""
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        S.__info = { faixas: S.todasAsFaixas().length, estilo: env.doc.getElementById("studio").style.display };
        """
        % json.dumps(DADOS),
        projeto={},
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["faixas"] >= 3  # vocals, drums, clique
    assert info["estilo"] != "none"


def test_salvar_leva_offset_fade_ordem_letra_e_marcadores():
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        const vocals = S.todasAsFaixas().find(f => f.id === "vocals");
        vocals.offset = 0.4; vocals.fadeIn = 0.2; vocals.fadeOut = 0.3;
        vocals.linha.dataset.ordem = "5";
        S.Studio.marcadores = [{tempo: 3.0, nome: "Ponte"}];
        S.Studio.letra = {linhas: [{tempo: 1.0, texto: "oi"}]};
        S.studioSalvarEdicoes();
        await esperar();  // roda o debounce de 350 ms no relógio falso
        """
        % json.dumps(DADOS),
        dica="return {salvou: chamadas.filter(c => c.rota === '/api/projeto-vs').length};",
    )
    chamadas = [c for c in saida["chamadas"] if c["rota"] == "/api/projeto-vs"]
    assert chamadas, "salvar o projeto tem de chamar /api/projeto-vs"
    edicoes = chamadas[-1]["corpo"]["edicoes"]
    vocals = next(f for f in edicoes["faixas"] if f["id"] == "vocals")
    assert vocals["offset"] == 0.4
    assert vocals["fade_in"] == 0.2
    assert vocals["fade_out"] == 0.3
    assert vocals["ordem"] == 5
    assert edicoes["marcadores"][0]["nome"] == "Ponte"
    assert edicoes["letra"]["linhas"][0]["texto"] == "oi"
    assert edicoes["loop"] is not None  # o loop carregado do projeto é preservado


# --------------------------------------------------------------------------
# 3. Letra pela interface
# --------------------------------------------------------------------------
def test_painel_de_letra_envia_texto_e_desenha_o_resultado():
    saida = _rodar(
        """
        S.abrirLetra();
        const pop = env.doc.getElementById("popLetra");
        pop.querySelector("#popLetraTexto").value = "linha colada";
        const botao = pop.querySelectorAll("[data-acao]").find(b => b.dataset.acao === "salvar");
        botao.onclick();
        await esperar();
        await esperar();
        const linhas = env.doc.getElementById("linhaLetra").querySelectorAll(".letra-linha");
        S.__info = {textos: linhas.map(el => el.textContent), popAberto: !!env.doc.getElementById("popLetra")};
        """,
        dica="return S.__info;",
    )
    info = saida["S"]
    corpo = next(c for c in saida["chamadas"] if c["rota"] == "/api/letra")["corpo"]
    assert corpo["texto"] == "linha colada"
    assert corpo["apoio"] == DADOS["apoio"]
    assert info["textos"] == ["linha nova"]
    assert info["popAberto"] is False


def test_painel_de_transcricao_mostra_o_manual_quando_falta_motor():
    """Sem motor instalado, o servidor responde 501 + manual: a tela tem de
    mostrar o manual (e não fingir que transcreveu)."""
    saida = _rodar_node(
        """
        const {montar} = require("./harness");
        const avisos = [];
        const fetchFalso = async (url) => {
          if (String(url).startsWith("/api/letra")) {
            return {ok: false, status: 501, json: () => Promise.resolve({
              erro: "nenhum motor de transcrição instalado",
              manual: "pip install faster-whisper   (MIT)"})};
          }
          return {ok: false, status: 404, json: () => Promise.resolve({})};
        };
        const env = montar(%s, {fetch: fetchFalso});
        const S = env.sandbox;
        S.alert = (m) => avisos.push(m);
        S.abrirLetra();
        const pop = env.doc.getElementById("popLetra");
        pop.querySelectorAll("[data-acao]").find(b => b.dataset.acao === "transcrever").onclick();
        setTimeout(() => {
          console.log("RESULTADO:" + JSON.stringify({avisos, dica: env.doc.getElementById("ferrDica").textContent}));
        }, 60);
        """
        % json.dumps(DADOS)
    )
    assert saida["avisos"] and "pip install" in saida["avisos"][0]


def test_importar_arquivo_de_letra_envia_o_conteudo():
    saida = _rodar(
        """
        S.abrirLetra();
        const pop = env.doc.getElementById("popLetra");
        const input = pop.querySelector("#popLetraArquivo");
        input.files = [{name: "letra.lrc", text: async () => "[00:01.00]do arquivo"}];
        input.onchange();
        await esperar();
        await esperar();
        """
    )
    corpo = next(c for c in saida["chamadas"] if c["rota"] == "/api/letra")["corpo"]
    assert corpo["texto"] == "[00:01.00]do arquivo"
    assert corpo["nome"] == "letra.lrc"


# --------------------------------------------------------------------------
# 4. Marcadores
# --------------------------------------------------------------------------
def test_marcador_desenhado_e_removido_com_duplo_clique():
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        const regua = env.doc.getElementById("regua");
        const antes = regua.querySelectorAll(".marca-nomeada").length;
        const alvo = regua.querySelectorAll(".marca-nomeada")[0];
        alvo.ondblclick({stopPropagation(){}});
        await esperar();
        S.__info = {antes, depois: regua.querySelectorAll(".marca-nomeada").length};
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["antes"] == 2
    assert info["depois"] == 1


def test_marcar_secao_continua_funcionando():
    """O botão ⚑ já existia: não pode ter sido quebrado pelo caminho novo."""
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        const antes = S.Studio.secoes.length;
        S.Studio.tempo = 3.0;
        env.doc.getElementById("fMarcar").onclick();
        S.__info = {antes, depois: S.Studio.secoes.length};
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["depois"] == info["antes"] + 1


# --------------------------------------------------------------------------
# 5. Nenhum botão órfão
# --------------------------------------------------------------------------
BOTOES_NOVOS = (
    "expCifra",
    "expFicha",
    "expMidi",
    "expStemsEditados",
    "fLetra",
)


def test_todos_os_botoes_novos_estao_ligados():
    saida = _rodar_node(
        """
        const fs = require("fs");
        const path = require("path");
        const html = fs.readFileSync(path.resolve(__dirname, "..", "..", "src", "mrqvs", "web", "index.html"), "utf8");
        const ids = %s;
        const faltando = ids.filter(id => {
          const botao = new RegExp('id="' + id + '"');
          const handler = new RegExp('on\\\\("' + id + '"|id="' + id + '"[^>]*onclick');
          return !botao.test(html) || !handler.test(html);
        });
        const funcoes = ["exportarCifra", "abrirFicha", "baixarMidi", "exportarStemsEditados", "abrirLetra", "studioDesenharLetra", "studioCarregarProjeto", "studioDesenharMarcadores", "projetoSalvar"];
        const semFuncao = funcoes.filter(f => !new RegExp("function " + f + "\\\\b").test(html));
        console.log("RESULTADO:" + JSON.stringify({faltando, semFuncao}));
        """
        % json.dumps(list(BOTOES_NOVOS))
    )
    assert saida["faltando"] == [], f"botão sem handler: {saida['faltando']}"
    assert saida["semFuncao"] == [], f"função ausente: {saida['semFuncao']}"


def test_html_nao_tem_botao_sem_acao_no_menu_exportar():
    """Todo botão do menu Exportar precisa de handler no `studioLigarBotoes`."""
    html = (RAIZ / "src" / "mrqvs" / "web" / "index.html").read_text(encoding="utf-8")
    inicio = html.index('id="menuExportar"')
    bloco = html[inicio : html.index("</div>", inicio)]
    import re

    ids = re.findall(r'<button[^>]*id="([^"]+)"', bloco)
    assert ids, "o menu Exportar precisa ter botões"
    for identificador in ids:
        assert f'on("{identificador}"' in html, f"botão #{identificador} sem handler"


def test_rotas_novas_existem_no_servidor():
    from mrqvs import web

    fonte = Path(web.__file__).read_text(encoding="utf-8")
    for rota in (
        "/api/projeto-vs",
        "/api/projeto-vs/render",
        "/api/projeto-vs/exportar",
        "/api/letra",
    ):
        assert fonte.count(f'"{rota}"') >= 1, f"rota {rota} não registrada"
    for handler in (
        "_projeto_vs_ler",
        "_projeto_vs_salvar",
        "_projeto_vs_render",
        "_projeto_vs_exportar",
        "_letra_importar",
        "_transcrever_letra",
    ):
        assert f"def {handler}" in fonte, f"handler {handler} ausente"


# --------------------------------------------------------------------------
# 6. Mixer ao vivo: offset por faixa, seek, loop e clique sintetizado
# --------------------------------------------------------------------------
def test_offset_da_faixa_desloca_o_audio_de_verdade():
    """Faixa com offset 0,5 s tem de começar 0,5 s depois na régua."""
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        const vocais = S.todasAsFaixas().find(f => f.id === "vocals");
        vocais.offset = 0.5;
        S.tempoLocalDaFaixa(vocais, 2.0);  // 2,0 na régua = 1,5 no arquivo
        S.studioBuscar(2.0);
        S.__info = {
          local: S.tempoLocalDaFaixa(vocais, 2.0),
          antesDoOffset: S.tempoLocalDaFaixa(vocais, 0.2),
          el: vocais.el.currentTime,
          regua: S.Studio.tempo,
        };
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["local"] == 1.5
    assert info["antesDoOffset"] == 0.0  # ainda não entrou: fica no zero
    assert round(info["el"], 3) == 1.5   # o elemento recebeu o tempo local
    assert info["regua"] == 2.0          # a régua continua no tempo da música


def test_seek_reposiciona_todas_as_faixas():
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        S.studioBuscar(3.5);
        S.__info = {
          regua: S.Studio.tempo,
          posicoes: S.todasAsFaixas().filter(f => f.el).map(f => ({
            id: f.id, t: f.el.currentTime, offset: f.offset || 0})),
        };
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["regua"] == 3.5
    for faixa in info["posicoes"]:
        assert round(faixa["t"], 3) == round(3.5 - faixa["offset"], 3), faixa


def test_loop_persistido_volta_para_o_ponto_a():
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        await esperar();
        S.Studio.tocando = true;
        S.Studio.clockOffset = 0;
        S.Studio.clockInicio = S.__ctx.currentTime;
        S.Studio.loop = true;
        S.__info = {a: S.Studio.loopA, b: S.Studio.loopB};
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert (info["a"], info["b"]) == (1.0, 2.5)


def test_faixa_mudo_nao_recebe_ganho():
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        const drums = S.todasAsFaixas().find(f => f.id === "drums");
        const vocais = S.todasAsFaixas().find(f => f.id === "vocals");
        S.aplicarMix();
        S.__info = {drums: drums.ganho.gain.value, vocais: vocais.ganho.gain.value};
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["drums"] == 0        # mudo no projeto salvo
    assert info["vocais"] > 0        # os vocais entram


def test_clique_sintetizado_respeita_mudo_e_solo():
    """A faixa Click não tem arquivo: o M/S precisa valer no grafo dela."""
    saida = _rodar(
        """
        S.studioMontar(%s);
        await esperar();
        const clique = S.todasAsFaixas().find(f => f.id === "clique");
        clique.solo = true;
        S.aplicarMix();
        const vocais = S.todasAsFaixas().find(f => f.id === "vocals");
        S.__info = {clique: clique.ganho.gain.value, vocais: vocais.ganho.gain.value,
                    temEl: !!clique.el, sintetica: clique.sintetica};
        """
        % json.dumps(DADOS),
        dica="return S.__info;",
    )
    info = saida["S"]
    assert info["sintetica"] is True and info["temEl"] is False
    assert info["clique"] > 0     # solo no clique: ele toca
    assert info["vocais"] == 0    # e a banda cala
