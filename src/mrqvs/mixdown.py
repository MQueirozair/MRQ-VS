"""Mixdown e edições do editor (Studio).

Por que isto vive no servidor e não no navegador: exportar "o que o usuário
está ouvindo" exige somar N arquivos com volume, mute, solo e pan. Fazer isso
no navegador significaria baixar tudo de novo, tocar em tempo real para
gravar (Web Audio não exporta offline de forma confiável) e ainda assim o
resultado sairia pior. Aqui é aritmética de amostras: rápido e exato.

O que NÃO se faz aqui: tocar nos arquivos originais. Todo resultado vai para
um arquivo novo (`_MIX.wav`), e o mix nunca sobrescreve um stem.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


def _ler_mono(caminho: Path, sample_rate: int):
    """Lê um arquivo de áudio e devolve (mono_ou_estereo, taxa)."""
    import numpy as np
    import soundfile as sf

    dados, taxa = sf.read(str(caminho), always_2d=True, dtype="float32")
    if taxa != sample_rate:
        from . import dsp

        dados = dsp.resample_linear(dados, taxa, sample_rate)
    return np.asarray(dados, dtype="float32"), sample_rate


def mixar(
    faixas: list[dict],
    destino: Path,
    sample_rate: int = 44100,
) -> dict:
    """Soma as faixas como o editor as apresenta.

    `faixas` é a lista que o navegador manda:
        {"caminho": "/caminho/absoluto.wav", "volume": 0..1,
         "pan": -1..1, "mudo": bool, "solo": bool}

    Regras (as mesmas da tela, e é por isso que ficam num lugar só):
      - se existe pelo menos um solo, só os solos entram;
      - mudo silencia aquela faixa, mesmo que outra esteja em solo;
      - pan é equal-power: sem isso, mover para a esquerda abaixa o volume
        total percebido em vez de mover o som.

    Devolve {"arquivo", "duracao", "faixas", "pico"} — e o `pico` importa:
    se a soma estourar 1.0, o arquivo sai distorcido, então normalizamos e
    avisamos em vez de entregar clipping calado.
    """
    import numpy as np

    try:
        import soundfile as sf
    except ModuleNotFoundError:
        from . import dsp

        raise dsp.MissingDependency("soundfile", "exportar a mixagem") from None

    validas = [f for f in faixas if f.get("caminho") and Path(f["caminho"]).is_file()]
    if not validas:
        raise ValueError("nenhuma faixa válida para mixar")

    tem_solo = any(f.get("solo") for f in validas)
    soma = None
    usadas = 0
    for f in validas:
        entra = f.get("solo") if tem_solo else not f.get("mudo")
        if not entra or f.get("mudo"):
            continue
        dados, _ = _ler_mono(Path(f["caminho"]), sample_rate)
        mono = dados.mean(axis=1) if dados.ndim > 1 else dados

        volume = float(f.get("volume", 1.0))
        volume = max(0.0, min(2.0, volume))
        pan = max(-1.0, min(1.0, float(f.get("pan", 0.0))))
        # equal-power: ângulo a 45° quando centrado
        ang = (pan + 1.0) * math.pi / 4.0
        esq = mono * volume * math.cos(ang)
        dir_ = mono * volume * math.sin(ang)

        if soma is None:
            soma = np.zeros((mono.size, 2), dtype=np.float32)
        if esq.size > soma.shape[0]:
            extra = esq.size - soma.shape[0]
            soma = np.pad(soma, ((0, extra), (0, 0)))
        soma[: esq.size, 0] += esq
        soma[: dir_.size, 1] += dir_
        usadas += 1

    if soma is None or not usadas:
        raise ValueError("todas as faixas estão mudas: nada para exportar")

    pico = float(np.max(np.abs(soma)))
    normalizado = False
    if pico > 0.99:
        soma *= 0.99 / pico
        normalizado = True

    destino.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(destino), soma, sample_rate, subtype="PCM_16")
    return {
        "arquivo": str(destino),
        "duracao": round(soma.shape[0] / sample_rate, 3),
        "faixas": usadas,
        "pico": round(pico, 4),
        "normalizado": normalizado,
    }


# --------------------------------------------------------------- edições ---
#: nome do arquivo de edições dentro da pasta `-apoio`. Fica ao lado do
#: `projeto.json` (gerado pelo programa) em vez de dentro dele: o projeto.json
#: é saída da análise e pode ser refeito; a edição é trabalho do usuário e não
#: pode ser perdida se ele reprocessar a música.
ARQUIVO_EDICOES = "edicoes.json"


def edicoes_path(apoio: Path) -> Path:
    return Path(apoio) / ARQUIVO_EDICOES


def ler_edicoes(apoio: Path) -> dict:
    """Edições salvas, ou um esqueleto vazio."""
    caminho = edicoes_path(apoio)
    vazio = {
        "acordes": None,
        "secoes": None,
        "compasso": None,
        "denominador": None,
        "bpm": None,
        "bpmManual": None,
        "offsetInicial": None,
        "mudancasCompasso": None,
        "tom": None,
        "transposicao": None,
        "master": None,
        "metronomo": None,
        "guiaAtiva": None,
        "contagem": None,
        "zoomOnda": None,
        "alturaLinha": None,
        "mix": None,
        "atualizado_em": "",
    }
    if not caminho.is_file():
        return vazio
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vazio
    if not isinstance(dados, dict):
        return vazio
    vazio.update({k: dados.get(k) for k in vazio if k in dados})
    return vazio


def salvar_edicoes(apoio: Path, payload: dict) -> dict:
    """Grava as edições do usuário.

    `acordes`/`secoes` chegando como `null` significa "não mexido" — e isso é
    diferente de lista vazia ("o usuário apagou todos"). Preservar essa
    diferença é o que permite voltar ao detectado sem perder a edição.
    """
    import time

    apoio = Path(apoio)
    apoio.mkdir(parents=True, exist_ok=True)
    atual = ler_edicoes(apoio)
    for chave in (
        "acordes",
        "secoes",
        "compasso",
        "denominador",
        "bpm",
        "bpmManual",
        "offsetInicial",
        "mudancasCompasso",
        "tom",
        "transposicao",
        "master",
        "metronomo",
        "guiaAtiva",
        "contagem",
        "zoomOnda",
        "alturaLinha",
        "mix",
    ):
        if chave in payload:
            atual[chave] = payload[chave]
    atual["atualizado_em"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    caminho = edicoes_path(apoio)
    caminho.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
    return atual
