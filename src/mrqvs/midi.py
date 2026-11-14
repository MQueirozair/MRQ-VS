"""MIDI do projeto: mapa de tempo, clique e cifra — sem biblioteca externa.

Por que escrever o arquivo à mão: um `.mid` é uma sequência de eventos com
 cabeçalho de 14 bytes. As bibliotecas que fazem isso (mido, pretty_midi)
 trazem dependências para tocar 40 linhas de struct — e o programa já promete
 rodar com `numpy` + `soundfile` e nada mais. O formato é público (SMF 1.0) e
 estável desde 1991: escrever isso aqui é mais previsível que depender de
 versão de pacote.

O que sai:

* **track 0** — mapa de tempo: um `set_tempo` por trecho de andamento e
  `time_signature` em cada troca de fórmula. É o que faz a DAW mostrar a régua
  certa quando o BPM muda no meio da música.
* **track 1** — clique: nota aguda no 1º tempo do compasso, média nos demais,
  respeitando a fórmula vigente (acento de 6/8 e 7/8 sai certo).
* **track 2** — cifra: cada compasso vira um acorde sustentado (tríade + baixo),
  no canal 2, para o tecladista importar e ouvir a harmonia.
* **track 3** — marcadores de seção (`marker`), com o nome que a estrutura
  detectou.

Nada aqui inventa harmonia: o acorde é o que está na cifra; compasso sem acorde
confiável simplesmente não gera nota (e isso fica registrado no arquivo).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import acordes as acordes_mod
from . import cifra as cifra_mod
from . import mapa_tempo as mapa_mod

#: Resolução: pulsos por semínima. 480 é o padrão que toda DAW lê bem e ainda
#: permite tercina (480/3 = 160) sem arredondar.
PPQ = 480

#: Programas General MIDI usados nos esboços.
PROGRAMA_CLIQUE = 115  # Woodblock
PROGRAMA_CIFRA = 0     # Acoustic Grand Piano
PROGRAMA_BAIXO = 33    # Acoustic Bass

CANAL_CLIQUE = 9   # canal 10 (percussão) — não depende de programa
CANAL_CIFRA = 2
CANAL_BAIXO = 3
CANAL_MARCADOR = 0


# ---------------------------------------------------------------- eventos ---
@dataclass
class Evento:
    tick: int
    mensagem: bytes
    #: ordem de desempate no mesmo tick: nota-off antes de nota-on, e
    #: metadados antes das notas (senão a DAW lê o acorde no tempo errado)
    prioridade: int = 5

    def dados(self) -> bytes:
        return _varint(0) + self.mensagem


@dataclass
class Trilha:
    nome: str
    eventos: list[Evento] = field(default_factory=list)

    def add(self, tick: int, mensagem: bytes, prioridade: int = 5) -> None:
        self.eventos.append(Evento(max(0, int(tick)), mensagem, prioridade))

    def ordenar(self) -> None:
        self.eventos.sort(key=lambda e: (e.tick, e.prioridade))

    def bytes(self) -> bytes:
        self.ordenar()
        saida = bytearray()
        # nome da trilha: é o que aparece na lista de tracks da DAW
        nome = self.nome.encode("utf-8")[:127]
        saida += _varint(0) + b"\xff\x03" + _varint(len(nome)) + nome
        anterior = 0
        for ev in self.eventos:
            delta = ev.tick - anterior
            anterior = ev.tick
            saida += _varint(delta) + ev.mensagem
        saida += _varint(0) + b"\xff\x2f\x00"  # end of track
        return b"MTrk" + struct.pack(">I", len(saida)) + bytes(saida)


# ------------------------------------------------------------------ utils ---
def _varint(valor: int) -> bytes:
    """Inteiro de tamanho variável do MIDI (7 bits por byte, MSB = continua)."""
    valor = max(0, int(valor))
    pedacos = [valor & 0x7F]
    valor >>= 7
    while valor:
        pedacos.append((valor & 0x7F) | 0x80)
        valor >>= 7
    return bytes(reversed(pedacos))


def _meta(tipo: int, dados: bytes | int) -> bytes:
    if isinstance(dados, int):
        dados = struct.pack(">I", dados)[1:]  # 3 bytes, como o set_tempo exige
    return bytes([0xFF, tipo]) + _varint(len(dados)) + dados


def _texto_meta(tipo: int, texto: str) -> bytes:
    return _meta(tipo, texto.encode("utf-8")[:255])


def _nota(canal: int, nota: int, velocidade: int, ligada: bool) -> bytes:
    return bytes([(0x90 if ligada else 0x80) | (canal & 0x0F), nota & 0x7F, velocidade & 0x7F])


def _tempo_us(bpm: float) -> int:
    """Microssegundos por semínima (o `set_tempo` do MIDI)."""
    if bpm <= 0:
        bpm = 120.0
    return int(round(60_000_000 / float(bpm)))


def _tick(mapa: mapa_mod.MapaTempo, tempo: float) -> int:
    """Segundos -> tick do arquivo, passando pela régua do projeto."""
    indice = mapa.indice_de_tempo(tempo)
    return max(0, int(round(indice * PPQ)))


# ------------------------------------------------------------- construção ---
def construir(
    mapa: mapa_mod.MapaTempo,
    cifra: cifra_mod.Cifra | None = None,
    secoes: list[dict] | None = None,
    com_clique: bool = True,
    com_cifra: bool = True,
    com_marcadores: bool = True,
    titulo: str = "",
) -> bytes:
    """Monta o `.mid` completo (SMF tipo 1) e devolve os bytes."""
    regencia = Trilha("MRQ VS — mapa de tempo")
    # nome da música no primeiro evento: é o que a DAW mostra ao importar
    regencia.add(0, _texto_meta(0x03, titulo or cifra.titulo if cifra else titulo or "MRQ VS"), 0)

    # --- mapa de tempo ---------------------------------------------------
    regencia.add(0, _meta(0x58, bytes([mapa.numerador, max(0, _log2(mapa.denominador)), 24, 8])), 0)
    regencia.add(0, _meta(0x51, _tempo_us(mapa.bpm or 120.0)), 1)
    # trocas de fórmula (1-based na entrada, 0-based na régua)
    formulas = {1: (mapa.numerador, mapa.denominador)}
    for m in mapa.mudancas:
        try:
            numero = int(m.get("compasso") or 0)
        except (TypeError, ValueError):
            continue
        if numero <= 1:
            continue
        formulas[numero] = (
            max(1, int(m.get("numerador") or mapa.numerador)),
            int(m.get("denominador") or mapa.denominador),
        )
    for numero, (num, den) in sorted(formulas.items()):
        if numero == 1:
            continue
        tick = _tick(mapa, mapa.inicio_do_compasso(numero - 1))
        regencia.add(tick, _meta(0x58, bytes([num, max(0, _log2(den)), 24, 8])), 0)
    # trocas de andamento medidas (não presumidas): cada trecho ganha o seu
    for trecho in mapa.andamentos():
        if trecho["compasso"] == 1:
            continue
        tick = _tick(mapa, mapa.inicio_do_compasso(trecho["compasso"] - 1))
        regencia.add(tick, _meta(0x51, _tempo_us(trecho["bpm"])), 1)

    trilhas = [regencia]

    # --- clique ----------------------------------------------------------
    if com_clique:
        clique = Trilha("Clique")
        clique.add(0, _texto_meta(0x03, "Clique"), 0)
        for batida in mapa.batidas or []:
            compasso, pulso = mapa.pulso_do_compasso(batida)
            num, _den = mapa.formula(compasso - 1)
            tick = _tick(mapa, batida)
            if pulso == 1:
                nota, vel = 76, 110 + max(0, min(17, num))
            else:
                nota, vel = 77, 78
            clique.add(tick, _nota(CANAL_CLIQUE, nota, vel, True), 6)
            clique.add(tick + PPQ // 8, _nota(CANAL_CLIQUE, nota, 0, False), 4)
        trilhas.append(clique)

    # --- cifra -----------------------------------------------------------
    if com_cifra and cifra is not None:
        acordes_midi = Trilha("Cifra")
        acordes_midi.add(0, _texto_meta(0x03, "Cifra"), 0)
        acordes_midi.add(0, bytes([0xC0 | CANAL_CIFRA, PROGRAMA_CIFRA]), 2)
        acordes_midi.add(0, bytes([0xC0 | CANAL_BAIXO, PROGRAMA_BAIXO]), 2)
        for linha in cifra.linhas:
            if not linha.acorde or linha.incerto:
                continue
            notas = notas_do_acorde(linha.acorde)
            if not notas:
                continue
            inicio = _tick(mapa, linha.inicio)
            # um tique antes do fim do compasso: a nota não invade o próximo
            fim = max(inicio + PPQ // 4, _tick(mapa, linha.fim) - 2)
            for nota in notas["acorde"]:
                acordes_midi.add(inicio, _nota(CANAL_CIFRA, nota, 72, True), 8)
                acordes_midi.add(fim, _nota(CANAL_CIFRA, nota, 0, False), 3)
            if notas["baixo"]:
                acordes_midi.add(inicio, _nota(CANAL_BAIXO, notas["baixo"], 84, True), 8)
                acordes_midi.add(fim, _nota(CANAL_BAIXO, notas["baixo"], 0, False), 3)
        trilhas.append(acordes_midi)

    # --- marcadores de seção ---------------------------------------------
    if com_marcadores and secoes:
        marcas = Trilha("Seções")
        marcas.add(0, _texto_meta(0x03, "Seções"), 0)
        for secao in secoes:
            nome = str(secao.get("nome") or secao.get("rotulo") or "").strip()
            try:
                inicio = float(secao.get("start", secao.get("inicio", 0.0)) or 0.0)
            except (TypeError, ValueError):
                continue
            if not nome:
                continue
            marcas.add(_tick(mapa, inicio), _texto_meta(0x06, nome), 0)
        if len(marcas.eventos) > 1:
            trilhas.append(marcas)

    return _arquivo(trilhas, ppq=PPQ)


def _arquivo(trilhas: list[Trilha], ppq: int = PPQ) -> bytes:
    cabecalho = b"MThd" + struct.pack(">IHHH", 6, 1, len(trilhas), ppq)
    return cabecalho + b"".join(t.bytes() for t in trilhas)


def _log2(valor: int) -> int:
    """Denominador -> expoente (4 -> 2, 8 -> 3), como o MIDI exige."""
    expoente = 0
    v = max(1, int(valor))
    while v > 1 and expoente < 6:
        v //= 2
        expoente += 1
    return expoente


#: Semitons da tríade por sufixo. Fora desta tabela o acorde não gera nota
#: (ex.: "7M" digitado à mão continua válido na cifra, só não vira MIDI).
_INTERVALOS = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "m7": (0, 3, 7, 10),
    "maj7": (0, 4, 7, 11),
    "7M": (0, 4, 7, 11),
    "sus4": (0, 5, 7),
    "sus2": (0, 2, 7),
    "dim": (0, 3, 6),
    "m7b5": (0, 3, 6, 10),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "9": (0, 4, 7, 10, 14),
    "add9": (0, 4, 7, 14),
    "5": (0, 7),
}

#: Faixa de conforto do piano (C3..C5) para o acorde não brigar com a voz.
OITAVA_ACORDE = 60
OITAVA_BAIXO = 36


def notas_do_acorde(acorde: str) -> dict:
    """{'acorde': [60, 64, 67], 'baixo': 40} — MIDI do acorde escrito.

    A tônica do acorde vai para a região do piano (C4 = 60); o baixo vai para
    C2/C3. Inversão (`D/F#`) usa o baixo pedido, não a fundamental.
    """
    raiz, sufixo, baixo = cifra_mod.separar(acorde)
    if not raiz:
        return {"acorde": [], "baixo": 0}
    indice = acordes_mod.NOTAS.index(raiz) if raiz in acordes_mod.NOTAS else (
        acordes_mod.NOTAS_BEMOL.index(raiz) if raiz in acordes_mod.NOTAS_BEMOL else -1
    )
    if indice < 0:
        return {"acorde": [], "baixo": 0}
    intervalos = _INTERVALOS.get(sufixo)
    if intervalos is None:
        return {"acorde": [], "baixo": 0}
    fundamental = OITAVA_ACORDE + indice
    notas = [fundamental + i for i in intervalos]
    # mantém tudo dentro de uma oitava e meia para não virar arpejo gigante
    notas = [n if n <= fundamental + 24 else n - 12 for n in notas]
    nota_baixo = 0
    if baixo:
        bi = acordes_mod.NOTAS.index(baixo) if baixo in acordes_mod.NOTAS else (
            acordes_mod.NOTAS_BEMOL.index(baixo) if baixo in acordes_mod.NOTAS_BEMOL else -1
        )
        if bi >= 0:
            nota_baixo = OITAVA_BAIXO + 12 + bi
    else:
        nota_baixo = OITAVA_BAIXO + 12 + indice
    return {"acorde": sorted(set(notas)), "baixo": nota_baixo}


def escrever(
    destino: Path,
    mapa: mapa_mod.MapaTempo,
    cifra: cifra_mod.Cifra | None = None,
    secoes: list[dict] | None = None,
    titulo: str = "",
) -> Path:
    """Grava o `.mid` e devolve o caminho."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(
        construir(mapa, cifra=cifra, secoes=secoes, titulo=titulo or (cifra.titulo if cifra else ""))
    )
    return destino


def ler_cabecalho(caminho: Path) -> dict:
    """Lê só o cabeçalho do `.mid` — usado nos testes para conferir o arquivo."""
    dados = Path(caminho).read_bytes()
    if dados[:4] != b"MThd":
        raise ValueError("não é um arquivo MIDI (falta MThd)")
    tamanho, formato, trilhas, ppq = struct.unpack(">IHHH", dados[4:14])
    return {"tamanho": tamanho, "formato": formato, "trilhas": trilhas, "ppq": ppq}
