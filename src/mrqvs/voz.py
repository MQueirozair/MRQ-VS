"""Voz da guia: números e nomes de seção falados em pt-BR.

Por que arquivos e não fala sintetizada na hora: a voz do sistema (Web
Speech) depende da voz instalada em cada máquina, muda de timbre entre
Windows, macOS e Linux, e **não entra no arquivo exportado** — o `.wav` da
guia sairia mudo no in-ear. Com as palavras gravadas, a guia é a mesma em
qualquer computador e vai junto no guia.wav/clique.wav que o músico leva para
o ensaio.

Cada palavra é um arquivo (`web/voz/palavras/<nome>.wav`), gerado a partir de
uma fala de IA em pt-BR. Um arquivo por palavra, e não uma fala longa cortada
por silêncio: o corte por energia juntava "solo interlúdio" numa palavra só
quando a IA lia sem pausa entre elas, e adivinhar onde termina uma palavra é
exatamente o tipo de erro que estraga a guia (anuncia "refrão" no lugar de
"ponte"). Arquivo separado não tem o que adivinhar.
"""

from __future__ import annotations

from pathlib import Path

#: Números falados, na ordem. O índice + 1 é o número.
NUMEROS = ["um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito"]

#: Nome do arquivo -> palavra que se fala. A chave é a mesma que a interface e
#: a estrutura usam (`estrutura.falado`).
SECOES = {
    "intro": "intro",
    "verso": "verso",
    "pre-refrao": "pré-refrão",
    "refrao": "refrão",
    "ponte": "ponte",
    "solo": "solo",
    "interludio": "interlúdio",
    "final": "final",
    "musica": "música",
}

#: Onde os WAV vivem dentro do pacote.
PASTA = "web/voz/palavras"

#: Pasta fora do pacote usada pelos testes e pela geração manual.
def pasta_padrao() -> Path:
    return Path(__file__).parent / PASTA


def arquivo(nome: str, pasta: Path | None = None) -> Path:
    return Path(pasta or pasta_padrao()) / f"{nome}.wav"


def existe(nome: str, pasta: Path | None = None) -> bool:
    return arquivo(nome, pasta).is_file()


def nomes_esperados() -> list[str]:
    """Todos os arquivos que o pacote deve ter."""
    return [str(i) for i in range(1, len(NUMEROS) + 1)] + list(SECOES)


def faltando(pasta: Path | None = None) -> list[str]:
    return [n for n in nomes_esperados() if not existe(n, pasta)]


def normalizar_audio(origem: Path, destino: Path) -> float:
    """Recorta o silêncio das pontas e normaliza o pico. Devolve os segundos.

    Silêncio nas pontas não é detalhe: cada palavra é agendada no pulso exato,
    e 40 ms de silêncio antes da voz fariam o "um" soar atrasado em relação ao
    clique que está tocando junto.
    """
    import numpy as np
    import soundfile as sf

    dados, taxa = sf.read(str(origem), always_2d=True, dtype="float32")
    mono = dados.mean(axis=1) if dados.ndim > 1 else dados
    mono = np.asarray(mono, dtype=np.float32)

    pico = float(np.abs(mono).max()) if mono.size else 0.0
    if pico <= 0:
        raise ValueError(f"{origem.name} está em silêncio")
    limiar = pico * 0.02
    acima = np.where(np.abs(mono) > limiar)[0]
    if acima.size:
        # 10 ms de folga para o ataque não ficar cortado
        folga = int(0.010 * taxa)
        ini = max(0, int(acima[0]) - folga)
        fim = min(mono.size, int(acima[-1]) + folga)
        mono = mono[ini:fim]

    # normaliza para 0,8: alto o bastante para o in-ear, com margem para somar
    # clique + guia sem estourar
    mono = mono * (0.8 / max(1e-6, float(np.abs(mono).max())))
    destino.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(destino), mono, taxa, subtype="PCM_16")
    return round(mono.size / float(taxa), 3)
