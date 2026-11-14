"""Estrutura musical: dar NOME às seções que a análise já separa.

O detector de seções (`analysis.estimate_sections`) entrega trechos com rótulo
A/B/C — "estes pedaços se parecem", que é verdade e é útil, mas não é o que a
banda chama de intro, verso, refrão, ponte.

O que este módulo faz é ler os números dessas seções (duração, energia,
repetição) e propor o nome que a música brasileira usa. Regras, em português
claro:

* a **primeira** seção é Intro — é o que toca antes de a banda entrar;
* a **última** é Final quando cai de energia;
* um trecho repetido com a **maior energia média** é o Refrão;
* o trecho que **precede um refrão** é o Pré-refrão, quando a energia sobe;
* a seção repetida que **não** é refrão é o Verso;
* uma seção que **nunca se repete** no meio da música, com energia parecida
  com o refrão, é Ponte;
* o resto é Interlúdio/Instrumental, admitindo o que não sabemos.

Por que por energia e repetição, e não por um modelo de IA: o material que o
programa recebe é o stem separado, que já perdeu parte da informação; um
classificador de seção treinado em pop internacional erra feio em sertanejo e
em gospel ao vivo. As regras abaixo são as que o próprio músico usa ao ouvir,
e é possível explicar cada nome dado — importante quando o programa erra e o
usuário precisa corrigir na tela.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Duração máxima de um pré-refrão, em segundos. 4 compassos em andamento
#: lento (60 BPM) dão 16 s; acima disso é verso, não passagem.
PRE_REFRao_MAX_SEG = 12.0

#: Nomes que a interface e a guia falada conhecem.
INTRO = "Intro"
VERSO = "Verso"
PRE_REFRao = "Pré-refrão"
REFRAO = "Refrão"
PONTE = "Ponte"
SOLO = "Solo"
INTERLUDIO = "Interlúdio"
FINAL = "Final"
#: música que a análise não conseguiu dividir (um bloco só)
MUSICA = "Música"


@dataclass
class Secao:
    """Um trecho com nome musical, no tempo da música."""

    inicio: float
    fim: float
    rotulo: str          # rótulo da análise (A/B/C), preservado
    nome: str            # Intro/Verso/Refrão/...
    energia: float = 0.0
    #: quantas vezes o mesmo material aparece na música
    repeticoes: int = 1
    #: de onde veio o nome (para a tela poder explicar e o usuário corrigir)
    motivo: str = ""

    @property
    def duracao(self) -> float:
        return max(0.0, self.fim - self.inicio)

    def as_dict(self) -> dict:
        return {
            "start": round(self.inicio, 2),
            "end": round(self.fim, 2),
            "rotulo": self.rotulo,
            "nome": self.nome,
            "energia": round(self.energia, 2),
            "repeticoes": self.repeticoes,
            "motivo": self.motivo,
        }


def _duracao_de(item) -> float:
    try:
        return max(0.0, float(getattr(item, "end", 0.0) or 0.0) - float(getattr(item, "start", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _duracao_total(itens: list) -> float:
    if not itens:
        return 0.0
    return max(
        float(getattr(itens[-1], "end", 0.0) or 0.0) - float(getattr(itens[0], "start", 0.0) or 0.0),
        1e-6,
    )


def _repeticoes(rotulos: list[str]) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for r in rotulos:
        contagem[r] = contagem.get(r, 0) + 1
    return contagem


def nomear_secoes(secoes: list, energia_de=None) -> list[Secao]:
    """Nomeia as seções da análise. `secoes` precisa ter start/end/label.

    `energia_de(secao)` devolve a energia média (dB) do trecho; quando não dá
    para medir, as regras de energia são simplesmente ignoradas — o nome sai
    pela posição e pela repetição, que já resolvem a maior parte dos casos.
    """
    itens = list(secoes or [])
    if not itens:
        return []

    rotulos = [str(getattr(s, "label", "A") or "A") for s in itens]
    repetem = _repeticoes(rotulos)

    def energia(s) -> float:
        if energia_de is None:
            return 0.0
        try:
            return float(energia_de(s) or 0.0)
        except Exception:  # noqa: BLE001 - energia é heurística, não crítica
            return 0.0

    energias = [energia(s) for s in itens]
    tem_energia = any(e != 0.0 for e in energias)

    # --- quem é o refrão ----------------------------------------------------
    # O refrão é o MATERIAL MAIS FORTE da música — repetido ou não. Uma música
    # pode ter um refrão que só aparece uma vez (final sem repetição) e um
    # verso que se repete muito: escolher entre os repetidos chamaria o verso
    # de refrão. A intro fica fora da disputa (já tem nome próprio).
    #
    # Empate entre materiais: a primeira aparição do verso é mais cedo, então
    # em empate escolhe-se o material cuja primeira aparição vem DEPOIS —
    # refrão costuma vir depois do primeiro verso.
    refrao = -1
    if len(itens) > 1:
        disputa = [i for i in range(len(itens)) if i != 0] or [0]
        if tem_energia:
            def forca(rotulo: str) -> float:
                vals = [energias[i] for i in disputa if rotulos[i] == rotulo]
                return max(vals) if vals else -1e9

            fortes = {r for r in {rotulos[i] for i in disputa}}
            melhor = max(fortes, key=lambda r: (forca(r), -min(i for i in disputa if rotulos[i] == r)))
            refrao = max(i for i in disputa if rotulos[i] == melhor)
        else:
            # sem energia: o refrão é o material repetido; se nada repete, é a
            # seção mais longa depois da intro (o trecho que "pega")
            repetidos = [i for i in disputa if repetem.get(rotulos[i], 1) > 1]
            refrao = max(repetidos or disputa, key=lambda i: (itens[i].end - itens[i].start))

    rotulo_do_refrao = rotulos[refrao] if refrao >= 0 else "\0"
    refrao_repetido = refrao >= 0 and repetem.get(rotulo_do_refrao, 1) > 1

    saida: list[Secao] = []
    vistos: dict[str, int] = {}
    for i, s in enumerate(itens):
        inicio = float(getattr(s, "start", 0.0) or 0.0)
        fim = float(getattr(s, "end", inicio) or inicio)
        rotulo = rotulos[i]
        vistos[rotulo] = vistos.get(rotulo, 0) + 1
        primeira_vez = vistos[rotulo] == 1

        # "antes do refrão" tem de olhar o PRÓXIMO refrão à frente, não a
        # última aparição dele: escolher a última e comparar `i + 1` fazia
        # nenhum trecho ficar antes do refrão (foi o bug que impedia o
        # pré-refrão de aparecer em música normal).
        rotulo_do_refrao = rotulos[refrao] if refrao >= 0 else "\0"
        proximo_refrao = next(
            (j for j in range(i + 1, len(itens)) if refrao >= 0 and rotulos[j] == rotulo_do_refrao),
            -1,
        )
        antes_do_refrao = proximo_refrao == i + 1 and rotulo != rotulo_do_refrao

        # "refrão" para a exibição: as aparições do material do refrão, OU a
        # posição escolhida quando o material só aparece uma vez
        eh_refrao = (refrao >= 0) and (
            rotulo == rotulo_do_refrao or (i == refrao and not refrao_repetido)
        )

        if len(itens) == 1:
            # música inteira num bloco só: não há estrutura para nomear
            nome, motivo = MUSICA, "a análise não separou seções"
        elif i == 0:
            nome, motivo = INTRO, "primeira seção da música"
        elif i == len(itens) - 1 and len(itens) > 2 and tem_energia and energias[i] <= min(energias) + 1.5:
            nome, motivo = FINAL, "última seção, mais baixa que as outras"
        elif eh_refrao:
            nome = REFRAO
            motivo = "material mais forte" if tem_energia else "material repetido"
        elif (
            antes_do_refrao
            and tem_energia
            and energias[i] >= energias[refrao] - 3.0
            # pré-refrão é um trecho que SOBE de forma audível em relação ao
            # anterior: é a subida que o ouvido reconhece, não a posição.
            # 2 dB é o mínimo que se percebe como "levantou" — abaixo disso é
            # variação de arranjo, não mudança de seção.
            and (i == 0 or energias[i] >= energias[i - 1] + 2.0)
            # e é curto em termos ABSOLUTOS: pré-refrão é uma passagem de 2 ou
            # 4 compassos — 8 s a 120 BPM. Um limite proporcional à música
            # deixava passar verso de 18 s numa música de 2 minutos.
            and _duracao_de(itens[i]) <= PRE_REFRao_MAX_SEG
        ):
            # Material que se repete é pré-refrão; material único é ponte
            # (B depois de ponte é comum em gospel e sertanejo).
            if repetem.get(rotulo, 1) > 1:
                nome, motivo = PRE_REFRao, "trecho curto que sobe e emenda no refrão"
            else:
                nome, motivo = PONTE, "trecho único antes do refrão"
        elif repetem.get(rotulo, 1) > 1:
            nome, motivo = VERSO, "material que se repete"
        elif tem_energia and energias[i] >= (max(energias) - 1.0) and not refrao_repetido:
            nome, motivo = REFRAO, "material mais forte"
        elif primeira_vez and tem_energia and energias[i] >= (max(energias) - 3.0):
            nome, motivo = PONTE, "trecho único, forte"
        else:
            nome, motivo = INTERLUDIO, "trecho único, sem repetição"

        saida.append(
            Secao(
                inicio=round(inicio, 2),
                fim=round(fim, 2),
                rotulo=rotulo,
                nome=nome,
                energia=round(energias[i], 2),
                repeticoes=repetem.get(rotulo, 1),
                motivo=motivo,
            )
        )
    return saida


#: Palavras que se fala ao anunciar a seção. A guia falada usa estas, não o
#: rótulo técnico: o músico precisa ouvir "refrão", não "B".
FALADO = {
    INTRO: "intro",
    VERSO: "verso",
    PRE_REFRao: "pré-refrão",
    REFRAO: "refrão",
    PONTE: "ponte",
    SOLO: "solo",
    INTERLUDIO: "interlúdio",
    FINAL: "final",
    MUSICA: "música",
}


def falado(nome: str) -> str:
    """Como o nome da seção é falado (a guia usa isso)."""
    return FALADO.get(nome, str(nome).lower())


def resumo(secoes: list[Secao]) -> str:
    """Uma linha para o relatório: o mapa que o programa entendeu."""
    if not secoes:
        return "sem seções detectadas"
    partes = [f"{s.nome} ({s.inicio:.0f}s)" for s in secoes]
    return " → ".join(partes)
