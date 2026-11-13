"""Guia: a faixa falada que anuncia a seção e conta antes dela.

O que o CueWee faz (pesquisado na documentacao deles, help.cuewee.com/pt):

* o **click** e gerado automaticamente com subdivisoes e contagens, travado no
  mapa de tempo da musica;
* a **guia de voz** e uma voz natural que anuncia as secoes ("intro, verso,
  refrao, ponte, solo") com contagem regressiva opcional nas transicoes;
* o click e a guia tocam exatamente a entrada que aparece na tela, e podem ser
  exportados junto ou separados.

Este modulo faz a mesma coisa sem servidor e sem voz sintetica:

* a guia e montada a partir das **secoes** que o programa ja detecta e da
  **grade de batidas** que ele ja calcula. O que faltava era o texto e o
  compasso — e o compasso agora e detectado (4/4 ou 3/4);
* a "voz" e uma **melodia de referencia**: frases curtas em notas de
  sintetizador com timbre reconhecivel. Nao e voz falada de verdade — isso
  exigiria um motor de fala (centenas de MB). A tela e o relatorio dizem isso
  com essas palavras, sem prometer o que nao entrega.

Por que notas e nao fala: a informacao que a banda precisa no in-ear e
"comeca o refrao em 4 tempos". Uma frase musical cumpre isso, e custa 0 MB.
O que a guia fala de verdade e a proxima coisa a resolver; o formato do audio
ja esta pronto para trocar a fonte sonora sem mudar mais nada.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Como cada rotulo de secao e anunciado.
NOMES_SECAO: dict[str, str] = {
    "intro": "Intro",
    "verso": "Verso",
    "refrao": "Refrão",
    "ponte": "Ponte",
    "solo": "Solo",
    "outro": "Final",
    "instrumental": "Instrumental",
    "A": "Parte A",
    "B": "Parte B",
    "C": "Parte C",
    "D": "Parte D",
}

#: Quantos tempos de contagem antes de cada secao. O CueWee usa a lista 1-7;
#: 4 e o padrao porque e o compasso mais comum e cabe inteiro num compasso.
CONTAGEM_PADRAO = 4


def nome_da_secao(rotulo: str) -> str:
    """Rotulo tecnico -> nome que se fala."""
    return NOMES_SECAO.get(rotulo, rotulo)


@dataclass
class Entrada:
    """Uma coisa que a guia toca: contagem ou anuncio."""

    tempo: float          # quando comeca, em segundos
    tipo: str             # "contagem" | "anuncio"
    valor: int | str      # 4, 3, ... ou o nome da secao
    secao: str = ""       # de qual secao isso faz parte

    @property
    def texto(self) -> str:
        return str(self.valor)

    def descricao(self) -> str:
        if self.tipo == "contagem":
            return f"contagem {self.valor}"
        return f"anúncio: {self.valor}"


def compor(
    secoes: list,
    batidas: list[float],
    *,
    contagem: int = CONTAGEM_PADRAO,
    anunciar_todas: bool = True,
) -> list[Entrada]:
    """Monta a lista de entradas da guia a partir das secoes reais.

    A primeira secao nao recebe contagem: nao ha de onde contar antes do
    primeiro tempo da musica (o CueWee faz o mesmo — as celulas que cairiam
    antes da primeira batida ficam em silencio).

    Uma secao mais curta que a contagem pedida recebe o que couber: melhor
    contar 2 do que atropelar a secao seguinte.
    """
    if not batidas:
        return []
    entradas: list[Entrada] = []
    passo = (batidas[1] - batidas[0]) if len(batidas) > 1 else 0.5

    for indice, secao in enumerate(secoes):
        inicio = float(getattr(secao, "start", 0.0))
        rotulo = str(getattr(secao, "label", ""))
        nome = nome_da_secao(rotulo)
        if not anunciar_todas and indice > 0 and nome == "Parte A":
            continue

        # Quantos tempos de contagem cabem ANTES desta secao. A conta e com o
        # FIM da secao (nao com o fim da anterior): as secoes sao contiguas,
        # entao `inicio - fim_anterior` e zero e a contagem nunca aparecia —
        # bug encontrado testando com a demo.
        cabem = contagem
        if indice > 0:
            fim_desta = float(getattr(secao, "end", inicio))
            disponivel = max(0.0, fim_desta - inicio)
            if passo > 0:
                cabem = max(0, min(contagem, int(disponivel // passo + 1e-6)))
            else:
                cabem = 0
            if cabem == 0:
                # secao curta demais para caber contagem: melhor anunciar no
                # tempo exato do que empurrar a contagem para cima do verso
                cabem = 0
        else:
            cabem = 0

        # anuncio no meio do compasso anterior, se houver espaco; senao junto
        # da primeira contagem (o anuncio importa mais que a separacao)
        if cabem:
            for n in range(cabem, 0, -1):
                tempo = inicio - n * passo
                if tempo >= 0:
                    entradas.append(Entrada(round(tempo, 4), "contagem", n, nome))
            inicio_anuncio = max(0.0, inicio - cabem * passo)
            entradas.append(Entrada(round(inicio_anuncio, 4), "anuncio", nome, nome))
        else:
            entradas.append(Entrada(round(inicio, 4), "anuncio", nome, nome))

    entradas.sort(key=lambda e: (e.tempo, 0 if e.tipo == "anuncio" else 1))
    return entradas


def descrever(entradas: list[Entrada]) -> list[str]:
    """Linhas para o relatorio: o que toca, onde e quando."""
    return [f"{e.tempo:6.2f}s  {e.descricao()}" for e in entradas]


def resumo(entradas: list[Entrada]) -> str:
    """Uma frase honesta sobre o que a guia e (e o que nao e)."""
    if not entradas:
        return "sem guia: não foi possível montar a grade de batidas."
    anuncios = sum(1 for e in entradas if e.tipo == "anuncio")
    return (
        f"guia com {anuncios} anúncio(s) de seção e contagem de até "
        f"{CONTAGEM_PADRAO} tempos. O áudio é uma melodia de referência "
        "(não é voz falada): o nome da seção e a contagem estão no relatório "
        "e na tela."
    )


# ---------------------------------------------------------------------------
# Áudio
# ---------------------------------------------------------------------------
#: Timbre de cada tipo de entrada. A contagem sobe de tom a cada número (o
#: ouvido lê "3, 2, 1" pela direção), o anúncio usa um par de notas curto e
#: distinto — é o "olha a seção nova" que a banda precisa escutar no in-ear.
ESCALA_CONTAGEM = (659.25, 783.99, 987.77, 1174.66, 1318.51, 1567.98, 1760.0)
ANUNCIO = (523.25, 783.99)


def escrever_audio(
    caminho,
    sample_rate: int,
    entradas: list[Entrada],
    duracao: float,
    volume: float = 0.5,
) -> None:
    """Grava a guia em WAV mono, alinhada ao segundo 0 da música.

    Mono e proposital: a guia vai para o in-ear, e um sinal mono entra igual
    nos dois lados — nada de "a guia só aparece de um lado" no fone.
    """
    import numpy as np

    try:
        import soundfile as sf
    except ModuleNotFoundError:
        from . import dsp

        raise dsp.MissingDependency("soundfile", "gerar a guia") from None

    total = int(duracao * sample_rate) + sample_rate // 10
    saida = np.zeros(total, dtype=np.float32)

    def tom(freq: float, dur: float, ganho: float) -> "np.ndarray":
        n = max(1, int(dur * sample_rate))
        t = np.arange(n) / sample_rate
        env = np.minimum(1.0, t / 0.005) * np.exp(-t * 6.0)
        # duas senoides (fundamental + oitava) para o timbre não sumir num
        # alto-falante pequeno
        onda = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
        return (onda * env * ganho).astype(np.float32)

    for entrada in entradas:
        inicio = int(entrada.tempo * sample_rate)
        if entrada.tipo == "contagem":
            numero = max(1, min(7, int(entrada.valor)))
            pedaco = tom(ESCALA_CONTAGEM[numero - 1], 0.09, volume * 0.7)
        else:
            # anúncio: duas notas ascendentes, mais longo, para destacar
            a = tom(ANUNCIO[0], 0.13, volume * 0.55)
            b = tom(ANUNCIO[1], 0.16, volume * 0.55)
            pedaco = np.concatenate([a, b])
        fim = min(total, inicio + pedaco.size)
        if inicio >= total or fim <= inicio:
            continue
        saida[inicio:fim] += pedaco[: fim - inicio]

    pico = float(np.max(np.abs(saida))) if saida.size else 0.0
    if pico > 0.98:
        saida *= 0.98 / pico

    from pathlib import Path

    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    sf.write(caminho, saida, sample_rate, subtype="PCM_16")


# ---------------------------------------------------------------------------
# Exportação L/R (o "renderizar L/R" do CueWee)
# ---------------------------------------------------------------------------
def escrever_lr(
    caminho,
    sample_rate: int,
    banda,
    ensaio,
    duracao: float,
    ganho_banda: float = 0.9,
    ganho_ensaio: float = 0.9,
) -> None:
    """Grava o par estéreo que o CueWee chama de L/R.

    Por que existe: no palco quase ninguém quer dois arquivos com o mesmo
    tamanho para sincronizar na mão. O padrão da indústria é UM arquivo
    estéreo em que o lado esquerdo leva click + guia (só para o in-ear da
    banda) e o direito leva a banda. Ligando o cabo L na entrada do in-ear e
    o R na mesa, o público nunca ouve o metrônomo.

    `banda` e `ensaio` são arrays mono do mesmo tamanho da música. O que vier
    mais curto é completado com silêncio (nunca desalinhado, nunca esticado).
    """
    import numpy as np

    try:
        import soundfile as sf
    except ModuleNotFoundError:
        from . import dsp

        raise dsp.MissingDependency("soundfile", "exportar em L/R") from None

    total = int(duracao * sample_rate)

    def ajustar(sinal, ganho: float) -> "np.ndarray":
        if sinal is None:
            return np.zeros(total, dtype=np.float32)
        arr = np.asarray(sinal, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        arr = arr * ganho
        if arr.size < total:
            arr = np.pad(arr, (0, total - arr.size))
        return arr[:total].astype(np.float32)

    esquerda = ajustar(ensaio, ganho_ensaio)
    direita = ajustar(banda, ganho_banda)
    estereo = np.stack([esquerda, direita], axis=1)

    pico = float(np.max(np.abs(estereo))) if estereo.size else 0.0
    if pico > 0.99:
        estereo *= 0.99 / pico

    from pathlib import Path

    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    sf.write(caminho, estereo, sample_rate, subtype="PCM_16")
