"""Recepção de arquivos enviados pelo navegador e conversão para áudio.

Por que existe: até a 0.1.13 só entrava link do YouTube ou caminho digitado à
mão. Quem tem o arquivo no PC — o caso mais comum de quem trabalha com
playback — precisava mover o arquivo para dentro da pasta e digitar o caminho.

A referência é a tela de upload do CueWee Studio (studio.cuewee.app/upload):
arrastar o arquivo para a caixa, ver o formato e o tempo aceitos, e mandar.

Três decisões que valem explicar:

* **Upload em fatias com progresso.** Um vídeo de 150 MB numa requisição só
  não mostra nada até terminar, e o usuário acha que travou. Aqui o navegador
  manda pedaços de 2 MB e cada resposta é uma linha de progresso.
* **Vídeo é convertido, não recusado.** O CueWee aceita MP3/WAV/FLAC/OGG e
  limite de 15 min. Aqui aceitamos também MP4/MOV/MKV e extraímos o áudio com
  o ffmpeg que já está embarcado — "converte vídeo em MP3 e separa as faixas"
  era o pedido, e é o que o ffmpeg já permite sem dependência nova.
* **Limite honesto e explícito.** 300 MB e 60 min, verificados no servidor e
  não só no navegador. Recusar depois de 10 minutos de upload seria cruel.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from . import media

#: Extensões de áudio que seguem direto para a separação.
AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif", ".wma"}
#: Extensões de vídeo: o áudio é extraído com ffmpeg antes de separar.
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".flv"}

#: Limite por arquivo. O CueWee usa 150 MB; aqui é maior porque vídeo de
#: playback de igreja costuma passar disso, e o custo é só disco.
LIMITE_BYTES = 300 * 1024 * 1024
#: Duração máxima depois de decodificar (evita 2 h de processamento).
LIMITE_SEGUNDOS = 60 * 60

_EXTENSOES = AUDIO_EXT | VIDEO_EXT


class UploadError(RuntimeError):
    """Falha no envio, com mensagem que o usuário consegue usar."""


def _pasta() -> Path:
    """Onde os envios ficam. Uma pasta só, limpa por `limpar()`."""
    from . import runtime

    base = Path(runtime.home()) if hasattr(runtime, "home") else None
    if base is None:  # pragma: no cover - runtime sempre tem home()
        base = Path.cwd()
    pasta = base / "envios"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def identificar(nome: str) -> str:
    """`'audio'` ou `'video'` a partir do nome do arquivo.

    Serve para a tela avisar antes de enviar: "isto é vídeo, o áudio será
    extraído". Descobrir só depois de 200 MB enviados seria tarde.
    """
    ext = Path(nome).suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return "desconhecido"


def aceita(nome: str) -> bool:
    return Path(nome).suffix.lower() in _EXTENSOES


def nome_seguro(nome: str) -> str:
    """Mantém só o nome do arquivo, sem caminho e sem surpresa.

    `../../etc/passwd` e `C:\\Windows\\system.ini` viram apenas `passwd` e
    `system.ini`. O navegador não manda caminho, mas o servidor não confia.
    """
    nome = (nome or "").replace("\\", "/").split("/")[-1].strip()
    nome = re.sub(r"[\x00-\x1f<>:\"|?*]", "", nome)
    if nome in ("", ".", ".."):
        nome = "audio"
    return nome[:180]


def _validar_id(ident: str) -> str:
    ident = (ident or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", ident):
        raise UploadError("identificador de envio inválido")
    return ident


def novo_envio(nome: str, tamanho: int = 0) -> dict:
    """Cria o registro de um envio e devolve `{id, nome, tipo, destino}`.

    O id é um uuid4 curto: serve de nome de pasta e não colide entre dois
    envios simultâneos. O nome original é preservado no registro para o
    programa usar como título da pasta de saída.
    """
    if not aceita(nome):
        extensoes = ", ".join(sorted(e.lstrip(".").upper() for e in _EXTENSOES))
        raise UploadError(
            f"formato não aceito: {Path(nome).suffix or '(sem extensão)'}.\n"
            f"Formatos que funcionam: {extensoes}."
        )
    if tamanho and int(tamanho) > LIMITE_BYTES:
        raise UploadError(
            f"o arquivo tem {int(tamanho) / 1e6:.0f} MB; o limite é "
            f"{LIMITE_BYTES / 1e6:.0f} MB."
        )
    ident = uuid.uuid4().hex[:12]
    destino = _pasta() / ident
    destino.mkdir(parents=True, exist_ok=True)
    seguro = nome_seguro(nome)
    return {
        "id": ident,
        "nome": seguro,
        "tipo": identificar(seguro),
        "destino": destino / seguro,
        "pasta": destino,
    }


def _registro(pasta: Path) -> Path:
    return pasta / "envio.json"


def gravar_registro(pasta: Path, dados: dict) -> None:
    _registro(pasta).write_text(
        json.dumps(dados, ensure_ascii=False), encoding="utf-8"
    )


def ler_registro(ident: str) -> dict:
    ident = _validar_id(ident)
    pasta = _pasta() / ident
    arq = _registro(pasta)
    if not arq.is_file():
        raise UploadError("envio não encontrado (a pasta foi apagada?)")
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise UploadError("o registro deste envio está corrompido") from None


def duracao(caminho: Path) -> float:
    """Duração em segundos, lida do ffprobe ou decodificando.

    Usada antes de separar: um arquivo de 50 min é recusado com aviso, não
    depois de 20 minutos de processamento.
    """
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        for pasta in media._pastas_locais():  # noqa: SLF001 - mesma família
            for alvo in ("ffprobe.exe", "ffprobe"):
                if (pasta / alvo).is_file():
                    ffprobe = str(pasta / alvo)
                    break
            if ffprobe:
                break
    if ffprobe:
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(caminho)],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0:
                return float((proc.stdout or "0").strip() or 0)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    # sem ffprobe: decodifica e mede (mais lento, mas não mente)
    try:
        amostras, taxa = media.load_audio(caminho, 44100)
        return amostras.shape[0] / taxa
    except Exception:  # noqa: BLE001 - a checagem é melhor-esforço
        return 0.0


def video_para_audio(caminho: Path, destino: Path | None = None) -> Path:
    """Extrai o áudio de um vídeo para WAV (o que o separador entende).

    É o "converter vídeo em MP3 e separar as faixas" pedido, com uma escolha
    técnica: a extração é para **WAV PCM**, não MP3. O separador precisa
    decodificar o áudio de novo, e passar por MP3 aqui introduziria perda
    justo na entrada da IA. O MP3 continua disponível na saída, escolhido na
    tela — o arquivo final sai em MP3 se você quiser.
    """
    ffmpeg = media.find_tool("ffmpeg")
    if not ffmpeg:
        raise UploadError(
            "o ffmpeg não foi encontrado, então não consigo tirar o áudio do "
            "vídeo.\nNo pacote portátil do Windows ele já vem embutido; se a "
            "pasta foi apagada, baixe em ffmpeg.org."
        )
    destino = destino or caminho.with_suffix(".wav")
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(caminho),
        "-vn",                    # sem vídeo
        "-acodec", "pcm_s16le",   # PCM: sem perda na entrada da IA
        "-ar", "44100",
        "-ac", "2",
        str(destino),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not destino.is_file() or destino.stat().st_size == 0:
        ultima = ((proc.stderr or "").strip().splitlines() or ["(sem detalhes)"])[-1]
        raise UploadError(f"não consegui extrair o áudio do vídeo: {ultima}")
    return destino


def preparar(ident: str) -> dict:
    """Valida o envio e devolve o caminho de áudio pronto para separar.

    Devolve `{audio, titulo, tipo, duracao}`. Se for vídeo, converte e mantém
    o vídeo original (o usuário pode querer o MP4 depois); o WAV extraído
    fica ao lado.
    """
    dados = ler_registro(ident)
    pasta = _pasta() / ident
    original = pasta / dados.get("nome", "")
    if not original.is_file():
        raise UploadError(
            "o arquivo deste envio não está mais na pasta — envie de novo."
        )

    tamanho = original.stat().st_size
    if tamanho > LIMITE_BYTES:
        raise UploadError(
            f"o arquivo tem {tamanho / 1e6:.0f} MB; o limite é "
            f"{LIMITE_BYTES / 1e6:.0f} MB."
        )

    tipo = identificar(original.name)
    if tipo == "video":
        audio = video_para_audio(original, pasta / (original.stem + ".wav"))
    elif tipo == "audio":
        audio = original
    else:
        raise UploadError(f"não sei o que fazer com '{original.suffix}'.")

    segundos = duracao(audio)
    if segundos > LIMITE_SEGUNDOS:
        raise UploadError(
            f"o áudio tem {segundos / 60:.0f} minutos; o limite é "
            f"{LIMITE_SEGUNDOS // 60} minutos."
        )

    return {
        "audio": audio,
        "titulo": dados.get("titulo") or original.stem,
        "tipo": tipo,
        "duracao": round(segundos, 2),
        "pasta": pasta,
    }


def limpar(ident: str) -> None:
    """Apaga os arquivos de um envio (chamado quando o trabalho termina)."""
    ident = _validar_id(ident)
    shutil.rmtree(_pasta() / ident, ignore_errors=True)


def receber_fatia(ident: str, inicio: int, dados: bytes) -> int:
    """Grava um pedaço do arquivo na posição `inicio`. Devolve o total.

    Escrita posicional (não append) para um reenvio da mesma fatia não
    duplicar bytes — rede instável reenvia, e o arquivo tem de continuar
    correto.
    """
    if inicio < 0:
        raise UploadError("posição inicial da fatia inválida.")
    if inicio + len(dados) > LIMITE_BYTES:
        raise UploadError(
            f"o arquivo passou do limite de {LIMITE_BYTES / 1e6:.0f} MB."
        )
    dados_reg = ler_registro(ident)
    pasta = _pasta() / _validar_id(ident)
    destino = pasta / dados_reg["nome"]
    with destino.open("r+b" if destino.exists() else "wb") as fh:
        fh.seek(inicio)
        fh.write(dados)
    total = destino.stat().st_size
    if total > LIMITE_BYTES:
        destino.unlink(missing_ok=True)
        raise UploadError(
            f"o arquivo passou do limite de {LIMITE_BYTES / 1e6:.0f} MB."
        )
    return total
