"""Projeto multitrack (`.mrqvs.json`): o que a tela edita e o servidor renderiza.

Por que um formato próprio: o `projeto.json` é **saída da análise** — ele é
refeito se a música for reprocessada. O que o usuário constrói depois disso
(volume, pan, mute, solo, ordem das faixas, loop, cifra corrigida, letra
alinhada) é trabalho dele e não pode ser perdido por reprocessar a música.
Separar os dois é a mesma decisão que já vale para `edicoes.json` — aqui ela
vira um projeto completo, com versão de formato, para a tela reabrir tudo.

Layout em disco:

    <Nome>-<BPM>/                    áudio (stems, mix, L/R)
    <Nome>-<BPM>-apoio/
        projeto.json                 análise (gerado pelo programa)
        projeto.mrqvs.json           ESTE projeto (editável, versionado)
        edicoes.json                 compatibilidade com o editor antigo
        cifra.txt / cifra.cho / cifra.csv
        letra.json / letra.lrc / letra.srt
        cifra-e-clique.mid
        ficha.html                   cifra + letra prontas para imprimir

Regras que este módulo garante:

* **nada é sobrescrito**: o render sempre escreve arquivo novo com sufixo;
* **mixer não-destrutivo**: volume/pan/mute/solo/offset só existem no JSON;
  os WAVs dos stems nunca são alterados;
* **stem ausente é avisado, não silenciado**: se o arquivo sumiu do disco, o
  render devolve o aviso e continua com o que existe;
* **formato tem versão**: projeto de versão futura é recusado com mensagem,
  em vez de ser lido pela metade.
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import cifra as cifra_mod
from . import letra as letra_mod
from . import mapa_tempo as mapa_mod

#: Versão do formato. Só sobe quando um campo muda de significado — campo
#: novo com default não quebra leitura de projeto antigo.
VERSAO = 1

ARQUIVO_PROJETO = "projeto.mrqvs.json"

#: Tipos de faixa que o mixer conhece.
TIPOS = ("stem", "ensaio", "importada", "clique", "guia", "mix")

#: Ganho máximo por faixa. +6 dB é o teto de um fader de console pequeno e
#: evita que um valor absurdo (ou corrompido) estoure a soma.
GANHO_MAX = 2.0
PAN_MAX = 1.0


class ProjetoInvalido(RuntimeError):
    """O arquivo de projeto não dá para ler (versão, JSON ou campos)."""


def _limitar(valor: float, minimo: float, maximo: float) -> float:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return minimo
    if v != v:  # NaN
        return minimo
    return max(minimo, min(maximo, v))


@dataclass
class Faixa:
    """Uma faixa do multitrack. Todos os campos são editáveis pela tela."""

    id: str
    nome: str
    #: caminho RELATIVO à pasta de áudio do projeto (portátil: mover a pasta
    #: do projeto não quebra o arquivo). Vazio = faixa sintetizada (clique).
    arquivo: str = ""
    tipo: str = "stem"
    cor: str = "#7f9ec9"
    volume: float = 1.0
    pan: float = 0.0
    mudo: bool = False
    solo: bool = False
    oculta: bool = False
    #: ordem na tela (menor em cima)
    ordem: int = 0
    #: deslocamento em segundos (+ = entra mais tarde)
    offset: float = 0.0
    #: altura da linha na timeline em px (0 = padrão)
    altura: int = 0
    #: fades em segundos (0 = sem fade)
    fade_in: float = 0.0
    fade_out: float = 0.0
    #: rótulo do arquivo como o usuário o vê (nome original)
    rotulo_arquivo: str = ""

    def normalizar(self) -> "Faixa":
        self.volume = _limitar(self.volume, 0.0, GANHO_MAX)
        self.pan = _limitar(self.pan, -PAN_MAX, PAN_MAX)
        self.offset = _limitar(self.offset, -3600.0, 3600.0)
        self.fade_in = _limitar(self.fade_in, 0.0, 60.0)
        self.fade_out = _limitar(self.fade_out, 0.0, 60.0)
        self.altura = int(_limitar(self.altura, 0, 400))
        self.ordem = int(_limitar(self.ordem, 0, 999))
        if self.tipo not in TIPOS:
            self.tipo = "stem"
        return self

    @property
    def entra_no_mix(self) -> bool:
        return (not self.mudo) and (not self.oculta)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "arquivo": self.arquivo,
            "tipo": self.tipo,
            "cor": self.cor,
            "volume": round(self.volume, 4),
            "pan": round(self.pan, 4),
            "mudo": bool(self.mudo),
            "solo": bool(self.solo),
            "oculta": bool(self.oculta),
            "ordem": self.ordem,
            "offset": round(self.offset, 4),
            "altura": self.altura,
            "fade_in": round(self.fade_in, 3),
            "fade_out": round(self.fade_out, 3),
            "rotulo_arquivo": self.rotulo_arquivo,
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "Faixa":
        base = str(dados.get("arquivo") or "")
        faixa = cls(
            id=str(dados.get("id") or dados.get("chave") or "faixa"),
            nome=str(dados.get("nome") or dados.get("id") or "Faixa"),
            arquivo=base.replace("\\", "/"),
            tipo=str(dados.get("tipo") or "stem"),
            cor=str(dados.get("cor") or "#7f9ec9"),
            volume=dados.get("volume", 1.0),
            pan=dados.get("pan", 0.0),
            mudo=bool(dados.get("mudo")),
            solo=bool(dados.get("solo")),
            oculta=bool(dados.get("oculta")),
            ordem=dados.get("ordem", 0),
            offset=dados.get("offset", 0.0),
            altura=dados.get("altura", 0),
            fade_in=dados.get("fade_in", 0.0),
            fade_out=dados.get("fade_out", 0.0),
            rotulo_arquivo=str(dados.get("rotulo_arquivo") or ""),
        )
        return faixa.normalizar()


@dataclass
class Marcador:
    """Ponto nomeado na timeline (seção, "solo de guitarra", "vem o refrão")."""

    tempo: float
    nome: str
    cor: str = "#d8b25a"
    #: compasso calculado na hora de gravar (para conferência humana)
    compasso: int = 0

    def as_dict(self) -> dict:
        return {
            "tempo": round(self.tempo, 3),
            "nome": self.nome,
            "cor": self.cor,
            "compasso": self.compasso,
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "Marcador":
        return cls(
            tempo=_limitar(dados.get("tempo", 0.0), 0.0, 86400.0),
            nome=str(dados.get("nome") or "Marcador"),
            cor=str(dados.get("cor") or "#d8b25a"),
            compasso=int(_limitar(dados.get("compasso", 0), 0, 99999)),
        )


@dataclass
class Mixagem:
    """Parâmetros globais do mixer."""

    master: float = 0.85
    #: normaliza o mix para -1 dBFS no render (evita clipping calado)
    normalizar: bool = True
    #: limiter simples no render: corta acima de 0,99 em vez de distorcer
    limitar: bool = True

    def as_dict(self) -> dict:
        return {
            "master": round(_limitar(self.master, 0.0, 1.0), 4),
            "normalizar": bool(self.normalizar),
            "limitar": bool(self.limitar),
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "Mixagem":
        dados = dados or {}
        return cls(
            master=_limitar(dados.get("master", 0.85), 0.0, 1.0),
            normalizar=bool(dados.get("normalizar", True)),
            limitar=bool(dados.get("limitar", True)),
        )


@dataclass
class ProjetoVS:
    """O projeto inteiro: áudio, régua, cifra, letra, marcadores e mixer."""

    #: pasta de ÁUDIO (a que tem os stems)
    pasta: Path = Path(".")
    titulo: str = ""
    artista: str = ""
    criado_em: str = ""
    atualizado_em: str = ""
    #: versão do programa que gravou (para diagnóstico)
    versao_programa: str = ""
    mapa: mapa_mod.MapaTempo = field(default_factory=mapa_mod.MapaTempo)
    faixas: list[Faixa] = field(default_factory=list)
    marcadores: list[Marcador] = field(default_factory=list)
    mixagem: Mixagem = field(default_factory=Mixagem)
    #: loop persistido: {inicio, fim} ou None
    loop: dict | None = None
    #: cifra e letra como dados (a tela desenha, o render exporta)
    cifra: dict = field(default_factory=dict)
    letra: dict = field(default_factory=dict)
    #: seções nomeadas: [{start, end, rotulo, nome}]
    secoes: list[dict] = field(default_factory=list)
    #: avisos acumulados do projeto (análise + render)
    avisos: list[str] = field(default_factory=list)
    #: versão do formato lida do disco (0 = nunca salvo)
    versao: int = VERSAO

    # -- pastas ----------------------------------------------------------
    @property
    def apoio(self) -> Path:
        pasta = Path(self.pasta)
        return pasta.parent / f"{pasta.name}-apoio"

    @property
    def caminho_projeto(self) -> Path:
        return self.apoio / ARQUIVO_PROJETO

    def caminho_da_faixa(self, faixa: Faixa) -> Path | None:
        """Caminho absoluto do áudio da faixa (None quando não existe)."""
        if not faixa.arquivo:
            return None
        alvo = Path(self.pasta) / faixa.arquivo
        return alvo if alvo.is_file() else None

    # -- faixas ----------------------------------------------------------
    def faixa(self, identificador: str) -> Faixa | None:
        return next((f for f in self.faixas if f.id == identificador), None)

    @property
    def faixas_ordenadas(self) -> list[Faixa]:
        return sorted(self.faixas, key=lambda f: (f.ordem, f.id))

    @property
    def tem_solo(self) -> bool:
        """Solo vale para as faixas audíveis: solo em faixa oculta não conta."""
        return any(f.solo and f.entra_no_mix for f in self.faixas)

    def audivel(self, faixa: Faixa) -> bool:
        """Esta faixa entra no mix agora? (regra única da tela e do servidor)"""
        if faixa.mudo or faixa.oculta:
            return False
        if self.tem_solo:
            return faixa.solo
        return True

    def ordenar(self, ordem: list[str]) -> None:
        """Aplica a nova ordem (lista de ids) — id desconhecido é ignorado."""
        posicao = {identificador: i for i, identificador in enumerate(ordem)}
        for f in self.faixas:
            if f.id in posicao:
                f.ordem = posicao[f.id]
        self.atualizar()

    def mover(self, identificador: str, direcao: int) -> bool:
        """Sobe (-1) ou desce (+1) uma faixa na lista. Devolve se mudou."""
        ordenadas = self.faixas_ordenadas
        alvo = next((i for i, f in enumerate(ordenadas) if f.id == identificador), None)
        if alvo is None:
            return False
        destino = alvo + (1 if direcao > 0 else -1)
        if destino < 0 or destino >= len(ordenadas):
            return False
        ordenadas[alvo], ordenadas[destino] = ordenadas[destino], ordenadas[alvo]
        self.ordenar([f.id for f in ordenadas])
        return True

    # -- marcadores ------------------------------------------------------
    def marcar(self, tempo: float, nome: str = "") -> Marcador:
        momento = _limitar(tempo, 0.0, 86400.0)
        compasso = self.mapa.compasso_de(momento) + 1 if self.mapa.duracao else 0
        marcador = Marcador(
            tempo=momento,
            nome=nome or f"Marcador {len(self.marcadores) + 1}",
            compasso=compasso,
        )
        self.marcadores.append(marcador)
        self.marcadores.sort(key=lambda m: m.tempo)
        self.atualizar()
        return marcador

    def remover_marcador(self, indice: int) -> bool:
        if 0 <= indice < len(self.marcadores):
            del self.marcadores[indice]
            self.atualizar()
            return True
        return False

    def secao_em(self, tempo: float) -> dict | None:
        for s in self.secoes:
            inicio = float(s.get("start", s.get("inicio", 0.0)) or 0.0)
            fim = float(s.get("end", s.get("fim", 0.0)) or 0.0)
            if inicio <= tempo < fim:
                return s
        return None

    # -- loop ------------------------------------------------------------
    def definir_loop(self, inicio: float, fim: float) -> bool:
        """Loop em segundos. Devolve False quando o trecho é curto demais."""
        a = _limitar(inicio, 0.0, 86400.0)
        b = _limitar(fim, 0.0, 86400.0)
        if b - a < 0.05:
            return False
        self.loop = {"inicio": round(a, 3), "fim": round(b, 3)}
        self.atualizar()
        return True

    def limpar_loop(self) -> None:
        self.loop = None
        self.atualizar()

    # -- cifra / letra ---------------------------------------------------
    def cifra_obj(self) -> cifra_mod.Cifra:
        """Cifra como objeto — reconstruída a partir do JSON salvo.

        Quando o JSON ainda não tem cifra (projeto novo), ela é montada da
        análise. Fazer isso aqui evita duas rotinas de leitura divergindo.
        """
        salva = self.cifra or {}
        secoes = salva.get("secoes") or []
        if secoes:
            resultado = cifra_mod.Cifra(
                titulo=salva.get("titulo") or self.titulo,
                artista=salva.get("artista") or self.artista,
                tom=salva.get("tom") or "",
                transposicao=int(salva.get("transposicao") or 0),
                numerador=int(salva.get("numerador") or self.mapa.numerador),
                denominador=int(salva.get("denominador") or self.mapa.denominador),
                bpm=float(salva.get("bpm") or self.mapa.bpm or 0.0),
                avisos=list(salva.get("avisos") or []),
            )
            for secao in secoes:
                trecho = cifra_mod.SecaoCifra(
                    nome=str(secao.get("nome") or "Seção"),
                    inicio=float(secao.get("inicio") or 0.0),
                    fim=float(secao.get("fim") or 0.0),
                )
                for linha in secao.get("linhas") or []:
                    trecho.linhas.append(
                        cifra_mod.LinhaCifra(
                            numero=int(linha.get("numero") or 0),
                            inicio=float(linha.get("inicio") or 0.0),
                            fim=float(linha.get("fim") or 0.0),
                            acorde=str(linha.get("acorde") or ""),
                            confianca=float(linha.get("confianca") or 0.0),
                            manual=bool(linha.get("manual")),
                            letra=str(linha.get("letra") or ""),
                        )
                    )
                resultado.secoes.append(trecho)
            return resultado
        return cifra_mod.Cifra(
            titulo=self.titulo,
            artista=self.artista,
            tom="",
            numerador=self.mapa.numerador,
            denominador=self.mapa.denominador,
            bpm=self.mapa.bpm,
        )

    def letra_obj(self) -> letra_mod.Letra:
        return letra_mod.Letra.de_dict(self.letra)

    # -- ciclo de vida ---------------------------------------------------
    def atualizar(self) -> "ProjetoVS":
        self.atualizado_em = time.strftime("%Y-%m-%dT%H:%M:%S")
        return self

    def as_dict(self) -> dict:
        return {
            "versao": VERSAO,
            "titulo": self.titulo,
            "artista": self.artista,
            "criado_em": self.criado_em,
            "atualizado_em": self.atualizado_em,
            "versao_programa": self.versao_programa,
            "pasta": str(self.pasta),
            "mapa": self.mapa.as_dict(),
            "faixas": [f.as_dict() for f in self.faixas_ordenadas],
            "marcadores": [m.as_dict() for m in self.marcadores],
            "mixagem": self.mixagem.as_dict(),
            "loop": self.loop,
            "secoes": self.secoes,
            "cifra": self.cifra,
            "letra": self.letra,
            "avisos": self.avisos,
        }

    def salvar(self, destino: Path | None = None) -> Path:
        """Grava o projeto (atômico: escreve `.tmp` e renomeia)."""
        self.atualizar()
        alvo = Path(destino) if destino else self.caminho_projeto
        alvo.parent.mkdir(parents=True, exist_ok=True)
        temporario = alvo.with_suffix(alvo.suffix + ".tmp")
        temporario.write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        temporario.replace(alvo)
        return alvo

    @classmethod
    def carregar(cls, apoio: Path) -> "ProjetoVS":
        """Lê o projeto da pasta `-apoio`. Levanta `ProjetoInvalido` se não der."""
        alvo = Path(apoio) / ARQUIVO_PROJETO
        if not alvo.is_file():
            raise ProjetoInvalido(f"projeto não encontrado: {alvo}")
        try:
            dados = json.loads(alvo.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProjetoInvalido(f"não foi possível ler o projeto: {exc}") from None
        if not isinstance(dados, dict):
            raise ProjetoInvalido("o arquivo de projeto não é um objeto JSON")
        versao = int(dados.get("versao") or 1)
        if versao > VERSAO:
            raise ProjetoInvalido(
                f"este projeto foi gravado por uma versão mais nova (formato {versao}); "
                f"este programa entende até o formato {VERSAO}. Atualize o MRQ VS para abrir."
            )
        return cls.de_dict(dados)

    @classmethod
    def de_dict(cls, dados: dict) -> "ProjetoVS":
        dados = dados or {}
        pasta = Path(str(dados.get("pasta") or "."))
        projeto = cls(
            pasta=pasta,
            titulo=str(dados.get("titulo") or ""),
            artista=str(dados.get("artista") or ""),
            criado_em=str(dados.get("criado_em") or ""),
            atualizado_em=str(dados.get("atualizado_em") or ""),
            versao_programa=str(dados.get("versao_programa") or ""),
            mapa=mapa_mod.MapaTempo.de_dict(dados.get("mapa") or {}),
            faixas=[Faixa.de_dict(f) for f in (dados.get("faixas") or []) if isinstance(f, dict)],
            marcadores=[
                Marcador.de_dict(m) for m in (dados.get("marcadores") or []) if isinstance(m, dict)
            ],
            mixagem=Mixagem.de_dict(dados.get("mixagem") or {}),
            loop=dados.get("loop") if isinstance(dados.get("loop"), dict) else None,
            secoes=[dict(s) for s in (dados.get("secoes") or []) if isinstance(s, dict)],
            cifra=dados.get("cifra") if isinstance(dados.get("cifra"), dict) else {},
            letra=dados.get("letra") if isinstance(dados.get("letra"), dict) else {},
            avisos=list(dados.get("avisos") or []),
            versao=int(dados.get("versao") or VERSAO),
        )
        if not projeto.criado_em:
            projeto.criado_em = time.strftime("%Y-%m-%dT%H:%M:%S")
        # projetos gravados por versões com defeito podem ter a mesma faixa
        # duas vezes (o L/R aparecia como stem e como ensaio). Aqui a segunda
        # cópia é descartada — abrir a música vale mais que preservar o erro.
        vistos: set[str] = set()
        unicas = []
        for faixa in projeto.faixas:
            if faixa.id in vistos:
                continue
            vistos.add(faixa.id)
            unicas.append(faixa)
        projeto.faixas = unicas
        # faixas sem ordem explícita herdam a posição atual da lista
        for i, faixa in enumerate(projeto.faixas):
            if faixa.ordem == 0 and i > 0:
                faixa.ordem = i
        return projeto

    # -- construção a partir do resultado do pipeline --------------------
    @classmethod
    def de_resultado(cls, resultado, version: str = "") -> "ProjetoVS":
        """Monta o projeto a partir do `project.ProjectResult`.

        É o caminho do "acabou de separar": pega o que a análise mediu
        (mapa, seções, acordes) e os arquivos exportados, e cria as faixas na
        ordem canônica do catálogo de stems.
        """
        from .stems import STEMS, STEM_ORDER

        folder = Path(resultado.folder)
        estudio = resultado.studio.as_dict() if getattr(resultado, "studio", None) else {}
        mapa = mapa_mod.MapaTempo.de_analise(
            batidas=estudio.get("batidas") or [],
            bpm=float(estudio.get("bpm") or getattr(resultado.analysis.tempo, "bpm", 0.0) or 0.0),
            numerador=int(estudio.get("compasso") or getattr(resultado, "compasso", 4) or 4),
            denominador=int(estudio.get("denominador") or 4),
            duracao=float(estudio.get("duracao") or 0.0),
            confianca=float(getattr(resultado.analysis.tempo, "confidence", 0.0) or 0.0),
        )
        projeto = cls(
            pasta=folder,
            titulo=str(getattr(resultado.media, "title", "") or folder.name),
            artista=str(getattr(resultado.media, "channel", "") or ""),
            criado_em=time.strftime("%Y-%m-%dT%H:%M:%S"),
            versao_programa=version,
            mapa=mapa,
            secoes=list(estudio.get("secoes") or []),
            avisos=list(getattr(resultado, "warnings", []) or []),
        )
        # faixas: os arquivos exportados, na ordem do catálogo
        escritos = dict(getattr(resultado, "stems_written", {}) or {})
        posicao = {nome: i for i, nome in enumerate(STEM_ORDER)}
        ordenados = sorted(
            escritos.items(),
            key=lambda kv: (posicao.get(kv[0], 80 + len(kv[1].name)), kv[1].name),
        )
        for chave, caminho in ordenados:
            caminho = Path(caminho)
            if not caminho.is_file():
                continue
            # Chaves que entram em `stems_written` sem serem stem:
            # * `ensaio_lr` — tem faixa própria (tipo "ensaio") no fim da lista;
            # * `clique`/`guia` — vêm da pasta de apoio, não da pasta de áudio
            #   (o `de_resultado` os cria com o caminho relativo certo).
            # Sem esta guarda cada um aparecia duas vezes, e o usuário via dois
            # "Click"/"Ensaio L/R" tocando a mesma coisa.
            if chave in ("ensaio_lr", "clique", "guia"):
                continue
            info = STEMS.get(chave)
            projeto.faixas.append(
                Faixa(
                    id=str(chave),
                    nome=info.label if info else str(chave).replace("_", " ").title(),
                    arquivo=caminho.name,
                    tipo="mix" if chave == "mix" else "stem",
                    cor=info.color if info else "#8a97a8",
                    rotulo_arquivo=caminho.name,
                    ordem=len(projeto.faixas),
                    # o mix e o L/R ficam calados: as faixas já somam o
                    # mesmo material, e somar os dois dobraria o volume. Se
                    # `mix` fosse o único arquivo (modo 2 stems), a tela
                    # descalaria sozinha — ver o trecho logo abaixo.
                    mudo=(chave in ("mix", "instrumental")),
                ).normalizar()
            )
        # faixas de ensaio: clique e guia vêm da pasta de apoio e entram no topo
        apoio = Path(projeto.apoio)
        for chave, nome, cor, tipo in (
            ("guia", "Guia", "#59c08a", "guia"),
            ("clique", "Click", "#c9a227", "clique"),
        ):
            origem = apoio / f"{chave}.wav"
            if not origem.is_file():
                continue
            projeto.faixas.insert(
                0,
                Faixa(
                    id=chave,
                    nome=nome,
                    arquivo=f"../{apoio.name}/{origem.name}",
                    tipo=tipo,
                    cor=cor,
                    rotulo_arquivo=origem.name,
                    ordem=0,
                    mudo=True,
                ).normalizar(),
            )
        lr = getattr(resultado, "lr", None)
        if lr and Path(lr).is_file() and "ensaio_lr" not in {f.id for f in projeto.faixas}:
            projeto.faixas.append(
                Faixa(
                    id="ensaio_lr",
                    nome="Ensaio L/R",
                    arquivo=Path(lr).name,
                    tipo="ensaio",
                    cor="#7a8dab",
                    rotulo_arquivo=Path(lr).name,
                    ordem=len(projeto.faixas),
                    mudo=True,
                ).normalizar()
            )
        # numeração final e descalação de segurança: o "primeiro clique" da
        # tela começa com o mix calado, mas se o mix for a ÚNICA faixa de
        # áudio (separação que só entregou o mix) ele precisa entrar — senão
        # o projeto abre mudo e parece que a separação falhou.
        for i, faixa in enumerate(projeto.faixas):
            faixa.ordem = i
        musicas = [f for f in projeto.faixas if f.tipo in ("stem", "mix", "importada")]
        audiveis = [f for f in musicas if not f.mudo]
        if musicas and not audiveis:
            musicas[0].mudo = False
            projeto.avisos.append(
                "o projeto tinha todas as faixas de música caladas; "
                f"a faixa {musicas[0].id} foi liberada para a música abrir audível"
            )
        # cifra montada da análise (o usuário corrige depois)
        cifra = cifra_mod.Cifra.de_estudio(
            estudio,
            list(getattr(resultado, "acordes", []) or []),
            titulo=projeto.titulo,
            artista=projeto.artista,
            mapa=mapa,
            bpm=mapa.bpm,
            tonalidade=str(estudio.get("tonalidade") or resultado.analysis.key.label()),
        )
        projeto.cifra = cifra.as_dict()
        # marcadores das seções: o mapa do CueWee já as tem, então elas entram
        # como marcadores nomeados em vez de o usuário recriar uma a uma
        for secao in projeto.secoes:
            nome = str(secao.get("nome") or "").strip()
            if not nome:
                continue
            projeto.marcadores.append(
                Marcador(
                    tempo=float(secao.get("start", 0.0) or 0.0),
                    nome=nome,
                    compasso=mapa.compasso_de(float(secao.get("start", 0.0) or 0.0)) + 1,
                )
            )
        return projeto

    # -- edição em lote (o que a tela manda) -----------------------------
    def aplicar_edicoes(self, payload: dict) -> dict:
        """Aplica um patch parcial vindo da tela e devolve o que mudou.

        Só os campos presentes no payload são tocados — é o que permite a tela
        mandar um slider de volume sem reescrever a cifra inteira.
        """
        mudou: list[str] = []
        if "titulo" in payload:
            self.titulo = str(payload.get("titulo") or "")
            mudou.append("titulo")
        if "artista" in payload:
            self.artista = str(payload.get("artista") or "")
            mudou.append("artista")
        if "mixagem" in payload and isinstance(payload["mixagem"], dict):
            self.mixagem = Mixagem.de_dict({**self.mixagem.as_dict(), **payload["mixagem"]})
            mudou.append("mixagem")
        if "mapa" in payload and isinstance(payload["mapa"], dict):
            atual = self.mapa
            novo = payload["mapa"]
            if "bpm" in novo:
                atual = atual.com_bpm(float(novo["bpm"]), manter_grade=bool(novo.get("manter_grade")))
            if "numerador" in novo or "denominador" in novo:
                atual = atual.com_formula(
                    int(novo.get("numerador", atual.numerador)),
                    int(novo.get("denominador", atual.denominador)),
                    int(novo.get("compasso", 1) or 1),
                )
            if "offset" in novo:
                atual = atual.com_offset(float(novo["offset"]))
            if "mudancas" in novo and isinstance(novo["mudancas"], list):
                atual.mudancas = [dict(m) for m in novo["mudancas"] if isinstance(m, dict)]
            if "batidas" in novo and isinstance(novo["batidas"], list):
                atual.batidas = [float(b) for b in novo["batidas"]]
                atual._normalizar()
            self.mapa = atual
            mudou.append("mapa")
        if "faixas" in payload and isinstance(payload["faixas"], list):
            for item in payload["faixas"]:
                if not isinstance(item, dict):
                    continue
                faixa = self.faixa(str(item.get("id") or ""))
                if faixa is None:
                    continue
                if "volume" in item:
                    faixa.volume = _limitar(item["volume"], 0.0, GANHO_MAX)
                if "pan" in item:
                    faixa.pan = _limitar(item["pan"], -PAN_MAX, PAN_MAX)
                if "mudo" in item:
                    faixa.mudo = bool(item["mudo"])
                if "solo" in item:
                    faixa.solo = bool(item["solo"])
                if "oculta" in item:
                    faixa.oculta = bool(item["oculta"])
                if "offset" in item:
                    faixa.offset = _limitar(item["offset"], -3600.0, 3600.0)
                if "nome" in item:
                    faixa.nome = str(item["nome"] or faixa.nome)
                if "altura" in item:
                    faixa.altura = int(_limitar(item["altura"], 0, 400))
                if "fade_in" in item:
                    faixa.fade_in = _limitar(item["fade_in"], 0.0, 60.0)
                if "fade_out" in item:
                    faixa.fade_out = _limitar(item["fade_out"], 0.0, 60.0)
                if "ordem" in item:
                    faixa.ordem = int(_limitar(item["ordem"], 0, 999))
                faixa.normalizar()
            mudou.append("faixas")
        if "ordem" in payload and isinstance(payload["ordem"], list):
            self.ordenar([str(i) for i in payload["ordem"]])
            mudou.append("ordem")
        if "loop" in payload:
            dados = payload["loop"]
            if not dados:
                self.loop = None
            elif isinstance(dados, dict):
                self.definir_loop(float(dados.get("inicio", 0)), float(dados.get("fim", 0)))
            mudou.append("loop")
        if "cifra" in payload and isinstance(payload["cifra"], dict):
            self.cifra = payload["cifra"]
            mudou.append("cifra")
        if "correcoes" in payload and isinstance(payload["correcoes"], dict):
            correcoes = {
                int(k): str(v) for k, v in payload["correcoes"].items() if str(k).isdigit()
            }
            self.cifra = self.cifra_obj().com_correcoes(correcoes).as_dict()
            mudou.append("cifra")
        if "transposicao" in payload:
            try:
                semitons = int(payload["transposicao"]) % 12
            except (TypeError, ValueError):
                semitons = 0
            self.cifra = self.cifra_obj().transposta(semitons).as_dict()
            mudou.append("cifra")
        if "letra" in payload and isinstance(payload["letra"], dict):
            self.letra = payload["letra"]
            mudou.append("letra")
        if "letras" in payload and isinstance(payload["letras"], list):
            # letras digitadas/importadas: alinha ao áudio do projeto
            linhas = [
                {"tempo": item.get("tempo"), "texto": item.get("texto")}
                for item in payload["letras"]
                if isinstance(item, dict) and str(item.get("texto") or "").strip()
            ]
            dados = {"linhas": [], "metodo": "importada", "avisos": []}
            for item in linhas:
                dados["linhas"].append(
                    {"tempo": float(item.get("tempo") or 0.0), "texto": str(item["texto"])}
                )
            self.letra = dados
            mudou.append("letra")
        if "secoes" in payload and isinstance(payload["secoes"], list):
            self.secoes = [dict(s) for s in payload["secoes"] if isinstance(s, dict)]
            mudou.append("secoes")
        if "marcadores" in payload and isinstance(payload["marcadores"], list):
            self.marcadores = [
                Marcador.de_dict(m) for m in payload["marcadores"] if isinstance(m, dict)
            ]
            self.marcadores.sort(key=lambda m: m.tempo)
            mudou.append("marcadores")
        if "marcar" in payload and isinstance(payload["marcar"], dict):
            self.marcar(
                float(payload["marcar"].get("tempo") or 0.0),
                str(payload["marcar"].get("nome") or ""),
            )
            mudou.append("marcadores")
        if mudou:
            self.atualizar()
        return {"ok": bool(mudou), "mudou": mudou, "versao": VERSAO}

    # -- mixagem ---------------------------------------------------------
    def renderizar(
        self,
        destino: Path | None = None,
        sample_rate: int = 44100,
        apenas: list[str] | None = None,
    ) -> dict:
        """Soma as faixas com volume, pan, offset, fades e mute/solo.

        O resultado é um WAV estéreo novo (`_MIX-vs.wav`), nunca por cima de
        um stem. Normalização e limiter são aplicados depois da soma, e o
        relatório diz o pico antes e depois para o usuário saber se houve
        redução.
        """
        import numpy as np

        try:
            import soundfile as sf
        except ModuleNotFoundError:
            from . import dsp

            raise dsp.MissingDependency("soundfile", "renderizar a mixagem") from None

        entram = [f for f in self.faixas_ordenadas if self.audivel(f)]
        if apenas:
            permitidos = {str(a) for a in apenas}
            entram = [f for f in entram if f.id in permitidos]
        ausentes = [f.id for f in entram if self.caminho_da_faixa(f) is None]
        entram = [f for f in entram if self.caminho_da_faixa(f) is not None]
        if not entram:
            raise ProjetoInvalido(
                "nenhuma faixa audível com arquivo disponível — "
                "verifique mute/solo e se os WAVs continuam na pasta do projeto"
            )

        soma = None
        for faixa in entram:
            caminho = self.caminho_da_faixa(faixa)
            if caminho is None:
                continue
            dados, taxa = sf.read(str(caminho), dtype="float32", always_2d=True)
            if taxa != sample_rate:
                from . import dsp as dsp_mod

                dados = dsp_mod.resample_linear(dados, taxa, sample_rate)
            if dados.ndim == 1:
                dados = np.stack([dados, dados], axis=1)
            if dados.shape[1] == 1:
                dados = np.repeat(dados, 2, axis=1)
            else:
                dados = dados[:, :2]
            mono = dados.mean(axis=1)
            if faixa.volume != 1.0:
                mono = mono * float(faixa.volume)
            if faixa.fade_in > 0 or faixa.fade_out > 0:
                mono = _aplicar_fades(mono, sample_rate, faixa.fade_in, faixa.fade_out)
            # equal-power: mover para o lado abaixa o outro lado, mas o
            # volume percebido não cai (mesma regra do mixdown do editor)
            angulo = (faixa.pan + 1.0) * math.pi / 4.0
            esq = mono * math.cos(angulo)
            dir_ = mono * math.sin(angulo)
            deslocamento = int(round(faixa.offset * sample_rate))
            corte = max(0, -deslocamento)
            inicio = max(0, deslocamento)
            if corte >= esq.size:
                continue
            esq = esq[corte:]
            dir_ = dir_[corte:]
            fim = inicio + esq.size
            if soma is None:
                soma = np.zeros((fim, 2), dtype=np.float32)
            elif fim > soma.shape[0]:
                soma = np.pad(soma, ((0, fim - soma.shape[0]), (0, 0)))
            soma[inicio:fim, 0] += esq
            soma[inicio:fim, 1] += dir_
        master = float(self.mixagem.master)
        if master != 1.0:
            soma *= master
        pico_antes = float(np.max(np.abs(soma))) if soma.size else 0.0
        reduzido = False
        if self.mixagem.limitar and pico_antes > 0.99:
            soma = np.clip(soma, -0.99, 0.99)
            reduzido = True
        if self.mixagem.normalizar and pico_antes > 0:
            alvo = 0.891  # -1 dBFS
            if abs(pico_antes - alvo) > 0.02:
                soma = np.clip(soma * (alvo / pico_antes), -0.99, 0.99)
                reduzido = True
        pico_depois = float(np.max(np.abs(soma))) if soma.size else 0.0

        destino = Path(destino) if destino else Path(self.pasta) / f"{Path(self.pasta).name}_MIX-vs.wav"
        destino.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(destino), soma, sample_rate, subtype="PCM_16")
        return {
            "arquivo": str(destino),
            "duracao": round(soma.shape[0] / sample_rate, 3),
            "faixas": [f.id for f in entram],
            "ausentes": ausentes,
            "pico_entrada": round(pico_antes, 4),
            "pico_saida": round(pico_depois, 4),
            "ajustado": reduzido,
            "sample_rate": sample_rate,
        }

    def renderizar_stems(
        self,
        pasta: Path | None = None,
        sample_rate: int = 44100,
        formato: str = "wav",
    ) -> dict:
        """Exporta cada faixa audível com as edições aplicadas, uma por arquivo.

        Por que reexportar stem já separado: se o usuário baixou 3 dB de uma
        faixa e cortou o começo, a DAW dele precisa receber **isso**, não o
        arquivo cru. O nome ganha `_edit` para nunca confundir com o original.
        """
        import numpy as np

        try:
            import soundfile as sf
        except ModuleNotFoundError:
            from . import dsp

            raise dsp.MissingDependency("soundfile", "exportar os stems editados") from None

        from . import export as export_mod

        pasta = Path(pasta) if pasta else Path(self.pasta) / "stems-editados"
        pasta.mkdir(parents=True, exist_ok=True)
        ok, motivo = export_mod.check_export_capabilities(formato)
        if not ok:
            raise ProjetoInvalido(f"não é possível exportar em {formato.upper()}: {motivo}")

        escritos: dict[str, str] = {}
        for faixa in self.faixas_ordenadas:
            if not self.audivel(faixa):
                continue
            caminho = self.caminho_da_faixa(faixa)
            if caminho is None:
                continue
            dados, taxa = sf.read(str(caminho), dtype="float32", always_2d=True)
            if taxa != sample_rate:
                from . import dsp as dsp_mod

                dados = dsp_mod.resample_linear(dados, taxa, sample_rate)
            if faixa.volume != 1.0:
                dados = dados * float(faixa.volume)
            if faixa.fade_in > 0 or faixa.fade_out > 0:
                mono = _aplicar_fades(dados.mean(axis=1), sample_rate, faixa.fade_in, faixa.fade_out)
                dados = np.stack([mono, mono], axis=1) if dados.shape[1] == 1 else np.stack(
                    [
                        _aplicar_fades(dados[:, 0], sample_rate, faixa.fade_in, faixa.fade_out),
                        _aplicar_fades(dados[:, 1], sample_rate, faixa.fade_in, faixa.fade_out),
                    ],
                    axis=1,
                )
            if faixa.pan != 0.0:
                angulo = (faixa.pan + 1.0) * math.pi / 4.0
                mono = dados.mean(axis=1)
                dados = np.stack([mono * math.cos(angulo), mono * math.sin(angulo)], axis=1)
            deslocamento = int(round(faixa.offset * sample_rate))
            if deslocamento > 0:
                dados = np.pad(dados, ((deslocamento, 0), (0, 0)))
            elif deslocamento < 0:
                dados = dados[-deslocamento:]
            if dados.size == 0:
                continue
            sufixo = "wav" if formato == "wav" else formato
            alvo = pasta / f"{_slug(faixa.id)}_edit.{sufixo}"
            ops = export_mod.ExportOptions(
                fmt=formato,
                bits=24,
                normalize=False,
                title=f"{self.titulo} — {faixa.nome}",
                artist=self.artista,
                bpm=self.mapa.bpm,
            )
            export_mod.export_audio(dados, sample_rate, alvo.with_suffix(""), ops)
            escritos[faixa.id] = str(alvo)
        if not escritos:
            raise ProjetoInvalido("nenhuma faixa pôde ser exportada")
        return {"pasta": str(pasta), "arquivos": escritos, "formato": formato}

    # -- exportação de texto/partitura -----------------------------------
    def exportar_apoio(self) -> dict:
        """Grava cifra, letra, MIDI e ficha imprimível na pasta `-apoio`."""
        from . import ficha as ficha_mod
        from . import midi as midi_mod

        apoio = Path(self.apoio)
        apoio.mkdir(parents=True, exist_ok=True)
        cifra = self.cifra_obj()
        base = _slug(self.titulo or Path(self.pasta).name)
        arquivos: dict[str, str] = {}
        for formato, caminho in cifra.escrever(apoio, base=f"{base}_cifra").items():
            arquivos[f"cifra_{formato}"] = str(caminho)
        letra = self.letra_obj()
        if not letra.vazia:
            for formato, caminho in letra.escrever(apoio, base=f"{base}_letra").items():
                arquivos[f"letra_{formato}"] = str(caminho)
        midi_path = apoio / f"{base}_cifra-e-clique.mid"
        midi_mod.escrever(
            midi_path,
            self.mapa,
            cifra=cifra,
            secoes=self.secoes,
            titulo=self.titulo or base,
        )
        arquivos["midi"] = str(midi_path)
        ficha_path = apoio / f"{base}_ficha.html"
        ficha_path.write_text(
            ficha_mod.gerar(self, cifra=cifra, letra=letra), encoding="utf-8"
        )
        arquivos["ficha"] = str(ficha_path)
        return arquivos


def _aplicar_fades(sinal, sample_rate: int, fade_in: float, fade_out: float):
    """Rampa linear curta nas pontas (evita estalo em corte seco)."""
    import numpy as np

    saida = np.array(sinal, dtype=np.float32, copy=True)
    n_in = min(int(max(0.0, fade_in) * sample_rate), saida.size)
    n_out = min(int(max(0.0, fade_out) * sample_rate), saida.size)
    if n_in > 1:
        saida[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)
    if n_out > 1:
        saida[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)
    return saida


def _slug(texto: str) -> str:
    limpo = re.sub(r"[^\w\-. ]+", "", str(texto or "faixa"), flags=re.UNICODE).strip()
    return (limpo or "faixa")[:60].replace(" ", "_")
