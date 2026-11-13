"""Entrada de mídia: YouTube (yt-dlp), arquivo local e decodificação (ffmpeg).

Duas filosofias aqui:

* **yt-dlp é opcional**. Se não estiver instalado, o programa continua
  aceitando arquivo local. Se estiver, funciona para qualquer site que o
  yt-dlp suporte (YouTube, SoundCloud, Vimeo...), não só YouTube.
* **ffmpeg é o cano universal**. Para MP3/MP4 e para decodificar formatos que
  o libsndfile não lê (m4a/aac/webm), delegamos ao ffmpeg. Quando ele falta,
  dizemos exatamente o que instalar em vez de estourar um `FileNotFoundError`
  no meio do pipeline.

Ambos são procurados em três lugares, nesta ordem: PATH do sistema, diretório
do programa (`tools/`, `lib/`, ao lado do python.exe) e, por fim, o pacote
`imageio_ffmpeg` se estiver instalado. Essa busca extra é o que faz o pacote
portátil do Windows funcionar **sem instalar nada**: o ffmpeg e o yt-dlp vão
embutidos em `lib/`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import dsp, runtime


class MediaError(RuntimeError):
    """Falha de download/decodificação, com instrução de correção."""


class FFmpegMissing(MediaError):
    """ffmpeg não está no PATH — erro de dependência, não de mídia."""


@dataclass
class MediaInfo:
    title: str
    channel: str = ""
    duration: float = 0.0
    video_id: str = ""
    webpage_url: str = ""
    upload_date: str = ""
    #: caminho do áudio extraído (WAV 44.1 kHz, sempre)
    audio_path: Path | None = None
    extra: dict = field(default_factory=dict)
    #: título antes de qualquer substituição por --title
    original_title: str = ""
    #: URL da capa (thumbnail) do vídeo, quando a fonte é um link
    thumbnail: str = ""

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "channel": self.channel,
            "duration": self.duration,
            "video_id": self.video_id,
            "webpage_url": self.webpage_url,
            "upload_date": self.upload_date,
            "thumbnail": self.thumbnail,
            "audio": str(self.audio_path) if self.audio_path else None,
        }


def _pastas_locais() -> list[Path]:
    """Onde procurar ferramentas embutidas no pacote.

    `tools/` é o lugar previsto; `lib/` e a pasta do interpretador entram
    porque é onde o pacote portátil do Windows coloca as coisas. O sys.path
    também entra, o que cobre o caso de o programa estar dentro de um zipapp.
    """
    pastas: list[Path] = []
    for base in [Path(__file__).resolve().parent.parent.parent, *(Path(p) for p in sys.path if p)]:
        for nome in ("tools", "lib", ""):
            candidata = (base / nome) if nome else base
            if candidata.is_dir():
                pastas.append(candidata)
    if sys.executable:
        pastas.append(Path(sys.executable).resolve().parent)
    vistos: set[Path] = set()
    unicas: list[Path] = []
    for p in pastas:
        if p not in vistos:
            vistos.add(p)
            unicas.append(p)
    return unicas


def find_tool(nome: str, *nomes_alt: str) -> str | None:
    """Acha `ffmpeg`/`yt-dlp` no PATH ou embutido no pacote.

    A busca por padrão (`ffmpeg-*.exe`, do wheel `imageio-ffmpeg`) é a última
    etapa e vale **só** para ferramentas cujo nome é `ffmpeg`: ela já devolveu
    o `ffmpeg.exe` quando o pedido era `yt-dlp`, e o resultado foi o ffmpeg
    sendo chamado com `--dump-single-json` ("Unrecognized option").
    """
    eh_ffmpeg = nome.lower().startswith("ffmpeg")
    alvos = ["ffmpeg", "ffmpeg.exe"] if eh_ffmpeg else [nome, *nomes_alt]

    for alvo in alvos:
        achado = shutil.which(alvo)
        if achado:
            return achado

    # arquivos com nome exato nas pastas do pacote
    for alvo in alvos:
        for pasta in _pastas_locais():
            for alvo_arquivo in (alvo, f"{alvo}.exe"):
                candidato = pasta / alvo_arquivo
                if candidato.is_file():
                    return str(candidato)

    if eh_ffmpeg:
        # binário do imageio-ffmpeg: ffmpeg-win-x86_64-v9.0.2.exe
        for pasta in _pastas_locais():
            for padrao in ("ffmpeg-*.exe", "ffmpeg*"):
                for candidato in sorted(pasta.glob(padrao)):
                    if candidato.is_file() and candidato.stat().st_size > 1_000_000:
                        return str(candidato)
        try:  # último recurso: o próprio pacote imageio_ffmpeg
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001 - dependência opcional
            return None
    return None


def require_ffmpeg() -> str:
    path = find_tool("ffmpeg") or shutil.which("ffmpeg")
    if not path:
        raise FFmpegMissing(
            "ffmpeg não encontrado no PATH.\n"
            "  Windows:  winget install Gyan.FFmpeg   (ou baixe ffmpeg.org e adicione ao PATH)\n"
            "  macOS:    brew install ffmpeg\n"
            "  Linux:    sudo apt install ffmpeg\n"
            "Ele é necessário para MP3/MP4 e para ler m4a/webm do YouTube."
        )
    return path


def have_ffmpeg() -> bool:
    return find_tool("ffmpeg") is not None


def _tem_modulo_ytdlp() -> bool:
    """O módulo `yt_dlp` está importável? (é assim que vem no pacote portátil)"""
    import importlib.util

    try:
        return importlib.util.find_spec("yt_dlp") is not None
    except (ImportError, ValueError):
        return False


def ytdlp_command(*opcoes: str) -> list[str]:
    """Linha de comando completa do yt-dlp, já como **lista**.

    Devolver lista (e não string para dividir depois) evita duas armadilhas
    que custaram dois bugs no Windows:

    1. caminho com espaço (`C:\\Program Files\\...`) e aspas sobrepostas;
    2. ordem: com `python.exe -m yt_dlp`, qualquer opção inserida antes do
       `-m yt_dlp` é lida pelo **Python**, que responde
       "unknown option --extract-audio".
    """
    path = find_tool("yt-dlp") or shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if path:
        return [path, *opcoes]
    if _tem_modulo_ytdlp():
        # este mesmo interpretador (funciona no embeddable e dentro do zipapp,
        # porque `lib/` está no sys.path — ver app/run.py)
        return [sys.executable, "-m", "yt_dlp", *opcoes]
    cmd = runtime.module_command("yt_dlp", *opcoes)
    if cmd:
        try:
            probe = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if probe.returncode == 0:
                return cmd
        except (OSError, subprocess.SubprocessError):
            pass
    raise MediaError(
        "yt-dlp não encontrado.\n"
        "  Instale com:  python -m pip install -U yt-dlp\n"
        "  (ou baixe o yt-dlp.exe de github.com/yt-dlp/yt-dlp/releases)\n"
        "  No pacote portátil do Windows ele já vem em lib\\ (isso aqui só"
        " aparece se a pasta foi apagada)."
    )


def require_ytdlp() -> str:
    """Versão legível de `ytdlp_command()`, para mensagens de diagnóstico."""
    return " ".join(ytdlp_command())


def _ytdlp_cmd(*opcoes: str) -> list[str]:
    """Compatibilidade: mesmo que `ytdlp_command`."""
    return ytdlp_command(*opcoes)


def _env_ytdlp() -> dict:
    """Ambiente para o subprocesso do yt-dlp.

    `sys.path` do processo pai **não** é herdado pelo filho. Quando o yt-dlp
    vem como módulo embutido em `lib/`, o comando `python -m yt_dlp` falharia
    com "No module named yt_dlp" (aconteceu). Aqui a pasta que contém o
    pacote `yt_dlp` entra no PYTHONPATH do filho, e a pasta do ffmpeg entra
    no PATH para a conversão em WAV.
    """

    env = dict(os.environ)
    pastas: list[str] = []

    try:
        import importlib.util

        spec = importlib.util.find_spec("yt_dlp")
        if spec and spec.submodule_search_locations:
            pastas.append(str(Path(next(iter(spec.submodule_search_locations))).parent))
    except (ImportError, ValueError, StopIteration):
        pass

    if not pastas:  # não há módulo: procura a pasta lib/ ao lado do programa
        pastas = [str(p) for p in _pastas_locais()]

    existentes = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys([*pastas, *existentes]))

    ffmpeg_path = find_tool("ffmpeg")
    if ffmpeg_path:
        env["PATH"] = str(Path(ffmpeg_path).parent) + os.pathsep + env.get("PATH", "")
    return env


def _explicar_erro_ytdlp(saida: str) -> str:
    """Traduz os erros mais comuns do yt-dlp em instrução de ação.

    O texto cru do yt-dlp vai junto no final — nunca escondemos a mensagem
    original —, mas o usuário precisa saber o que *fazer*.
    """
    texto = (saida or "").strip()
    baixo = texto.lower()
    dica = ""
    if "sign in to confirm" in baixo or "not a bot" in baixo:
        dica = (
            "O YouTube está pedindo confirmação anti-robô. Isso costuma resolver com "
            "cookies do navegador: exporte o arquivo cookies.txt (extensão "
            '"Get cookies.txt LOCALLY") e rode com --cookies cookies.txt.'
        )
    elif "unable to download api page" in baixo or "ssl" in baixo or "timed out" in baixo:
        dica = "Falha de conexão com o YouTube: verifique a internet, proxy ou firewall."
    elif "unsupported url" in baixo:
        dica = "O link não é de um site que o yt-dlp conheça. Confira se copiou o endereço do vídeo."
    elif "private video" in baixo or "members-only" in baixo:
        dica = "O vídeo é privado ou restrito — não é possível baixar."
    elif "requested format is not available" in baixo:
        dica = "Esse vídeo não oferece a faixa de áudio pedida. Tente novamente (o yt-dlp escolhe outra)."
    elif "no module named yt_dlp" in baixo:
        dica = "O módulo yt-dlp não foi encontrado: a pasta lib\\ do pacote está incompleta."
    elif "is not recognized" in baixo or "unknown option" in baixo:
        dica = "O comando do yt-dlp foi montado errado — me envie esta mensagem inteira."
    return f"{dica}\n\n{texto[-1800:]}" if dica else texto[-1800:]


def buscar(nome: str, limite: int = 8, timeout: int = 90) -> list[dict]:
    """Busca músicas por **nome** e devolve os candidatos.

    Existe por causa do StemRoller (stemroller.com): lá você digita "Nome da
    Banda - Nome da Música" e recebe os stems, sem precisar achar o link. Aqui
    era obrigatório colar a URL, o que é o passo mais chato do fluxo.

    Usa `ytsearch` do próprio yt-dlp, que já está embarcado — nenhuma
    dependência nova. Devolve lista de dicts com `url`, `titulo`, `duracao`,
    `canal` e `capa`.
    """
    nome = (nome or "").strip()
    if not nome:
        return []
    if nome.startswith(("http://", "https://")):
        # já é link: não há o que buscar
        return []

    cmd = ytdlp_command(
        f"ytsearch{max(1, min(limite, 25))}:{nome}",
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        "--flat-playlist",
    )
    try:
        proc = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=timeout, env=_env_ytdlp()
        )
    except subprocess.TimeoutExpired:
        raise MediaError(
            "a busca demorou demais. Verifique a internet e tente de novo."
        ) from None
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaError(f"não consegui buscar: {exc}") from None

    if proc.returncode != 0:
        baixo = (proc.stderr or "").lower()
        if "unable to download" in baixo or "network" in baixo:
            raise MediaError("a busca falhou por falta de internet.")
        raise MediaError(
            "a busca falhou. yt-dlp disse:\n"
            + ((proc.stderr or "").strip().splitlines() or ["(sem detalhes)"])[-1]
        )

    try:
        dados = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        raise MediaError("a busca devolveu algo inesperado do yt-dlp.") from None

    resultados: list[dict] = []
    for item in (dados.get("entries") or [])[:limite]:
        if not item:
            continue
        vid = item.get("id") or ""
        url = item.get("url") or item.get("webpage_url") or ""
        # no `--flat-playlist` o yt-dlp devolve só o id; montamos o link
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={vid}" if vid else url
        if not url:
            continue
        duracao = item.get("duration")
        resultados.append(
            {
                "url": url,
                "titulo": item.get("title") or "",
                "canal": item.get("channel") or item.get("uploader") or "",
                "duracao": int(duracao) if isinstance(duracao, (int, float)) else 0,
                "capa": (item.get("thumbnails") or [{}])[-1].get("url", "")
                if item.get("thumbnails")
                else (item.get("thumbnail") or ""),
            }
        )
    return resultados


def probe_url(url: str, timeout: int = 120) -> MediaInfo:
    """Lê metadados do vídeo sem baixar o áudio."""
    cmd = ytdlp_command("--dump-single-json", "--no-playlist", "--no-warnings", url)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_env_ytdlp())
    if proc.returncode != 0:
        raise MediaError(
            f"não foi possível ler os metadados de {url}\n"
            f"comando: {' '.join(cmd)}\n"
            f"saída do yt-dlp:\n{_explicar_erro_ytdlp(proc.stderr or proc.stdout)}"
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"metadados inválidos devolvidos pelo yt-dlp: {exc}") from None
    # yt-dlp devolve `thumbnail` (a melhor) e `thumbnails` (lista). Quando a
    # primeira falta, usamos a de maior largura — a capa é o que o usuário vê
    # na interface e dentro da pasta do projeto.
    capa = data.get("thumbnail") or ""
    if not capa:
        lista = [t for t in (data.get("thumbnails") or []) if t.get("url")]
        if lista:
            capa = max(lista, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))["url"]

    return MediaInfo(
        title=data.get("title") or "Sem título",
        thumbnail=capa,
        channel=data.get("uploader") or data.get("channel") or "",
        duration=float(data.get("duration") or 0.0),
        video_id=data.get("id") or "",
        webpage_url=data.get("webpage_url") or url,
        upload_date=data.get("upload_date") or "",
        extra={
            "filesize_approx": data.get("filesize_approx"),
            "extractor": data.get("extractor"),
            # capa do vídeo: a interface mostra e a pasta do projeto guarda
            "thumbnail": data.get("thumbnail") or "",
            "thumbnails": data.get("thumbnails") or [],
        },
    )


def download_audio(url: str, workdir: Path, info: MediaInfo | None = None, progress=None) -> MediaInfo:
    """Baixa o melhor áudio do vídeo e converte para WAV 44.1 kHz estéreo.

    Baixamos `bestaudio` (não o vídeo): o vídeo costuma ter 100–300 MB e o
    áudio já vem em opus/m4a de qualidade suficiente para separação.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    info = info or probe_url(url)
    if progress:
        progress(f"baixando áudio de “{info.title}”…")
    out_tmpl = str(workdir / "source.%(ext)s")
    base = _ytdlp_cmd(
        "-f", "bestaudio/best", "--no-playlist", "--no-warnings", "-o", out_tmpl, "--no-progress"
    )
    if have_ffmpeg():
        # Com ffmpeg o yt-dlp já entrega WAV direto, sem etapa extra.
        cmd = base + [
            "--extract-audio",
            "--audio-format",
            "wav",
            "--audio-quality",
            "0",
            url,
        ]
    else:
        # Sem ffmpeg o yt-dlp não converte; baixamos o container original
        # (m4a/webm) e a decodificação fica para o decoder do sistema.
        cmd = base + [url]
    env = _env_ytdlp()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=env)
    except FileNotFoundError as exc:
        raise MediaError(
            f"não consegui executar o yt-dlp: {exc}\n"
            f"comando: {' '.join(cmd)}"
        ) from None
    if proc.returncode != 0:
        saida = (proc.stderr or proc.stdout or "").strip()
        raise MediaError(
            "o download falhou\n"
            f"comando: {' '.join(cmd)}\n"
            f"saída do yt-dlp:\n{saida[-2000:]}"
        )
    candidates = sorted(workdir.glob("source.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise MediaError("o yt-dlp terminou sem gerar arquivo de áudio")
    downloaded = candidates[0]
    if downloaded.suffix.lower() != ".wav":
        wav = workdir / "source.wav"
        if progress:
            progress("convertendo para WAV…")
        to_wav(downloaded, wav)
        downloaded.unlink(missing_ok=True)
        downloaded = wav
    info.audio_path = downloaded
    return info


def to_wav(src: Path, dst: Path, sample_rate: int = 44100, channels: int = 2) -> Path:
    """Normaliza qualquer mídia para WAV PCM 16-bit no sample rate pedido."""
    ffmpeg = require_ffmpeg()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dst.exists():
        raise MediaError(f"ffmpeg não conseguiu converter {src.name}\n{proc.stderr.strip()[-1500:]}")
    return dst


def load_audio(path: Path, sample_rate: int = 44100):
    """Lê um arquivo de áudio como (dados float32, sample_rate).

    Tenta libsndfile (rápido, sem subprocesso). Se o formato não for
    suportado (m4a/aac/webm/mp3 em alguns builds), cai para ffmpeg + WAV.
    """
    try:
        import soundfile as sf
    except ModuleNotFoundError:
        raise dsp.MissingDependency("soundfile", "ler arquivos de áudio") from None
    except OSError as exc:
        # O módulo `soundfile` pode estar instalado e a biblioteca nativa
        # (libsndfile) não carregar — o caso do pacote portátil em que só o
        # Python foi copiado. Antes isso virava traceback feio; agora é erro
        # explicado com o que fazer.
        raise dsp.MissingDependency(
            "libsndfile",
            "abrir o arquivo de áudio (o módulo soundfile está instalado, mas a "
            f"biblioteca nativa não carregou: {exc})",
        ) from None

    alvo = Path(path)
    if not alvo.is_file():
        raise MediaError(f"arquivo de áudio não encontrado: {alvo}")

    try:
        data, sr = sf.read(str(alvo), dtype="float32", always_2d=False)
        if sr != sample_rate:
            data = dsp.resample_linear(data, sr, sample_rate)
            sr = sample_rate
        return data, sr
    except Exception:
        # libsndfile não reconheceu o formato (m4a/webm/aac/mp4): tenta pelo ffmpeg.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "decoded.wav"
            to_wav(alvo, wav, sample_rate=sample_rate)
            data, sr = sf.read(str(wav), dtype="float32", always_2d=False)
        return data, sr


def download_and_convert(url: str, workdir: Path, progress=None) -> MediaInfo:
    """Atalho: metadados + download + WAV 44.1 kHz, tudo em `workdir`."""
    info = probe_url(url)
    return download_audio(url, workdir, info, progress=progress)
