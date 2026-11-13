"""Instalador do "cérebro" de IA (demucs + torch), um clique.

Por que existe: o backend que separa com qualidade de Moises é o Demucs, e
ele depende de PyTorch — cerca de 1 GB de download. Isso não pode ir dentro
do zip portátil (o pacote passaria de 60 MB para 1,5 GB), então fica como uma
instalação opcional, feita **na máquina do usuário**, dentro de `mrq-ai/`:

    mrq-ai/python.exe          interpretador extraído (Python completo)
    mrq-ai/Lib/site-packages   demucs, torch, ...

Detalhes que importam de verdade:

* o Python **embutido** do pacote (`runtime/`) não serve: ele é isolado por
  `._pth` e não tem `ensurepip`/`venv`. Por isso o instalador baixa um Python
  completo do python.org e o extrai.
* o download é grande; mostramos progresso em MB, não uma tela parada.
* se falhar no meio, o ambiente é apagado — nunca sobra meia instalação que
  faça o programa achar que tem IA quando não tem.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import runtime

#: Versões de Python tentadas em ordem. Um 404 numa versão não pode matar a
#: instalação — o python.org remove builds antigas de vez em quando.
PYTHON_VERSOES = ("3.13.7", "3.13.6", "3.13.5", "3.13.4", "3.13.3", "3.12.10")
PYTHON_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"
#: get-pip, para instalar pacotes no Python extraído
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"
PACOTE = "demucs"

#: Pacote que o Demucs **usa mas não declara** como dependência.
#: Verificado abrindo o `demucs-4.1.0` de verdade e lendo os imports no topo
#: de cada módulo que o `python -m demucs` carrega:
#:
#:     separate.py    torch
#:     api.py         sphn, torch
#:     apply.py       torch, tqdm
#:     demucs.py      julius, torch
#:     transformer.py einops, numpy, torch     <- o import que quebrava
#:     htdemucs.py    einops, torch
#:     audio.py       julius, lameenc, numpy, torch
#:     repo.py        torch, yaml
#:
#: Todos os outros vêm declarados no `requires_dist` do pacote. O `numpy`
#: NÃO — e é importado direto em `transformer.py` e `audio.py`. Resultado
#: num ambiente limpo:
#:
#:     ModuleNotFoundError: No module named 'numpy'
#:
#: O bug é do empacotamento do Demucs, mas quem vê a tela de erro é o
#: usuário, então instalamos nós.
PACOTES_EXTRA = ("numpy",)
#: Tudo o que o motor de IA precisa ter para funcionar de verdade.
PACOTES = (PACOTE, *PACOTES_EXTRA)

#: Motor de qualidade superior, opcional. O `audio-separator` traz o
#: BS-RoFormer (1º lugar no SDX23), que na separação de VOZ fica ~4 dB acima
#: do Demucs: 12.9 dB contra 8.3 dB. Numa faixa de igreja isso é a diferença
#: entre uma voz limpa e uma voz com resto de banda.
#:
#: Por que não entra no pacote principal: são mais ~400 MB e o Demucs já
#: resolve 4 e 6 stems. Vem só se o usuário quiser, e reaproveita o torch
#: que já está instalado — o custo não é 1 GB de novo.
PACOTE_QUALIDADE = "audio-separator"
#: O substituto do Spleeter. Vem depois do torch na mesma instalação, então
#: somado ao motor de IA custa quase nada a mais.
PACOTE_LEVE = "openunmix"

#: Script que lista o que falta no ambiente. `find_spec` acha o pacote sem
#: importar (importar torch aqui custaria 200 MB de RAM na interface).
_CODIGO_DOS_FALTANTES = (
    "import importlib.util\n"
    f"faltam = [m for m in {list(PACOTES)!r} "
    "if importlib.util.find_spec(m) is None]\n"
    "print(' '.join(faltam))\n"
)

_UA = "Mozilla/5.0 (compatible; MRQ-VS)"


class IAError(RuntimeError):
    """Falha na instalação do ambiente de IA, com instrução de correção."""


# ---------------------------------------------------------------------------
# Estado da instalação, legível por outra requisição HTTP
# ---------------------------------------------------------------------------
# Por que isto existe: a instalação leva 10–20 min. Antes, a interface ficava
# com uma barra animada "de mentira" e não tinha como saber se estava
# andando, travada ou morta — era exatamente a tela que o usuário descreveu
# como "não sai disto". Agora o progresso é real e qualquer requisição pode
# ler (e cancelar) sem esperar o download terminar.
ESTADO: dict = {
    "rodando": False,
    "fracao": 0.0,
    "texto": "",
    "erro": "",
    "terminado": False,
    "iniciado_em": 0.0,
    "cancelar": False,
}


def estado() -> dict:
    """Cópia do estado atual (é o que `/api/ia/estado` devolve)."""
    dados = {k: v for k, v in ESTADO.items() if k != "cancelar"}
    if ESTADO["rodando"]:
        dados["instalado"] = False
        dados["faltando"] = []
    else:
        # `faltando` é o que permite a tela oferecer o botão certo: se o
        # ambiente existe mas não carrega, o problema é reparo, não instalação.
        faltando = _modulos_que_faltam()
        dados["faltando"] = faltando
        dados["instalado"] = not faltando
        dados["reparavel"] = bool(faltando) and runtime.ai_python() is not None
        # Motor de qualidade (RoFormer): só faz sentido oferecer se o motor
        # principal já funciona, porque ele reaproveita o torch de lá.
        dados["qualidade"] = _testar_audio_separator() if not faltando else False
    return dados


def cancelar() -> None:
    """Pede o cancelamento; o próximo passo da instalação para e limpa tudo."""
    if ESTADO["rodando"]:
        ESTADO["cancelar"] = True
        ESTADO["texto"] = "cancelando…"


def _checar_cancelamento() -> None:
    if ESTADO["cancelar"]:
        raise IAError("instalação cancelada por você")


def _publicar(fracao: float, texto: str) -> None:
    ESTADO["fracao"] = max(0.0, min(1.0, float(fracao)))
    ESTADO["texto"] = texto


def esta_instalado() -> bool:
    """True quando `mrq-ai` tem interpretador **e** o demucs importa."""
    return bool(_modulos_que_faltam() == [])


def _modulos_que_faltam() -> list[str]:
    """Módulos que o motor de IA precisa e não estão presentes.

    Por que não basta testar o demucs: o `estado` de 0.1.10 dizia "instalado"
    para um ambiente em que **o demucs não importa** — o `_testar_demucs`
    devolvia False, a instalação dava certo, e só na hora de separar o áudio
    vinha o erro de verdade. Aqui listamos o nome de cada um que falta, para a
    tela poder dizer "falta numpy" em vez de "instalado" + erro.
    """
    python = runtime.ai_python()
    if python is None:
        return ["python"]
    # `find_spec` num subprocesso: barato, e não contamina o processo da
    # interface com o torch carregado (200 MB de RAM à toa).
    proc = _rodar_teste(python, _CODIGO_DOS_FALTANTES)
    if proc is None:
        return list(PACOTES)
    try:
        return proc.strip().split()
    except Exception:  # noqa: BLE001 - saída inesperada = não confiar
        return list(PACOTES)


def _rodar_teste(python: Path, codigo: str) -> str | None:
    """Roda um `-c` curto e devolve o stdout, ou None se falhar."""
    try:
        proc = subprocess.run(
            [str(python), "-c", codigo],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _testar_demucs() -> bool:  # noqa: D401 - mantido por compatibilidade
    """O demucs carrega de fato? (import completo, não só `find_spec`)."""
    python = runtime.ai_python()
    if python is None:
        return False
    try:
        proc = subprocess.run(
            [str(python), "-c", "import demucs, torch, numpy; print(demucs.__version__)"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _baixar(url: str, destino: Path, progress=None, rotulo: str = "") -> Path:
    """Download com progresso em MB. `progress(fracao, texto)`."""
    import urllib.request

    destino.parent.mkdir(parents=True, exist_ok=True)
    pedido = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(pedido, timeout=120) as resposta:
        total = int(resposta.headers.get("Content-Length") or 0)
        baixado = 0
        with destino.open("wb") as fh:
            while True:
                bloco = resposta.read(1024 * 256)
                if not bloco:
                    break
                fh.write(bloco)
                baixado += len(bloco)
                if progress and total:
                    progress(
                        baixado / total,
                        f"{rotulo}: {baixado / 1e6:.0f} / {total / 1e6:.0f} MB",
                    )
    if destino.stat().st_size < 1024:
        raise IAError(f"o download de {url} veio vazio")
    return destino


def python_do_sistema() -> str | None:
    """Python 3.10+ com pip, se já existir na máquina.

    Quando existe, é o melhor caminho: cria-se um venv em `mrq-ai/` e nada de
    baixar interpretador — a instalação fica bem menor e mais confiável.
    """
    candidatos = []
    for nome in ("python", "python3", "py"):
        achado = shutil.which(nome)
        if achado:
            candidatos.append([achado])
    for cmd in candidatos:
        try:
            proc = subprocess.run(
                [*cmd, "-c", "import sys; print(sys.version_info[:2])"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        try:
            maior, menor = (int(x) for x in proc.stdout.strip().strip("()").split(","))
        except ValueError:
            continue
        if (maior, menor) >= (3, 10):
            return " ".join(cmd)
    return None


def instalar_qualidade(progress=None) -> Path:
    """Instala o BS-RoFormer (via audio-separator) reaproveitando o torch.

    Qualidade: o RoFormer é o estado da arte (SDX23), ~4 dB acima do Demucs
    em voz. O download extra é o pacote e as libs de apoio; o torch de 1 GB
    que já está em `mrq-ai/` é reutilizado, então não se paga duas vezes.

    Falha de forma explícita: se o ambiente de IA ainda não existe, isso é um
    erro de uso, não algo para tentar consertar aqui.
    """
    import time

    alvo = runtime.ai_dir()
    python = runtime.ai_python()
    if python is None:
        raise IAError(
            "instale primeiro o motor de IA (botão 'Instalar IA') — o "
            "RoFormer reaproveita o torch que ele instala"
        )

    ESTADO.update(
        rodando=True,
        fracao=0.30,
        texto="instalando o motor de qualidade (BS-RoFormer)…",
        erro="",
        terminado=False,
        iniciado_em=time.time(),
        cancelar=False,
    )
    try:
        _checar_cancelamento()
        _rodar(
            [str(python), "-m", "pip", "install", "--no-input",
             "--no-warn-script-location", "--disable-pip-version-check",
             "--progress-bar", "off", PACOTE_QUALIDADE],
            alvo,
            "instalar o motor de qualidade",
            timeout=5400,
        )
        ESTADO.update(fracao=0.97, texto="verificando o motor de qualidade…")
        if not _testar_audio_separator():
            raise IAError(
                "o audio-separator foi instalado mas não carrega.\n"
                + manual()
            )
        ESTADO.update(rodando=False, terminado=True, fracao=1.0, texto="pronto!")
        return alvo
    except Exception as exc:
        ESTADO.update(
            rodando=False,
            terminado=True,
            texto="falhou",
            erro=str(exc) or "falha desconhecida ao instalar o motor de qualidade",
        )
        raise
    finally:
        ESTADO["cancelar"] = False


def instalar_leve(progress=None) -> Path:
    """Instala o open-unmix no ambiente de IA — o motor leve.

    Por que no mesmo ambiente do Demucs e não num terceiro: o open-unmix
    precisa de torch, e o torch já está aqui (1 GB). Instalar num ambiente
    separado significaria baixar o torch de novo por causa de um pacote de
    poucos MB. O que se paga é só o modelo (~300 MB de pesos na primeira
    separação).
    """
    import time

    alvo = runtime.ai_dir()
    python = runtime.ai_python()
    if python is None:
        raise IAError(
            "instale primeiro o motor de IA (botão 'Instalar IA') — o motor "
            "leve reaproveita o torch que ele instala"
        )

    ESTADO.update(
        rodando=True,
        fracao=0.25,
        texto="instalando o motor leve (open-unmix)…",
        erro="",
        terminado=False,
        iniciado_em=time.time(),
        cancelar=False,
    )
    try:
        _checar_cancelamento()
        _rodar(
            [str(python), "-m", "pip", "install", "--no-input",
             "--no-warn-script-location", "--disable-pip-version-check",
             "--progress-bar", "off", PACOTE_LEVE],
            alvo,
            "instalar o motor leve",
            timeout=3600,
        )
        ESTADO.update(fracao=0.92, texto="verificando o motor leve…")
        if not _testar_openunmix():
            raise IAError("o open-unmix foi instalado mas não carrega.\n" + manual())
        ESTADO.update(rodando=False, terminado=True, fracao=1.0, texto="pronto!")
        return alvo
    except Exception as exc:
        ESTADO.update(
            rodando=False,
            terminado=True,
            texto="falhou",
            erro=str(exc) or "falha desconhecida ao instalar o motor leve",
        )
        raise
    finally:
        ESTADO["cancelar"] = False


def _testar_openunmix() -> bool:
    python = runtime.ai_python()
    if python is None:
        return False
    try:
        proc = subprocess.run(
            [str(python), "-c", "import openunmix, torch; print('ok')"],
            capture_output=True, text=True, timeout=240,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _testar_audio_separator() -> bool:
    """O `audio-separator` importa? (o CLI é o que o programa executa)"""
    python = runtime.ai_python()
    if python is None:
        return False
    try:
        proc = subprocess.run(
            [str(python), "-c", "import audio_separator; print('ok')"],
            capture_output=True, text=True, timeout=180,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def reparar(progress=None) -> Path:
    """Completa um ambiente que já existe, sem baixar torch de novo.

    O caso real: o usuário instalou na 0.1.10, o Demucs veio **sem numpy**
    (dependência não declarada no pacote dele) e separar áudio falhou com
    `ModuleNotFoundError`. Reinstalar tudo custaria outro 1 GB de download.
    Aqui só instalamos o que falta, e a verificação final continua sendo o
    import de verdade.
    """
    import time

    alvo = runtime.ai_dir()
    python = runtime.ai_python()
    if python is None:
        # não há ambiente nenhum: é uma instalação do zero, não um reparo
        return instalar(progress=progress)

    faltam = _modulos_que_faltam()
    ESTADO.update(
        rodando=True,
        fracao=0.5 if faltam else 0.9,
        texto="verificando o motor de IA…",
        erro="",
        terminado=False,
        iniciado_em=time.time(),
        cancelar=False,
    )
    try:
        if faltam:
            ESTADO.update(
                fracao=0.6,
                texto="faltava " + ", ".join(faltam) + " — instalando…",
            )
            _checar_cancelamento()
            _rodar(
                [str(python), "-m", "pip", "install", "--no-input",
                 "--no-warn-script-location", "--disable-pip-version-check",
                 "--progress-bar", "off", *faltam],
                alvo,
                "completar o motor de IA",
                timeout=3600,
            )
        ESTADO.update(fracao=0.97, texto="verificando a instalação…")
        if not _testar_demucs():
            raise IAError(
                "o motor de IA ainda não carrega depois do reparo.\n"
                + manual()
            )
        ESTADO.update(rodando=False, terminado=True, fracao=1.0, texto="pronto!")
        return alvo
    except Exception as exc:
        ESTADO.update(
            rodando=False,
            terminado=True,
            texto="falhou",
            erro=str(exc) or "falha desconhecida no reparo",
        )
        raise
    finally:
        ESTADO["cancelar"] = False


def instalar(progress=None, forcar: bool = False) -> Path:
    """Monta o ambiente de IA (demucs + torch) em `mrq-ai/`.

    Publica o andamento em `ESTADO` (lido por `/api/ia/estado`), respeita
    `cancelar()` entre os passos e, ao falhar, deixa o motivo exato em
    `ESTADO["erro"]` — nunca uma barra girando para sempre.
    """
    import time

    alvo = runtime.ai_dir()
    if esta_instalado() and not forcar:
        ESTADO.update(rodando=False, fracao=1.0, texto="já estava instalado", terminado=True)
        return alvo

    # reinicia o estado: uma tentativa nova não pode herdar o erro da anterior
    ESTADO.update(
        rodando=True,
        fracao=0.0,
        texto="preparando…",
        erro="",
        terminado=False,
        iniciado_em=time.time(),
        cancelar=False,
    )

    def dizer(fracao: float, texto: str) -> None:
        # O cancelamento é checado em TODO aviso de progresso: é o ponto por
        # onde a instalação passa o tempo inteiro. Sem isso, cancelar durante
        # os downloads (a maior parte do tempo) não fazia nada.
        _checar_cancelamento()
        _publicar(fracao, texto)
        if progress:
            progress(fracao, texto)

    try:
        resultado = _instalar_de_verdade(alvo, dizer, forcar)
    except BaseException as exc:
        ESTADO.update(
            rodando=False,
            terminado=True,
            erro=str(exc) or exc.__class__.__name__,
            texto="falhou",
        )
        raise
    finally:
        ESTADO["cancelar"] = False
    ESTADO.update(rodando=False, terminado=True, fracao=1.0, texto="pronto!")
    return resultado


def _instalar_de_verdade(alvo: Path, dizer, forcar: bool) -> Path:
    """O trabalho em si (separado para o estado ser sempre finalizado)."""
    if alvo.exists() and forcar:
        shutil.rmtree(alvo, ignore_errors=True)

    # Atalho: Python do sistema -> venv. Evita baixar ~30 MB de interpretador
    # e usa o pip já testado da máquina.
    sistema = python_do_sistema()
    if sistema and not forcar:
        try:
            alvo.mkdir(parents=True, exist_ok=True)
            dizer(0.02, f"criando o ambiente com o Python do sistema ({sistema})…")
            _checar_cancelamento()
            _rodar([sistema, "-m", "venv", str(alvo)], alvo.parent, "criar o ambiente")
            python = runtime.ai_python()
            if python is None:
                raise IAError("o venv foi criado mas não tem python")
            dizer(0.10, "instalando demucs e torch (pode levar 10–20 min)…")
            _checar_cancelamento()
            # --progress-bar: sem isso o pip fica MUDO por 15 minutos e não há
            # como mostrar andamento nem detectar travamento.
            _rodar(
                [str(python), "-m", "pip", "install", "--no-input",
                 "--no-warn-script-location", "--disable-pip-version-check",
                 "--progress-bar", "off", *PACOTES],
                alvo,
                "instalar o demucs",
                timeout=7200,
            )
            dizer(0.98, "verificando a instalação…")
            if not _testar_demucs():
                faltam = _modulos_que_faltam()
                detalhe = f" (falta: {', '.join(faltam)})" if faltam else ""
                raise IAError("o demucs foi instalado mas não carrega" + detalhe)
            dizer(1.0, "pronto!")
            return alvo
        except Exception:
            # venv com o Python do sistema pode falhar (sem venv/ensurepip).
            # Não é fatal: cai para o Python embutido baixado, exceto se o
            # usuário pediu cancelamento.
            if ESTADO["cancelar"]:
                shutil.rmtree(alvo, ignore_errors=True)
                raise
            if esta_instalado():
                raise
            shutil.rmtree(alvo, ignore_errors=True)
            dizer(0.02, "o Python do sistema não serve; baixando um Python completo…")

    alvo.mkdir(parents=True, exist_ok=True)
    temporario = alvo / "_download.zip"
    try:
        # 1. Python completo (o embeddable do pacote não tem pip)
        dizer(0.01, "baixando o Python para o motor de IA…")
        for versao in PYTHON_VERSOES:
            _checar_cancelamento()
            try:
                _baixar(
                    PYTHON_URL.format(v=versao),
                    temporario,
                    progress=lambda f, t: dizer(0.02 + f * 0.28, t),
                    rotulo=f"Python {versao}",
                )
                break
            except Exception:
                if ESTADO["cancelar"]:
                    raise
                continue
        else:
            raise IAError(
                "não consegui baixar o Python do python.org (rede/firewall?).\n"
                + manual()
            )
        with zipfile.ZipFile(temporario) as z:
            z.extractall(alvo)
        temporario.unlink(missing_ok=True)

        python = runtime.ai_python()
        if python is None:
            raise IAError("o Python baixado não tem python.exe — baixe de novo")
        # o zip do python.org traz `python313._pth` que isola do site-packages;
        # sem apagar/ajustar, `pip install` "funciona" mas o import não acha.
        _habilitar_site_packages(alvo)

        # 2. pip
        _checar_cancelamento()
        dizer(0.32, "preparando o pip…")
        getpip = alvo / "get-pip.py"
        _baixar(GETPIP_URL, getpip, progress=lambda f, t: dizer(0.32 + f * 0.06, t), rotulo="pip")
        _rodar([str(python), str(getpip), "--no-warn-script-location"], alvo, "instalar o pip")
        getpip.unlink(missing_ok=True)

        # 3. demucs (+ torch)
        _checar_cancelamento()
        dizer(0.40, "instalando demucs e torch (pode levar 10–20 min)…")
        _rodar(
            [str(python), "-m", "pip", "install", "--no-input",
             "--no-warn-script-location", "--disable-pip-version-check",
             "--progress-bar", "off", *PACOTES],
            alvo,
            "instalar o demucs",
            timeout=7200,
        )
        dizer(0.98, "verificando a instalação…")
        if not _testar_demucs():
            faltam = _modulos_que_faltam()
            detalhe = f" (falta: {', '.join(faltam)})" if faltam else ""
            raise IAError("o demucs foi instalado mas não carrega" + detalhe)
        dizer(1.0, "pronto!")
        return alvo
    except Exception:
        if not esta_instalado():
            shutil.rmtree(alvo, ignore_errors=True)  # não deixa meia instalação
        raise


def _habilitar_site_packages(alvo: Path) -> None:
    """Ajusta o `._pth` do Python embutido para enxergar o pip/site-packages."""
    for pth in alvo.glob("python*._pth"):
        linhas = pth.read_text(encoding="utf-8", errors="replace").splitlines()
        if "Lib\\site-packages" in linhas or "Lib/site-packages" in linhas:
            continue
        linhas += ["Lib\\site-packages", "import site"]
        pth.write_text("\r\n".join(linhas) + "\r\n", encoding="utf-8")


def _rodar(cmd: list[str], cwd: Path, acao: str, timeout: int = 900) -> None:
    """Executa um passo da instalação mostrando o que ele está fazendo.

    Antes era `subprocess.run(capture_output=True)`: o pip ficava 15 minutos
    sem imprimir nada e a interface não tinha como saber se estava vivo,
    travado num download ou esperando rede. Agora as últimas linhas de saída
    vão para `ESTADO["texto"]`, e há um limite de tempo de verdade.
    """
    import time

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    inicio = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as exc:
        raise IAError(f"não consegui executar {cmd[0]}: {exc}") from None

    ultimas: list[str] = []
    try:
        assert proc.stdout is not None
        for linha in proc.stdout:
            linha = linha.strip()
            if linha:
                ultimas.append(linha)
                del ultimas[:-40]
                # o pip reescreve a mesma linha do progresso; mostramos a última
                _publicar(ESTADO["fracao"], f"{acao}: {linha[:160]}")
            if ESTADO["cancelar"]:
                proc.kill()
                raise IAError("instalação cancelada por você")
            if time.time() - inicio > timeout:
                proc.kill()
                raise IAError(f"{acao} demorou mais de {timeout // 60} min e foi interrompido")
        proc.wait(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0:
        raise IAError(f"falhou ao {acao}:\n" + "\n".join(ultimas[-20:]))


def remover() -> None:
    """Apaga o ambiente de IA (volta ao backend DSP)."""
    shutil.rmtree(runtime.ai_dir(), ignore_errors=True)


def manual() -> str:
    """Instruções para quem prefere instalar à mão."""
    return (
        "Instalação manual do motor de IA:\n"
        "  1. winget install Python.Python.3.12\n"
        "  2. python -m pip install demucs\n"
        "  O MRQ VS encontra o demucs do sistema automaticamente."
    )
