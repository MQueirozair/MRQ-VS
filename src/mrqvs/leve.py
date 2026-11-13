"""Motor leve: o que o Spleeter fazia, sem o Spleeter.

O problema que este modulo resolve
----------------------------------
A tela mostrava "spleeter - opcional" em cinza com a explicacao "foi
descontinuado em 2022 e exige TensorFlow 2.12.1, que so existe para Python
ate 3.11". Verdadeiro, e inutil: o selo dizia "nao da" sem dizer "entao use
isto". O usuario ficava com um item cinza na tela e nenhuma alternativa.

O Spleeter existia por tres motivos: rodar em CPU fraca, ser leve de
instalar e ser rapido. Dois caminhos resolvem esses tres motivos hoje:

1. `--two-stems=vocals` no Demucs (que o programa JA tem)
   O Demucs separa voz acompanhamento gastando ~1/3 do tempo do modo de 6
   stems, porque nao precisa alinhar 6 saidas. E o mesmo modelo, entao a
   qualidade nao cai: so o numero de saidas cai. Para playback de igreja
   (voz de um lado, base do outro) e exatamente o que se precisa.

2. open-unmix (`umxl`) como backend de verdade
   E o sucessor natural do Spleeter: mesmo papel (referencia academica,
   leve, roda em CPU), mesmo tipo de instalacao (pip), e funciona no
   Python 3.13 — ao contrario do Spleeter. Custa ~300 MB de pesos contra
   ~1 GB do Demucs com torch. Fica abaixo do Demucs em qualidade e isso
   esta escrito na tela: 5,9 dB contra 7,7 dB de media.

O que NAO fazer: embutir o Spleeter num Python 3.11 paralelo. Seriam ~400 MB
a mais no pacote, para instalar um motor pior que o que ja esta la e sem
manutencao desde 2022. Nao paga o custo.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Por que cada caminho existe e para quem serve.
CAMINHOS: dict[str, dict[str, str]] = {
    "rapido": {
        "nome": "Rápido: só voz + instrumental",
        "motor": "demucs --two-stems=vocals",
        "precisa": "Demucs (já instalado se você usa a IA)",
        "tempo": "≈ 1/3 do tempo do modo completo",
        "qualidade": "mesma qualidade de voz do Demucs (8,9 dB no htdemucs_ft)",
        "quando": (
            "é o caso da maioria: você quer a voz separada e a base tocando "
            "junto. Não precisa de bateria, baixo e resto em arquivos "
            "separados."
        ),
    },
    "leve": {
        "nome": "Leve: 4 stems num PC sem placa de vídeo",
        "motor": "open-unmix (umxl)",
        "precisa": "open-unmix + torch (~300 MB, roda em CPU)",
        "tempo": "mais rápido que o Demucs em CPU",
        "qualidade": "5,9 dB de média — abaixo do Demucs (7,7 dB), acima do DSP",
        "quando": (
            "você quer bateria, baixo, voz e resto separados, mas o Demucs "
            "demora demais na sua máquina. É o papel que o Spleeter tinha."
        ),
    },
}

#: Comparação honesta, para a tela e para o relatório.
COMPARACAO: tuple[tuple[str, str, str, str], ...] = (
    # motor, instalação, SDR médio, roda no Python 3.13?
    ("Spleeter (descontinuado)", "TensorFlow 2.12 · ~400 MB", "5,4 dB", "não"),
    ("open-unmix (umxl)", "torch · ~300 MB", "5,9 dB", "sim"),
    ("Demucs htdemucs", "torch · ~1 GB", "7,7 dB", "sim"),
    ("Demucs htdemucs_ft", "+ 4× mais lento", "8,5 dB", "sim"),
    ("BS-RoFormer (voz)", "audio-separator", "voz 12,9 dB", "sim"),
)


@dataclass(frozen=True)
class Caminho:
    chave: str
    nome: str
    motor: str
    precisa: str
    tempo: str
    qualidade: str
    quando: str
    disponivel: bool = False


def caminhos(demucs_ok: bool = False, openunmix_ok: bool = False) -> list[Caminho]:
    """Os dois caminhos, com o que ja esta instalado marcado."""
    prontos = {"rapido": demucs_ok, "leve": openunmix_ok}
    return [
        Caminho(chave=chave, disponivel=prontos[chave], **dados)
        for chave, dados in CAMINHOS.items()
    ]


def resumo() -> str:
    """Uma frase para o rodapé da tela — sem jargão e sem promessa vazia."""
    return (
        "Spleeter está fora porque exige um Python antigo. No lugar dele o "
        "MRQ VS tem dois caminhos: separar só voz + instrumental (3× mais "
        "rápido, mesma qualidade de voz) ou instalar o open-unmix, que roda "
        "no Python atual e é o substituto leve do Spleeter."
    )


def comando_dois_stems(audio: str, destino: str, modelo: str = "htdemucs_ft") -> list[str]:
    """Argumentos do Demucs no modo voz + instrumental.

    `--two-stems=vocals` faz o Demucs calcular duas saidas em vez de seis.
    O tempo cai na proporcao e a memória também, que é o que permite rodar
    numa máquina modesta.
    """
    return ["--name", modelo, "--two-stems", "vocals", "-o", destino, audio]
