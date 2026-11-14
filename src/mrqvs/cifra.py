"""Cifra do projeto: acordes por compasso, com confiança, correção e transposição.

O que existia antes: `acordes.por_compasso` detectava um acorde por compasso e
o editor desenhava isso na tela. Faltava o que o músico **leva embora**: a
cifra em texto, em ChordPro (que o SongBook/OnSong/ChordPro leem) e a mesma
cifra no tom em que a banda vai tocar.

Três regras que este módulo não quebra:

1. **Confiança é dado, não enfeite.** Acorde com confiança baixa sai marcado
   com `?` e com a confiança no CSV. Quem lê sabe o que foi medido e o que foi
   chute — inventar "Dm7" bonito no papel seria pior que mostrar "?".
2. **A correção do usuário vence a detecção**, sempre, e sobrevive a
   reprocessar a música (`edicoes.json`).
3. **Nada é sobrescrito.** A cifra é escrita em arquivo novo dentro da pasta
   `-apoio`, ao lado do relatório.

O formato do acorde é o mesmo da tela (`acordes.TIPOS`): tônica + sufixo, com
baixo invertido opcional (`D/F#`). Transpor mexe na tônica e no baixo, nunca no
sufixo.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import acordes as acordes_mod
from . import mapa_tempo as mapa_mod

#: Abaixo disso o acorde aparece com `?` — o mesmo piso que a tela usa para
#: escrever "—" em vez de um nome.
CONFIANCA_MINIMA = 0.2

#: Marcador de compasso sem acorde. "N.C." = "no chord", usado em cifra.
SEM_ACORDE = "N.C."

#: Sufixos que o parser aceita além dos de `acordes.TIPOS`. Serve só para ler
#: uma cifra que o usuário digitou; a detecção continua restrita ao catálogo.
SUFIXOS_EXTRA = (
    "m7b5", "dim", "aug", "6", "m6", "9", "m9", "maj9", "11", "13", "add9",
    "sus2", "7sus4", "7M", "maj7", "º", "+", "5",
)

_RE_ACORDE = re.compile(r"^([A-G][#b]?)([^/]*)(?:/([A-G][#b]?))?$")

#: Ordem de preferência para escrever bemóis ou sustenidos, decidida pelo tom
#: (a mesma regra de `acordes.usar_bemol`, aplicada à tonalidade de destino).
_BEMOL_POR_GRAFIA = {"Db", "Eb", "Gb", "Ab", "Bb", "F", "C"}


def _indice(nota: str) -> int:
    """Índice cromático de uma nota escrita com sustenido ou bemol."""
    if nota in acordes_mod.NOTAS:
        return acordes_mod.NOTAS.index(nota)
    if nota in acordes_mod.NOTAS_BEMOL:
        return acordes_mod.NOTAS_BEMOL.index(nota)
    return -1


def separar(acorde: str) -> tuple[str, str, str]:
    """'F#m7/A' -> ('F#', 'm7', 'A'). Devolve ('', '', '') se não for acorde."""
    texto = str(acorde or "").strip().replace("♯", "#").replace("♭", "b")
    if not texto or texto in ("?", "—", "-", SEM_ACORDE):
        return "", "", ""
    casou = _RE_ACORDE.match(texto)
    if not casou:
        return "", "", ""
    raiz, sufixo, baixo = casou.group(1), casou.group(2) or "", casou.group(3) or ""
    if _indice(raiz) < 0:
        return "", "", ""
    return raiz, sufixo, baixo


def transpor_acorde(acorde: str, semitons: int, bemol: bool = False) -> str:
    """Transpõe tônica e baixo, preserva o sufixo e a inversão.

    Acorde que não é acorde (texto livre que o usuário digitou) volta
    idêntico: melhor devolver o que ele escreveu do que apagar.
    """
    raiz, sufixo, baixo = separar(acorde)
    if not raiz:
        return str(acorde or "").strip()
    tabela = acordes_mod.NOTAS_BEMOL if bemol else acordes_mod.NOTAS

    def mover(nota: str) -> str:
        return tabela[(_indice(nota) + int(semitons)) % 12]

    novo = mover(raiz) + sufixo
    if baixo:
        novo += "/" + mover(baixo)
    return novo


@dataclass
class LinhaCifra:
    """Um compasso na cifra."""

    numero: int
    inicio: float
    fim: float
    acorde: str = ""
    confianca: float = 0.0
    #: True quando o acorde veio de correção do usuário
    manual: bool = False
    #: letra que cai dentro deste compasso (preenchida por `com_letra`)
    letra: str = ""

    @property
    def incerto(self) -> bool:
        return (not self.manual) and (not self.acorde or self.confianca < CONFIANCA_MINIMA)

    @property
    def rotulo(self) -> str:
        """Acorde como sai no papel: com `?` quando a estimativa é fraca."""
        if not self.acorde:
            return SEM_ACORDE
        return self.acorde + ("?" if self.incerto else "")

    @property
    def formula(self) -> str:
        return f"{self.numero}"

    def as_dict(self) -> dict:
        return {
            "numero": self.numero,
            "inicio": round(self.inicio, 3),
            "fim": round(self.fim, 3),
            "acorde": self.acorde,
            "rotulo": self.rotulo,
            "confianca": round(self.confianca, 3),
            "manual": self.manual,
            "incerto": self.incerto,
            "letra": self.letra,
        }


@dataclass
class SecaoCifra:
    nome: str
    inicio: float
    fim: float
    linhas: list[LinhaCifra] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "nome": self.nome,
            "inicio": round(self.inicio, 3),
            "fim": round(self.fim, 3),
            "linhas": [ln.as_dict() for ln in self.linhas],
        }


@dataclass
class Cifra:
    titulo: str = ""
    artista: str = ""
    tom: str = ""
    #: semitons de transposição aplicados (0 = tom gravado)
    transposicao: int = 0
    numerador: int = 4
    denominador: int = 4
    bpm: float = 0.0
    secoes: list[SecaoCifra] = field(default_factory=list)
    #: avisos honestos: "tom pouco definido", "compasso incerto"...
    avisos: list[str] = field(default_factory=list)

    # -- leitura ---------------------------------------------------------
    @property
    def linhas(self) -> list[LinhaCifra]:
        return [ln for secao in self.secoes for ln in secao.linhas]

    @property
    def tom_exibido(self) -> str:
        """Tonalidade escrita na cifra (já transposta)."""
        if not self.tom:
            return ""
        partes = self.tom.split()
        if self.transposicao:
            raiz, resto = _raiz_e_resto(self.tom)
            if raiz:
                novo = transpor_acorde(
                    raiz, self.transposicao, usar_bemol(_tonica_destino(self.tom, self.transposicao))
                )
                partes = [novo] + ([resto] if resto else [])
        return " ".join(partes).strip()

    @property
    def resumo(self) -> str:
        incertas = sum(1 for ln in self.linhas if ln.incerto)
        total = len(self.linhas)
        pedacos = [f"{total} compassos"]
        if incertas:
            pedacos.append(f"{incertas} sem acorde confiável")
        if self.transposicao:
            pedacos.append(f"transposta {self.transposicao:+d} semitom(ns)")
        return " · ".join(pedacos)

    # -- construção ------------------------------------------------------
    @classmethod
    def de_estudio(
        cls,
        estudio: dict | None,
        acordes: list[dict] | None = None,
        titulo: str = "",
        artista: str = "",
        mapa: mapa_mod.MapaTempo | None = None,
        bpm: float = 0.0,
        tonalidade: str = "",
    ) -> "Cifra":
        """Monta a cifra a partir dos dados que o projeto já produz.

        `estudio` é o `StudioData.as_dict()` (tem batidas, compasso, seções e
        acordes). Pode ser combinado com `acordes` (a lista solta que vem em
        `/api/run`) e com um `mapa` de tempo já editado — nesse caso o mapa
        manda na régua, e os acordes são encaixados nos compassos dele.
        """
        estudio = estudio or {}
        lista_acordes = list(acordes if acordes is not None else (estudio.get("acordes") or []))
        secoes_brutas = estudio.get("secoes") or []
        numerador = int(estudio.get("compasso") or estudio.get("numerador") or 4)
        denominador = int(estudio.get("denominador") or 4)
        if mapa is None:
            mapa = mapa_mod.MapaTempo.de_analise(
                batidas=estudio.get("batidas") or [],
                bpm=float(estudio.get("bpm") or bpm or 0.0),
                numerador=numerador,
                denominador=denominador,
                duracao=float(estudio.get("duracao") or 0.0),
            )
        cifra = cls(
            titulo=titulo or "",
            artista=artista or "",
            tom=(tonalidade or estudio.get("tonalidade") or "").strip(),
            numerador=mapa.numerador,
            denominador=mapa.denominador,
            bpm=float(mapa.bpm or bpm or 0.0),
        )
        compassos = mapa.compassos()

        # acordes por índice de compasso detectado. A chave é o número que o
        # detector gravou (1-based); aceitar `compasso` e `inicio` cobre
        # projeto.json antigo e edições feitas à mão.
        por_numero: dict[int, dict] = {}
        for a in lista_acordes:
            if not isinstance(a, dict):
                continue
            try:
                numero = int(a.get("compasso") or 0)
            except (TypeError, ValueError):
                numero = 0
            if numero > 0:
                por_numero[numero] = a
        # acorde cujo início cai num compasso: usado quando o detector não
        # numerou (ou numerou fora da régua editada)
        por_tempo: list[dict] = [a for a in lista_acordes if isinstance(a, dict)]

        def acorde_do(compasso) -> dict:
            if compasso.numero in por_numero:
                return por_numero[compasso.numero]
            melhor, dist = None, 1e9
            for a in por_tempo:
                try:
                    inicio = float(a.get("inicio"))
                except (TypeError, ValueError):
                    continue
                d = abs(inicio - compasso.inicio)
                if d < dist:
                    melhor, dist = a, d
            # tolerância de meio compasso: acorde detectado no compasso vizinho
            # por causa de uma batida fora do lugar continua sendo deste
            return melhor if melhor is not None and dist <= compasso.duracao else {}

        # Atribuição por POSIÇÃO DO COMPASSO, não por sobreposição de janela.
        # Um compasso que cruza a fronteira de duas seções caía nas duas e
        # aparecia duplicado na cifra (o defeito aparecia no teste com seção
        # de 0–12 s e compasso de 10,5–13 s). Aqui cada compasso pertence a
        # exatamente uma seção: a que contém o seu INÍCIO.
        fronteiras: list[tuple[str, float, float]] = []
        for s in secoes_brutas:
            inicio = float(s.get("start", s.get("inicio", 0.0)) or 0.0)
            fim = float(s.get("end", s.get("fim", 0.0)) or 0.0)
            if fim <= inicio:
                continue
            fronteiras.append((str(s.get("nome") or s.get("rotulo") or "Seção"), inicio, fim))
        if not fronteiras:
            fronteiras = [("Música", 0.0, mapa.duracao or float("inf"))]

        grupos: list[tuple[str, list[LinhaCifra]]] = []
        for c in compassos:
            dono = next(
                (nome for nome, ini, f in fronteiras if ini - 1e-6 <= c.inicio < f - 1e-6),
                None,
            )
            if dono is None:
                # compasso antes da primeira seção ou depois da última: não
                # pode sumir da cifra nem entrar na seção errada
                dono = "Trecho sem seção"
            dado = acorde_do(c)
            bruto = str(dado.get("acorde") or "").strip()
            conf = float(dado.get("confianca") or 0.0)
            if bruto in ("", "?", "—", "-"):
                bruto, conf = "", 0.0
            linha = LinhaCifra(
                numero=c.numero,
                inicio=c.inicio,
                fim=c.fim,
                acorde=bruto,
                confianca=conf,
                manual=bool(dado.get("manual")),
            )
            if grupos and grupos[-1][0] == dono:
                grupos[-1][1].append(linha)
            else:
                grupos.append((dono, [linha]))

        for nome, linhas in grupos:
            cifra.secoes.append(
                SecaoCifra(
                    nome=nome,
                    inicio=linhas[0].inicio,
                    fim=linhas[-1].fim,
                    linhas=linhas,
                )
            )

        if cifra.tom and cifra.tom in ("—", "-"):
            cifra.tom = ""
        if not cifra.tom:
            cifra.avisos.append("tonalidade não identificada — a cifra está no tom gravado")
        incertas = sum(1 for ln in cifra.linhas if ln.incerto)
        if incertas:
            cifra.avisos.append(
                f"{incertas} compasso(s) sem acorde confiável, marcados com '?' — "
                "confira e corrija no editor"
            )
        return cifra

    # -- edição ----------------------------------------------------------
    def transposta(self, semitons: int) -> "Cifra":
        """Cópia da cifra `semitons` acima (ou abaixo, se negativo).

        A grafia (bemol/sustenido) é decidida pelo TOM DE DESTINO — em F maior
        o acorde de A# se escreve Bb, como numa partitura.
        """
        deslocamento = int(semitons) % 12
        destino = _tonica_destino(self.tom, deslocamento) if self.tom else ""
        bemol = usar_bemol(destino or self.tom)
        nova = Cifra(
            titulo=self.titulo,
            artista=self.artista,
            tom=self.tom,
            transposicao=deslocamento,
            numerador=self.numerador,
            denominador=self.denominador,
            bpm=self.bpm,
            avisos=list(self.avisos),
        )
        for secao in self.secoes:
            copia = SecaoCifra(nome=secao.nome, inicio=secao.inicio, fim=secao.fim)
            for ln in secao.linhas:
                copia.linhas.append(
                    LinhaCifra(
                        numero=ln.numero,
                        inicio=ln.inicio,
                        fim=ln.fim,
                        acorde=transpor_acorde(ln.acorde, deslocamento, bemol) if ln.acorde else "",
                        confianca=ln.confianca,
                        manual=ln.manual,
                        letra=ln.letra,
                    )
                )
            nova.secoes.append(copia)
        return nova

    def com_correcoes(self, correcoes: dict[int, str]) -> "Cifra":
        """Aplica {numero_do_compasso: "Am7"} por cima do detectado.

        Compasso com string vazia é "sem acorde" — diferente de "não mexido",
        que é o compasso ausente do dicionário.
        """
        nova = Cifra(
            titulo=self.titulo,
            artista=self.artista,
            tom=self.tom,
            transposicao=self.transposicao,
            numerador=self.numerador,
            denominador=self.denominador,
            bpm=self.bpm,
            avisos=list(self.avisos),
        )
        for secao in self.secoes:
            copia = SecaoCifra(nome=secao.nome, inicio=secao.inicio, fim=secao.fim)
            for ln in secao.linhas:
                if ln.numero in correcoes:
                    texto = str(correcoes[ln.numero] or "").strip()
                    copia.linhas.append(
                        LinhaCifra(
                            numero=ln.numero,
                            inicio=ln.inicio,
                            fim=ln.fim,
                            acorde="" if texto in ("", SEM_ACORDE) else texto,
                            confianca=1.0,
                            manual=True,
                            letra=ln.letra,
                        )
                    )
                else:
                    copia.linhas.append(ln)
            nova.secoes.append(copia)
        return nova

    def com_letra(self, linhas_letra: list[dict]) -> "Cifra":
        """Encaixa linhas de letra sincronizada nos compassos.

        `linhas_letra` = [{"tempo": 12.3, "texto": "..."}]; cada linha vai
        para o compasso em que começa. A letra não é inventada: sem letra
        sincronizada, a cifra sai só com acordes.
        """
        nova = Cifra(
            titulo=self.titulo,
            artista=self.artista,
            tom=self.tom,
            transposicao=self.transposicao,
            numerador=self.numerador,
            denominador=self.denominador,
            bpm=self.bpm,
            avisos=list(self.avisos),
        )
        for secao in self.secoes:
            copia = SecaoCifra(nome=secao.nome, inicio=secao.inicio, fim=secao.fim)
            for ln in secao.linhas:
                copia.linhas.append(
                    LinhaCifra(
                        numero=ln.numero,
                        inicio=ln.inicio,
                        fim=ln.fim,
                        acorde=ln.acorde,
                        confianca=ln.confianca,
                        manual=ln.manual,
                        letra=ln.letra,
                    )
                )
            nova.secoes.append(copia)
        for item in linhas_letra or []:
            try:
                tempo = float(item.get("tempo"))
            except (TypeError, ValueError):
                continue
            texto = str(item.get("texto") or "").strip()
            if not texto:
                continue
            for secao in nova.secoes:
                alvo = next(
                    (ln for ln in secao.linhas if ln.inicio - 1e-6 <= tempo < ln.fim + 1e-6),
                    None,
                )
                if alvo is not None:
                    alvo.letra = (alvo.letra + " " + texto).strip() if alvo.letra else texto
                    break
        return nova

    def as_dict(self) -> dict:
        return {
            "titulo": self.titulo,
            "artista": self.artista,
            "tom": self.tom,
            "tom_exibido": self.tom_exibido,
            "transposicao": self.transposicao,
            "bpm": round(self.bpm, 1),
            "compasso": f"{self.numerador}/{self.denominador}",
            "resumo": self.resumo,
            "avisos": self.avisos,
            "secoes": [s.as_dict() for s in self.secoes],
        }

    # -- exportação ------------------------------------------------------
    def para_txt(self, largura: int = 60) -> str:
        """Cifra em texto puro, uma linha de acordes por seção.

        Formato de cifra de violão: acordes numa linha, letra embaixo quando
        existe. Compassos consecutivos com o MESMO acorde são agrupados
        (`Am (2x)`) para não virar uma parede de acordes repetidos.
        """
        linhas: list[str] = []
        titulo = self.titulo or "Sem título"
        linhas.append(titulo)
        meta = []
        if self.artista:
            meta.append(self.artista)
        if self.tom_exibido:
            meta.append(f"Tom: {self.tom_exibido}")
        if self.bpm:
            meta.append(f"{self.bpm:.0f} BPM")
        meta.append(f"Compasso: {self.numerador}/{self.denominador}")
        linhas.append(" · ".join(meta))
        if self.transposicao:
            linhas.append(f"(transposta {self.transposicao:+d} semitom(ns) do tom gravado)")
        if self.avisos:
            linhas.append("")
            for aviso in self.avisos:
                linhas.append(f"! {aviso}")
        for secao in self.secoes:
            linhas.append("")
            linhas.append(f"[{secao.nome}]  (compasso {secao.linhas[0].numero if secao.linhas else '?'})")
            linhas.extend(_quebrar(_agrupar(secao.linhas), largura))
            for ln in secao.linhas:
                if ln.letra:
                    linhas.append(f"  {ln.numero:>3}  {ln.letra}")
        linhas.append("")
        linhas.append("? = acorde estimado com baixa confiança; N.C. = sem acorde")
        return "\n".join(linhas) + "\n"

    def para_chordpro(self) -> str:
        """ChordPro (o formato que SongBook, OnSong e ChordPro leem)."""
        saida = []
        titulo = self.titulo or "Sem título"
        saida.append(f"{{title: {titulo}}}")
        if self.artista:
            saida.append(f"{{artist: {self.artista}}}")
        if self.tom_exibido:
            saida.append(f"{{key: {self.tom_exibido}}}")
        if self.bpm:
            saida.append(f"{{tempo: {self.bpm:.0f}}}")
        saida.append(f"{{time: {self.numerador}/{self.denominador}}}")
        if self.transposicao:
            saida.append(f"{{comment: transposta {self.transposicao:+d} semitom(ns)}}")
        for aviso in self.avisos:
            saida.append(f"{{comment: {aviso}}}")
        for secao in self.secoes:
            saida.append("")
            saida.append(f"{{comment: {secao.nome}}}")
            # uma linha por compasso com acorde: `[Am]letra`. Compasso sem
            # acorde e sem letra não vira `[]` solto — player de cifra trata
            # isso como acorde vazio e mostra um retângulo em branco.
            for ln in secao.linhas:
                if not ln.acorde and not ln.letra:
                    continue
                if ln.letra:
                    saida.append(f"[{ln.rotulo}]{ln.letra}")
                else:
                    saida.append(f"[{ln.rotulo}]")
        saida.append("")
        return "\n".join(saida) + "\n"

    def para_csv(self) -> str:
        """CSV para planilha: número, tempo, acorde, confiança, manual."""
        buffer = io.StringIO()
        escritor = csv.writer(buffer, lineterminator="\n")
        escritor.writerow(
            ["compasso", "inicio_s", "fim_s", "secao", "acorde", "confianca", "manual", "incerto", "letra"]
        )
        for secao in self.secoes:
            for ln in secao.linhas:
                escritor.writerow(
                    [
                        ln.numero,
                        f"{ln.inicio:.3f}",
                        f"{ln.fim:.3f}",
                        secao.nome,
                        ln.acorde,
                        f"{ln.confianca:.2f}",
                        "sim" if ln.manual else "nao",
                        "sim" if ln.incerto else "nao",
                        ln.letra,
                    ]
                )
        return buffer.getvalue()

    def escrever(self, pasta: Path, base: str | None = None) -> dict[str, Path]:
        """Grava `.txt`, `.cho` (ChordPro) e `.csv` na pasta `-apoio`.

        Devolve {formato: caminho}. Nunca sobrescreve nada fora da pasta de
        apoio — e escrever a cifra é barato, então os três saem juntos.
        """
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        nome = base or _nome_de_arquivo(self.titulo)
        alvos = {
            "txt": pasta / f"{nome}_cifra.txt",
            "chordpro": pasta / f"{nome}_cifra.cho",
            "csv": pasta / f"{nome}_cifra.csv",
        }
        alvos["txt"].write_text(self.para_txt(), encoding="utf-8")
        alvos["chordpro"].write_text(self.para_chordpro(), encoding="utf-8")
        alvos["csv"].write_text(self.para_csv(), encoding="utf-8")
        return alvos


# ------------------------------------------------------------------ ajuda ---
def _nome_de_arquivo(titulo: str) -> str:
    limpo = re.sub(r"[^\w\-. ]+", "", str(titulo or "cifra"), flags=re.UNICODE).strip()
    return (limpo or "cifra")[:60].replace(" ", "_")


def _raiz_e_resto(tom: str) -> tuple[str, str]:
    partes = str(tom or "").split()
    if not partes:
        return "", ""
    raiz = partes[0]
    if raiz.endswith("m") and len(raiz) > 1:
        # "F#m" -> raiz "F#", qualidade "menor"
        return raiz[:-1], ("menor " + " ".join(partes[1:])).strip()
    return raiz, " ".join(partes[1:])


def _tonica_destino(tom: str, semitons: int) -> str:
    raiz, _ = _raiz_e_resto(tom)
    if not raiz or _indice(raiz) < 0:
        return ""
    # a grafia segue a tônica de destino; em menor, a relativa maior decide
    bemol = usar_bemol(tom)
    tabela = acordes_mod.NOTAS_BEMOL if bemol else acordes_mod.NOTAS
    return tabela[(_indice(raiz) + int(semitons)) % 12]


def usar_bemol(tonalidade: str) -> bool:
    return acordes_mod.usar_bemol(tonalidade)


def _agrupar(linhas: list[LinhaCifra]) -> list[tuple[str, int]]:
    """[(rótulo, quantos compassos)] — mesmo acorde seguido vira `Am (3x)`."""
    saida: list[tuple[str, int]] = []
    for ln in linhas:
        rotulo = ln.rotulo
        if saida and saida[-1][0] == rotulo:
            saida[-1] = (rotulo, saida[-1][1] + 1)
        else:
            saida.append((rotulo, 1))
    return saida


def _quebrar(pares: list[tuple[str, int]], largura: int) -> list[str]:
    """Quebra a sequência de acordes em linhas de até `largura` colunas."""
    linhas: list[str] = []
    atual = ""
    for rotulo, vezes in pares:
        pedaco = rotulo if vezes == 1 else f"{rotulo} ({vezes}x)"
        candidato = f"{atual}  {pedaco}".strip() if atual else pedaco
        if len(candidato) > largura and atual:
            linhas.append(atual)
            atual = pedaco
        else:
            atual = candidato
    if atual:
        linhas.append(atual)
    return linhas or ["—"]
