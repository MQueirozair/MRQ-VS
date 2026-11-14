"""Testes do núcleo multitrack: mapa de tempo, cifra, MIDI, letra e projeto.

O que estes testes protegem, e por quê:

* **mapa de tempo** — a régua com BPM e compasso variáveis é a base de tudo
  (clique, cifra, MIDI, exportação). Se `inicio_do_compasso` e `compasso_de`
  deixarem de ser inversos, a música inteira sai fora de registro e o defeito
  aparece em três lugares ao mesmo tempo;
* **cifra** — a confiança é dado: acorde fraco tem de sair com `?`, e a
  transposição tem de mexer na tônica sem estragar o sufixo nem a inversão;
* **MIDI** — arquivo binário com estrutura verificável (MThd, nº de trilhas,
  PPQ); um byte errado faz a DAW recusar o arquivo em silêncio;
* **letra** — alinhamento nunca pode jogar linha depois do fim da música, e
  não pode "melhorar" um `.lrc` que já veio com tempo;
* **projeto** — salvar/abrir tem de devolver o mesmo estado, mute/solo têm de
  seguir a regra do mixer, e stem ausente tem de virar aviso, não silêncio.

Todos os áudios são gerados no próprio teste (senão o teste depende do disco
de quem roda) e nenhum teste depende de GPU, modelo de IA ou rede.
"""

from __future__ import annotations

import json
import re
import struct
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from mrqvs import cifra as cifra_mod
from mrqvs import ficha as ficha_mod
from mrqvs import letra as letra_mod
from mrqvs import mapa_tempo as mapa_mod
from mrqvs import midi as midi_mod
from mrqvs import projeto_vs as pv_mod


# ---------------------------------------------------------------- utilidades ---
def _grade(bpm: float, duracao: float, inicio: float = 0.5) -> list[float]:
    passo = 60.0 / bpm
    n = int((duracao - inicio) / passo)
    return [round(inicio + i * passo, 4) for i in range(n)]


def _tom(n: int, freq: float, sr: int = 8000, amp: float = 0.3):
    t = np.arange(n) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _com_voz(sr: int = 8000, duracao: float = 10.0, trechos=((0.5, 2.5), (4.0, 6.0), (7.0, 9.5))):
    sinal = np.zeros(int(sr * duracao), np.float32)
    for a, b in trechos:
        sinal[int(a * sr) : int(b * sr)] = _tom(int((b - a) * sr), 220.0, sr, 0.4)
    return sinal


# ------------------------------------------------------------ mapa de tempo ---
def test_mapa_tempo_inverso_exato():
    """`inicio_do_compasso` e `compasso_de` são inversos — senão a régua mente."""
    mapa = mapa_mod.MapaTempo.de_analise(_grade(96, 40), 96, 4, 4, 40.0, 0.7)
    for n in range(0, mapa.total_compassos()):
        inicio = mapa.inicio_do_compasso(n)
        assert mapa.compasso_de(inicio + 1e-3) == n
        assert mapa.compasso_de(inicio + mapa.duracao_do_compasso(n) - 1e-3) == n


def test_mapa_tempo_bpm_variado_e_medido_nao_presumido():
    """Duas metades, 90 e 120 BPM: o mapa tem de mostrar dois andamentos."""
    # 12 batidas a 90 BPM (3 compassos de 4/4) e o resto a 120 — a troca cai
    # exatamente numa batida, como acontece numa música de verdade
    passo_a, passo_b = 60.0 / 90.0, 60.0 / 120.0
    batidas = [round(0.5 + i * passo_a, 4) for i in range(12)]
    t = batidas[-1] + passo_b
    while t < 20.0:
        batidas.append(round(t, 4))
        t += passo_b
    mapa = mapa_mod.MapaTempo.de_analise(batidas, 90, 4, 4, 20.0, 0.8)
    trechos = mapa.andamentos()
    assert len(trechos) == 2, trechos
    assert abs(trechos[0]["bpm"] - 90) < 1.0
    assert abs(trechos[1]["bpm"] - 120) < 1.0
    # o BPM local acompanha a música (é medido, não o nominal)
    assert abs(mapa.bpm_local(2.0) - 90) < 2
    assert abs(mapa.bpm_local(18.0) - 120) < 2
    assert len(mapa.mudancas_de_andamento()) == 1


def test_mapa_tempo_compasso_composto_cai_no_lugar():
    """6/8 tem 3 semínimas por compasso; 7/8 tem 3,5 — não 4 nem 3."""
    mapa = mapa_mod.MapaTempo.de_analise(_grade(120, 60), 120, 4, 4, 60.0, 0.9)
    seis_oito = mapa.com_formula(6, 8)
    sete_oito = mapa.com_formula(7, 8)
    assert seis_oito.unidades_do_compasso(0) == 3.0
    assert sete_oito.unidades_do_compasso(0) == 3.5


def test_mapa_tempo_troca_de_formula_no_meio():
    """4/4 até o compasso 3, 6/8 depois: as colcheias passam a correr mais rápido."""
    mapa = mapa_mod.MapaTempo.de_analise(_grade(120, 40), 120, 4, 4, 40.0, 0.9)
    com_mudanca = mapa.com_formula(6, 8, compasso=4)
    assert com_mudanca.formula(0) == (4, 4)
    assert com_mudanca.formula(2) == (4, 4)
    assert com_mudanca.formula(3) == (6, 8)
    # 6/8 = 3 semínimas contra 4 do 4/4: o compasso seguinte chega ANTES
    assert com_mudanca.inicio_do_compasso(4) < mapa.inicio_do_compasso(4)
    # a fórmula nova não contamina os compassos anteriores
    assert com_mudanca.inicio_do_compasso(3) == pytest.approx(mapa.inicio_do_compasso(3))


def test_mapa_tempo_sem_grade_avisa_que_extrapola():
    mapa = mapa_mod.MapaTempo.de_analise([], 120, 4, 4, 10.0, 0.0)
    assert not mapa.preciso
    assert abs(mapa.inicio_do_compasso(4) - 8.0) < 1e-6
    dados = mapa.as_dict()
    assert dados["preciso"] is False
    assert dados["total_compassos"] >= 5


def test_mapa_tempo_pulso_do_compasso():
    mapa = mapa_mod.MapaTempo.de_analise(_grade(120, 20), 120, 3, 4, 20.0, 0.9)
    compasso, pulso = mapa.pulso_do_compasso(mapa.inicio_do_compasso(2))
    assert (compasso, pulso) == (3, 1)
    depois = mapa.inicio_do_compasso(2) + 0.6  # 1,2 s depois do "um" de 3/4
    assert mapa.pulso_do_compasso(depois) == (3, 2)


def test_mapa_tempo_com_bpm_troca_grade_ou_so_numero():
    mapa = mapa_mod.MapaTempo.de_analise(_grade(96, 20), 96, 4, 4, 20.0, 0.5)
    so_numero = mapa.com_bpm(100, manter_grade=True)
    assert so_numero.batidas == mapa.batidas
    assert abs(so_numero.bpm - 100) < 1e-6
    regerado = mapa.com_bpm(100)
    assert regerado.batidas == []
    assert "metrônomo" in regerado.origem


def test_mapa_tempo_serializa_e_volta():
    mapa = mapa_mod.MapaTempo.de_analise(_grade(96, 20), 96, 4, 4, 20.0, 0.5)
    volta = mapa_mod.MapaTempo.de_dict(json.loads(json.dumps(mapa.as_dict())))
    assert volta.batidas == mapa.batidas
    assert volta.total_compassos() == mapa.total_compassos()
    assert volta.inicio_do_compasso(3) == pytest.approx(mapa.inicio_do_compasso(3))


# -------------------------------------------------------------------- cifra ---
def _cifra_de_teste(bpm: float = 96.0, duracao: float = 24.0, acordes=None) -> cifra_mod.Cifra:
    batidas = _grade(bpm, duracao)
    mapa = mapa_mod.MapaTempo.de_analise(batidas, bpm, 4, 4, duracao, 0.8)
    if acordes is None:
        acordes = [
            {
                "compasso": i + 1,
                "inicio": mapa.inicio_do_compasso(i),
                "fim": mapa.inicio_do_compasso(i + 1),
                "acorde": ["C", "G", "Am", "F"][i % 4],
                "confianca": 0.9 if i % 4 else 0.1,
            }
            for i in range(8)
        ]
    estudio = {
        "batidas": batidas,
        "compasso": 4,
        "denominador": 4,
        "bpm": bpm,
        "duracao": duracao,
        "tonalidade": "C maior",
        "secoes": [
            {"start": 0.0, "end": duracao / 2, "nome": "Verso"},
            {"start": duracao / 2, "end": duracao, "nome": "Refrão"},
        ],
    }
    return cifra_mod.Cifra.de_estudio(
        estudio, acordes, "Teste", "Banda", mapa=mapa, tonalidade="C maior"
    )


def test_cifra_marca_acorde_de_baixa_confianca():
    cifra = _cifra_de_teste()
    fracos = [ln for ln in cifra.linhas if ln.confianca < cifra_mod.CONFIANCA_MINIMA]
    assert fracos, "o fixture precisa ter acorde fraco"
    # fraco COM acorde sai "C?"; fraco SEM acorde sai "N.C." (sem interrogação,
    # porque não há acorde para duvidar). Os dois casos são "não confie".
    assert all(
        ln.rotulo == cifra_mod.SEM_ACORDE or ln.rotulo.endswith("?") for ln in fracos
    )
    # e só os fracos: acorde medido com confiança sai limpo, sem interrogação
    fortes = [ln for ln in cifra.linhas if ln.confianca >= cifra_mod.CONFIANCA_MINIMA]
    assert fortes and not any(ln.rotulo.endswith("?") for ln in fortes)
    assert "sem acorde confiável" in cifra.resumo
    assert any("?" in aviso or "sem acorde" in aviso for aviso in cifra.avisos)


def test_cifra_compasso_sem_acorde_nao_inventa():
    batidas = _grade(96, 24)
    mapa = mapa_mod.MapaTempo.de_analise(batidas, 96, 4, 4, 24.0, 0.8)
    cifra = cifra_mod.Cifra.de_estudio(
        {"batidas": batidas, "compasso": 4, "duracao": 24.0, "bpm": 96, "tonalidade": ""},
        [],
        mapa=mapa,
    )
    assert cifra.linhas
    assert all(ln.acorde == "" for ln in cifra.linhas)
    assert all(ln.rotulo == cifra_mod.SEM_ACORDE for ln in cifra.linhas)
    assert any("tonalidade" in aviso for aviso in cifra.avisos)


def test_transposicao_preserva_sufixo_e_inversao():
    # sem tom, a grafia é sustenido (a tônica e o baixo andam juntos)
    assert cifra_mod.transpor_acorde("D/F#", 2, bemol=False) == "E/G#"
    # com tom de bemol, o MESMO acorde se escreve Ab — é a armadura que manda
    assert cifra_mod.transpor_acorde("D/F#", 2, bemol=True) == "E/Ab"
    assert cifra_mod.transpor_acorde("Am7", 3, bemol=True) == "Cm7"
    assert cifra_mod.transpor_acorde("F#m7b5", -1, bemol=False) == "Fm7b5"
    # texto que não é acorde volta igual: melhor devolver o que o usuário
    # escreveu do que apagar
    assert cifra_mod.transpor_acorde("solo livre", 2) == "solo livre"
    assert cifra_mod.transpor_acorde("", 2) == ""


def test_cifra_transposta_muda_tom_e_grafia():
    cifra = _cifra_de_teste()
    acima = cifra.transposta(2)
    assert acima.transposicao == 2
    assert acima.tom_exibido.split()[0] == "D"
    # dó maior + 2 = ré; os acordes acompanham
    assert acima.linhas[0].acorde == "D"
    assert "D maior" in acima.tom_exibido


def test_correcao_manual_vence_e_nao_vira_incerto():
    cifra = _cifra_de_teste()
    numero = cifra.linhas[0].numero
    corrigida = cifra.com_correcoes({numero: "Bm7"})
    linha = next(ln for ln in corrigida.linhas if ln.numero == numero)
    assert linha.acorde == "Bm7"
    assert linha.manual is True
    assert linha.incerto is False
    # apagar = string vazia, sem virar "não mexido"
    apagada = cifra.com_correcoes({numero: ""})
    linha = next(ln for ln in apagada.linhas if ln.numero == numero)
    assert linha.acorde == ""
    assert linha.manual is True


def test_cifra_exporta_txt_chordpro_csv(tmp_path):
    cifra = _cifra_de_teste()
    arquivos = cifra.escrever(tmp_path, base="musica_cifra")
    assert set(arquivos) == {"txt", "chordpro", "csv"}
    for caminho in arquivos.values():
        assert caminho.is_file() and caminho.stat().st_size > 0
    texto = arquivos["txt"].read_text(encoding="utf-8")
    assert "Tom: C maior" in texto
    assert "[Verso]" in texto and "[Refrão]" in texto
    chordpro = arquivos["chordpro"].read_text(encoding="utf-8")
    assert "{title: Teste}" in chordpro and "{time: 4/4}" in chordpro
    assert "[G]" in chordpro
    assert "[C?]" in chordpro  # acorde fraco marcado, nunca escondido
    linhas_csv = arquivos["csv"].read_text(encoding="utf-8").splitlines()
    assert linhas_csv[0].startswith("compasso,inicio_s")
    assert len(linhas_csv) == len(cifra.linhas) + 1


def test_cifra_com_letra_encaixa_no_compasso(tmp_path):
    cifra = _cifra_de_teste()
    inicio = cifra.linhas[1].inicio + 0.1
    com_letra = cifra.com_letra([{"tempo": inicio, "texto": "primeira linha"}])
    assert com_letra.linhas[1].letra == "primeira linha"
    assert com_letra.linhas[0].letra == ""


# --------------------------------------------------------------------- MIDI ---
def test_midi_cabecalho_e_trilhas(tmp_path):
    cifra = _cifra_de_teste()
    batidas = _grade(96, 24)
    mapa = mapa_mod.MapaTempo.de_analise(batidas, 96, 4, 4, 24.0, 0.8)
    destino = tmp_path / "teste.mid"
    midi_mod.escrever(destino, mapa, cifra=cifra, secoes=[{"start": 0.0, "nome": "Verso"}])
    dados = destino.read_bytes()
    assert dados[:4] == b"MThd"
    cabecalho = midi_mod.ler_cabecalho(destino)
    assert cabecalho["formato"] == 1
    assert cabecalho["ppq"] == midi_mod.PPQ
    assert cabecalho["trilhas"] >= 3
    # mesma quantidade de "MTrk" no arquivo que no cabeçalho
    assert dados.count(b"MTrk") == cabecalho["trilhas"]


def test_midi_tem_mapa_de_tempo_e_marcador(tmp_path):
    batidas = _grade(100, 30)
    mapa = mapa_mod.MapaTempo.de_analise(batidas, 100, 4, 4, 30.0, 0.8)
    dados = midi_mod.construir(mapa, secoes=[{"start": 0.0, "nome": "Intro"}], com_clique=True)
    assert b"\xff\x51" in dados  # set_tempo
    assert b"\xff\x58" in dados  # time_signature
    assert b"\xff\x06" in dados  # marker


def test_midi_cifra_nao_gera_nota_para_acorde_incerto():
    acerto = midi_mod.notas_do_acorde("C")
    assert acerto["acorde"] == [60, 64, 67]
    assert acerto["baixo"] == 48
    invertido = midi_mod.notas_do_acorde("D/F#")
    assert invertido["baixo"] == 54  # F#2, não D2
    assert midi_mod.notas_do_acorde("")["acorde"] == []
    # sufixo fora do catálogo não inventa harmonia
    assert midi_mod.notas_do_acorde("Cqualquercoisa")["acorde"] == []


def test_midi_varint():
    assert midi_mod._varint(0) == b"\x00"
    assert midi_mod._varint(127) == b"\x7f"
    assert midi_mod._varint(128) == b"\x81\x00"
    assert midi_mod._varint(480) == b"\x83\x60"


def test_midi_lido_por_leitor_externo_se_disponivel(tmp_path):
    """Se houver mido instalado, o arquivo tem de ser aceito por ele."""
    mido = pytest.importorskip("mido")
    cifra = _cifra_de_teste()
    batidas = _grade(96, 24)
    mapa = mapa_mod.MapaTempo.de_analise(batidas, 96, 4, 4, 24.0, 0.8)
    destino = tmp_path / "teste.mid"
    midi_mod.escrever(destino, mapa, cifra=cifra)
    lido = mido.MidiFile(str(destino))
    assert lido.type == 1
    assert lido.ticks_per_beat == midi_mod.PPQ


# -------------------------------------------------------------------- letra ---
def test_letra_lrc_com_tempo_e_preservada():
    letra = letra_mod.ler_lrc("[ti:Musica]\n[00:12.50]primeira\n[00:15,00]segunda")
    assert letra.titulo == "Musica"
    assert [ln.tempo for ln in letra.linhas] == [12.5, 15.0]
    assert letra.linhas[0].fim == 15.0
    # alinhar não mexe em letra que já tem tempo
    alinhada = letra_mod.alinhar(letra, _com_voz(), 8000, 10.0)
    assert [ln.tempo for ln in alinhada.linhas] == [12.5, 15.0]
    assert any("preservado" in aviso for aviso in alinhada.avisos)


def test_letra_srt_e_detectada_pelo_conteudo():
    texto = "1\n00:00:01,000 --> 00:00:03,000\nprimeira linha\n\n2\n00:00:04,500 --> 00:00:06,000\nsegunda\n"
    assert letra_mod.detectar_formato(texto, "letra.txt") == "srt"
    letra = letra_mod.ler_srt(texto)
    assert len(letra.linhas) == 2
    assert letra.linhas[1].tempo == pytest.approx(4.5)
    assert "00:00:01,000 --> 00:00:03,000" in letra.para_srt()


def test_alinhamento_por_energia_nao_passa_do_fim_do_cantado():
    sinal = _com_voz()
    letra = letra_mod.ler_texto("\n".join(f"linha {i}" for i in range(1, 6)))
    alinhada = letra_mod.alinhar(letra, sinal, 8000, 10.0)
    assert len(alinhada.linhas) == 5
    assert all(ln.metodo == "energia" for ln in alinhada.linhas)
    # a última linha termina dentro do último trecho cantado (9,5 s)
    assert alinhada.linhas[-1].fim <= 9.55
    # e as linhas não se sobrepõem
    for antes, depois in zip(alinhada.linhas, alinhada.linhas[1:]):
        assert depois.tempo >= antes.tempo
    assert any("estimad" in aviso or "energia" in aviso for aviso in alinhada.avisos)


def test_alinhamento_com_uma_linha_por_trecho_sobe_a_confianca():
    sinal = _com_voz()
    letra = letra_mod.ler_texto("um\ndois\ntres")
    alinhada = letra_mod.alinhar(letra, sinal, 8000, 10.0)
    assert [round(ln.tempo, 1) for ln in alinhada.linhas] == [0.5, 4.0, 7.0]
    assert all(ln.confianca >= 0.8 for ln in alinhada.linhas)


def test_transcricao_sem_motor_levanta_com_manual():
    if letra_mod.motor_disponivel() is not None:
        pytest.skip("há motor de transcrição instalado neste ambiente")
    with pytest.raises(letra_mod.MotorIndisponivel) as erro:
        letra_mod.transcrever(Path("nao-existe.wav"))
    assert "pip install" in str(erro.value)


def test_letra_exporta_lrc_srt_txt_json(tmp_path):
    letra = letra_mod.alinhar(
        letra_mod.ler_texto("primeira\nsegunda"), _com_voz(), 8000, 10.0
    )
    arquivos = letra.escrever(tmp_path, base="letra")
    assert set(arquivos) == {"lrc", "srt", "txt", "json"}
    lrc = arquivos["lrc"].read_text(encoding="utf-8")
    assert re.search(r"^\[\d{2}:\d{2}\.\d{2}\]primeira$", lrc, re.MULTILINE)
    json_lido = json.loads(arquivos["json"].read_text(encoding="utf-8"))
    assert json_lido["metodo"] == "energia"
    assert len(json_lido["linhas"]) == 2


# ------------------------------------------------------------------ projeto ---
def _projeto_de_teste(tmp_path: Path, faixas=("vocals", "drums", "bass"), sr: int = 8000):
    pasta = tmp_path / "Musica-96BPM"
    pasta.mkdir(parents=True, exist_ok=True)
    for i, nome in enumerate(faixas):
        sf.write(str(pasta / f"{nome}.wav"), _tom(sr * 2, 220.0 + i * 55, sr, 0.2), sr)
    batidas = _grade(96, 4.0)
    mapa = mapa_mod.MapaTempo.de_analise(batidas, 96, 4, 4, 4.0, 0.8)
    projeto = pv_mod.ProjetoVS(
        pasta=pasta,
        titulo="Musica",
        artista="Banda",
        mapa=mapa,
        secoes=[{"start": 0.0, "end": 2.0, "nome": "Verso"}],
    )
    for i, nome in enumerate(faixas):
        projeto.faixas.append(
            pv_mod.Faixa(id=nome, nome=nome.title(), arquivo=f"{nome}.wav", ordem=i).normalizar()
        )
    return projeto


def test_projeto_salva_e_abre_igual(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    projeto.marcar(1.0, "Refrão")
    caminho = projeto.salvar()
    assert caminho.name == pv_mod.ARQUIVO_PROJETO
    aberto = pv_mod.ProjetoVS.carregar(projeto.apoio)
    assert [f.id for f in aberto.faixas_ordenadas] == [f.id for f in projeto.faixas_ordenadas]
    assert aberto.mapa.bpm == projeto.mapa.bpm
    assert aberto.marcadores[0].nome == "Refrão"
    assert aberto.titulo == "Musica"


def test_projeto_recusa_formato_do_futuro(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    caminho = projeto.salvar()
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["versao"] = pv_mod.VERSAO + 1
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(pv_mod.ProjetoInvalido) as erro:
        pv_mod.ProjetoVS.carregar(projeto.apoio)
    assert "mais nova" in str(erro.value)


def test_projeto_inexistente_avisa():
    with pytest.raises(pv_mod.ProjetoInvalido):
        pv_mod.ProjetoVS.carregar(Path("/caminho/que/nao/existe"))


def test_mixer_solo_e_mute_seguem_a_mesma_regra(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    vocals = projeto.faixa("vocals")
    drums = projeto.faixa("drums")
    assert projeto.audivel(drums) is True
    drums.mudo = True
    assert projeto.audivel(drums) is False
    drums.mudo = False
    vocals.solo = True
    assert projeto.tem_solo is True
    assert projeto.audivel(vocals) is True
    assert projeto.audivel(drums) is False  # solo em um cala os outros
    # solo em faixa oculta não pode calar a banda inteira
    vocals.oculta = True
    assert projeto.tem_solo is False
    assert projeto.audivel(drums) is True


def test_render_soma_volume_e_pan_de_verdade(tmp_path):
    projeto = _projeto_de_teste(tmp_path, faixas=("vocals",))
    sem_volume = projeto.renderizar(destino=tmp_path / "a.wav")
    projeto.faixa("vocals").volume = 0.5
    com_volume = projeto.renderizar(destino=tmp_path / "b.wav")
    assert com_volume["pico_entrada"] < sem_volume["pico_entrada"]
    projeto.faixa("vocals").volume = 1.0
    projeto.faixa("vocals").pan = -1.0
    esquerda = projeto.renderizar(destino=tmp_path / "c.wav")
    assert esquerda["pico_entrada"] > 0
    dados, _ = sf.read(str(tmp_path / "c.wav"), dtype="float32", always_2d=True)
    assert np.abs(dados[:, 0]).max() > np.abs(dados[:, 1]).max()


def test_render_nao_toca_nos_arquivos_originais(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    original = projeto.caminho_da_faixa(projeto.faixa("vocals"))
    antes = original.read_bytes()
    projeto.faixa("vocals").volume = 0.1
    projeto.renderizar(destino=tmp_path / "mix.wav")
    assert original.read_bytes() == antes


def test_render_avisa_stem_ausente_em_vez_de_ignorar(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    (Path(projeto.pasta) / "drums.wav").unlink()
    resultado = projeto.renderizar(destino=tmp_path / "mix.wav")
    assert "drums" in resultado["ausentes"]
    assert "vocals" in resultado["faixas"]


def test_render_sem_faixa_audivel_falha_com_mensagem(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    for faixa in projeto.faixas:
        faixa.mudo = True
    with pytest.raises(pv_mod.ProjetoInvalido) as erro:
        projeto.renderizar(destino=tmp_path / "mix.wav")
    assert "mute" in str(erro.value)


def test_render_stems_editados_nao_sobrescrevem_originais(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    projeto.faixa("vocals").volume = 0.5
    resultado = projeto.renderizar_stems()
    assert set(resultado["arquivos"]) == {"vocals", "drums", "bass"}
    assert (Path(projeto.pasta) / "vocals.wav").is_file()
    assert all(Path(p).name.endswith("_edit.wav") for p in resultado["arquivos"].values())


def test_projeto_ordem_e_loop(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    assert [f.id for f in projeto.faixas_ordenadas] == ["vocals", "drums", "bass"]
    assert projeto.mover("bass", -1) is True
    assert [f.id for f in projeto.faixas_ordenadas] == ["vocals", "bass", "drums"]
    assert projeto.mover("vocals", -1) is False  # já está no topo
    projeto.ordenar(["drums", "bass", "vocals"])
    assert [f.id for f in projeto.faixas_ordenadas] == ["drums", "bass", "vocals"]
    assert projeto.definir_loop(1.0, 2.0) is True
    assert projeto.loop == {"inicio": 1.0, "fim": 2.0}
    assert projeto.definir_loop(1.0, 1.01) is False
    projeto.limpar_loop()
    assert projeto.loop is None


def test_aplicar_edicoes_so_toca_no_que_veio(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    antes_titulo = projeto.titulo
    resultado = projeto.aplicar_edicoes({"faixas": [{"id": "drums", "volume": 0.3, "mudo": True}]})
    assert resultado["ok"] is True and "faixas" in resultado["mudou"]
    assert projeto.faixa("drums").volume == pytest.approx(0.3)
    assert projeto.faixa("drums").mudo is True
    assert projeto.titulo == antes_titulo  # não veio no payload, não mudou
    # valor absurdo é limitado, não aceito cegamente
    projeto.aplicar_edicoes({"faixas": [{"id": "drums", "volume": 999}]})
    assert projeto.faixa("drums").volume <= pv_mod.GANHO_MAX


def test_projeto_exporta_cifra_midi_e_ficha(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    cifra = cifra_mod.Cifra.de_estudio(
        {"batidas": projeto.mapa.batidas, "compasso": 4, "bpm": 96, "duracao": 4.0},
        [
            {
                "compasso": 1,
                "inicio": 0.0,
                "fim": 2.0,
                "acorde": "C",
                "confianca": 0.9,
            }
        ],
        "Musica",
        "Banda",
        mapa=projeto.mapa,
        tonalidade="C maior",
    )
    projeto.cifra = cifra.as_dict()
    arquivos = projeto.exportar_apoio()
    assert "midi" in arquivos and Path(arquivos["midi"]).is_file()
    assert "ficha" in arquivos and Path(arquivos["ficha"]).is_file()
    assert Path(arquivos["cifra_txt"]).is_file()
    ficha = Path(arquivos["ficha"]).read_text(encoding="utf-8")
    assert "Musica" in ficha and "Cifra" in ficha and "A4" in ficha
    # a ficha avisa o que é estimado em vez de esconder
    assert "O que foi estimado" in ficha


def test_ficha_sem_letra_e_sem_acorde_nao_quebra(tmp_path):
    projeto = _projeto_de_teste(tmp_path)
    projeto.cifra = {}
    html = ficha_mod.gerar(projeto)
    assert "<html" in html and "Nenhum acorde" in html


# --------------------------------------------------------------------- API ---
@pytest.fixture()
def servidor(tmp_path, monkeypatch):
    """Servidor web em porta livre, com uma raiz temporária autorizada."""
    import socket
    import threading

    from mrqvs import web as web_mod

    pasta = tmp_path / "projeto"
    pasta.mkdir()
    monkeypatch.setattr(web_mod, "_OUT_ROOT", tmp_path)
    monkeypatch.setattr(web_mod, "_MUSICAS", tmp_path)
    servidor_http = web_mod.ThreadingHTTPServer(("127.0.0.1", 0), web_mod.Handler)
    porta = servidor_http.server_address[1]
    thread = threading.Thread(target=servidor_http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{porta}"
    finally:
        servidor_http.shutdown()
        servidor_http.server_close()
        thread.join(timeout=5)
    _ = socket


def _post(base: str, rota: str, payload: dict) -> tuple[int, dict]:
    dados = json.dumps(payload).encode("utf-8")
    pedido = urllib.request.Request(
        base + rota, data=dados, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            return resposta.status, json.loads(resposta.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def _get(base: str, rota: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base + rota, timeout=30) as resposta:
            return resposta.status, json.loads(resposta.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def test_api_projeto_vs_ciclo_completo(servidor, tmp_path):
    projeto = _projeto_de_teste(tmp_path / "musica")
    projeto.salvar()
    apoio = str(projeto.apoio)

    status, dados = _get(servidor, "/api/projeto-vs?apoio=" + urllib.parse.quote(apoio))
    assert status == 200
    assert dados["ok"] is True
    assert [f["id"] for f in dados["faixas"]] == ["vocals", "drums", "bass"]

    status, salvo = _post(
        servidor,
        "/api/projeto-vs",
        {
            "apoio": apoio,
            "edicoes": {
                "faixas": [{"id": "drums", "mudo": True, "pan": -0.5}],
                "marcar": {"tempo": 1.0, "nome": "Refrão"},
            },
        },
    )
    assert status == 200 and salvo["ok"] is True
    assert "faixas" in salvo["mudou"]

    # o que foi salvo está no disco: reabrir pelo GET mostra o mute
    status, relido = _get(servidor, "/api/projeto-vs?apoio=" + urllib.parse.quote(apoio))
    drums = next(f for f in relido["faixas"] if f["id"] == "drums")
    assert drums["mudo"] is True
    assert relido["marcadores"][0]["nome"] == "Refrão"

    status, render = _post(
        servidor, "/api/projeto-vs/render", {"apoio": apoio, "tipo": "mix"}
    )
    assert status == 200, render
    assert render["url"].startswith("/api/file?p=")
    assert "drums" not in render["faixas"]

    status, exportado = _post(
        servidor, "/api/projeto-vs/exportar", {"apoio": apoio}
    )
    assert status == 200, exportado
    assert "midi" in exportado["arquivos"]
    assert exportado["arquivos"]["midi"]["url"].startswith("/api/file?p=")


def test_api_projeto_vs_erros(servidor, tmp_path):
    status, _ = _get(servidor, "/api/projeto-vs")
    assert status == 400
    # dentro da raiz autorizada mas sem projeto = 404 (não é problema de permissão)
    sem_projeto = tmp_path / "sem-projeto"
    sem_projeto.mkdir(exist_ok=True)
    status, dados = _get(
        servidor, "/api/projeto-vs?apoio=" + urllib.parse.quote(str(sem_projeto))
    )
    assert status == 404
    # fora das raízes conhecidas = 403
    status, dados = _get(
        servidor, "/api/projeto-vs?apoio=" + urllib.parse.quote(str(Path("/etc")))
    )
    assert status == 403
    status, dados = _post(servidor, "/api/projeto-vs", {"apoio": str(tmp_path / "nao-existe")})
    assert status == 404


def test_api_letra_colada_alinha_e_grava(servidor, tmp_path):
    pasta = tmp_path / "musica-letra"
    pasta.mkdir()
    sr = 8000
    sinal = _com_voz(sr, 6.0, ((0.2, 2.0), (2.5, 5.0)))
    sf.write(str(pasta / "vocals.wav"), sinal, sr)
    batidas = _grade(96, 6.0)
    mapa = mapa_mod.MapaTempo.de_analise(batidas, 96, 4, 4, 6.0, 0.8)
    projeto = pv_mod.ProjetoVS(pasta=pasta, titulo="Com Letra", mapa=mapa)
    projeto.faixas.append(
        pv_mod.Faixa(id="vocals", nome="Vocais", arquivo="vocals.wav").normalizar()
    )
    projeto.salvar()

    status, dados = _post(
        servidor,
        "/api/letra",
        {"apoio": str(projeto.apoio), "texto": "primeira linha\nsegunda linha"},
    )
    assert status == 200, dados
    assert len(dados["letra"]["linhas"]) == 2
    assert dados["letra"]["metodo"] == "energia"
    assert "lrc" in dados["arquivos"]
    # ficou gravado no projeto: reabrir traz a letra
    status, relido = _get(
        servidor, "/api/projeto-vs?apoio=" + urllib.parse.quote(str(projeto.apoio))
    )
    assert len(relido["letra"]["linhas"]) == 2


def test_api_letra_vazia_e_transcricao_sem_motor(servidor, tmp_path):
    projeto = _projeto_de_teste(tmp_path / "m")
    projeto.salvar()
    status, dados = _post(servidor, "/api/letra", {"apoio": str(projeto.apoio), "texto": ""})
    assert status == 400
    assert "manual" in dados and "pip install" in dados["manual"]

    if letra_mod.motor_disponivel() is None:
        status, dados = _post(
            servidor, "/api/letra", {"apoio": str(projeto.apoio), "transcrever": True}
        )
        assert status == 501
        assert dados["motor"] is None


def test_api_letra_arquivo_lrc(servidor, tmp_path):
    projeto = _projeto_de_teste(tmp_path / "m2")
    projeto.salvar()
    texto = "[00:01.00]primeira\n[00:02.50]segunda"
    status, dados = _post(
        servidor, "/api/letra", {"apoio": str(projeto.apoio), "texto": texto, "nome": "a.lrc"}
    )
    assert status == 200, dados
    assert [round(ln["tempo"], 2) for ln in dados["letra"]["linhas"]] == [1.0, 2.5]


def test_run_publica_projeto_multitrack(tmp_path, monkeypatch):
    """O pipeline completo tem de deixar o `.mrqvs.json` na pasta de apoio."""
    from mrqvs import project

    origem = tmp_path / "fonte.wav"
    sr = 8000
    sf.write(str(origem), _tom(sr * 3, 220.0, sr, 0.25), sr)
    destino = tmp_path / "saida"
    resultado = project.run(
        project.ProjectOptions(
            source=str(origem),
            out_root=destino,
            out_dir=destino,
            stems=["drums"],
            fmt="wav",
            title="Teste Unidade",
            click=True,
            guia=False,
            exportar_lr=False,
            sample_rate=sr,
        )
    )
    assert resultado.projeto_vs is not None and Path(resultado.projeto_vs).is_file()
    projeto = pv_mod.ProjetoVS.carregar(resultado.folder.parent / f"{resultado.folder.name}-apoio")
    assert projeto.titulo
    assert projeto.faixas, "o projeto precisa listar as faixas exportadas"
    assert resultado.cifra_arquivos.get("txt")
    assert projetos_minimos_validos(projeto)
    _ = monkeypatch


def projetos_minimos_validos(projeto: pv_mod.ProjetoVS) -> bool:
    """Sanidade do projeto gerado: régua, faixas com arquivo e cifra válida."""
    assert projeto.mapa.duracao > 0
    for faixa in projeto.faixas:
        assert projeto.caminho_da_faixa(faixa) is not None, faixa.arquivo
    dados = projeto.cifra_obj().as_dict()
    assert "secoes" in dados
    return True


def test_exemplo_de_projeto_no_relatorio(tmp_path):
    """O relatório em JSON e o projeto têm de concordar sobre a régua."""
    from mrqvs import project

    origem = tmp_path / "fonte.wav"
    sr = 8000
    sf.write(str(origem), _tom(sr * 3, 220.0, sr, 0.25), sr)
    destino = tmp_path / "s"
    resultado = project.run(
        project.ProjectOptions(
            source=str(origem),
            out_root=destino,
            out_dir=destino,
            stems=["drums"],
            fmt="wav",
            title="Concordancia",
            click=True,
            guia=False,
            exportar_lr=False,
            acordes=False,
            sample_rate=sr,
        )
    )
    dados = json.loads(resultado.report_json.read_text(encoding="utf-8"))
    estudio = dados["analise"]["estudio"]
    projeto = pv_mod.ProjetoVS.carregar(resultado.folder.parent / f"{resultado.folder.name}-apoio")
    assert estudio["compasso"] == projeto.mapa.numerador
    assert abs(float(estudio["bpm"]) - projeto.mapa.bpm) < 0.01
    assert struct.calcsize(">IHHH") == 10  # o cabeçalho MIDI, documentado


def test_projeto_gerado_nao_repete_faixa(tmp_path):
    """Cada faixa aparece uma vez só — o bug era o L/R duplicado na lista."""
    from mrqvs import project

    origem = tmp_path / "fonte.wav"
    sr = 8000
    sf.write(str(origem), _tom(sr * 3, 220.0, sr, 0.25), sr)
    destino = tmp_path / "s"
    resultado = project.run(
        project.ProjectOptions(
            source=str(origem),
            out_root=destino,
            out_dir=destino,
            stems=["drums"],
            fmt="wav",
            title="Duplicata",
            click=True,
            guia=True,
            exportar_lr=True,
            sample_rate=sr,
        )
    )
    projeto = pv_mod.ProjetoVS.carregar(resultado.folder.parent / f"{resultado.folder.name}-apoio")
    ids = [f.id for f in projeto.faixas]
    assert len(ids) == len(set(ids)), f"faixa repetida no projeto: {ids}"
    ordens = [f.ordem for f in projeto.faixas_ordenadas]
    assert ordens == list(range(len(ordens))), f"ordem com buraco ou repetida: {ordens}"
    # e a música tem de abrir com algo audível (não toda calada)
    assert any(projeto.audivel(f) for f in projeto.faixas if f.tipo in ("stem", "mix"))


def test_projeto_com_uma_faixa_nao_abre_mudo(tmp_path):
    """Separação de uma faixa só: a música tem de abrir ouvindo algo."""
    from mrqvs import project

    origem = tmp_path / "fonte.wav"
    sr = 8000
    sf.write(str(origem), _tom(sr * 3, 220.0, sr, 0.25), sr)
    destino = tmp_path / "s"
    resultado = project.run(
        project.ProjectOptions(
            source=str(origem),
            out_root=destino,
            out_dir=destino,
            stems=["other"],
            fmt="wav",
            title="Uma Faixa",
            click=False,
            guia=False,
            exportar_lr=False,
            sample_rate=sr,
        )
    )
    projeto = pv_mod.ProjetoVS.carregar(resultado.folder.parent / f"{resultado.folder.name}-apoio")
    assert projeto.faixas
    assert any(projeto.audivel(f) for f in projeto.faixas)


# ------------------------------------------------------------- interface CLI ---
def test_cli_projeto_lista_e_transpoe(tmp_path, capsys):
    """`mrq-vs projeto` usa o mesmo módulo da tela — e tem de funcionar."""
    from mrqvs import cli

    projeto = _projeto_de_teste(tmp_path)
    projeto.cifra = cifra_mod.Cifra.de_estudio(
        {
            "batidas": projeto.mapa.batidas, "compasso": 4, "bpm": 96,
            "duracao": 4.0, "tonalidade": "C maior",
        },
        [{"compasso": 1, "inicio": 0.0, "fim": 2.0, "acorde": "C", "confiancia": 0.9,
          "confianca": 0.9}],
        "Musica", "Banda", mapa=projeto.mapa, tonalidade="C maior",
    ).as_dict()
    projeto.salvar()

    assert cli.main(["projeto", "lista", str(projeto.pasta)]) == 0
    saida = capsys.readouterr().out
    assert "Musica" in saida and "vocals.wav" in saida
    assert "96 BPM" in saida

    assert cli.main(["projeto", "transpor", str(projeto.pasta), "--semitons", "2"]) == 0
    lido = pv_mod.ProjetoVS.carregar(projeto.apoio)
    assert lido.cifra_obj().linhas[0].acorde == "D"
    assert "o áudio não foi alterado" in capsys.readouterr().out


def test_cli_projeto_mix_e_exportar(tmp_path, capsys):
    from mrqvs import cli

    projeto = _projeto_de_teste(tmp_path)
    projeto.cifra = cifra_mod.Cifra.de_estudio(
        {"batidas": projeto.mapa.batidas, "compasso": 4, "bpm": 96, "duracao": 4.0},
        [{"compasso": 1, "inicio": 0.0, "fim": 2.0, "acorde": "C", "confianca": 0.9}],
        "Musica", mapa=projeto.mapa,
    ).as_dict()
    projeto.salvar()
    destino = tmp_path / "saida.wav"
    assert cli.main(["projeto", "mix", str(projeto.pasta), "--destino", str(destino)]) == 0
    assert destino.is_file()
    assert "mix:" in capsys.readouterr().out

    assert cli.main(["projeto", "exportar", str(projeto.pasta)]) == 0
    saida = capsys.readouterr().out
    assert "midi" in saida and "ficha" in saida
    assert list(Path(projeto.apoio).glob("*.mid"))


def test_cli_projeto_erros_claros(tmp_path, capsys):
    from mrqvs import cli

    assert cli.main(["projeto", "lista", str(tmp_path / "nada")]) == 2
    assert "não encontrada" in capsys.readouterr().err
    pasta = tmp_path / "sem-projeto"
    pasta.mkdir()
    assert cli.main(["projeto", "lista", str(pasta)]) == 1
    assert "Separe a música" in capsys.readouterr().err


def test_cli_projeto_marcar_e_corrigir_compasso(tmp_path, capsys):
    from mrqvs import cli

    projeto = _projeto_de_teste(tmp_path)
    projeto.salvar()
    assert cli.main(["projeto", "marcar", str(projeto.pasta), "--tempo", "1.5", "--nome", "Ponte"]) == 0
    lido = pv_mod.ProjetoVS.carregar(projeto.apoio)
    assert lido.marcadores[0].nome == "Ponte"
    assert cli.main(["projeto", "corrigir", str(projeto.pasta), "--compasso", "3/4"]) == 0
    lido = pv_mod.ProjetoVS.carregar(projeto.apoio)
    assert (lido.mapa.numerador, lido.mapa.denominador) == (3, 4)
    _ = capsys


def test_cli_projeto_letra_alinhada(tmp_path, capsys):
    """Letra por arquivo na CLI: alinha ao áudio e grava lrc/srt/txt/json."""
    from mrqvs import cli

    pasta = tmp_path / "ComLetra"
    pasta.mkdir()
    sr = 8000
    sinal = _com_voz(sr, 6.0, ((0.2, 2.0), (2.5, 5.0)))
    sf.write(str(pasta / "vocals.wav"), sinal, sr)
    projeto = pv_mod.ProjetoVS(
        pasta=pasta,
        titulo="Com Letra",
        mapa=mapa_mod.MapaTempo.de_analise(_grade(96, 6.0), 96, 4, 4, 6.0, 0.8),
    )
    projeto.faixas.append(pv_mod.Faixa(id="vocals", nome="Vocais", arquivo="vocals.wav").normalizar())
    projeto.salvar()
    arquivo = tmp_path / "letra.txt"
    arquivo.write_text("primeira linha\nsegunda linha\n", encoding="utf-8")

    assert cli.main(["projeto", "letra", str(pasta), "--letra", str(arquivo)]) == 0
    lido = pv_mod.ProjetoVS.carregar(projeto.apoio)
    assert len(lido.letra_obj().linhas) == 2
    assert (projeto.apoio / "letra.lrc").is_file()
    saida = capsys.readouterr().out
    assert "letra_lrc" in saida


def test_cli_projeto_letra_sem_arquivo(tmp_path, capsys):
    from mrqvs import cli

    projeto = _projeto_de_teste(tmp_path)
    projeto.salvar()
    assert cli.main(["projeto", "letra", str(projeto.pasta)]) == 2
    assert "informe o arquivo de letra" in capsys.readouterr().err
    assert cli.main(
        ["projeto", "letra", str(projeto.pasta), "--letra", str(tmp_path / "nao.txt")]
    ) == 2
    assert "não encontrado" in capsys.readouterr().err
