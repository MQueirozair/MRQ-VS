"""Motor de separação com backends plugáveis.

Hierarquia (a primeira que existir e funcionar é usada):

1. **demucs** (`htdemucs_6s` por padrão) — melhor qualidade aberta; 4 ou 6
   stems reais. Requer torch, ou seja, ~2 GB de dependências e um CPU decente.
2. **audio-separator** (MDX / BS-RoFormer em ONNX) — boa qualidade, roda em
   CPU sem torch, e tem modelos que o Demucs não tem.
3. **spleeter** — legado (Deezer), rápido e leve; qualidade abaixo dos dois.
4. **dsp-fallback** — HPSS + máscaras espectrais, numpy puro. Não é IA: é a
   separação "clássica" (mediana espectral), honestamente rotulada como
   aproximada no relatório. Serve para o programa funcionar em qualquer
   máquina e como base de comparação.

Todos os backends de terceiros são chamados como **processo externo** (CLI),
nunca importados: assim um torch quebrado ou uma versão incompatível não
derruba o app, e o usuário vê o log real do erro. O backend DSP é interno e
puro, então é o único que sempre dá para testar.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import dsp, runtime


class SeparationError(RuntimeError):
    """Falha ao separar, com a saída real do backend anexada."""

    def __init__(self, backend: str, message: str, log: str = "") -> None:
        detail = f"\n\n--- saída do backend ({backend}) ---\n{log.strip()}" if log.strip() else ""
        super().__init__(f"{message}{detail}")
        self.backend = backend
        self.log = log


@dataclass
class BackendStatus:
    name: str
    available: bool
    #: por que não está disponível / como instalar
    detail: str
    version: str = ""
    #: True para motores alternativos que **não** são necessários (não são erro)
    opcional: bool = False
    #: Peças que faltam para este motor funcionar (ex.: ["numpy"]).
    #: A tela usa isto para dizer "falta numpy" em vez de "não instalada".
    faltando: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "opcional": self.opcional,
            "detail": self.detail,
            "version": self.version,
            "faltando": list(self.faltando),
        }


# ---------------------------------------------------------------------------
# Detecção de backends
# ---------------------------------------------------------------------------


def _python_module_available(module: str) -> tuple[bool, str]:
    """Testa import num processo filho (não suja o processo atual).

    Usa `runtime.module_command()` para não tentar importar dentro do próprio
    executável portátil (ver `runtime.py`).
    """
    cmd = runtime.module_command(module)
    if cmd is None:
        return False, "sem Python no PATH (executável portátil) — instale Python para usar este backend"
    try:
        proc = subprocess.run(
            [cmd[0], "-c", f"import {module}, sys; print(getattr({module}, '__version__', ''))"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"não foi possível executar o Python atual: {exc}"
    if proc.returncode == 0:
        return True, proc.stdout.strip()
    return False, (proc.stderr.strip().splitlines() or ["módulo não encontrado"])[-1]


#: Módulos que o `python -m demucs` precisa importar para separar áudio.
#: Ordem do mais provável de faltar para o menos, e nomes de import.
_MODULOS_DO_DEMUCS = ("numpy", "torch", "einops", "julius", "lameenc", "sphn", "yaml", "tqdm")


def _testar_demucs_de_verdade() -> tuple[bool, str, str, tuple[str, ...]]:
    """Testa o demucs pelo caminho que o programa realmente executa.

    Devolve `(ok, versao, detalhe, faltando)`. Quando falta alguma peça,
    `faltando` traz o nome e `detalhe` a instrução — foi essa informação que
    faltou na 0.1.10: a tela dizia "demucs ✓" e o usuário só descobria o
    problema no erro de separação.

    Importar `demucs.separate` seria o teste mais direto, mas carrega o torch
    inteiro (centenas de MB e alguns segundos) toda vez que a página abre.
    Em vez disso checamos `find_spec` de cada dependência — instantâneo — e
    depois só importamos o demucs de verdade, que aí é barato.
    """
    python = runtime.python_cmd()
    if python is None:
        return (
            False,
            "",
            "sem Python: o executável portátil não roda demucs — "
            "instale em 'Instalar IA' (ou Python + python -m pip install demucs)",
            (),
        )

    codigo = (
        "import importlib.util\n"
        f"faltam = [m for m in {list(_MODULOS_DO_DEMUCS)!r} "
        "if importlib.util.find_spec(m) is None]\n"
        "if importlib.util.find_spec('demucs') is None:\n"
        "    faltam.insert(0, 'demucs')\n"
        "print('FALTAM:' + ' '.join(faltam))\n"
    )
    try:
        proc = subprocess.run(
            [python, "-c", codigo],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "", f"não consegui testar o demucs: {exc}", ()

    if proc.returncode != 0:
        ultima = (proc.stderr.strip().splitlines() or ["erro desconhecido"])[-1]
        return False, "", f"o Python não respondeu: {ultima}", ()

    linha = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FALTAM:")), "")
    faltam = linha[len("FALTAM:") :].split()
    if faltam:
        # o conserto é o mesmo botão em todos os casos, então a mensagem é direta
        return (
            False,
            "",
            "incompleto: falta " + ", ".join(faltam)
            + " — use 'Completar instalação' no painel Motor de IA",
            tuple(faltam),
        )

    # tudo presente: agora sim importar o demucs (barato, nada falta)
    ok, versao = _python_module_available("demucs")
    if ok:
        return (
            True,
            versao,
            "pronto (stems: drums, bass, other, vocals, guitar, piano com htdemucs_6s)",
            (),
        )
    return (
        False, versao,
        "o demucs está instalado mas não carrega — use 'Completar instalação'",
        (),
    )


def detect_backends() -> list[BackendStatus]:
    statuses: list[BackendStatus] = []

    # O selo do demucs já mentiu uma vez: mostrava "demucs ✓" com o numpy
    # faltando, e o erro só aparecia ao clicar em Separar. O motivo é sutil —
    # `demucs/__init__.py` tem uma única linha, `__version__ = "4.1.0"`:
    #
    #     $ python -c "import demucs"      -> rc=0   (não importa nada!)
    #     $ python -c "from demucs.separate import main"
    #     ModuleNotFoundError: No module named 'numpy'
    #
    # Ou seja, `import demucs` não prova nada. Só o caminho que o programa
    # usa de verdade (`python -m demucs`) carrega torch, numpy, einops...
    # Então é isso que testamos aqui.
    ok_demucs, demucs_version, demucs_detail, demucs_faltando = _testar_demucs_de_verdade()
    # O demucs é o motor recomendado, mas o programa funciona sem ele (DSP).
    # Por isso o `doctor` o mostra como "não instalado", não como falha.
    statuses.append(
        BackendStatus(
            "demucs",
            ok_demucs,
            demucs_detail,
            demucs_version,
            opcional=False,
            faltando=demucs_faltando,
        )
    )

    # Estas duas NÃO são instaladas de propósito. Antes o selo só dizia
    # "áudio-separator" e "spleeter" em cinza, e a pergunta óbvia — "por que
    # não estão aprovados?" — não tinha resposta em lugar nenhum da tela.
    ok_as, as_version = _python_module_available("audio_separator")
    statuses.append(
        BackendStatus(
            "audio-separator",
            ok_as,
            "instalado por você — usando como alternativa ao demucs"
            if ok_as
            else (
                "não instalado de propósito: pesa mais de 1 GB e baixa os "
                "modelos de outro site (o Demucs já faz o mesmo trabalho). "
                "Se quiser, instale: python -m pip install audio-separator"
            ),
            as_version,
            opcional=True,
        )
    )

    # open-unmix: o substituto do Spleeter. Antes a tela tinha um selo cinza
    # dizendo "spleeter: não dá" e nada mais — um beco sem saída. Agora o
    # substituto está aqui, com o mesmo papel e funcionando no Python atual.
    ok_um, um_version = _python_module_available("openunmix")
    statuses.append(
        BackendStatus(
            "openunmix",
            ok_um,
            "instalado — o motor leve, roda em CPU (4 stems, ~300 MB)"
            if ok_um
            else (
                "motor leve, no lugar do spleeter: 4 stems, roda em CPU e "
                "custa ~300 MB (contra ~1 GB do demucs). Separa um pouco "
                "abaixo do demucs e bem acima do DSP. "
                "Instale com o botão 'Instalar motor leve'."
            ),
            um_version,
            opcional=False,
        )
    )

    ok_sp, sp_version = _python_module_available("spleeter")
    statuses.append(
        BackendStatus(
            "spleeter",
            ok_sp,
            "instalado por você — usando como alternativa ao demucs"
            if ok_sp
            else (
                "substituído: exige TensorFlow 2.12.1, que só existe até o "
                "Python 3.11. Use o caminho 'leve' (open-unmix) ou o modo "
                "'só voz + instrumental', que faz o mesmo trabalho e mais "
                "rápido."
            ),
            sp_version,
            opcional=True,
        )
    )

    statuses.append(
        BackendStatus(
            "dsp-fallback",
            True,
            "sempre disponível (numpy puro, HPSS + máscaras — aproximado, não é IA)",
        )
    )
    return statuses


#: Backends que só existem em cada modelo. Escolher um modelo RoFormer e cair
#: no Demucs não é "degradar": é passar um nome de arquivo que o Demucs não
#: conhece, e o Demucs falha. Por isso o modelo manda no backend.
BACKEND_DO_MODELO: dict[str, str] = {
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt": "audio-separator",
    "UVR-MDX-NET-Inst_HQ_3.onnx": "audio-separator",
    "mdx_extra": "audio-separator",
    "mdx_extra_q": "audio-separator",
    "spleeter:4stems": "spleeter",
    "spleeter:5stems": "spleeter",
    "umxl": "openunmix",
    "umxhq": "openunmix",
    "dsp-fallback": "dsp-fallback",
}


def choose_backend(
    preferred: str = "auto",
    need_stems: tuple[str, ...] = (),
    model: str = "",
) -> str:
    """Escolhe o backend disponível que cobre `need_stems`.

    `model` (quando informado) tem prioridade: cada família de modelo só roda
    no backend dela. Antes, pedir o RoFormer e o backend automático escolher o
    Demucs resultava em `dsp-fallback` — ou seja, o usuário pedia a melhor
    voz do mundo e recebia a separação aproximada.
    """
    from .stems import MODEL_STEMS

    order = ["demucs", "audio-separator", "openunmix", "spleeter", "dsp-fallback"]
    if preferred != "auto":
        if preferred not in order:
            raise ValueError(f"backend desconhecido: {preferred} (opções: auto, {', '.join(order)})")
        order = [preferred]
    elif model and model in BACKEND_DO_MODELO:
        dono = BACKEND_DO_MODELO[model]
        order = [dono] + [b for b in order if b != dono]

    available = {s.name for s in detect_backends() if s.available}
    for name in order:
        if name not in available:
            continue
        modelo_do_backend = model or DEFAULT_MODEL_FOR_BACKEND.get(name, "")
        native = set(MODEL_STEMS.get(modelo_do_backend, ()))
        # `need_stems` vazio = "tanto faz"; o backend DSP cobre o básico sempre.
        if not need_stems or set(need_stems) <= native or name == "dsp-fallback":
            return name
    return "dsp-fallback"


DEFAULT_MODEL_FOR_BACKEND = {
    "demucs": "htdemucs_6s",
    "audio-separator": "mdx_extra_q",
    "openunmix": "umxl",
    "spleeter": "spleeter:4stems",
    "dsp-fallback": "dsp-fallback",
}


# ---------------------------------------------------------------------------
# Separação
# ---------------------------------------------------------------------------


@dataclass
class SeparationResult:
    backend: str
    model: str
    #: nome do stem -> caminho do arquivo .wav (44.1 kHz, float32 ou pcm16)
    stems: dict[str, Path]
    sample_rate: int
    log: str = ""


def _run(cmd: list[str], log_path: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if log_path is not None:
        log_path.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")
    return proc


def separate(
    audio_path: Path,
    out_dir: Path,
    backend: str = "auto",
    model: str = "",
    stems: tuple[str, ...] = (),
    device: str = "auto",
    log_path: Path | None = None,
    progress=None,
    dois_stems: str = "",
) -> SeparationResult:
    """Separa `audio_path` em stems dentro de `out_dir`.

    `stems` vazio = todos os nativos do modelo (mais barato e previsível).
    Devolve um `SeparationResult` só com os stems nativos do backend — os
    derivados são calculados depois por `derive.py`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen = choose_backend(backend, stems, model)
    # Modelo e backend precisam combinar: passar um .ckpt do RoFormer para o
    # Demucs produz "unrecognized model" no log dele, que não diz nada ao
    # usuário. Falhamos aqui, com a explicação.
    dono = BACKEND_DO_MODELO.get(model)
    if model and dono and chosen != dono:
        raise SeparationError(
            chosen,
            f"o modelo '{model}' só roda no backend '{dono}', mas foi pedido "
            f"'{chosen}'.",
        )
    model = model or DEFAULT_MODEL_FOR_BACKEND[chosen]
    if progress:
        extra = f", modo 2 stems ({dois_stems})" if dois_stems else ""
        progress(f"separando com {chosen} ({model}){extra}…")

    if chosen == "demucs":
        return _separate_demucs(audio_path, out_dir, model, device, log_path, dois_stems)
    if chosen == "audio-separator":
        return _separate_audio_separator(audio_path, out_dir, model, log_path)
    if chosen == "openunmix":
        return _separate_openunmix(audio_path, out_dir, model, log_path)
    if chosen == "spleeter":
        return _separate_spleeter(audio_path, out_dir, model, log_path)
    return _separate_dsp(audio_path, out_dir, log_path)


def _bandpass_weight(freqs, lo: float, hi: float, knee: float = 0.7):
    """1 dentro de [lo, hi], caindo em `knee` oitavas nas bordas."""
    import numpy as np

    f = np.maximum(freqs, 1e-3)
    up = np.clip(np.log2(f / max(lo, 1e-3)) / knee, 0.0, 1.0)
    down = np.clip(np.log2(max(hi, lo * 2) / f) / knee, 0.0, 1.0)
    return (up * down).astype(np.float32)


def _lowpass_weight(freqs, flat_to: float, zero_at: float):
    """1 até `flat_to`, rampa linear (em oitavas) até 0 em `zero_at`."""
    import numpy as np

    f = np.maximum(freqs, 1e-3)
    return np.clip(np.log2(zero_at / f) / np.log2(zero_at / flat_to), 0.0, 1.0).astype(np.float32)


def _write_stems(stems: dict[str, "object"], sample_rate: int, out_dir: Path) -> dict[str, Path]:
    """Escreve os stems como WAV float32 de 44.1 kHz (via soundfile)."""
    try:
        import soundfile as sf
    except ModuleNotFoundError:
        raise dsp.MissingDependency("soundfile", "gravar os stems em WAV") from None
    paths: dict[str, Path] = {}
    for name, data in stems.items():
        path = out_dir / f"{name}.wav"
        sf.write(path, data, sample_rate, subtype="FLOAT")
        paths[name] = path
    return paths


# -- demucs ------------------------------------------------------------------


def _taxa_do_wav(caminho: Path) -> int | None:
    """Sample rate de um arquivo WAV lendo 44 bytes do cabeçalho.

    Existe para o MRQ VS não depender do `soundfile` (que o demucs não traz)
    apenas para saber a taxa dos stems que ele mesmo acabou de gravar.
    """
    import struct

    try:
        with caminho.open("rb") as fh:
            cabecalho = fh.read(44)
    except OSError:
        return None
    if len(cabecalho) < 28 or cabecalho[0:4] != b"RIFF" or cabecalho[8:12] != b"WAVE":
        return None
    try:
        return struct.unpack("<I", cabecalho[24:28])[0]
    except struct.error:
        return None


#: Peças que o demucs 4.1.0 **usa e não declara** no pacote. Quando uma delas
#: falta, o Python cospe um `ModuleNotFoundError` de 20 linhas em que a única
#: frase útil é a última — e ela nem menciona o programa que o usuário está
#: tentando usar.
_PECAS_DO_DEMUCS = ("numpy", "soundfile", "torch", "sphn", "julius", "lameenc", "einops")


def _explicar_falha_do_demucs(saida: str) -> str:
    """Traduz o erro do backend para algo que o usuário possa resolver.

    O caso real (0.1.10): `ModuleNotFoundError: No module named 'numpy'` no
    meio de um traceback de 6 arquivos. A mensagem que aparecia era só "o
    Demucs falhou ao separar o áudio", e o usuário não tinha o que fazer.
    """
    texto = saida or ""
    for peca in _PECAS_DO_DEMUCS:
        if f"No module named '{peca}'" in texto:
            return (
                f"falta o pacote '{peca}' no motor de IA — ele não veio na "
                "instalação do demucs.\n"
                "Clique em \"Completar instalação\" no painel Motor de IA: "
                f"baixa só o {peca}, sem repetir o download de 1 GB."
            )
    if "CUBLAS" in texto or "CUDA out of memory" in texto or "out of memory" in texto:
        return (
            "o Demucs ficou sem memória. Feche outros programas e tente de "
            "novo, ou escolha o modelo mais leve."
        )
    return "o Demucs falhou ao separar o áudio"


def _separate_demucs(
    audio_path: Path,
    out_dir: Path,
    model: str,
    device: str,
    log_path: Path | None,
    dois_stems: str = "",
) -> SeparationResult:
    """Roda o Demucs. Com `dois_stems` (ex.: "vocals") calcula só 2 saidas.

    `--two-stems=vocals` existe no proprio Demucs e e o caminho rápido que
    substitui o Spleeter no uso mais comum: voz de um lado, base do outro,
    ~1/3 do tempo e da memória do modo de 6 stems. A qualidade de voz e a
    mesma do modelo escolhido - muda o numero de saidas, nao o modelo.
    """
    device_args: list[str] = []
    if device != "auto":
        device_args = ["-d", device]
    dois_args: list[str] = []
    if dois_stems:
        dois_args = ["--two-stems", dois_stems]
    base = runtime.module_command(
        "demucs", "--name", model, "-o", str(out_dir), *dois_args, *device_args, str(audio_path)
    )
    if base is None:
        raise SeparationError("demucs", "nenhum Python encontrado para rodar o Demucs")
    cmd = base
    proc = _run(cmd, log_path)
    if proc.returncode != 0:
        raise SeparationError(
            "demucs", _explicar_falha_do_demucs(proc.stderr or proc.stdout), proc.stderr
        )

    # Demucs grava <out_dir>/<model>/<nome_da_entrada>/*.wav
    candidate_dirs = sorted(out_dir.glob(f"{model}/*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidate_dirs:
        raise SeparationError("demucs", "o Demucs terminou sem gerar pasta de saída", proc.stdout)
    stem_dir = candidate_dirs[0]

    found: dict[str, Path] = {}
    sample_rate = 44100
    for wav in sorted(stem_dir.glob("*.wav")):
        if wav.stem == "no_vocals":
            found["instrumental"] = wav
        else:
            found[wav.stem] = wav
    if found:
        # O Demucs grava o que o `-o` mandar: WAV, e por isso o `.wav`.
        # Antes isto dependia do `soundfile` só para ler a taxa — pacote que
        # não vem com o demucs. Lendo o cabeçalho do próprio WAV, a separação
        # funciona sem instalar nada a mais.
        sample_rate = _taxa_do_wav(next(iter(found.values()))) or 44100
    if not found:
        raise SeparationError("demucs", "o Demucs terminou mas não produziu nenhum .wav", proc.stdout)
    return SeparationResult("demucs", model, found, sample_rate, proc.stderr)


# -- audio-separator ---------------------------------------------------------


def _separate_audio_separator(
    audio_path: Path, out_dir: Path, model: str, log_path: Path | None
) -> SeparationResult:
    model_file = model if model.endswith((".onnx", ".ckpt", ".pth", ".yaml")) else f"{model}.yaml"
    base = runtime.module_command(
        "audio_separator",
        str(audio_path),
        "--model_filename",
        model_file,
        "--output_dir",
        str(out_dir),
        "--output_format",
        "WAV",
        "--sample_rate",
        "44100",
    )
    if base is None:
        raise SeparationError("audio-separator", "nenhum Python encontrado para rodar o audio-separator")
    cmd = base
    proc = _run(cmd, log_path)
    if proc.returncode != 0:
        raise SeparationError(
            "audio-separator",
            "o audio-separator falhou (modelo não baixado? veja o log abaixo)",
            proc.stderr,
        )
    found: dict[str, Path] = {}
    for wav in sorted(out_dir.glob("*.wav")):
        # audio-separator nomeia "<original>_(Vocals)_modelo.wav"
        lower = wav.stem.lower()
        for stem in ("vocals", "instrumental", "drums", "bass", "guitar", "piano", "other"):
            if f"({stem})" in lower:
                found[stem] = wav
                break
    if not found:
        raise SeparationError("audio-separator", "nenhum stem reconhecível foi gerado", proc.stdout)
    return SeparationResult("audio-separator", model, found, 44100, proc.stderr)


# -- spleeter -----------------------------------------------------------------


def _separate_spleeter(
    audio_path: Path, out_dir: Path, model: str, log_path: Path | None
) -> SeparationResult:
    stems = "5stems" if model.endswith("5stems") else "4stems"
    base = runtime.module_command(
        "spleeter", "separate", "-p", f"spleeter:{stems}", "-o", str(out_dir), str(audio_path)
    )
    if base is None:
        raise SeparationError("spleeter", "nenhum Python encontrado para rodar o Spleeter")
    cmd = base
    proc = _run(cmd, log_path)
    if proc.returncode != 0:
        raise SeparationError("spleeter", "o Spleeter falhou", proc.stderr)
    found: dict[str, Path] = {}
    for wav in sorted(out_dir.rglob("*.wav")):
        found[wav.stem] = wav
    if not found:
        raise SeparationError("spleeter", "o Spleeter terminou sem gerar stems", proc.stdout)
    sample_rate = 44100
    try:
        import soundfile as sf

        sample_rate = int(sf.info(next(iter(found.values()))).samplerate)
    except Exception:  # pragma: no cover - só informativo
        pass
    return SeparationResult("spleeter", f"spleeter:{stems}", found, sample_rate, proc.stderr)


# -- open-unmix: o substituto do spleeter ------------------------------------
# Roda em qualquer Python 3.10+, roda em CPU e e leve (~300 MB com torch).
# O Spleeter ficou impossivel (tensorflow 2.12.1 so tem wheel ate cp311), mas
# o papel dele - separacao leve de 4 stems - continua existindo. Este e ele.

_CODIGO_OPENUNMIX = """
import sys
from pathlib import Path
import numpy as np
import torch

modelo = sys.argv[1]
entrada = sys.argv[2]
saida = Path(sys.argv[3])

from openunmix import predict
import soundfile as sf

audio, taxa = sf.read(entrada, always_2d=True)
# (amostras, canais) -> (canais, amostras), que e o que o open-unmix espera
mix = torch.from_numpy(audio.T.astype(np.float32))
if taxa != 44100:
    import torchaudio
    mix = torchaudio.functional.resample(mix, taxa, 44100)
    taxa = 44100

estimativas = predict.separate(
    mix, rate=taxa, model_str=modelo, device="cpu"
)
for nome, tensores in estimativas.items():
    arr = tensores.detach().cpu().numpy()
    if arr.ndim == 3:
        arr = arr[0]
    sf.write(str(saida / f"{nome}.wav"), arr.T, taxa, subtype="FLOAT")
print("OK")
"""


def _separate_openunmix(
    audio_path: Path, out_dir: Path, model: str, log_path: Path | None
) -> SeparationResult:
    """Separa com open-unmix, chamando o Python num subprocesso.

    Subprocesso pelo mesmo motivo do demucs: carregar torch no processo da
    interface faria a pagina travar por segundos a cada consulta de status.
    """
    python = runtime.python_cmd()
    if python is None:
        raise SeparationError("openunmix", "nenhum Python encontrado para rodar o open-unmix")
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [python, "-c", _CODIGO_OPENUNMIX, model or "umxl", str(audio_path), str(out_dir)]
    proc = _run(cmd, log_path)
    if proc.returncode != 0:
        erro = proc.stderr or proc.stdout
        raise SeparationError("openunmix", _explicar_falha_do_openunmix(erro), erro)

    found: dict[str, Path] = {}
    for wav in sorted(out_dir.glob("*.wav")):
        found[wav.stem] = wav
    if not found:
        raise SeparationError("openunmix", "o open-unmix terminou sem gerar stems", proc.stdout)
    taxa = _taxa_do_wav(next(iter(found.values()))) or 44100
    return SeparationResult("openunmix", model or "umxl", found, taxa, proc.stderr)


def _explicar_falha_do_openunmix(saida: str) -> str:
    """Traduz o erro do open-unmix para algo acionável."""
    texto = (saida or "").lower()
    if "no module named 'openunmix'" in texto:
        return (
            "o open-unmix não está instalado. Use o botão 'Instalar motor leve' "
            "na tela, ou: python -m pip install openunmix"
        )
    if "no module named 'torch'" in texto:
        return "falta o torch: python -m pip install torch openunmix"
    if "memory" in texto or "out of memory" in texto:
        return (
            "faltou memória. Tente o modo 'só voz + instrumental', que usa "
            "menos memória, ou feche outros programas."
        )
    return "o open-unmix falhou: " + (saida or "").strip().splitlines()[-1][:300]


# -- dsp-fallback (HPSS + máscaras) -----------------------------------------


NOMES_STEMS = ("vocals", "drums", "bass", "other")


def separate_dsp(mix, sample_rate: int, n_fft: int = 4096) -> dict[str, "object"]:
    """Separação clássica em numpy puro: vocals / drums / bass / other.

    Como funciona (e por que é honestamente "aproximado"):

    1. **HPSS** (harmonic/percussive source separation, Fitzgerald 2010):
       mediana no eixo do tempo deixa a harmonia (linhas horizontais),
       mediana no eixo da frequência deixa a percussão (picos verticais).
    2. **Bateria** = componente percussivo; **harmonia** = o resto.
    3. Dentro da harmonia, **baixo** = máscara de banda < 250 Hz com peso
       decrescente (o fundamental do baixo quase sempre mora lá);
       **vocais** = faixa de presença 300 Hz–3,5 kHz com máscara tipo Wiener
       contra o resto — é o que separa "voz" de "instrumento" por EQ, uma
       aproximação grosseira da separação por conteúdo.
    4. **other** = harmonia - vocais - baixo.

    A soma dos quatro reconstitui o mix quase exatamente (é uma partição
    espectral por máscaras que somam 1), então nunca "desaparece" áudio.

    Esta função devolve tudo em memória (é o que os testes e o uso
    programático querem). O caminho de arquivo do app usa `_separar_blocos` e
    grava cada trecho no WAV na hora — ver `_separate_dsp`.
    """
    dsp.require_numpy("separar com o backend DSP")
    import numpy as np

    mono_stereo = np.asarray(mix, dtype=np.float32)
    channels = 1 if mono_stereo.ndim == 1 else mono_stereo.shape[1]
    comprimento = mono_stereo.shape[0]

    pedacos: dict[str, list] = {name: [] for name in NOMES_STEMS}
    for nomes, trechos in _separar_blocos(mono_stereo, sample_rate, n_fft):
        for nome, trecho in zip(nomes, trechos):
            pedacos[nome].append(trecho)

    out: dict[str, "object"] = {}
    for nome, lista in pedacos.items():
        audio = np.concatenate(lista, axis=0) if lista else np.zeros((0, channels), np.float32)
        out[nome] = audio[:comprimento] if mono_stereo.ndim != 1 else audio[:comprimento, 0]
    return out


def _norm_bloco(inicio: int, n: int, hop: int, n_fft: int, janela, np) -> "object":
    """Soma de `janela**2` (overlap-add) para os `n` quadros do bloco.

    Crucial incluir os quadros **anteriores** (pre-roll): em `hop = n_fft/4`
    cada amostra recebe 4 janelas, e as 3 de trás vêm dos quadros que ficaram
    no bloco anterior. Sem isso a normalização "recomeça do zero" em cada
    bloco e o áudio sai amplificado ~1e8 nas emendas.

    A janela soma `1.5` no interior; só a primeira amostra do sinal inteiro
    tem norma ~0, igual ao `istft` de uma passada só.
    """
    pre = min(3, inicio)
    win_sq = janela**2
    total = (n + pre - 1) * hop + n_fft
    norm = np.zeros(total, dtype=np.float32)
    for k in range(n + pre):
        norm[k * hop : k * hop + n_fft] += win_sq
    return norm[pre * hop : pre * hop + (n - 1) * hop + n_fft]


def _separar_blocos(mix, sample_rate: int, n_fft: int = 4096):
    """Gerador do backend DSP: devolve `(nomes, trechos)` por bloco de tempo.

    Por que em blocos: um espectrograma de faixa longa (710 s → 33257 × 2049)
    tem 273 MB por matriz float32, e o pipeline usa várias. Calcular tudo de
    uma vez pedia 7,87 GiB e derrubava o Windows do usuário (o erro
    "Unable to allocate 7.87 GiB for an array with shape (33257, 2049, 31)").

    Cada `trecho` é um array `(amostras, canais)` já normalizado e pronto
    para gravar. A memória fica limitada ao tamanho do bloco (~alguns MB),
    independente da duração da música. O resultado é idêntico ao cálculo de
    uma passada só — a normalização pela janela² é a mesma, feita por trecho.
    """
    dsp.require_numpy("separar com o backend DSP")
    import numpy as np

    mono_stereo = np.asarray(mix, dtype=np.float32)
    channels = 1 if mono_stereo.ndim == 1 else mono_stereo.shape[1]
    comprimento = mono_stereo.shape[0]
    hop = n_fft // 4
    janela = dsp.hann(n_fft)
    freqs = dsp.stft_freqs(n_fft, sample_rate)
    n_quadros = dsp.stft_quadros(comprimento, n_fft, hop)

    # Pesos por banda. Os valores não são "gosto": são o que faz cada stem
    # cair na fonte certa no teste de regressão com a demo
    # (tests/test_separation.py). Música real varia, mas estes limites são os
    # usuais em produção: fundamental de baixo abaixo de ~200 Hz e região de
    # presença da voz de ~300 Hz a 4 kHz. Linha = bin (espectrograma em
    # (quadros, bins), como `dsp.stft`).
    vocal_weight = _bandpass_weight(freqs, 300.0, 4000.0)[None, :]
    bass_weight = _lowpass_weight(freqs, 180.0, 260.0)[None, :]

    # Cauda entre blocos: a sobreposição do último quadro de um bloco com o
    # primeiro do seguinte é `n_fft - hop` amostras. Elas são guardadas
    # **sem normalizar**, porque o próximo bloco ainda vai somar a parte dele
    # (normalizar duas vezes apagaria o áudio — foi um bug real).
    cauda = n_fft - hop
    carry = {n: np.zeros((channels, cauda), dtype=np.float32) for n in NOMES_STEMS}
    carry_norm = np.zeros(cauda, dtype=np.float32)
    emitido = 0  # amostras já entregues ao consumidor

    for inicio in range(0, n_quadros, dsp.HPSS_BLOCO):
        fim = min(inicio + dsp.HPSS_BLOCO, n_quadros)
        n = fim - inicio
        bloco_len = (n - 1) * hop + n_fft
        prontas = min(n * hop, comprimento - inicio * hop)
        norm = _norm_bloco(inicio, n, hop, n_fft, janela, np)
        trechos = [np.zeros((prontas, channels), dtype=np.float32) for _ in NOMES_STEMS]

        for ch in range(channels):
            sinal_ch = mono_stereo if mono_stereo.ndim == 1 else mono_stereo[:, ch]
            # `mix[:, ch]` tem stride de 2 canais; a STFT indexa por amostra
            if mono_stereo.ndim != 1:
                sinal_ch = np.ascontiguousarray(sinal_ch)
            # magnitude do bloco COM contexto no tempo: o HPSS precisa de
            # `half` quadros de cada lado para a mediana bater com o cálculo
            # feito de uma vez só
            half = 15
            ctx_ini = max(0, inicio - half)
            ctx_fim = min(n_quadros, fim + half)
            spec_ctx = dsp.stft_faixa(sinal_ch, n_fft, hop, janela, ctx_ini, ctx_fim)
            mag = np.abs(spec_ctx)
            del spec_ctx
            # completa o contexto nas pontas do sinal (borda `edge`)
            esq = half - (inicio - ctx_ini)
            dir_ = half - (ctx_fim - fim)
            if esq or dir_:
                mag = np.pad(mag, ((esq, dir_), (0, 0)), mode="edge")
            masks = _mascaras_do_bloco(mag, vocal_weight, bass_weight, np)
            del mag
            spec = dsp.stft_faixa(sinal_ch, n_fft, hop, janela, inicio, fim)
            for i, nome in enumerate(NOMES_STEMS):
                saida = np.zeros(bloco_len, dtype=np.float32)
                dsp.istft_soma(
                    saida, norm, spec * masks[i], n_fft, hop, janela, 0, somar_norm=False
                )
                # soma a cauda crua do bloco anterior (mesma faixa absoluta)
                saida[:cauda] += carry[nome][ch]
                # trecho pronto: dividir pela janela² acumulada **uma vez**
                pedaco = saida[:prontas] / np.maximum(norm[:prontas], 1e-8)
                if channels == 1:
                    trechos[i][:, 0] = pedaco
                else:
                    trechos[i][:, ch] = pedaco
                carry[nome][ch] = saida[prontas : prontas + cauda]
                del saida, pedaco
            if ch == 0:
                carry_norm = norm[prontas : prontas + cauda].copy()
            del spec, masks
        emitido += prontas
        yield NOMES_STEMS, trechos

    # Sobra a cauda do último bloco. Já está com todas as contribuições
    # somadas; falta só normalizar e cortar no comprimento do áudio.
    resto = comprimento - emitido
    if resto > 0:
        trechos = [np.zeros((resto, channels), dtype=np.float32) for _ in NOMES_STEMS]
        for i, nome in enumerate(NOMES_STEMS):
            for ch in range(channels):
                pedaco = carry[nome][ch][:resto] / np.maximum(carry_norm[:resto], 1e-8)
                if channels == 1:
                    trechos[i][:, 0] = pedaco
                else:
                    trechos[i][:, ch] = pedaco
        yield NOMES_STEMS, trechos


def _mascaras_do_bloco(mag, vocal_weight, bass_weight, np):
    """As quatro máscaras de um bloco, a partir da magnitude magnitude-orientada.

    `mag` é `(quadros, bins)` e já contém `half` quadros de contexto dos dois
    lados; a saída tem uma linha por quadro do bloco.
    """
    # HPSS do miolo (o contexto é consumido pela janela de mediana)
    mask_h = dsp.hpss_mask_h(mag, width=31)
    # no contexto padeado, o primeiro quadro do bloco mora na linha `half`
    half = 15
    mag = mag[half : half + mask_h.shape[0], :]

    # O peso `mask_h` entra **dentro** das máscaras: vocais e baixo só podem
    # levar energia harmônica. Sem isso a soma das quatro saídas passa de 1
    # no médio-grave e o mix reconstruído fica com ganho extra.
    vocal_mag = mag * mask_h * vocal_weight
    bass_mag = mag * mask_h * bass_weight
    vocal_mask = dsp.soft_mask(vocal_mag, bass_mag + 1e-6, power=2.0)
    vocal_mask *= vocal_weight
    vocal_mask *= mask_h
    bass_mask = dsp.soft_mask(bass_mag, vocal_mag + 1e-6, power=2.0)
    bass_mask *= bass_weight
    bass_mask *= mask_h
    del vocal_mag, bass_mag

    # Nunca somar > 1 (senão um mesmo bin entra em dois stems e o total não
    # reconstrói o mix).
    soma = vocal_mask + bass_mask
    over = soma > 1.0
    vocal_mask[over] /= soma[over]
    bass_mask[over] /= soma[over]
    del soma, over

    # `other` = mask_h menos o que vocais e baixo já levaram (as duas máscaras
    # já contêm mask_h). Se fosse mask_h*(1-v-b) a soma das quatro passaria
    # de 1 e o mix sairia com ganho extra.
    other_mask = np.clip(mask_h - vocal_mask - bass_mask, 0.0, None)
    drums_mask = np.clip(1.0 - mask_h, 0.0, 1.0)
    return (vocal_mask, drums_mask, bass_mask, other_mask)


def _separate_dsp(audio_path: Path, out_dir: Path, log_path: Path | None) -> SeparationResult:
    """Backend DSP no caminho de arquivo: separa e grava **por trechos**.

    É o caminho que o app usa numa música de verdade. Extrair tudo para a RAM
    custaria, além do áudio, quatro stems de 238 MB (estéreo, 710 s) — por
    isso aqui os trechos saem do gerador e vão direto para o WAV.
    """
    try:
        import soundfile as sf
    except ModuleNotFoundError:
        raise dsp.MissingDependency("soundfile", "ler/gravar o áudio no backend DSP") from None
    import numpy as np

    data, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
    channels = data.shape[1]
    paths = {name: out_dir / f"{name}.wav" for name in NOMES_STEMS}
    # `subtype="FLOAT"` porque é o que o resto do pipeline espera ler de volta
    # (32 bits, sem clipping). O `_write_stems` também grava assim.
    handles = {
        name: sf.SoundFile(
            path, mode="w", samplerate=sample_rate, channels=channels, subtype="FLOAT"
        )
        for name, path in paths.items()
    }
    escritas = 0
    try:
        for nomes, trechos in _separar_blocos(data, sample_rate):
            for nome, trecho in zip(nomes, trechos):
                # trecho vem (amostras, canais)
                handles[nome].write(np.asarray(trecho))
            escritas += trechos[0].shape[0]
    finally:
        for handle in handles.values():
            handle.close()
    log = (
        f"backend DSP: {len(paths)} stems (vocals/drums/bass/other) a partir de "
        f"{audio_path.name} — {escritas / sample_rate:.1f} s, gravados por trechos"
    )
    if log_path:
        log_path.write_text(log, encoding="utf-8")
    return SeparationResult("dsp-fallback", "dsp-fallback", paths, sample_rate, log)


def doctor() -> int:
    """`mrq-vs doctor`: mostra o que está instalado e o que falta."""
    rows = detect_backends()
    width = max(len(r.name) for r in rows)
    print("Backends de separação\n")
    for row in rows:
        # opcional e ausente não é falha: marcador "-" em vez de falta
        # nada aqui é "falha": sem demucs o DSP assume; o resto é alternativa
        mark = "ok  " if row.available else "-   "
        version = f"  ({row.version})" if row.version else ""
        print(f"  [{mark}] {row.name:<{width}}  {row.detail}{version}")
    if any(r.opcional and not r.available for r in rows):
        print("  (-) = alternativa opcional; o demucs é o motor recomendado.")
    print(f"\n  {runtime.interpreter_note()}\n")
    from . import media

    # Nada de "[falt]" aqui: em 0.1.8 o programa passou a não usar vermelho
    # nem para sinalizar ausência de opcional — só "ok" ou "-".
    for tool, why in (("ffmpeg", "converter/decodificar mídia"), ("yt-dlp", "baixar do YouTube")):
        path = media.find_tool(tool)
        if not path and tool == "yt-dlp" and media._tem_modulo_ytdlp():
            path = "modulo yt_dlp (embutido)"
        print(f"  [{'ok  ' if path else '-   '}] {tool:<{width}}  {'em ' + path if path else why}")
    try:
        import numpy

        print(f"\n  numpy: ok ({numpy.__version__})")
    except ModuleNotFoundError:
        print("\n  numpy: não instalado — python -m pip install numpy")
    try:
        import soundfile

        print(f"  soundfile: ok ({soundfile.__version__}, libsndfile {soundfile.__libsndfile_version__})")
    except ModuleNotFoundError:
        print("  soundfile: não instalado — python -m pip install soundfile")
    return 0


def as_json(statuses: list[BackendStatus]) -> str:
    return json.dumps([s.as_dict() for s in statuses], ensure_ascii=False, indent=2)
