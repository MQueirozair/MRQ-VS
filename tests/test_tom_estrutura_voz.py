"""Tom audível, nomes de seção e voz na guia.

Três coisas que o usuário reportou e que este arquivo trava:

1. mudar o tom não mudava o SOM — só os acordes na tela;
2. as seções existiam como A/B/C, não como intro/verso/refrão/ponte;
3. a guia era uma melodia, não voz contando 1-2-3-4 nem falando a seção.

O que NÃO se testa aqui: qualidade subjetiva do áudio. Isso é escuta, não
teste automatizado — o que os testes garantem é o comportamento medível:
a transposição muda a altura mantendo a duração, a estrutura nomeia, e a guia
coloca a palavra falada no tempo certo.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HTML = RAIZ / "src" / "mrqvs" / "web" / "index.html"


# --------------------------------------------------------------- transposição
def test_filtro_de_transposicao_mantem_a_duracao():
    """+2 semitons = razão 1,1225; o atempo compensa para a música não acelerar."""
    from mrqvs import transpor

    cadeia = transpor._filtro(2, "atempo")
    assert "asetrate=44100*1.122462" in cadeia
    # o inverso exato: 1/1,1225 = 0,8909
    assert "atempo=0.890899" in cadeia
    # subir 12 semitons dobra a leitura e o atempo volta à metade
    doze = transpor._filtro(12, "atempo")
    assert "asetrate=44100*2.000000" in doze
    assert "atempo=0.500000" in doze


def test_rubberband_e_preferido_quando_o_ffmpeg_tem():
    """O filtro que preserva transiente vem antes do par asetrate+atempo."""
    from mrqvs import transpor

    cadeia = transpor._filtro(-3, "rubberband")
    assert cadeia.startswith("rubberband=pitch=")
    assert "asetrate" not in cadeia


def test_transpor_recusa_sem_ffmpeg_em_vez_de_entregar_arquivo_errado(tmp_path):
    from mrqvs import transpor

    origem = tmp_path / "a.wav"
    origem.write_bytes(b"RIFF")
    with pytest.raises(transpor.TransposicaoIndisponivel):
        transpor.transpor_arquivo(origem, tmp_path / "b.wav", 2, ffmpeg="")
    # e recusa antes de mexer em qualquer coisa
    assert not (tmp_path / "b.wav").exists()


def test_transpor_limita_semitons_e_zero():
    from mrqvs import transpor

    with pytest.raises(ValueError):
        transpor.transpor_arquivo(Path("/nada.wav"), Path("/x.wav"), 0)
    assert transpor.SEMITONS_MAX <= 12


def test_pasta_do_tom_fica_ao_lado_e_nunca_por_cima():
    from mrqvs import transpor

    original = Path("/musicas/Louvor")
    assert transpor.pasta_do_tom(original, 3) == Path("/musicas/Louvor-tom+3")
    assert transpor.pasta_do_tom(original, -2) == Path("/musicas/Louvor-tom-2")


# ------------------------------------------------------- tom ao vivo (tela)
def test_tom_ao_vivo_muda_o_som_e_a_cifra_juntos():
    """Era o defeito: a cifra transpunha e o áudio ficava no tom gravado."""
    saida = _rodar_js(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.ligarContextoAudio();
        const casos = [];
        for (const passo of [1, 2, 5, 6, 7, -1]){
          S.transposicao = 0;
          S.tomAoVivo = 0;
          sb.studioTranspor(passo);
          casos.push({passo, cifra: S.transposicao, som: S.tomAoVivo,
                      profundidade: S.tomProf.gain.value});
        }
        console.log(JSON.stringify(casos));
        """
    )
    casos = json.loads(saida.strip().splitlines()[-1])
    for c in casos:
        # som e cifra têm de concordar módulo 12 (transpor +7 = -5)
        assert (c["cifra"] - c["som"]) % 12 == 0, c
        # e o som fica no caminho mais curto, dentro do que não vira "coro"
        assert -6 <= c["som"] <= 6, c
    # todos os passos geraram modulação de verdade (nada de ganho zero)
    assert all(abs(c["profundidade"]) > 0 for c in casos)


def test_sem_transposicao_o_no_de_tom_nao_artefata():
    """Zero semitons = profundidade zero: som limpo, sem vibrato."""
    saida = _rodar_js(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox;
        sb.ligarContextoAudio();
        sb.religarTomNasFaixas();
        S.tomAoVivo = 0;
        sb.aplicarTomAoVivo();
        console.log(JSON.stringify({prof: sb.profundidadeDoTom(0),
                                    ganho: S.tomProf.gain.value}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["prof"] == 0 and r["ganho"] == 0


# ------------------------------------------------------------------ estrutura
def _secao(inicio, fim, rotulo, energia=0.0):
    class _S:
        start = inicio
        end = fim
        label = rotulo
        loudness_db = energia

    return _S()


def test_estrutura_nomeia_forma_tipica():
    from mrqvs import estrutura

    secs = [
        _secao(0, 12, "A", -20),
        _secao(12, 30, "A", -18),
        _secao(30, 48, "B", -12),   # refrão: repetido e mais forte
        _secao(48, 66, "A", -18),
        _secao(66, 84, "B", -12),
        _secao(84, 96, "C", -13),   # único, forte: ponte
        _secao(96, 114, "B", -12),
        _secao(114, 126, "B", -22),  # último e mais baixo: final
    ]
    nomes = [s.nome for s in estrutura.nomear_secoes(secs, lambda s: s.loudness_db)]
    assert nomes == [
        estrutura.INTRO,
        estrutura.VERSO,
        estrutura.REFRAO,
        estrutura.VERSO,
        estrutura.REFRAO,
        estrutura.PONTE,
        estrutura.REFRAO,
        estrutura.FINAL,
    ]


def test_estrutura_reconhece_pre_refrao_que_sobe():
    """Pré-refrão é o trecho CURTO, que REPETE e sobe para o refrão.

    Um trecho único que emenda no refrão é ponte — as duas coisas existem em
    música real e a diferença é justamente repetir ou não.
    """
    from mrqvs import estrutura

    secs = [
        _secao(0, 12, "A", -20),
        _secao(12, 30, "A", -18),
        _secao(30, 38, "C", -12),   # curto, sobe e emenda no refrão...
        _secao(38, 56, "B", -11),
        _secao(56, 74, "A", -18),
        _secao(74, 82, "C", -12),   # ...e volta igual na segunda vez
        _secao(82, 100, "B", -11),
    ]
    nomes = [s.nome for s in estrutura.nomear_secoes(secs, lambda s: s.loudness_db)]
    assert nomes[2] == estrutura.PRE_REFRao
    assert nomes[5] == estrutura.PRE_REFRao, "vale em toda volta do refrão"


def test_estrutura_nao_chama_verso_longo_de_pre_refrao():
    """Verso de 18 s que sobe 2 dB não é pré-refrão: é verso."""
    from mrqvs import estrutura

    secs = [
        _secao(0, 12, "A", -20),
        _secao(12, 30, "A", -18),   # 18 s: estrofe, não passagem
        _secao(30, 48, "B", -12),
        _secao(48, 66, "A", -18),
        _secao(66, 84, "B", -12),
    ]
    nomes = [s.nome for s in estrutura.nomear_secoes(secs, lambda s: s.loudness_db)]
    assert nomes[1] == estrutura.VERSO
    assert estrutura.PRE_REFRao not in nomes


def test_estrutura_nao_inventa_nome_sem_informacao():
    """Música de um bloco só não tem verso nem refrão: o nome tem de admitir."""
    from mrqvs import estrutura

    nomes = [s.nome for s in estrutura.nomear_secoes([_secao(0, 180, "A")])]
    assert nomes == [estrutura.MUSICA]


def test_estrutura_toda_secao_diz_por_que_recebeu_o_nome():
    """O usuário precisa poder discordar: cada nome tem um motivo legível."""
    from mrqvs import estrutura

    secs = [_secao(0, 10, "A", -20), _secao(10, 30, "B", -14), _secao(30, 50, "A", -20)]
    for s in estrutura.nomear_secoes(secs, lambda x: x.loudness_db):
        assert s.motivo, f"{s.nome} sem motivo"
        assert s.rotulo, "o rótulo da análise tem de ser preservado"


# ------------------------------------------------------------ voz da guia
def test_voz_do_pacote_carrega_e_tem_todas_as_palavras():
    """Trava o pacote: as 17 palavras têm de vir junto do programa.

    Deixou de ser `xfail`: o pacote está completo (1..8 + as 9 seções). Se
    alguém apagar um WAV ou esquecer de incluí-lo no `package-data`, o teste
    falha aqui em vez de a guia cair em silêncio na melodia.
    """
    from mrqvs import voz

    assert voz.faltando() == [], f"faltam palavras de voz no pacote: {voz.faltando()}"
    esperados = voz.nomes_esperados()
    assert len(esperados) == 17
    for nome in esperados:
        caminho = voz.arquivo(nome)
        assert caminho.is_file(), f"{nome}.wav ausente"
        assert caminho.stat().st_size > 8_000, f"{nome}.wav suspeito de estar vazio"


def test_todo_wav_de_voz_tem_audio_de_verdade():
    """Arquivo de 44 bytes (cabeçalho só) passaria no teste acima.

    Pico normalizado em 0,8 e sinal não constante: confirma que a síntese
    gerou fala, não silêncio.
    """
    import numpy as np
    import soundfile as sf

    from mrqvs import voz

    for nome in voz.nomes_esperados():
        dados, taxa = sf.read(str(voz.arquivo(nome)), always_2d=True, dtype="float32")
        assert taxa == 44_100, f"{nome}.wav em {taxa} Hz"
        mono = dados.mean(axis=1)
        assert mono.size > 0, f"{nome}.wav sem amostras"
        assert float(np.abs(mono).max()) > 0.5, f"{nome}.wav baixo demais"
        assert float(mono.std()) > 0.01, f"{nome}.wav praticamente constante"
        segundos = mono.size / float(taxa)
        assert 0.15 < segundos < 2.5, f"{nome}.wav com {segundos:.2f}s fora do esperado"


def test_guia_fala_a_secao_e_a_contagem(tmp_path):
    """A guia tem de ter voz no anúncio, na contagem e na entrada da seção."""
    from mrqvs import guia, project, estrutura

    secs = [
        _secao(0, 12, "A", -20),
        _secao(12, 30, "A", -18),
        _secao(30, 48, "B", -12),
    ]
    nomeadas = estrutura.nomear_secoes(secs, lambda s: s.loudness_db)
    entradas = guia.compor(
        project.analised_para_guia(secs, nomeadas),
        [i * 0.5 for i in range(140)],
        contagem=4,
    )
    # a palavra tem de estar na entrada: é ela que a guia grava
    falas = [e.fala for e in entradas if e.fala]
    assert "refrão" in falas
    assert any(e.tipo == "contagem" for e in entradas)

    destino = tmp_path / "guia.wav"
    resultado = guia.escrever_audio(str(destino), 44100, entradas, 48.0)
    assert destino.is_file()
    assert resultado["com_voz"] is True
    assert resultado["faladas"] >= 5


def test_guia_sem_arquivos_de_voz_continua_soando(tmp_path):
    """Voz ausente não pode deixar a guia muda: cai na melodia e avisa."""
    from mrqvs import guia

    entradas = [
        guia.Entrada(0.0, "anuncio", "Refrão", "Refrão", fala="refrão"),
        guia.Entrada(2.0, "contagem", 4, "Refrão"),
    ]
    destino = tmp_path / "guia.wav"
    resultado = guia.escrever_audio(str(destino), 44100, entradas, 8.0, com_voz=False)
    assert destino.is_file() and destino.stat().st_size > 1000
    assert resultado["faladas"] == 0 and resultado["melodias"] == 2
    assert "melodia" in guia.resumo(entradas, resultado)


def test_resumo_da_guia_diz_quantas_falaram():
    from mrqvs import guia

    entradas = [guia.Entrada(0.0, "anuncio", "Verso", fala="verso")]
    texto = guia.resumo(entradas, {"com_voz": True, "faladas": 7, "melodias": 2})
    assert "voz falada" in texto and "7" in texto
    # e quando falta voz, o texto é honesto em vez de prometer
    assert "melodia de referência" in guia.resumo(entradas, {"com_voz": False})


# ------------------------------------------------------- o tom na interface
def test_interface_tem_o_seletor_de_som_da_contagem():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="trSomContagem"' in html
    assert '<option value="bip">' in html
    assert '<option value="voz">' in html


def test_transporte_mostra_que_o_som_da_contagem_muda():
    saida = _rodar_js(
        """
        const {montar} = require("./harness");
        const h = montar();
        const S = h.Studio, sb = h.sandbox, doc = h.doc;
        S.contagem = 4;
        const sel = doc.getElementById("trSomContagem");
        sel.value = "voz";
        sel.onchange();
        const depois = {modo: sb.modoDaContagem(), valor: sel.value,
                        texto: doc.getElementById("trContagemTexto").textContent};
        sel.value = "bip";
        sel.onchange();
        const volta = {modo: sb.modoDaContagem(), valor: sel.value};
        console.log(JSON.stringify({depois, volta}));
        """
    )
    r = json.loads(saida.strip().splitlines()[-1])
    assert r["depois"]["modo"] == "voz" and r["depois"]["valor"] == "voz"
    assert "voz" in r["depois"]["texto"]
    assert r["volta"]["modo"] == "bip"


# ------------------------------------------------------------------- apoio
def _rodar_js(corpo: str) -> str:
    """Roda um trecho JS no harness do Studio e devolve o stdout."""
    proc = subprocess.run(
        ["node", "-e", corpo],
        cwd=str(RAIZ / "tests" / "js"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"JS falhou:\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout
