"""Biblioteca de musicas ja separadas - reabrir com um clique.

Por que existe: ate a 0.1.15, ao fechar a tela (ou reiniciar o programa) o
resultado desaparecia. Para ouvir uma musica separada ontem era preciso
lembrar a pasta, abrir o Explorer e achar os stems na mao. Quem usa o
programa toda semana separa dezenas de musicas, entao isso vira trabalho.

O que este modulo faz: guarda, num unico JSON dentro da pasta de dados do
programa (runtime.home()), o indice de tudo que ja foi separado. Cada
entrada aponta para a pasta de audio e para a pasta `-apoio`. A tela chama
`listar()` e mostra a lista; clicar chama /api/biblioteca/abrir e o player
recarrega os arquivos direto do disco, sem separar nada de novo.

Decisoes que importam:

* o indice e derivado do disco, nao uma copia da verdade. `listar()` descarta
  entradas cuja pasta sumiu (pen drive removido, pasta apagada) - melhor a
  lista encolher do que abrir um erro.
* a capa sai da pasta `-apoio` a cada leitura, entao trocar a capa na mao
  atualiza a lista sozinho.
* escrita atomica (tmp + replace): o programa pode ser fechado no meio sem
  deixar o indice pela metade.
* o indice nunca guarda audio, so caminhos. Assim nao duplica os stems.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

from . import runtime

ARQUIVO = "biblioteca.json"
EXTS_AUDIO = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".aiff", ".aif", ".wma"}
EXTS_CAPA = (".jpg", ".jpeg", ".png", ".webp")


def _caminho() -> Path:
    return runtime.home() / ARQUIVO


def _ler() -> dict[str, Any]:
    caminho = _caminho()
    if not caminho.is_file():
        return {"versoes": []}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"versoes": []}
    if not isinstance(dados, dict) or not isinstance(dados.get("versoes"), list):
        return {"versoes": []}
    return dados


def _gravar(dados: dict[str, Any]) -> None:
    caminho = _caminho()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, caminho)


def _capa_da_pasta(apoio: Path | None) -> str:
    if apoio is None:
        return ""
    for ext in EXTS_CAPA:
        achada = sorted(apoio.glob(f"*{ext}"))
        if achada:
            return str(achada[0])
    return ""


def _contar_audio(pasta: Path) -> int:
    try:
        return sum(1 for f in pasta.iterdir() if f.is_file() and f.suffix.lower() in EXTS_AUDIO)
    except OSError:
        return 0


def registrar(
    pasta: str | Path,
    *,
    apoio: str | Path | None = None,
    titulo: str = "",
    bpm: int | None = None,
    tom: str = "",
    motor: str = "",
    duracao: float | None = None,
    origem: str = "",
) -> dict[str, Any]:
    """Grava (ou atualiza) a entrada desta musica no indice."""
    pasta = Path(pasta)
    # a pasta `-apoio` tambem tem audio (original e clique), mas nao e uma
    # musica separada: registrar ela encheria a lista de duplicatas
    if pasta.name.endswith("-apoio"):
        return {}
    apoio_p = Path(apoio) if apoio else None
    if apoio_p is None:
        candidata = pasta.parent / f"{pasta.name}-apoio"
        apoio_p = candidata if candidata.is_dir() else None

    entrada = {
        "id": str(pasta),
        "pasta": str(pasta),
        "apoio": str(apoio_p) if apoio_p else "",
        "nome": pasta.name,
        "titulo": titulo or pasta.name,
        "bpm": bpm,
        "tom": tom or "",
        "motor": motor or "",
        "duracao": duracao,
        "origem": origem or "",
        "stems": _contar_audio(pasta),
        "capa": _capa_da_pasta(apoio_p),
        "salvo_em": time.time(),
    }
    if entrada["stems"] == 0:
        return entrada

    dados = _ler()
    versoes = [v for v in dados["versoes"] if v.get("id") != entrada["id"]]
    dados["versoes"] = [entrada, *versoes][:500]
    _gravar(dados)
    return entrada


def listar(limite: int = 100) -> list[dict[str, Any]]:
    """Lista o que ainda existe no disco, do mais recente para o mais antigo."""
    dados = _ler()
    vivas: list[dict[str, Any]] = []
    for entrada in dados.get("versoes", []):
        pasta = Path(entrada.get("pasta", ""))
        if not entrada.get("pasta") or not pasta.is_dir():
            continue
        entrada["stems"] = _contar_audio(pasta)
        if entrada["stems"] == 0:
            continue
        apoio = Path(entrada["apoio"]) if entrada.get("apoio") else None
        entrada["capa"] = _capa_da_pasta(apoio) if apoio and apoio.is_dir() else ""
        vivas.append(entrada)
    if len(vivas) != len(dados.get("versoes", [])):
        dados["versoes"] = vivas
        _gravar(dados)
    return vivas[:limite]


def _chave_do_stem(arquivo: Path, mapa_json: dict[str, str]) -> str:
    """Descobre o id canônico do stem (`vocals`, `drums`, `mix`, `ensaio_lr`)."""
    import re

    if arquivo.name in mapa_json:
        return mapa_json[arquivo.name]
    nome = arquivo.stem
    if nome.upper().endswith("ENSAIO_LR"):
        return "ensaio_lr"
    m = re.search(r"_(\d{2})_([a-z0-9_]+)$", nome.lower())
    if m:
        return m.group(2)
    return nome


def abrir(identificador: str) -> dict[str, Any] | None:
    """Carrega uma musica salva para a tela, com os audios ja prontos.

    Devolve o mesmo formato que a tela usa no resultado, para o player e a
    lista de arquivos serem montados pelo mesmo codigo - nada de uma segunda
    tela que quebra quando a primeira muda.
    """
    from urllib.parse import quote

    pasta = Path(identificador)
    if not pasta.is_dir():
        return None
    entrada = next((v for v in listar(limite=500) if v.get("id") == identificador), None)
    if entrada is None:
        return None

    apoio = Path(entrada["apoio"]) if entrada.get("apoio") else None
    if apoio is None or not apoio.is_dir():
        candidata = pasta.parent / f"{pasta.name}-apoio"
        apoio = candidata if candidata.is_dir() else None

    relatorio = ""
    if apoio and (apoio / "relatorio.md").is_file():
        relatorio = str(apoio / "relatorio.md")

    # Compasso, acordes e faixas de ensaio vem do projeto.json gravado na
    # pasta -apoio. Sem isso, reabrir uma musica da biblioteca mostrava a
    # tela sem a faixa de acordes e sem o player de guia/clique - parecia
    # que a musica tinha sido separada por uma versao antiga.
    compasso, compasso_conf, acordes_json = 4, 0.0, []
    camelot = ""
    secoes_json: list[dict[str, Any]] = []
    estudio: dict[str, Any] = {}
    mapa_nomes: dict[str, str] = {}
    guia_url = clique_url = lr_url = ""
    if apoio:
        try:
            dados_json = json.loads((apoio / "projeto.json").read_text(encoding="utf-8"))
            analise = dados_json.get("analise") or {}
            compasso = int(analise.get("compasso") or 4)
            compasso_conf = float(analise.get("compasso_confianca") or 0.0)
            camelot = str(analise.get("camelot") or "")
            acordes_json = analise.get("acordes") or []
            secoes_json = analise.get("secoes") or []
            estudio = analise.get("estudio") or {}
            mapa_nomes = {
                str(nome_arq): str(chave)
                for chave, nome_arq in (dados_json.get("arquivos") or {}).items()
            }
            # edições do editor (cifra, seções, compasso): são do usuário e
            # vencem a detecção — se ele corrigiu um acorde, reabrir a música
            # não pode trazer o acorde errado de volta.
            try:
                from . import mixdown

                edicoes = mixdown.ler_edicoes(apoio)
            except Exception:  # noqa: BLE001
                edicoes = {}
            if not estudio:
                # projeto.json de versão anterior à timeline do Studio: monta
                # o mínimo com o que já existe lá. Sem isto a música antiga
                # abre sem régua e sem cifra, e parece que o Studio quebrou.
                estudio = {
                    "batidas": analise.get("batidas") or [],
                    "compasso": compasso,
                    "compasso_confianca": compasso_conf,
                    "acordes": acordes_json,
                    "secoes": [
                        {
                            "start": s.get("inicio", 0.0),
                            "end": s.get("fim", 0.0),
                            "rotulo": s.get("rotulo", ""),
                            "nome": s.get("rotulo", ""),
                        }
                        for s in secoes_json
                    ],
                    "duracao": float((dados_json.get("audio") or {}).get("duracao") or 0.0),
                    "bpm": float(analise.get("bpm") or 0.0),
                    "tonalidade": analise.get("tonalidade") or "",
                }
            # As edições vencem o detectado. `is not None` importa: lista
            # vazia significa "o usuário apagou todos", não "não mexeu".
            if edicoes.get("acordes") is not None:
                estudio["acordes"] = edicoes["acordes"]
            if edicoes.get("secoes") is not None:
                estudio["secoes"] = edicoes["secoes"]
            if edicoes.get("compasso"):
                estudio["compasso"] = int(edicoes["compasso"])
                compasso = int(edicoes["compasso"])
            if edicoes.get("denominador"):
                estudio["denominador"] = 8 if int(edicoes["denominador"]) == 8 else 4
            if edicoes.get("bpm"):
                estudio["bpm"] = float(edicoes["bpm"])
            if edicoes.get("tom"):
                estudio["tonalidade"] = str(edicoes["tom"])
        except (OSError, ValueError):
            pass
        for nome, chave in (("guia.wav", "guia"), ("clique.wav", "clique")):
            alvo = apoio / nome
            if alvo.is_file():
                url = f"/api/file?p={quote(alvo.as_posix(), safe='/')}"
                if chave == "guia":
                    guia_url = url
                else:
                    clique_url = url

    # L/R fica na pasta de AUDIO (é áudio de palco, vai junto dos stems)
    for candidato in sorted(pasta.glob("*ENSAIO_LR*")):
        if candidato.is_file() and candidato.suffix.lower() in EXTS_AUDIO:
            lr_url = f"/api/file?p={quote(candidato.as_posix(), safe='/')}"
            break

    arquivos: dict[str, Any] = {}
    for f in sorted(pasta.iterdir()):
        if not f.is_file() or f.suffix.lower() not in EXTS_AUDIO:
            continue
        chave = _chave_do_stem(f, mapa_nomes)
        arquivos[chave] = {
            "nome": f.name,
            "url": f"/api/file?p={quote(f.as_posix(), safe='/')}",
            "audio": True,
        }
    if not arquivos:
        return None

    # Mesmo contrato do /api/run: `render()` na tela e um so. Faltando um
    # campo aqui (bpm_confianca, secoes...) o resultado reaberto aparecia
    # pela metade - e "pela metade" nao da erro, so fica errado calado.
    return {
        "ok": True,
        "pasta": str(pasta),
        "nome_pasta": pasta.name,
        "apoio": str(apoio) if apoio else "",
        # O topo da tela (KPIs) tem de mostrar o MESMO que o Studio: se o
        # usuário corrigiu o BPM ou o tom, é a correção que vale, não o que
        # foi detectado na primeira separação (que ficava "—" para sempre).
        "bpm": estudio.get("bpm") or entrada.get("bpm"),
        "bpm_confianca": 1.0,
        "tonalidade": estudio.get("tonalidade") or entrada.get("tom") or "—",
        "camelot": camelot,
        "secoes": secoes_json,
        "compasso": compasso,
        "compasso_confianca": compasso_conf,
        "acordes": acordes_json,
        "estudio": estudio,
        "guia": guia_url,
        "clique": clique_url,
        "lr": lr_url,
        "backend": (entrada.get("motor") or "").split("/")[0] or "—",
        "model": (entrada.get("motor") or "/").split("/")[-1] or "—",
        "arquivos": arquivos,
        "avisos": [],
        "segundos": 0,
        # /api/file aceita caminho absoluto dentro das raizes conhecidas
        "relatorio": f"/api/file?p={quote(Path(relatorio).as_posix(), safe='/')}" if relatorio else "",
        "capa": (
            f"/api/bib/capa?p={quote(Path(entrada['capa']).as_posix(), safe='/')}"
            if entrada.get("capa")
            else ""
        ),
        "titulo": entrada.get("titulo", pasta.name),
        "motor": entrada.get("motor", ""),
        "duracao": entrada.get("duracao"),
        "stems": len(arquivos),
        "da_biblioteca": True,
    }


def remover(identificador: str) -> bool:
    """Tira a musica da lista. Nao apaga os arquivos do disco."""
    dados = _ler()
    antes = len(dados.get("versoes", []))
    dados["versoes"] = [v for v in dados.get("versoes", []) if v.get("id") != identificador]
    if len(dados["versoes"]) == antes:
        return False
    _gravar(dados)
    return True


def esquecer(pastas: Iterable[str | Path]) -> None:
    """Remove do indice as pastas indicadas (usado em testes)."""
    alvos = {str(Path(p)) for p in pastas}
    dados = _ler()
    dados["versoes"] = [v for v in dados.get("versoes", []) if v.get("id") not in alvos]
    _gravar(dados)
