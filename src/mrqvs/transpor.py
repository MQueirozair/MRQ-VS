"""Transposição de tom: muda a altura sem mudar o andamento.

Por que existe: o usuário muda o tom na cifra e quer **ouvir** naquele tom.
Até aqui o programa só transpõe os acordes na tela — o áudio continuava no
tom gravado, e ensaiar no tom da cifra era impossível.

Três níveis, do melhor para o mais simples, escolhidos pelo que o ffmpeg
instalado realmente tem:

1. ``rubberband`` — mantém a duração e preserva transientes (ideal para
   bateria e baixo).
2. ``atempo`` + ``asetrate`` — o par clássico: ``asetrate`` sobe a altura (e
   acelera), ``atempo`` devolve a duração. Não usa biblioteca externa e o
   resultado é honesto, mas em mudanças grandes aparece o artefato de
   "flange" nas faixas com harmônicos ricos (voz, prato).
3. Recusa explícita — se nem 2 está disponível, a função levanta erro em vez
   de entregar um arquivo que mente sobre o que fez.

O que NUNCA acontece aqui: sobrescrever o arquivo do usuário. Tudo é escrito
num diretório novo (``-tom+N``/``-tom-N``) ao lado dos originais.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import media

#: Nome do filtro do Rubber Band no ffmpeg (builds completos trazem).
FILTRO_RUBBERBAND = "rubberband"

#: Quantos semitons aceitamos. Além disso o artefato domina e o resultado
#: deixa de ser útil para ensaio — melhor recusar do que entregar lixo.
SEMITONS_MAX = 12


class TransposicaoIndisponivel(RuntimeError):
    """O ffmpeg instalado não sabe transpor (ou falta ffmpeg)."""


def _filtros_do_ffmpeg(ffmpeg: str) -> str:
    """Lista de filtros do build. String vazia quando não dá para saber."""
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


def metodo_disponivel(ffmpeg: str | None = None) -> str:
    """Qual método este ffmpeg consegue usar: ``rubberband``, ``atempo`` ou ``""``."""
    ffmpeg = ffmpeg or media.find_tool("ffmpeg")
    if not ffmpeg:
        return ""
    filtros = _filtros_do_ffmpeg(ffmpeg)
    if not filtros:
        # Não deu para listar (build exótico): o atempo existe desde 2011 e é
        # a aposta segura; rubberband só quando confirmado.
        return "atempo"
    if f" {FILTRO_RUBBERBAND} " in f" {filtros} ":
        return "rubberband"
    if " atempo " in f" {filtros} ":
        return "atempo"
    return ""


def _filtro(semitons: int, metodo: str) -> str:
    """Cadeia de filtros que muda a altura em `semitons` mantendo a duração."""
    fator_tom = 2.0 ** (semitons / 12.0)
    if metodo == "rubberband":
        # pitch em semitons (razão de frequência), tempo intocado
        return f"rubberband=pitch={fator_tom:.6f}"
    # asetrate muda a taxa de leitura (altura E velocidade); atempo compensa a
    # velocidade. O atempo aceita 0.5..2.0 por instância — fora disso, encadeia.
    fator_tempo = 1.0 / fator_tom
    partes = [f"asetrate=44100*{fator_tom:.6f}", "aresample=44100"]
    restante = fator_tempo
    while restante < 0.5 or restante > 2.0:
        passo = 2.0 if restante > 2.0 else 0.5
        partes.append(f"atempo={passo}")
        restante /= passo
    partes.append(f"atempo={restante:.6f}")
    return ",".join(partes)


def transpor_arquivo(
    origem: Path,
    destino: Path,
    semitons: int,
    *,
    ffmpeg: str | None = None,
    metodo: str | None = None,
) -> dict:
    """Grava `origem` em `destino` com a altura mudada em `semitons`.

    Devolve ``{"arquivo", "semitons", "metodo", "duracao"}``. A duração é lida
    do arquivo gerado para que o chamador possa conferir a promessa de "mesma
    duração" em vez de confiar nela.
    """
    origem = Path(origem)
    destino = Path(destino)
    # validar o pedido ANTES de olhar o arquivo: pedir 0 semitom é erro de
    # quem chamou, e a mensagem tem de falar disso, não de arquivo faltando
    semitons = int(semitons)
    if semitons == 0:
        raise ValueError("zero semitons não muda nada")
    if abs(semitons) > SEMITONS_MAX:
        raise ValueError(f"máximo de {SEMITONS_MAX} semitons por transposição")
    if not origem.is_file():
        raise FileNotFoundError(f"arquivo não encontrado: {origem}")

    ffmpeg = ffmpeg or media.find_tool("ffmpeg")
    if not ffmpeg:
        raise TransposicaoIndisponivel(
            "transpor o áudio precisa do ffmpeg (no pacote portátil ele já vem)"
        )
    metodo = metodo or metodo_disponivel(ffmpeg)
    if metodo not in ("rubberband", "atempo"):
        raise TransposicaoIndisponivel(
            "o ffmpeg instalado não tem o filtro de mudança de tom (atempo)"
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(origem),
        "-filter:a",
        _filtro(semitons, metodo),
        "-c:a",
        "pcm_s16le",
        str(destino),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not destino.is_file():
        raise TransposicaoIndisponivel(
            "o ffmpeg falhou ao transpor:\n" + (proc.stderr.strip()[-800:] or "(sem mensagem)")
        )
    return {
        "arquivo": str(destino),
        "semitons": semitons,
        "metodo": metodo,
        "duracao": duracao_do_wav(destino),
    }


def duracao_do_wav(caminho: Path) -> float:
    """Duração em segundos (0.0 quando não dá para ler)."""
    try:
        import soundfile as sf

        info = sf.info(str(caminho))
        return round(float(info.frames) / float(info.samplerate or 1), 3)
    except Exception:  # noqa: BLE001 - duração é informativa, não crítica
        return 0.0


def pasta_do_tom(pasta: Path, semitons: int) -> Path:
    """Diretório de cada transposição, ao lado dos stems originais."""
    sinal = "+" if semitons > 0 else "-"
    return Path(pasta).with_name(f"{Path(pasta).name}-tom{sinal}{abs(int(semitons))}")


def transpor_pasta(
    pasta: Path,
    semitons: int,
    *,
    ffmpeg: str | None = None,
    progresso=None,
) -> dict:
    """Transpõe todos os WAV de `pasta` para uma pasta nova ao lado.

    Os originais não são tocados. Arquivos que não decodificam são copiados
    como estão (um clique.wav que o ffmpeg não abriu não pode sumir do
    projeto) e o resumo diz quantos foram copiados sem transpor.
    """
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise FileNotFoundError(f"pasta não encontrada: {pasta}")
    destino = pasta_do_tom(pasta, semitons)
    destino.mkdir(parents=True, exist_ok=True)

    arquivos = sorted(p for p in pasta.iterdir() if p.is_file() and p.suffix.lower() == ".wav")
    if not arquivos:
        raise ValueError("nenhum WAV para transpor nessa pasta")

    feitos: list[str] = []
    copiados: list[str] = []
    for i, arq in enumerate(arquivos):
        alvo = destino / arq.name
        try:
            transpor_arquivo(arq, alvo, semitons, ffmpeg=ffmpeg)
            feitos.append(arq.name)
        except (TransposicaoIndisponivel, ValueError, OSError):
            shutil.copy2(arq, alvo)
            copiados.append(arq.name)
        if progresso:
            progresso(i + 1, len(arquivos), arq.name)

    return {
        "pasta": str(destino),
        "semitons": int(semitons),
        "transpostos": feitos,
        "copiados": copiados,
    }
