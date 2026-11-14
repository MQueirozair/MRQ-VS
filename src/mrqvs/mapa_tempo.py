"""Mapa de tempo: a régua mestra do projeto, com BPM e compasso que mudam.

Por que isto existe separado de `analysis.TempoInfo`: o analisador responde
"o BPM é 96". Só que música de verdade acelera no refrão, faz um rallentando
no fim e troca de 4/4 para 6/8 na ponte. Guardar um número só obrigava a tela
(e o clique, e a cifra, e o MIDI) a fingir que o andamento é constante.

O mapa é a **única** fonte de conversão entre tempo (segundos) e posição
musical (batida, compasso) em todo o programa. Régua, cifra, clique, MIDI,
exportação PDF e a reabertura do projeto passam por aqui — é o que mantém
tudo em registro quando o andamento muda.

Como a grade funciona (mesma convenção do editor, em `web/index.html`):

* `batidas` é a grade de **semínimas** detectada (segundos por batida);
* a fórmula do compasso diz quantos pulsos cabem nele, e o denominador diz
  quanto vale cada pulso em semínimas: 6/8 = 3 semínimas, 7/8 = 3,5;
* o compasso `n` começa na semínima acumulada `sum(unidades(0..n-1))`, que é
  convertida em segundos interpolando a grade real. Assim 7/8 cai no lugar em
  vez de arredondar para 4 ou 3.

Nada aqui inventa dado: `bpm_local` mede o espaçamento REAL entre batidas da
grade; quando a grade não existe, o mapa devolve o BPM informado e diz que é
uma extrapolação (`preciso`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Limites de sanidade. Fora disso não é andamento, é erro de detecção.
BPM_MIN = 20.0
BPM_MAX = 400.0

#: Denominadores que o editor e o MIDI sabem representar.
DENOMINADORES = (2, 4, 8, 16)

#: Variação relativa a partir da qual dois trechos têm andamento diferente.
#: 3% é acima do ruído de medição de uma grade de batidas e abaixo do que o
#: músico percebe como "mudou o andamento" (~5%).
LIMIAR_ANDAMENTO = 0.03


def _unidades(numerador: int, denominador: int) -> float:
    """Quantas semínimas (unidades de BPM) cabem em um compasso."""
    numerador = max(1, int(numerador or 4))
    denominador = int(denominador or 4)
    if denominador not in DENOMINADORES:
        denominador = 4
    return numerador * (4.0 / denominador)


@dataclass(frozen=True)
class Compasso:
    """Um compasso da régua: posição musical e janela de tempo."""

    #: 1-based, como o músico conta ("compasso 12")
    numero: int
    inicio: float
    fim: float
    numerador: int
    denominador: int
    #: BPM medido dentro deste compasso (semínimas por minuto)
    bpm: float
    #: índice da semínima em que o compasso começa (0 = primeira batida)
    indice: int
    #: True quando o BPM veio de extrapolação (grade ausente ou curta)
    estimado: bool = False

    @property
    def duracao(self) -> float:
        return max(0.0, self.fim - self.inicio)

    @property
    def formula(self) -> str:
        return f"{self.numerador}/{self.denominador}"

    def as_dict(self) -> dict:
        return {
            "numero": self.numero,
            "inicio": round(self.inicio, 4),
            "fim": round(self.fim, 4),
            "numerador": self.numerador,
            "denominador": self.denominador,
            "formula": self.formula,
            "bpm": round(self.bpm, 2),
            "estimado": self.estimado,
        }


@dataclass
class MapaTempo:
    """Régua completa: grade de batidas + fórmula + mudanças declaradas."""

    #: segundos de cada semínima detectada (pode estar vazio)
    batidas: list[float] = field(default_factory=list)
    #: BPM nominal (o que a análise mediu; usado quando não há grade)
    bpm: float = 0.0
    numerador: int = 4
    denominador: int = 4
    #: deslocamento aplicado a toda a régua (ajuste fino do usuário)
    offset: float = 0.0
    #: [{compasso: 12, numerador: 6, denominador: 8}] — troca a partir do
    #: compasso 12 (1-based). O primeiro item pode ser a fórmula inicial.
    mudancas: list[dict] = field(default_factory=list)
    duracao: float = 0.0
    #: confiança da grade (a de `TempoInfo`, quando veio da análise)
    confianca: float = 0.0
    #: nome do detector, só para o relatório ("grade detectada", "metrônomo")
    origem: str = ""
    _caches: dict = field(default_factory=dict, repr=False, compare=False)

    # -- construção ------------------------------------------------------
    @classmethod
    def de_analise(
        cls,
        batidas: list[float],
        bpm: float,
        numerador: int = 4,
        denominador: int = 4,
        duracao: float = 0.0,
        confianca: float = 0.0,
    ) -> "MapaTempo":
        mapa = cls(
            batidas=[round(float(b), 4) for b in (batidas or []) if b is not None and b >= 0],
            bpm=float(bpm or 0.0),
            numerador=max(1, int(numerador or 4)),
            denominador=int(denominador if int(denominador or 4) in DENOMINADORES else 4),
            duracao=float(duracao or 0.0),
            confianca=float(confianca or 0.0),
            origem="grade detectada" if batidas else "sem grade",
        )
        mapa._normalizar()
        return mapa

    def _normalizar(self) -> None:
        # batidas fora de ordem (ou repetidas) quebram a interpolação: a
        # régua inteira sai deslocada. Ordenar e remover duplicata é barato.
        if self.batidas:
            unicas: list[float] = []
            for b in self.batidas:
                if not unicas or b - unicas[-1] > 1e-4:
                    unicas.append(b)
            self.batidas = unicas
        if self.bpm <= 0 and len(self.batidas) >= 2:
            self.bpm = 60.0 / self._passo_medio()
        self.bpm = max(0.0, min(BPM_MAX, self.bpm))
        if self.numerador < 1:
            self.numerador = 4
        if self.denominador not in DENOMINADORES:
            self.denominador = 4
        self._caches = {}

    @property
    def preciso(self) -> bool:
        """A régua acompanha a música ou extrapola o BPM?"""
        return len(self.batidas) >= 4

    def _passo_medio(self) -> float:
        if len(self.batidas) >= 2:
            difs = [b - a for a, b in zip(self.batidas, self.batidas[1:]) if b - a > 1e-4]
            if difs:
                difs.sort()
                return difs[len(difs) // 2]
        if self.bpm > 0:
            return 60.0 / self.bpm
        return 0.5

    # -- fórmula ---------------------------------------------------------
    def formula(self, compasso: int = 0) -> tuple[int, int]:
        """Fórmula vigente no compasso (0-based)."""
        num, den = self.numerador, self.denominador
        alvo = int(compasso) + 1
        for m in self.mudancas:
            try:
                inicio = int(m.get("compasso", 0) or 0)
            except (TypeError, ValueError):
                continue
            if inicio and alvo >= inicio:
                num = max(1, int(m.get("numerador", num) or num))
                d = int(m.get("denominador", den) or den)
                if d in DENOMINADORES:
                    den = d
        return num, den

    def unidades_do_compasso(self, compasso: int = 0) -> float:
        num, den = self.formula(compasso)
        return _unidades(num, den)

    def _acumuladas(self, n: int) -> float:
        """Semínimas até o começo do compasso `n` (cache em prefixo)."""
        alvo = max(0, int(n))
        cache = self._caches.setdefault("unidades", [0.0])
        while len(cache) <= alvo:
            cache.append(cache[-1] + self.unidades_do_compasso(len(cache) - 1))
        return cache[alvo]

    # -- tempo <-> posição ----------------------------------------------
    def tempo_de_indice(self, indice: float) -> float:
        """Índice fracionário de semínima -> segundos."""
        idx = float(indice or 0.0)
        b = self.batidas
        if len(b) >= 2:
            if idx <= 0:
                return b[0] + idx * (b[1] - b[0]) + self.offset
            i = int(math.floor(idx))
            if i + 1 < len(b):
                return b[i] + (idx - i) * (b[i + 1] - b[i]) + self.offset
            passo = (b[-1] - b[-2]) or self._passo_medio()
            return b[-1] + (idx - (len(b) - 1)) * passo + self.offset
        return idx * self._passo_medio() + self.offset

    def indice_de_tempo(self, tempo: float) -> float:
        """Segundos -> índice fracionário de semínima (inverso exato)."""
        alvo = float(tempo or 0.0) - self.offset
        b = self.batidas
        if len(b) >= 2:
            if alvo <= b[0]:
                passo = (b[1] - b[0]) or self._passo_medio()
                return (alvo - b[0]) / passo
            if alvo >= b[-1]:
                passo = (b[-1] - b[-2]) or self._passo_medio()
                return (len(b) - 1) + (alvo - b[-1]) / passo
            lo, hi = 0, len(b) - 1
            while hi - lo > 1:
                meio = (lo + hi) // 2
                if b[meio] <= alvo:
                    lo = meio
                else:
                    hi = meio
            passo = (b[hi] - b[lo]) or self._passo_medio()
            return lo + (alvo - b[lo]) / passo
        return alvo / self._passo_medio()

    def inicio_do_compasso(self, compasso: int) -> float:
        n = max(0, int(compasso))
        cache = self._caches.setdefault("inicios", {})
        if n not in cache:
            cache[n] = self.tempo_de_indice(self._acumuladas(n))
        return cache[n]

    def duracao_do_compasso(self, compasso: int) -> float:
        return max(0.0, self.inicio_do_compasso(compasso + 1) - self.inicio_do_compasso(compasso))

    def compasso_de(self, tempo: float) -> int:
        """Compasso (0-based) que contém `tempo` — busca binária na régua."""
        alvo = float(tempo or 0.0)
        if alvo <= self.inicio_do_compasso(0):
            return 0
        lo, hi = 0, 1
        guarda = 0
        while self.inicio_do_compasso(hi) <= alvo and guarda < 32:
            lo, hi = hi, hi * 2
            guarda += 1
        while hi - lo > 1:
            meio = (lo + hi) // 2
            if self.inicio_do_compasso(meio) <= alvo:
                lo = meio
            else:
                hi = meio
        return lo

    def pulso_do_compasso(self, tempo: float) -> tuple[int, int]:
        """(compasso 1-based, pulso 1-based) — onde o play está, em música."""
        n = self.compasso_de(tempo)
        num, _den = self.formula(n)
        inicio = self.inicio_do_compasso(n)
        duracao = max(1e-6, self.duracao_do_compasso(n))
        fracao = min(0.999999, max(0.0, (float(tempo) - inicio) / duracao))
        return n + 1, min(num, int(fracao * num) + 1)

    # -- BPM real (medido, não presumido) --------------------------------
    def _bpm_entre_indices(self, inicio: int, fim: int) -> tuple[float, bool]:
        """BPM medido entre dois índices da grade. (bpm, estimado)."""
        b = self.batidas
        if len(b) < 2:
            return (self.bpm or 120.0, True)
        i = max(0, min(len(b) - 1, int(inicio)))
        j = max(0, min(len(b) - 1, int(fim)))
        if j <= i:
            i, j = max(0, j - 1), min(len(b) - 1, i + 1)
        if j <= i:
            return (self.bpm or 120.0, True)
        span = b[j] - b[i]
        if span <= 1e-6:
            return (self.bpm or 120.0, True)
        return (60.0 * (j - i) / span, False)

    def bpm_local(self, tempo: float, janela: float = 4.0) -> float:
        """BPM medido nos arredores de `tempo` (média das batidas vizinhas).

        Sem grade, devolve o BPM nominal — e o chamador deve olhar
        `preciso`/`estimado` antes de afirmar qualquer coisa.
        """
        if not self.preciso:
            return self.bpm
        idx = self.indice_de_tempo(tempo)
        passo_indices = max(1.0, round(janela / self._passo_medio()))
        esquerda = int(math.floor(idx - passo_indices / 2))
        direita = int(math.ceil(idx + passo_indices / 2))
        bpm, _ = self._bpm_entre_indices(esquerda, direita)
        return bpm

    def compassos(self) -> list[Compasso]:
        """Régua completa, compasso a compasso, com o BPM de cada um."""
        total = self.total_compassos()
        saida: list[Compasso] = []
        for n in range(total):
            num, den = self.formula(n)
            inicio = self.inicio_do_compasso(n)
            fim = self.inicio_do_compasso(n + 1)
            if self.duracao:
                fim = min(fim, max(inicio, self.duracao))
            bpm, estimado = self._bpm_entre_indices(
                int(self._acumuladas(n)), int(self._acumuladas(n + 1))
            )
            saida.append(
                Compasso(
                    numero=n + 1,
                    inicio=inicio,
                    fim=fim,
                    numerador=num,
                    denominador=den,
                    bpm=bpm,
                    indice=int(self._acumuladas(n)),
                    estimado=estimado,
                )
            )
        return saida

    def total_compassos(self) -> int:
        """Quantos compassos a música ocupa (parcial no fim conta como 1)."""
        if self.duracao and self.duracao > 0:
            return max(1, self.compasso_de(max(0.0, self.duracao - 1e-6)) + 1)
        if self.batidas:
            return max(1, int(self._acumuladas(1) * 0 + len(self.batidas) // max(1, self.numerador)))
        return 1

    # -- andamentos (mudança de BPM) -------------------------------------
    def andamentos(self, limiar: float = LIMIAR_ANDAMENTO) -> list[dict]:
        """Trechos com andamento estável: [{compasso, inicio, bpm, estimado}].

        O BPM é medido a cada batida e os vizinhos dentro de `limiar` são
        fundidos — é assim que "96 até o compasso 24, 104 no refrão" sai do
        próprio áudio. Medir na batida (e não no compasso) evita que o
        compasso da fronteira misture metade de cada andamento e invente um
        BPM intermediário: no teste de 90→120 aparecia um trecho de 96 BPM
        que não existe na música.
        """
        trechos: list[dict] = []
        for compasso, bpm, estimado, inicio in self._bpm_por_batida():
            if not trechos:
                trechos.append(
                    {"compasso": compasso, "inicio": inicio, "bpm": bpm, "estimado": estimado}
                )
                continue
            atual = trechos[-1]
            base = atual["bpm"] or bpm
            if base > 0 and abs(bpm - base) / base > limiar:
                trechos.append(
                    {"compasso": compasso, "inicio": inicio, "bpm": bpm, "estimado": estimado}
                )
        return trechos

    def _bpm_por_batida(self) -> list[tuple[int, float, bool, float]]:
        """(compasso, bpm, estimado, inicio) medido a cada batida da grade.

        Cada batida rende um BPM (intervalo até a próxima); o compasso é o da
        batida. Sem grade, devolve um item só com o BPM nominal marcado como
        estimado — o chamador vê `estimado` e não afirma nada.
        """
        if not self.preciso:
            return [(1, self.bpm or 120.0, True, self.tempo_de_indice(0))]
        saida: list[tuple[int, float, bool, float]] = []
        for i in range(len(self.batidas) - 1):
            passo = self.batidas[i + 1] - self.batidas[i]
            if passo <= 1e-6:
                continue
            compasso = self.compasso_de(self.batidas[i]) + 1
            saida.append((compasso, 60.0 / passo, False, self.batidas[i]))
        return saida

    def mudancas_de_andamento(self, limiar: float = LIMIAR_ANDAMENTO) -> list[dict]:
        """Só as mudanças (sem o primeiro trecho), prontas para a tela."""
        trechos = self.andamentos(limiar=limiar)
        if len(trechos) <= 1:
            return []
        return [
            {
                "compasso": t["compasso"],
                "inicio": round(t["inicio"], 3),
                "bpm": round(t["bpm"], 1),
            }
            for t in trechos[1:]
        ]

    # -- edição ----------------------------------------------------------
    def com_formula(self, numerador: int, denominador: int, compasso: int = 1) -> "MapaTempo":
        """Troca a fórmula a partir do compasso `compasso` (1-based)."""
        num = max(1, int(numerador))
        den = int(denominador) if int(denominador) in DENOMINADORES else 4
        novo = self._clonar()
        if compasso <= 1:
            novo.numerador, novo.denominador = num, den
            novo.mudancas = [
                m for m in novo.mudancas if int(m.get("compasso", 0) or 0) > 1
            ]
        else:
            novo.mudancas = [
                m for m in novo.mudancas if int(m.get("compasso", 0) or 0) != int(compasso)
            ]
            novo.mudancas.append(
                {"compasso": int(compasso), "numerador": num, "denominador": den}
            )
            novo.mudancas.sort(key=lambda m: int(m.get("compasso", 0) or 0))
        novo._caches = {}
        return novo

    def com_bpm(self, bpm: float, manter_grade: bool = False) -> "MapaTempo":
        """Troca o BPM nominal.

        `manter_grade=True` mantém as batidas detectadas (só corrige o
        número mostrado). Sem isso, a grade é regerada a partir do offset —
        é o que o usuário espera ao digitar um BPM na barra de ferramentas,
        e é a mesma regra do editor.
        """
        novo = self._clonar()
        novo.bpm = max(BPM_MIN, min(BPM_MAX, float(bpm)))
        if not manter_grade:
            novo.batidas = []
            novo.origem = "metrônomo (BPM informado)"
        novo._normalizar()
        return novo

    def com_offset(self, offset: float) -> "MapaTempo":
        novo = self._clonar()
        novo.offset = float(offset)
        novo._caches = {}
        return novo

    def _clonar(self) -> "MapaTempo":
        return MapaTempo(
            batidas=list(self.batidas),
            bpm=self.bpm,
            numerador=self.numerador,
            denominador=self.denominador,
            offset=self.offset,
            mudancas=[dict(m) for m in self.mudancas],
            duracao=self.duracao,
            confianca=self.confianca,
            origem=self.origem,
        )

    # -- serialização ----------------------------------------------------
    def as_dict(self) -> dict:
        """Formato que vai para o `projeto.json` e para a tela."""
        return {
            "batidas": [round(b, 4) for b in self.batidas],
            "bpm": round(self.bpm, 2),
            "numerador": self.numerador,
            "denominador": self.denominador,
            "offset": round(self.offset, 4),
            "mudancas": [dict(m) for m in self.mudancas],
            "duracao": round(self.duracao, 3),
            "confianca": round(self.confianca, 3),
            "origem": self.origem,
            "preciso": self.preciso,
            "total_compassos": self.total_compassos(),
            # o que a tela precisa desenhar sem recalcular nada: a régua
            # pronta e os trechos de andamento medidos
            "compassos": [c.as_dict() for c in self.compassos()],
            "andamentos": [
                {**t, "inicio": round(t["inicio"], 3), "bpm": round(t["bpm"], 1)}
                for t in self.andamentos()
            ],
        }

    @classmethod
    def de_dict(cls, dados: dict | None) -> "MapaTempo":
        """Reconstrói o mapa do `projeto.json` (ou de `edicoes.json`)."""
        dados = dados or {}
        mapa = cls(
            batidas=[float(b) for b in (dados.get("batidas") or [])],
            bpm=float(dados.get("bpm") or 0.0),
            numerador=int(dados.get("numerador") or dados.get("compasso") or 4),
            denominador=int(dados.get("denominador") or 4),
            offset=float(dados.get("offset") or dados.get("offsetInicial") or 0.0),
            mudancas=[dict(m) for m in (dados.get("mudancas") or dados.get("mudancasCompasso") or [])],
            duracao=float(dados.get("duracao") or 0.0),
            confianca=float(dados.get("confianca") or 0.0),
            origem=str(dados.get("origem") or ""),
        )
        mapa._normalizar()
        return mapa


def regra_por_batida(mapa: MapaTempo, batidas: list[float]) -> list[tuple[int, int]]:
    """Para cada batida da lista, (pulso 1-based, numerador do compasso).

    Serve para acentuar o clique e escrever o MIDI: com a fórmula mudando no
    meio, "tempo 1 do compasso" deixou de ser `i % 4`.
    """
    saida: list[tuple[int, int]] = []
    for t in batidas:
        compasso, pulso = mapa.pulso_do_compasso(t)
        num, _den = mapa.formula(compasso - 1)
        saida.append((pulso, num))
    return saida
