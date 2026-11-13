"""Exportação: WAV / MP3 / MP4, com metadados e visualizador.

Regras de desenho:

* **WAV** é a entrega "de estúdio": float32 ou PCM 24/16, sem normalização
  forçada (só se o usuário pedir). É o padrão, porque stem normalizado
  individualmente perde a relação de volume do mix.
* **MP3** para escutar no celular: usa o encoder LAME do ffmpeg, bitrate
  configurável, e grava as tags ID3 (título, artista, BPM, algoritmo) — o
  BPM aparece no player, que é o que o usuário pediu ("com BPM").
* **MP4** para compartilhar: áudio AAC + um visualizador de forma de onda
  gerado pelo próprio ffmpeg (`showwaves`). Nada de imagem estática no repo,
  nada de dependência de fontes.

Todas as conversões usam um arquivo WAV intermediário em pasta temporária:
é mais lento que um pipe, mas deixa o log legível e evita ler duas vezes o
mesmo arquivo quando o original é decodificado por libsndfile.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import dsp, media


class ExportError(media.MediaError):
    """Falha de exportação.

    Herda de `media.MediaError` para que um ffmpeg ausente seja tratado pelo
    mesmo `except` na CLI e no servidor web: é dependência faltando, não bug
    de mídia do usuário.
    """


class FFmpegMissing(ExportError):
    """ffmpeg ausente ou sem o encoder necessário."""


FORMATS = ("wav", "mp3", "mp4")

#: Bitrate padrão por formato — 320k para MP3 (máxima compatibilidade com
#: aparelhos que não tocam VBR bem), 256k AAC para MP4.
DEFAULT_BITRATE = {"mp3": "320k", "mp4": "256k"}


@dataclass
class ExportOptions:
    fmt: str = "wav"
    #: 16/24/32 (float) para WAV; ignorado nos outros
    bits: int = 24
    bitrate: str = ""
    #: normalizar o pico de cada arquivo para -1 dBFS
    normalize: bool = False
    #: nome/tags embutidos
    title: str = ""
    artist: str = ""
    bpm: float = 0.0

    def __post_init__(self) -> None:
        self.fmt = self.fmt.lower().lstrip(".")
        if self.fmt not in FORMATS:
            raise ValueError(f"formato '{self.fmt}' não suportado (use {', '.join(FORMATS)})")
        if not self.bitrate:
            self.bitrate = DEFAULT_BITRATE.get(self.fmt, "")

    @property
    def suffix(self) -> str:
        return self.fmt


def _run_ffmpeg(args: list[str]) -> None:
    try:
        ffmpeg = media.require_ffmpeg()
    except media.FFmpegMissing as exc:
        raise FFmpegMissing(str(exc)) from None
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ExportError(
            "o ffmpeg falhou ao exportar.\n" + (proc.stderr.strip()[-1500:] or "(sem mensagem)")
        )


def _tags(opts: ExportOptions) -> list[str]:
    args: list[str] = []
    if opts.title:
        args += ["-metadata", f"title={opts.title}"]
    if opts.artist:
        args += ["-metadata", f"artist={opts.artist}"]
        args += ["-metadata", f"album_artist={opts.artist}"]
    if opts.bpm:
        args += ["-metadata", f"TBPM={int(round(opts.bpm))}"]
        args += ["-metadata", f"bpm={int(round(opts.bpm))}"]
    args += ["-metadata", "encoded_by=MRQ VS", "-metadata", "comment=stems gerados por MRQ VS"]
    return args


def _write_wav(data, sample_rate: int, dst: Path, bits: int, normalize: bool) -> Path:
    try:
        import soundfile as sf
    except ModuleNotFoundError:
        raise dsp.MissingDependency("soundfile", "gravar WAV") from None
    if normalize:
        data = dsp.normalize_peak(data, -1.0)
    subtype = {16: "PCM_16", 24: "PCM_24", 32: "FLOAT"}.get(bits, "PCM_24")
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(dst, data, sample_rate, subtype=subtype)
    return dst


def export_audio(
    data,
    sample_rate: int,
    dst_no_ext: Path,
    opts: ExportOptions,
) -> Path:
    """Exporta um buffer de áudio para o formato pedido.

    `dst_no_ext` é o caminho sem extensão; a extensão vem de `opts.fmt`.
    """
    dst = dst_no_ext.with_suffix(f".{opts.suffix}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    if opts.fmt == "wav":
        return _write_wav(data, sample_rate, dst, opts.bits, opts.normalize)

    with tempfile.TemporaryDirectory(prefix="mrqvs-export-") as tmp:
        wav = _write_wav(data, sample_rate, Path(tmp) / "src.wav", 32, opts.normalize)
        if opts.fmt == "mp3":
            _run_ffmpeg(["-i", str(wav), "-c:a", "libmp3lame", "-b:a", opts.bitrate, *_tags(opts), str(dst)])
        else:  # mp4 com visualizador de forma de onda
            _mp4_from_wav(wav, dst, opts)
    return dst


def _mp4_from_wav(wav: Path, dst: Path, opts: ExportOptions, size: str = "1280x720") -> None:
    """Áudio AAC + `showwaves` do ffmpeg.

    Se o build do ffmpeg não tiver o filtro `showwaves`, a exportação cai
    para um MP4 só de áudio com fundo preto — melhor entregar o arquivo do
    que falhar por causa de um enfeite.
    """
    filters = (
        f"[0:a]showwaves=s={size}:mode=cline:rate=25:colors=0x5fd0a0|0x4f9dde,"
        f"format=yuv420p[v]"
    )
    args = [
        "-i",
        str(wav),
        "-filter_complex",
        filters,
        "-map",
        "[v]",
        "-map",
        "0:a",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        opts.bitrate,
        *_tags(opts),
        "-shortest",
        str(dst),
    ]
    try:
        _run_ffmpeg(args)
    except ExportError:
        _run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x101418:s={size}:r=10",
                "-i",
                str(wav),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                "-b:a",
                opts.bitrate,
                "-shortest",
                *_tags(opts),
                str(dst),
            ]
        )


def export_session(
    stems: dict[str, object],
    sample_rate: int,
    out_dir: Path,
    prefix: str,
    opts: ExportOptions,
    progress=None,
) -> dict[str, Path]:
    """Exporta todos os stems + o mix completo no formato escolhido."""
    from .naming import stem_filename

    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for stem, data in stems.items():
        if progress:
            progress(f"exportando {stem}.{opts.suffix}…")
        target = out_dir / stem_filename(prefix, stem, opts.suffix)
        written[stem] = export_audio(data, sample_rate, target.with_suffix(""), opts)

    # Mix de conferência: soma dos stems independentes (deve soar como o
    # original). Quando um derivado convive com o stem pai (ex.: `kick` junto
    # de `drums`, ou `instrumental` junto de `drums`/`bass`/`other`), somamos
    # só o pai para não duplicar energia no `00_mix`.
    import numpy as np

    from .stems import STEMS

    tem_base_nativa = bool({"drums", "bass", "guitar", "piano", "other"} & set(stems))
    mix = None
    for stem, data in stems.items():
        if stem == "instrumental" and tem_base_nativa:
            continue
        info = STEMS.get(stem)
        if info and info.derived_from and stem != "instrumental":
            if any(parent in stems for parent in info.derived_from):
                continue
        arr = np.asarray(data, dtype=np.float32)
        if mix is None:
            mix = arr.copy()
        else:
            n = min(mix.shape[0], arr.shape[0])
            mix = mix[:n] + arr[:n]
    if mix is not None:
        if progress:
            progress(f"exportando o mix completo ({opts.suffix})…")
        target = out_dir / f"{prefix}_00_mix.{opts.suffix}"
        written["mix"] = export_audio(mix, sample_rate, target.with_suffix(""), opts)
    return written


def check_export_capabilities(fmt: str) -> tuple[bool, str]:
    """Antes de prometer MP3/MP4, confirma que existe ffmpeg com o encoder."""
    if fmt == "wav":
        return True, "sem dependências extras"
    if not media.have_ffmpeg():
        return False, "precisa do ffmpeg (no pacote portátil ele já vem em lib\\)"
    try:
        encoders = subprocess.run(
            [media.find_tool("ffmpeg") or "ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False, "não foi possível consultar os encoders do ffmpeg"
    needed = "libmp3lame" if fmt == "mp3" else "libx264"
    if needed not in encoders:
        return False, f"o ffmpeg instalado não tem o encoder {needed}"
    return True, f"pronto ({needed})"
