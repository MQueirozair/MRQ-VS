"""Letra sincronizada: transcrição (quando há motor) e alinhamento ao áudio.

Duas situações reais, tratadas de forma diferente — e o arquivo diz qual foi:

**1. O usuário já tem a letra.** Ele cola o texto ou importa `.lrc`/`.srt`.
Aqui a letra NÃO é inventada: o programa mede onde a voz canta (energia do
stem de vocais, ou do mix quando não há separação), e distribui as linhas
pelos trechos cantados, ponderando pelo número de sílabas de cada linha. O
resultado é um alinhamento **estimado por energia** — e é chamado assim em
todo lugar, com confiança por linha. Se a contagem de linhas e de trechos
cantados combina, a confiança sobe; se não combina, o alinhamento continua
útil, mas o cabeçalho avisa que é aproximado.

**2. O usuário não tem a letra.** Aí é transcrição de verdade, e ela precisa
de um motor de fala instalado (`faster-whisper`, `whisper` ou `vosk`). Este
módulo usa o primeiro que existir, roda local, e devolve os tempos que o
próprio motor mediu. Sem motor instalado, levanta `MotorIndisponivel` com a
instrução de instalação — **não** devolve letra chutada nem "processando"
infinito.

Por que não embutir um modelo: são centenas de MB de pesos com licença
própria, e o programa promete instalar leve. Quem quer transcrever instala com
um comando; o resto do fluxo (importar letra, alinhar, exportar LRC) funciona
sem nada disso.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

#: Motores de transcrição reconhecidos, na ordem de preferência.
#: (módulo, como instalar, licença do pacote)
MOTORES = (
    ("faster_whisper", "pip install faster-whisper", "MIT"),
    ("whisper", "pip install openai-whisper", "MIT"),
    ("vosk", "pip install vosk", "Apache-2.0"),
)

#: Abaixo disso o trecho não conta como voz (é o mesmo piso do `estrutura`,
#: relativo ao próprio material: música baixinha não vira "sem voz").
PISO_ENERGIA = 0.08

#: Duas linhas nunca devem começar a menos disso; evita empilhar texto.
SEPARACAO_MINIMA = 0.35

_RE_LRC = re.compile(r"^\[(\d{1,2}):(\d{1,2}(?:[.,]\d{1,3})?)\](.*)$")
_RE_LRC_META = re.compile(r"^\[(ti|ar|al|by|offset):(.*)\]$", re.IGNORECASE)
_RE_SRT_TEMPO = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


class MotorIndisponivel(RuntimeError):
    """Não há motor de transcrição instalado — e a mensagem diz como resolver."""


class LetraInvalida(ValueError):
    """O texto/tempo informado não dá para interpretar."""


@dataclass
class LinhaLetra:
    tempo: float
    texto: str
    #: quando a linha termina (0 = até a próxima)
    fim: float = 0.0
    confianca: float = 0.0
    #: "motor" (tempo veio do transcritor), "importada" (.lrc/.srt com tempo)
    #: ou "energia" (alinhamento estimado do texto fornecido)
    metodo: str = ""

    def as_dict(self) -> dict:
        return {
            "tempo": round(self.tempo, 3),
            "fim": round(self.fim, 3),
            "texto": self.texto,
            "confianca": round(self.confianca, 3),
            "metodo": self.metodo,
        }


@dataclass
class Letra:
    linhas: list[LinhaLetra] = field(default_factory=list)
    titulo: str = ""
    artista: str = ""
    #: "motor" | "importada" | "energia" | ""
    metodo: str = ""
    #: avisos honestos sobre o que foi medido e o que foi estimado
    avisos: list[str] = field(default_factory=list)

    @property
    def vazia(self) -> bool:
        return not self.linhas

    @property
    def confianca_media(self) -> float:
        if not self.linhas:
            return 0.0
        return sum(ln.confianca for ln in self.linhas) / len(self.linhas)

    def texto_completo(self) -> str:
        return "\n".join(ln.texto for ln in self.linhas)

    def as_dict(self) -> dict:
        return {
            "titulo": self.titulo,
            "artista": self.artista,
            "metodo": self.metodo,
            "confianca_media": round(self.confianca_media, 3),
            "linhas": [ln.as_dict() for ln in self.linhas],
            "avisos": list(self.avisos),
        }

    @classmethod
    def de_dict(cls, dados: dict | None) -> "Letra":
        dados = dados or {}
        linhas = []
        for item in dados.get("linhas") or []:
            try:
                linhas.append(
                    LinhaLetra(
                        tempo=float(item.get("tempo") or 0.0),
                        texto=str(item.get("texto") or ""),
                        fim=float(item.get("fim") or 0.0),
                        confianca=float(item.get("confianca") or 0.0),
                        metodo=str(item.get("metodo") or ""),
                    )
                )
            except (TypeError, ValueError):
                continue
        return cls(
            linhas=linhas,
            titulo=str(dados.get("titulo") or ""),
            artista=str(dados.get("artista") or ""),
            metodo=str(dados.get("metodo") or ""),
            avisos=list(dados.get("avisos") or []),
        )

    # -- exportação ------------------------------------------------------
    def para_lrc(self) -> str:
        partes = []
        if self.titulo:
            partes.append(f"[ti:{self.titulo}]")
        if self.artista:
            partes.append(f"[ar:{self.artista}]")
        if self.metodo:
            partes.append(f"[by:MRQ VS · alinhamento por {self.metodo}]")
        for ln in self.linhas:
            if not ln.texto:
                continue
            minuto = int(ln.tempo // 60)
            segundo = ln.tempo - minuto * 60
            partes.append(f"[{minuto:02d}:{segundo:05.2f}]{ln.texto}")
        return "\n".join(partes) + "\n"

    def para_srt(self) -> str:
        blocos = []
        for i, ln in enumerate(self.linhas, start=1):
            if not ln.texto:
                continue
            fim = ln.fim or (ln.tempo + 3.0)
            blocos.append(
                f"{i}\n{_srt_tempo(ln.tempo)} --> {_srt_tempo(max(fim, ln.tempo + 0.2))}\n{ln.texto}\n"
            )
        return "\n".join(blocos)

    def para_txt(self) -> str:
        return self.texto_completo() + "\n"

    def escrever(self, pasta: Path, base: str = "letra") -> dict[str, Path]:
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        alvos = {
            "lrc": pasta / f"{base}.lrc",
            "srt": pasta / f"{base}.srt",
            "txt": pasta / f"{base}.txt",
            "json": pasta / f"{base}.json",
        }
        alvos["lrc"].write_text(self.para_lrc(), encoding="utf-8")
        alvos["srt"].write_text(self.para_srt(), encoding="utf-8")
        alvos["txt"].write_text(self.para_txt(), encoding="utf-8")
        alvos["json"].write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return alvos


# ------------------------------------------------------------------ parsers ---
def _segundos(minuto: str, segundo: str) -> float:
    return int(minuto) * 60 + float(str(segundo).replace(",", "."))


def _hms(horas: str, minutos: str, segundos: str, milesimos: str) -> float:
    """'00:00:01' + '000' -> 1.0. O `.srt` conta horas; o `.lrc` não."""
    return (
        int(horas) * 3600
        + int(minutos) * 60
        + int(segundos)
        + int(milesimos.ljust(3, "0")[:3]) / 1000.0
    )


def _srt_tempo(segundos: float) -> str:
    """Segundos -> 'HH:MM:SS,mmm' (o formato exigido pelo .srt)."""
    total = max(0.0, float(segundos or 0.0))
    horas = int(total // 3600)
    minutos = int((total % 3600) // 60)
    resto = total - horas * 3600 - minutos * 60
    return f"{horas:02d}:{minutos:02d}:{resto:06.3f}".replace(".", ",")


def ler_lrc(texto: str) -> Letra:
    """`.lrc` -> Letra com os tempos do arquivo (método `importada`)."""
    letra = Letra(metodo="importada")
    for linha_bruta in str(texto or "").splitlines():
        linha = linha_bruta.strip()
        if not linha:
            continue
        meta = _RE_LRC_META.match(linha)
        if meta:
            chave, valor = meta.group(1).lower(), meta.group(2).strip()
            if chave == "ti":
                letra.titulo = valor
            elif chave == "ar":
                letra.artista = valor
            continue
        casou = _RE_LRC.match(linha)
        if not casou:
            continue
        tempo = _segundos(casou.group(1), casou.group(2))
        conteudo = casou.group(3).strip()
        letra.linhas.append(LinhaLetra(tempo=tempo, texto=conteudo, confianca=1.0, metodo="importada"))
    _fechar_intervalos(letra)
    if not letra.linhas:
        raise LetraInvalida("nenhuma linha com tempo reconhecida neste .lrc")
    return letra


def ler_srt(texto: str) -> Letra:
    """`.srt` -> Letra (usa o início de cada bloco como tempo da linha)."""
    letra = Letra(metodo="importada")
    bruto = str(texto or "").replace("\r\n", "\n").strip()
    blocos = re.split(r"\n{2,}", bruto)
    for bloco in blocos:
        linhas = [ln for ln in bloco.split("\n") if ln.strip()]
        if not linhas:
            continue
        indice_tempo = next((i for i, ln in enumerate(linhas) if _RE_SRT_TEMPO.search(ln)), None)
        if indice_tempo is None:
            continue
        casou = _RE_SRT_TEMPO.search(linhas[indice_tempo])
        inicio = _hms(casou.group(1), casou.group(2), casou.group(3), casou.group(4))
        fim = _hms(casou.group(5), casou.group(6), casou.group(7), casou.group(8))
        conteudo = " ".join(ln.strip() for ln in linhas[indice_tempo + 1 :]).strip()
        if not conteudo:
            continue
        letra.linhas.append(
            LinhaLetra(tempo=inicio, texto=conteudo, fim=fim, confianca=1.0, metodo="importada")
        )
    if not letra.linhas:
        raise LetraInvalida("nenhum bloco com tempo reconhecido neste .srt")
    return letra


def ler_texto(texto: str) -> Letra:
    """Texto puro: uma linha de letra por linha de arquivo, sem tempo."""
    letra = Letra(metodo="")
    for bruta in str(texto or "").splitlines():
        linha = bruta.strip()
        if not linha or linha.startswith("#"):
            continue
        letra.linhas.append(LinhaLetra(tempo=0.0, texto=linha, confianca=0.0, metodo=""))
    if not letra.linhas:
        raise LetraInvalida("o texto está vazio")
    return letra


def detectar_formato(texto: str, nome_arquivo: str = "") -> str:
    """'lrc' | 'srt' | 'txt' — decide pelo conteúdo, não pela extensão só."""
    sufixo = Path(nome_arquivo).suffix.lower()
    if sufixo == ".lrc" or re.search(r"^\[\d{1,2}:\d{2}", str(texto or ""), re.MULTILINE):
        return "lrc"
    if sufixo in (".srt", ".vtt") or "-->" in str(texto or ""):
        return "srt"
    return "txt"


def ler_arquivo(caminho: Path) -> Letra:
    """Lê `.lrc`, `.srt` ou `.txt` do disco."""
    caminho = Path(caminho)
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    formato = detectar_formato(texto, caminho.name)
    if formato == "lrc":
        return ler_lrc(texto)
    if formato == "srt":
        return ler_srt(texto)
    return ler_texto(texto)


def _fechar_intervalos(letra: Letra) -> None:
    """Preenche `fim` de cada linha com o início da próxima."""
    for i, ln in enumerate(letra.linhas):
        if ln.fim and ln.fim > ln.tempo:
            continue
        proxima = letra.linhas[i + 1].tempo if i + 1 < len(letra.linhas) else 0.0
        ln.fim = proxima if proxima > ln.tempo else ln.tempo + 3.0


# -------------------------------------------------------------- transcrição ---
def motor_disponivel() -> tuple[str, str] | None:
    """(módulo, licença) do primeiro transcritor instalado, ou None."""
    import importlib.util

    for modulo, _instrucao, licenca in MOTORES:
        if importlib.util.find_spec(modulo) is not None:
            return modulo, licenca
    return None


def manual() -> str:
    """Texto para o usuário instalar um transcritor — mostrado na tela."""
    linhas = ["Nenhum motor de transcrição instalado. Para transcrever a letra do áudio:"]
    for modulo, instrucao, licenca in MOTORES:
        linhas.append(f"  {instrucao}   ({modulo}, licença {licenca})")
    linhas.append("")
    linhas.append("Sem motor de transcrição você ainda pode: colar a letra, importar .lrc/.srt")
    linhas.append("e alinhar ao áudio (o alinhamento por energia é estimado e diz isso).")
    return "\n".join(linhas)


def transcrever(
    audio: Path,
    idioma: str = "pt",
    modelo: str = "",
    progresso=None,
) -> Letra:
    """Transcreve a voz do arquivo e devolve a letra com os tempos do motor.

    Levanta `MotorIndisponivel` quando nenhum transcritor está instalado —
    nunca devolve letra inventada.
    """
    escolhido = motor_disponivel()
    if escolhido is None:
        raise MotorIndisponivel(manual())
    modulo, licenca = escolhido
    if progresso:
        progresso(f"transcrevendo com {modulo} (licença {licenca})…")
    if modulo == "faster_whisper":
        return _transcrever_faster_whisper(Path(audio), idioma, modelo)
    if modulo == "whisper":
        return _transcrever_whisper(Path(audio), idioma, modelo)
    return _transcrever_vosk(Path(audio), idioma, modelo)


def _transcrever_faster_whisper(audio: Path, idioma: str, modelo: str) -> Letra:
    from faster_whisper import WhisperModel  # type: ignore[import-not-found]

    nome = modelo or "small"
    motor = WhisperModel(nome, device="auto", compute_type="int8")
    segmentos, info = motor.transcribe(str(audio), language=idioma or None, vad_filter=True)
    letra = Letra(metodo="motor")
    for seg in segmentos:
        texto = str(getattr(seg, "text", "") or "").strip()
        if not texto:
            continue
        letra.linhas.append(
            LinhaLetra(
                tempo=float(seg.start),
                fim=float(seg.end),
                texto=texto,
                # o faster-whisper expõe a probabilidade média do segmento; se
                # não expuser, a confiança fica 0 e o aviso diz que é aproximada
                confianca=float(getattr(seg, "avg_logprob", 0.0) and min(1.0, max(0.0, 1.0 + getattr(seg, "avg_logprob", -1.0) / 2))),
                metodo="motor",
            )
        )
    letra.avisos.append(f"transcrito por faster-whisper ({nome}); confira nomes e palavras raras")
    if info and getattr(info, "language", ""):
        letra.avisos.append(f"idioma detectado: {info.language}")
    return letra


def _transcrever_whisper(audio: Path, idioma: str, modelo: str) -> Letra:
    import whisper  # type: ignore[import-not-found]

    motor = whisper.load_model(modelo or "small")
    resultado = motor.transcribe(str(audio), language=idioma or None)
    letra = Letra(metodo="motor")
    for seg in resultado.get("segments", []):
        texto = str(seg.get("text") or "").strip()
        if not texto:
            continue
        letra.linhas.append(
            LinhaLetra(
                tempo=float(seg.get("start", 0.0)),
                fim=float(seg.get("end", 0.0)),
                texto=texto,
                confianca=float(seg.get("avg_logprob") and 0.7 or 0.0),
                metodo="motor",
            )
        )
    letra.avisos.append("transcrito por openai-whisper; confira nomes e palavras raras")
    return letra


def _transcrever_vosk(audio: Path, idioma: str, modelo: str) -> Letra:
    import json as _json
    import subprocess
    import sys

    from vosk import KaldiRecognizer, Model  # type: ignore[import-not-found]

    pasta_modelo = modelo or ""
    if not pasta_modelo or not Path(pasta_modelo).is_dir():
        raise MotorIndisponivel(
            "vosk precisa do caminho do modelo em português. Baixe em "
            "https://alphacephei.com/vosk/models e informe a pasta em `modelo`."
        )
    # o vosk lê PCM 16 kHz mono; converter aqui com o próprio Python evita
    # exigir ffmpeg só para transcrever
    from . import dsp, media

    audio_data, taxa = media.load_audio(Path(audio), 16000)
    mono = dsp.to_mono(audio_data)
    pcm = (mono * 32767).astype("int16").tobytes()
    modelo_kaldi = Model(str(pasta_modelo))
    reconhecedor = KaldiRecognizer(modelo_kaldi, taxa)
    reconhecedor.SetWords(True)
    letra = Letra(metodo="motor")
    passo = taxa * 2  # 1 s de PCM 16-bit mono
    for inicio in range(0, len(pcm), passo):
        pedaco = pcm[inicio : inicio + passo]
        if reconhecedor.AcceptWaveform(pedaco):
            dados = _json.loads(reconhecedor.Result() or "{}")
            texto = str(dados.get("text") or "").strip()
            if not texto:
                continue
            palavras = dados.get("result") or []
            t0 = float(palavras[0]["start"]) if palavras else inicio / passo
            t1 = float(palavras[-1]["end"]) if palavras else t0 + 1.0
            letra.linhas.append(LinhaLetra(tempo=t0, fim=t1, texto=texto, confianca=0.6, metodo="motor"))
    dados = _json.loads(reconhecedor.FinalResult() or "{}")
    texto = str(dados.get("text") or "").strip()
    if texto:
        letra.linhas.append(LinhaLetra(tempo=letra.linhas[-1].fim if letra.linhas else 0.0, texto=texto, confianca=0.6, metodo="motor"))
    letra.avisos.append("transcrito por vosk (modelo local); a pontuação não vem do vosk")
    _ = subprocess, sys  # imports usados só em versões anteriores do caminho
    return letra


# ---------------------------------------------------------------- alinhamento ---
def trechos_cantados(audio, sample_rate: int, janela: float = 0.05) -> list[tuple[float, float]]:
    """Onde há voz: [(início, fim)] medidos pela energia do sinal.

    Trabalha com o envelope RMS em janelas curtas, sem depender de numpy para
    o caso pequeno. O limiar é relativo ao próprio material (percentil 70),
    então música baixa e música alta concordam sobre "aqui tem voz".
    """
    import numpy as np

    sinal = np.asarray(audio, dtype=np.float32)
    if sinal.ndim > 1:
        sinal = sinal.mean(axis=1)
    if sinal.size == 0:
        return []
    passo = max(1, int(janela * sample_rate))
    quadros = sinal.size // passo
    if quadros < 2:
        return [(0.0, sinal.size / sample_rate)]
    energia = np.sqrt(
        np.mean(np.reshape(sinal[: quadros * passo], (quadros, passo)) ** 2, axis=1)
    )
    pico = float(np.percentile(energia, 95)) or float(energia.max()) or 1.0
    limiar = max(pico * PISO_ENERGIA, float(np.percentile(energia, 70)) * 0.6)
    ativo = energia >= limiar
    trechos: list[tuple[float, float]] = []
    inicio = None
    for i, dentro in enumerate(ativo):
        if dentro and inicio is None:
            inicio = i
        elif not dentro and inicio is not None:
            trechos.append((inicio * janela, i * janela))
            inicio = None
    if inicio is not None:
        trechos.append((inicio * janela, quadros * janela))
    # trechos de menos de 120 ms são sopro/ruído, não linha cantada
    return [(a, b) for a, b in trechos if b - a >= 0.12]


def _silabas(texto: str) -> int:
    """Estimativa de sílabas em português: grupos de vogais, com dígrafos."""
    palavra = re.sub(r"[^\wáàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ]", "", str(texto or "").lower())
    if not palavra:
        return 0
    grupos = re.findall(r"[aeiouáàâãéêíóôõúü]+", palavra)
    return max(1, len(grupos))


def alinhar(
    letra: Letra,
    audio,
    sample_rate: int,
    duracao: float = 0.0,
    mapa=None,
) -> Letra:
    """Dá tempo às linhas de letra a partir da voz medida no áudio.

    Entrada esperada: letra sem tempo (texto colado) ou com tempo parcial.
    Se todas as linhas já têm tempo (`.lrc`/`.srt`), devolve como está — não
    "melhora" um dado que já veio certo.

    O método: mede os trechos cantados, distribui as linhas na ordem,
    ponderando pelo número de sílabas. Quando a contagem de linhas e de
    trechos bate, cada linha ganha o seu trecho (confiança alta). Quando não
    bate, o tempo é proporcional às sílabas dentro do total cantado
    (confiança menor, e o aviso diz isso).
    """
    linhas = [ln for ln in letra.linhas if ln.texto]
    if not linhas:
        raise LetraInvalida("não há linhas de letra para alinhar")
    ja_temporizada = all(ln.tempo > 0 for ln in linhas)
    if ja_temporizada:
        letra.avisos.append("a letra já veio com tempo (importada): o alinhamento foi preservado")
        _fechar_intervalos(letra)
        return letra

    trechos = trechos_cantados(audio, sample_rate)
    total = float(duracao or (len(audio) / sample_rate if hasattr(audio, "__len__") else 0.0))
    if not trechos:
        # sem voz destacada: distribui no tempo total, e diz que é fraco
        if total <= 0:
            raise LetraInvalida("não foi possível medir a duração do áudio")
        trechos = [(0.0, total)]
        letra.avisos.append(
            "não foi possível destacar trechos de voz neste áudio (material instrumental?) — "
            "as linhas foram distribuídas no tempo total, sem precisão"
        )
        confianca_base = 0.15
    else:
        confianca_base = 0.75

    silabas = [_silabas(ln.texto) for ln in linhas]
    soma_silabas = sum(silabas) or len(linhas)
    casamento = len(trechos) == len(linhas)

    if casamento:
        for ln, (a, b) in zip(linhas, trechos):
            ln.tempo = round(a, 3)
            ln.fim = round(b, 3)
            ln.confianca = 0.85
            ln.metodo = "energia"
        letra.avisos.append(
            f"{len(linhas)} linhas encaixadas em {len(trechos)} trechos de voz medidos no áudio"
        )
    else:
        # Tempo "cantado" x tempo real: as pausas instrumentais não contam.
        # Cada linha recebe uma fatia do total cantado proporcional às suas
        # sílabas e a fatia é levada de volta para o tempo real pulando as
        # pausas — assim nenhuma linha cai depois do fim da música (era o
        # defeito da primeira versão, que empurrava a última linha para o
        # silêncio final).
        acumulado: list[tuple[float, float, float, float]] = []
        cursor = 0.0
        for a, b in trechos:
            acumulado.append((cursor, cursor + (b - a), a, b))
            cursor += b - a
        total_cantado = max(1e-6, cursor)

        def real_do_cantado(x: float) -> tuple[float, float]:
            x = max(0.0, min(total_cantado, x))
            for inicio_c, fim_c, inicio_r, fim_r in acumulado:
                if x <= fim_c + 1e-9:
                    return inicio_r + (x - inicio_c), fim_r
            ultimo = acumulado[-1]
            return ultimo[3], ultimo[3]

        posicao = 0.0
        for i, ln in enumerate(linhas):
            fatia = total_cantado * (silabas[i] or 1) / max(1, soma_silabas)
            inicio_real, _ = real_do_cantado(posicao)
            fim_real, _ = real_do_cantado(posicao + fatia)
            ln.tempo = round(inicio_real, 3)
            ln.fim = round(max(inicio_real + SEPARACAO_MINIMA, fim_real), 3)
            ln.confianca = 0.45
            ln.metodo = "energia"
            posicao += fatia
        letra.avisos.append(
            f"alinhamento aproximado: {len(linhas)} linhas para {len(trechos)} trechos de voz — "
            "confira os tempos e ajuste os que estiverem fora"
        )
        confianca_base = 0.45

    # encaixe na régua: se há mapa de tempo, arredondar para a batida mais
    # próxima deixa a letra coerente com o clique e com a cifra
    if mapa is not None and getattr(mapa, "preciso", False):
        for ln in letra.linhas:
            if ln.metodo != "energia":
                continue
            indice = mapa.indice_de_tempo(ln.tempo)
            arredondado = round(indice * 2) / 2  # meia semínima
            ln.tempo = round(mapa.tempo_de_indice(arredondado), 3)

    letra.metodo = "energia"
    parenteses = f" (confiança média {confianca_base:.2f})"
    letra.avisos.append(
        "tempos marcados como 'energia': vieram da energia da voz, não de um transcritor" + parenteses
    )
    _fechar_intervalos(letra)
    return letra


def salvar(letra: Letra, apoio: Path, base: str = "letra") -> Path:
    """Grava `letra.json` na pasta de apoio (fonte da verdade para reabrir)."""
    apoio = Path(apoio)
    apoio.mkdir(parents=True, exist_ok=True)
    alvo = apoio / f"{base}.json"
    alvo.write_text(json.dumps(letra.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return alvo


def carregar(apoio: Path, base: str = "letra") -> Letra | None:
    """Letra salva na pasta de apoio, se existir."""
    alvo = Path(apoio) / f"{base}.json"
    if not alvo.is_file():
        return None
    try:
        return Letra.de_dict(json.loads(alvo.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None
