"""Utilidades de DSP em numpy puro — sem scipy, sem dependências além de numpy.

Todo o resto do `mrqvs` é escrito em cima destas funções (STFT, filtros,
detecção de BPM por autocorrelação, matrizes de gênero etc.), de propósito:
DSP feito à mão é auditável, testável e não arrasta um segundo ecossistema
(laço de C) além do que o separador de stems já precisa.

Se o numpy não estiver instalado (ex.: rodando o subset de funções de texto),
as funções que dependem dele levantam `MissingDependency` com a instrução de
instalação — nada de `ImportError` cru no meio do processamento.
"""

from __future__ import annotations

import math
from typing import Optional

try:  # pragma: no cover - depende do ambiente
    import numpy as np
except ModuleNotFoundError as exc:  # pragma: no cover - depende do ambiente
    np = None  # type: ignore[assignment]
    _NUMPY_IMPORT_ERROR: Optional[Exception] = exc
else:
    _NUMPY_IMPORT_ERROR = None


class MissingDependency(RuntimeError):
    """Dependência de processamento ausente, com instrução de instalação."""

    def __init__(self, package: str, why: str) -> None:
        super().__init__(
            f"A dependência '{package}' é necessária para {why}.\n"
            f"Instale com:  python -m pip install {package}"
        )
        self.package = package


def require_numpy(why: str) -> None:
    if np is None:  # pragma: no cover - depende do ambiente
        raise MissingDependency("numpy", why)


# ---------------------------------------------------------------------------
# Janelas e STFT
# ---------------------------------------------------------------------------


def hann(n: int) -> "np.ndarray":
    require_numpy("gerar janelas de análise")
    return np.hanning(n).astype(np.float32)


#: Quadros por bloco na STFT/iSTFT. Limita os buffers temporários a poucos MB.
STFT_BLOCO = 256


def stft(
    signal: "np.ndarray",
    n_fft: int = 4096,
    hop: Optional[int] = None,
    window: Optional["np.ndarray"] = None,
) -> "np.ndarray":
    """STFT de um sinal 1-D. Devolve complexo com forma (frames, bins).

    `n_fft` tem que ser par (bin de Nyquist no fim), que é o que esperamos
    também na inversa.

    Processa em blocos de `STFT_BLOCO` quadros: a versão "de uma vez" montava
    uma matriz de índices int64 (1 GB para 710 s a 44,1 kHz) mais um buffer
    de 500 MB, e era o que estourava a memória em músicas longas. O resultado
    é bit a bit o mesmo.
    """
    require_numpy("calcular a STFT")
    signal = np.asarray(signal, dtype=np.float32)
    hop = hop or n_fft // 4
    window = hann(n_fft) if window is None else window
    if signal.shape[0] < n_fft:
        signal = np.pad(signal, (0, n_fft - signal.shape[0]))
    # Frames cobrindo **todas** as amostras (não só até o último frame cheio):
    # sem isso, o último < hop amostras e o rabo das janelas de borda ficam
    # fora da análise e a soma das máscaras deixa de reconstruir o sinal.
    frames = 1 + int(np.ceil(max(signal.shape[0] - n_fft, 0) / hop)) + 1
    pad = n_fft + hop * (frames - 1) - signal.shape[0]
    if pad > 0:
        signal = np.pad(signal, (0, pad))
    bins = n_fft // 2 + 1
    spec = np.empty((frames, bins), dtype=np.complex64)
    base = np.arange(n_fft, dtype=np.int64)
    for i in range(0, frames, STFT_BLOCO):
        j = min(i + STFT_BLOCO, frames)
        idx = base[None, :] + hop * np.arange(i, j, dtype=np.int64)[:, None]
        buf = signal[idx] * window[None, :]
        spec[i:j] = np.fft.rfft(buf, axis=1)
        del idx, buf
    return spec


def istft(
    spec: "np.ndarray",
    n_fft: int = 4096,
    hop: Optional[int] = None,
    window: Optional["np.ndarray"] = None,
    length: Optional[int] = None,
) -> "np.ndarray":
    """Inversa da STFT acima (overlap-add com normalização pela janela²).

    Também em blocos: a `irfft` de todos os quadros de uma vez custava
    centenas de MB por stem.
    """
    require_numpy("reconstruir o áudio de uma STFT")
    hop = hop or n_fft // 4
    window = hann(n_fft) if window is None else window
    frames = spec.shape[0]
    total = n_fft + hop * (frames - 1)
    out = np.zeros(total, dtype=np.float32)
    norm = np.zeros(total, dtype=np.float32)
    win_sq = (window**2).astype(np.float32)
    for i in range(0, frames, STFT_BLOCO):
        j = min(i + STFT_BLOCO, frames)
        bloco = np.fft.irfft(np.asarray(spec[i:j]), n=n_fft).astype(np.float32)
        bloco *= window[None, :]
        for k in range(j - i):
            start = (i + k) * hop
            out[start : start + n_fft] += bloco[k]
            norm[start : start + n_fft] += win_sq
        del bloco
    out /= np.maximum(norm, 1e-8)
    if length is not None:
        if out.shape[0] < length:
            out = np.pad(out, (0, length - out.shape[0]))
        out = out[:length]
    return out


def stft_quadros(n_amostras: int, n_fft: int, hop: int) -> int:
    """Quantidade de quadros que `stft` produz para `n_amostras` amostras."""
    return 1 + int(np.ceil(max(n_amostras - n_fft, 0) / hop)) + 1


def stft_faixa(
    signal: "np.ndarray",
    n_fft: int,
    hop: int,
    janela: "np.ndarray",
    inicio: int,
    fim: int,
) -> "np.ndarray":
    """STFT só dos quadros `[inicio, fim)`, sem montar o espectrograma todo.

    Idêntica às colunas correspondentes de `stft(signal)` — o padding do fim
    do sinal é feito por mascaramento (`idx < n`), sem copiar o sinal.
    """
    n = int(np.shape(signal)[0])
    base = np.arange(n_fft, dtype=np.int64)
    idx = base[None, :] + hop * np.arange(inicio, fim, dtype=np.int64)[:, None]
    dentro = idx < n
    buf = signal[np.clip(idx, 0, max(n - 1, 0))] * janela[None, :]
    buf *= dentro
    return np.fft.rfft(buf, axis=1).astype(np.complex64)


def istft_soma(
    destino: "np.ndarray",
    norm: "np.ndarray",
    spec: "np.ndarray",
    n_fft: int,
    hop: int,
    janela: "np.ndarray",
    primeiro_quadro: int,
    somar_norm: bool = True,
) -> None:
    """Overlap-add de `spec` (quadros a partir de `primeiro_quadro`).

    Soma em `destino` e, se `somar_norm`, em `norm` a janela² — o `norm` pode
    ser acumulado uma vez por canal e reaproveitado por todos os stems.
    """
    win_sq = janela**2
    for k in range(spec.shape[0]):
        frame = np.fft.irfft(spec[k], n=n_fft).astype(np.float32) * janela
        start = (primeiro_quadro + k) * hop
        destino[start : start + n_fft] += frame
        if somar_norm:
            norm[start : start + n_fft] += win_sq


def istft_finaliza(destino: "np.ndarray", norm: "np.ndarray", length: int) -> "np.ndarray":
    """Divide pelo `norm` acumulado e corta/estende para `length` amostras."""
    destino /= np.maximum(norm, 1e-8)
    if destino.shape[0] < length:
        destino = np.pad(destino, (0, length - destino.shape[0]))
    return destino[:length]


def stft_freqs(n_fft: int, sample_rate: int) -> "np.ndarray":
    require_numpy("listar as frequências da STFT")
    return np.fft.rfftfreq(n_fft, d=1.0 / sample_rate).astype(np.float32)


# ---------------------------------------------------------------------------
# Espectrograma / matrizes espectrais auxiliares
# ---------------------------------------------------------------------------


def power_spectrogram(spec: "np.ndarray") -> "np.ndarray":
    require_numpy("calcular o espectrograma")
    return (np.abs(spec) ** 2).astype(np.float32)


#: Orçamento de memória do filtro de mediana, em bytes (64 MB). O `np.median`
#: copia a janela deslizante inteira, então processar 710 s de uma vez pediria
#: ~8 GB — foi exatamente o `Unable to allocate 7.87 GiB` relatado no Windows.
_MEDIAN_BUDGET = 64 * 1024 * 1024


def _mediana_central(janelas: "np.ndarray", axis: int = -1) -> "np.ndarray":
    """Mediana de uma janela deslizante com uma única cópia.

    `sliding_window_view` é view; o partition precisa de array gravável, então
    copiamos uma vez. Depois basta a posição central — é a definição de
    mediana para um número ímpar de amostras.
    """
    dados = np.array(janelas, dtype=np.float32, copy=True)
    k = dados.shape[axis] // 2
    dados.partition(k, axis=axis)  # in-place: sem segunda cópia
    return np.take(dados, k, axis=axis)


def _median_core(arr: "np.ndarray", width: int, axis: int) -> "np.ndarray":
    """Mediana deslizante **sem padding**, em faixas com memória limitada.

    Contrato explícito (fonte de dois bugs quando era implícito):
    a saída tem `arr.shape[axis] - width + 1` posições naquele eixo — é a
    janela que cabe de fato. Quem chama é que decide como tratar as bordas.
    """
    require_numpy("filtrar o espectrograma")
    largura = int(width)
    if largura % 2 == 0:
        largura += 1
    n_linhas, n_colunas = arr.shape
    if largura > (arr.shape[axis]):
        raise ValueError("janela maior que o eixo filtrado")

    if axis == 0:
        total = n_colunas
        custo = max(1, n_linhas * largura * 4)
        n_out = n_linhas - largura + 1
        saida = np.empty((n_out, n_colunas), dtype=np.float32)
    else:
        total = n_linhas
        custo = max(1, n_colunas * largura * 4)
        n_out = n_colunas - largura + 1
        saida = np.empty((n_linhas, n_out), dtype=np.float32)

    passo = max(1, min(total, _MEDIAN_BUDGET // custo))
    for inicio in range(0, total, passo):
        fim = min(inicio + passo, total)
        if axis == 0:
            janelas = np.lib.stride_tricks.sliding_window_view(arr[:, inicio:fim], largura, axis=0)
            saida[:, inicio:fim] = _mediana_central(janelas, axis=-1)
        else:
            janelas = np.lib.stride_tricks.sliding_window_view(arr[inicio:fim], largura, axis=1)
            saida[inicio:fim] = _mediana_central(janelas, axis=-1)
    return saida.astype(arr.dtype, copy=False)


def median_filter_harmonic(spec: "np.ndarray", width: int = 17) -> "np.ndarray":
    """Filtro de mediana sobre cada **harmônico** (linha de frequência).

    Base do HPSS clássico (Fitzgerald 2010): percussão aparece como picos
    verticais, harmonia como linhas horizontais. A mediana longa ao longo do
    tempo apaga a percussão e deixa a melodia.
    """
    require_numpy("filtrar o espectrograma")
    half = int(width) // 2
    padded = np.pad(spec, ((half, half), (0, 0)), mode="edge")
    return _median_core(padded, width, axis=0)


def median_filter_percussive(spec: "np.ndarray", width: int = 17) -> "np.ndarray":
    """Mediana ao longo da **frequência** (mesma ideia, eixo trocado)."""
    require_numpy("filtrar o espectrograma")
    half = int(width) // 2
    padded = np.pad(spec, ((0, 0), (half, half)), mode="edge")
    return _median_core(padded, width, axis=1)


#: Quadros por bloco no HPSS. 512 quadros ≈ 6 s a 44,1 kHz com hop 1024.
HPSS_BLOCO = 512


def hpss_mask_h(ctx: "np.ndarray", width: int = 31, power: float = 1.0) -> "np.ndarray":
    """Máscara harmônica de um trecho **com contexto** no tempo.

    Convenção do espectrograma: `(quadros, bins)` — a mesma de `stft()`. O
    eixo 0 é o tempo, o 1 é a frequência.

    `ctx` são quadros consecutivos já com `width//2` quadros de contexto de
    cada lado; a saída tem uma linha por quadro **central**
    (`ctx.shape[0] - width + 1` linhas).

    - harmônico = mediana ao longo do **tempo** (apaga picos curtos, sobra o
      que se sustenta = melodia/instrumentos);
    - percussivo = mediana ao longo da **frequência** (apaga o que é largo em
      frequência, sobra o ataque = bateria).
    """
    require_numpy("calcular as máscaras do HPSS")
    half = max(1, int(width) // 2)
    if ctx.shape[0] < width:
        raise ValueError("contexto menor que a janela do HPSS")
    # harmônico: mediana no tempo (perde `width-1` quadros, centrados)
    h = _median_core(ctx, width, axis=0)
    # percussivo: mediana na frequência, com borda de graves/agudos repetida
    p = _median_core(np.pad(ctx, ((0, 0), (half, half)), mode="edge"), width, axis=1)
    # alinha as duas: `p` cobre o contexto todo, `h` só o miolo
    off = (ctx.shape[0] - h.shape[0]) // 2
    p = p[off : off + h.shape[0]]
    return soft_mask(h, p, power=power)


def hpss_masks(
    mag: "np.ndarray",
    width: int = 31,
    bloco: int = HPSS_BLOCO,
    power: float = 1.0,
    apenas_harmonica: bool = False,
) -> tuple["np.ndarray", "np.ndarray"] | "np.ndarray":
    """Máscaras harmônica e percussiva (HPSS) de um espectrograma inteiro.

    `mag` é `(quadros, bins)`, igual à saída de `stft`.

    Por que em blocos: cada matriz tem o tamanho do espectrograma — numa
    faixa de 710 s são 33257 × 2049 float32 ≈ 273 MB cada, e o `np.median`
    clássico pedia 7,87 GiB de uma vez (o erro relatado no Windows).

    `apenas_harmonica=True` devolve só a máscara harmônica: a percussiva é
    exatamente `1 - h`, então guardá-la é 273 MB de RAM por nada.
    """
    require_numpy("calcular as máscaras do HPSS")
    n_quadros = mag.shape[0]
    half = max(1, int(width) // 2)
    # contexto de tempo repetindo as bordas do sinal (`edge`), uma vez só
    mag_pad = np.pad(mag, ((half, half), (0, 0)), mode="edge")
    saida_h = np.empty_like(mag)
    saida_p = None if apenas_harmonica else np.empty_like(mag)
    for inicio in range(0, n_quadros, bloco):
        fim = min(inicio + bloco, n_quadros)
        # contexto ao redor; no array padeado o quadro `t` mora em `t + half`
        mask_h = hpss_mask_h(mag_pad[inicio : fim + 2 * half], width=width, power=power)
        saida_h[inicio:fim] = mask_h
        if saida_p is not None:
            saida_p[inicio:fim] = np.clip(1.0 - mask_h, 0.0, 1.0)
        del mask_h
    if saida_p is None:
        return saida_h
    return saida_h, saida_p


def soft_mask(
    target: "np.ndarray",
    other: "np.ndarray",
    power: float = 2.0,
    saida: Optional["np.ndarray"] = None,
) -> "np.ndarray":
    """Máscara tipo Wiener entre duas estimativas espectrais.

    `target**p / (target**p + other**p + eps)` — suave (sem porta dura),
    reduz "musical noise" comparado com uma máscara binária.

    Evita alocar `target ** power` como array novo (260 MB por chamada numa
    faixa de 710 s, e o pipeline chama duas vezes por canal): eleva ao
    quadrado em buffers reaproveitáveis. `saida` é um buffer do chamador; sem
    ele um float32 é alocado aqui.
    """
    require_numpy("calcular máscaras espectrais")
    t = np.array(target, dtype=np.float32, copy=True) if saida is None else saida
    np.maximum(t, 0.0, out=t)
    o = np.maximum(np.asarray(other, dtype=np.float32), 0.0)
    np.power(t, power, out=t)
    np.power(o, power, out=o)
    t += o
    t += 1e-10
    del o
    # numerador precisa do original; `num` é descartado na divisão
    num = np.maximum(np.asarray(target, dtype=np.float32), 0.0)
    np.power(num, power, out=num)
    np.divide(num, t, out=t)
    return t


# ---------------------------------------------------------------------------
# BPM / beat-grid
# ---------------------------------------------------------------------------


def onset_envelope(spec: "np.ndarray", sample_rate: int, hop: int) -> "np.ndarray":
    """Envelope de onsets por fluxo espectral (soma das diferenças positivas).

    Mesma ideia do "spectral flux" do librosa: quanto a energia cresce por
    bin entre dois frames consecutivos, somado. Barato e funciona bem para
    música com percussão.
    """
    require_numpy("calcular o envelope de onsets")
    mag = np.log1p(np.abs(spec).astype(np.float32))
    diff = np.diff(mag, axis=0)
    flux = np.maximum(diff, 0.0).sum(axis=1)
    # Suaviza para tirar o ruído de alta frequência do cálculo de tempo.
    if flux.size >= 3:
        kernel = np.array([0.25, 0.5, 0.25], dtype=np.float32)
        flux = np.convolve(flux, kernel, mode="same")
    env = np.concatenate([[0.0], flux]).astype(np.float32)
    # Remove a média (autocorrelação sem o pico em lag 0 dominando).
    return env - env.mean() if env.size else env


def tempo_from_onset_envelope(
    env: "np.ndarray",
    hop: int,
    sample_rate: int,
    min_bpm: float = 50.0,
    max_bpm: float = 220.0,
) -> tuple[float, float]:
    """BPM + confiança pela autocorrelação do envelope de onsets.

    Devolve (bpm, confiança 0..1). A confiança é o pico normalizado pela
    energia total da autocorrelação — baixa em material sem pulso claro
    (pad, textura), o que a interface usa para avisar em vez de mentir.
    """
    require_numpy("detectar o BPM")
    env = np.asarray(env, dtype=np.float32)
    if env.size < 8 or not np.any(env):
        return 0.0, 0.0
    frame_rate = sample_rate / hop
    min_lag = max(1, int(math.floor(frame_rate * 60.0 / max_bpm)))
    max_lag = min(env.size - 1, int(math.ceil(frame_rate * 60.0 / min_bpm)))
    if max_lag <= min_lag:
        return 0.0, 0.0
    spectrum = np.fft.rfft(env, n=2 * env.size)
    ac = np.fft.irfft(spectrum * np.conjugate(spectrum))[: env.size].real
    if ac[0] <= 0:
        return 0.0, 0.0
    seg = ac[min_lag : max_lag + 1]
    if seg.size == 0:
        return 0.0, 0.0
    best = int(np.argmax(seg))
    lag = best + min_lag
    # Parábola nos 3 pontos do pico: precisão sub-frame (senão o BPM fica
    # sempre num inteiro "chutado" pela resolução do hop).
    if 0 < best < seg.size - 1:
        y0, y1, y2 = float(seg[best - 1]), float(seg[best]), float(seg[best + 1])
        denom = y0 - 2.0 * y1 + y2
        if abs(denom) > 1e-12:
            lag = lag + 0.5 * (y0 - y2) / denom
    bpm = 60.0 * frame_rate / lag
    confidence = float(np.clip(seg[best] / (ac[0] + 1e-12), 0.0, 1.0))
    # Oitava: energia "batendo" a 90 e a 180 são a mesma batida; prefere a
    # faixa 70..160, que é onde o ouvido humano conta o pulso na maioria do
    # repertório popular.
    while bpm < 70.0 and bpm * 2 <= max_bpm:
        bpm *= 2
    while bpm > 160.0 and bpm / 2 >= min_bpm:
        bpm /= 2
    return round(float(bpm), 1), confidence


def beat_times(
    env: "np.ndarray",
    hop: int,
    sample_rate: int,
    bpm: float,
) -> list[float]:
    """Grade de batidas alinhada ao envelope de onsets (primeiro tempo + passo)."""
    require_numpy("montar a grade de batidas")
    if bpm <= 0:
        return []
    env = np.asarray(env, dtype=np.float32)
    if env.size == 0:
        return []
    period = max(1, int(round(60.0 / bpm * sample_rate / hop)))
    counts = max(1, env.size // period)
    best_offset, best_score = 0, -1.0
    for offset in range(min(period, env.size)):
        idx = offset + period * np.arange(counts)
        idx = idx[idx < env.size]
        if idx.size == 0:
            continue
        score = float(env[idx].mean())
        if score > best_score:
            best_offset, best_score = offset, score
    return beat_grid(sample_rate, bpm, env.size / (sample_rate / hop), start=best_offset / (sample_rate / hop))


def beat_grid(sample_rate: int, bpm: float, duration: float, start: float = 0.0) -> list[float]:
    """Grade **regular** de `bpm` a partir de `start`.

    É a grade que serve para exportar clique e cortar em compasso: o usuário
    quer a batida estável, não as micro-variações de um baterista.
    """
    if bpm <= 0 or duration <= 0:
        return []
    step = 60.0 / bpm
    out: list[float] = []
    t = max(0.0, start)
    while t < duration:
        out.append(round(t, 4))
        t += step
    return out


# ---------------------------------------------------------------------------
# Pós-processamento / mistura de canais
# ---------------------------------------------------------------------------


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def gain_to_db(gain: float) -> float:
    return 20.0 * math.log10(max(gain, 1e-9))


def peak(signal: "np.ndarray") -> float:
    require_numpy("medir o pico de um sinal")
    return float(np.max(np.abs(signal))) if signal.size else 0.0


def rms(signal: "np.ndarray") -> float:
    require_numpy("medir o RMS de um sinal")
    return float(np.sqrt(np.mean(signal**2))) if signal.size else 0.0


def db_rms(signal: "np.ndarray") -> float:
    return gain_to_db(rms(signal))


def to_mono(audio: "np.ndarray") -> "np.ndarray":
    """(frames, canais) -> (frames,). Aceita já-mono."""
    require_numpy("converter para mono")
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1)


def to_stereo(audio: "np.ndarray") -> "np.ndarray":
    """Aceita (frames,), (frames,1) ou (frames,canais) e devolve (frames,2)."""
    require_numpy("converter para estéreo")
    if audio.ndim == 1:
        return np.stack([audio, audio], axis=1)
    if audio.shape[1] == 2:
        return audio
    if audio.shape[1] == 1:
        return np.repeat(audio, 2, axis=1)
    # Fora do caso normal (multicanal vindo de um container exótico):
    # mantém os dois primeiros canais.
    return audio[:, :2]


def fade(signal: "np.ndarray", sample_rate: int, fade_in: float = 0.005, fade_out: float = 0.02) -> "np.ndarray":
    """Rampa curta nas pontas — evita clique em amostra cortada no zero."""
    require_numpy("aplicar fade")
    out = signal.copy()
    n_in = min(int(fade_in * sample_rate), out.shape[0] // 2)
    n_out = min(int(fade_out * sample_rate), out.shape[0] // 2)
    if n_in > 0:
        out[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=out.dtype)[:, None] if out.ndim > 1 else np.linspace(0.0, 1.0, n_in, dtype=out.dtype)
    if n_out > 0:
        ramp = np.linspace(1.0, 0.0, n_out, dtype=out.dtype)
        out[-n_out:] *= ramp[:, None] if out.ndim > 1 else ramp
    return out


def normalize_peak(signal: "np.ndarray", target_db: float = -1.0) -> "np.ndarray":
    p = peak(signal)
    if p <= 0:
        return signal
    return (signal * (db_to_gain(target_db) / p)).astype(signal.dtype)


def resample_linear(signal: "np.ndarray", src_rate: int, dst_rate: int) -> "np.ndarray":
    """Reamostragem linear simples (interpolação 1ª ordem).

    Suficiente para o caminho de fallback e para reduzir o material de
    análise (BPM/EQ); o áudio final sempre passa por um resampler de
    qualidade (soxr/librosa) quando o backend de IA está disponível — aqui
    não vale arrastar outra dependência só para isso.
    """
    require_numpy("reamostrar áudio")
    if src_rate == dst_rate or signal.size == 0:
        return signal
    n_out = int(round(signal.shape[0] * dst_rate / src_rate))
    x_old = np.linspace(0.0, 1.0, signal.shape[0], endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    if signal.ndim == 1:
        return np.interp(x_new, x_old, signal).astype(np.float32)
    return np.stack(
        [np.interp(x_new, x_old, signal[:, c]) for c in range(signal.shape[1])], axis=1
    ).astype(np.float32)
