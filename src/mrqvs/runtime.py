"""Detecção do "Python de verdade" para chamar backends externos.

Parece exagero, mas é essencial: o MRQ VS é distribuído também como executável
único (PyInstaller). Dentro de um binário congelado, `sys.executable` **é o
próprio mrq-vs.exe** — rodar `[sys.executable, "-m", "demucs"]` reiniciaria o
app em vez de chamar o Demucs, num laço silencioso que parece "travamento".

Então toda chamada a um backend externo (`demucs`, `audio_separator`,
`spleeter`, `yt_dlp`) passa por `python_cmd()`, que devolve o interpretador do
sistema quando estamos congelados e o interpretador atual quando rodamos a
partir do código-fonte.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

#: Nomes de interpretador tentados, em ordem, quando congelado.
CANDIDATES = ("python3", "python", "py")

#: Ambiente de IA do pacote portátil (`mrq-ai/`) — o mesmo diretório em que o
#: instalador de IA (`mrqvs.ai`) coloca demucs + torch.
AI_DIRNAME = "mrq-ai"


def _user_data_dir() -> Path:
    """Pasta persistente de dados do usuário quando instalado fora do repo."""
    import os

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local:
            return Path(local) / "MRQ-VS"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "mrq-vs"
    return Path.home() / ".local" / "share" / "mrq-vs"


def home() -> Path:
    """Raiz dos dados do usuário (envios, saídas, ambiente de IA).

    Mesma lógica de `ai_dir()`: `MRQVS_HOME` quando existe, senão a pasta do
    pacote portátil (`runtime/` e `app/` lado a lado), senão a pasta do `.pyz`
    ou do repositório em desenvolvimento (`pyproject.toml`), e por fim uma
    pasta persistente do usuário (nunca o `_MEI` temporário do PyInstaller nem
    `site-packages` somente-leitura).
    """
    import os

    base = os.environ.get("MRQVS_HOME")
    if base:
        return Path(base)
    here = Path(__file__).resolve()
    for candidato in here.parents:
        if (candidato / "runtime").is_dir() and (candidato / "app").is_dir():
            return candidato
        if candidato.suffix.lower() == ".pyz":
            pai = candidato.parent
            return pai.parent if pai.name == "app" else pai
    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / AI_DIRNAME).is_dir() or (exe_dir / "musicas").is_dir():
            return exe_dir
        return _user_data_dir()
    repo_root = here.parents[2]
    if (repo_root / "pyproject.toml").is_file():
        return repo_root
    return _user_data_dir()


def ai_dir() -> Path:
    """Pasta do ambiente de IA.

    No pacote portátil ela fica **fora** de `runtime/` e de `lib/`, porque é
    criada depois, na máquina do usuário, e não deve ser confundida com o
    Python embutido (que é isolado por ._pth e não carrega site-packages).
    """
    import os

    base = os.environ.get("MRQVS_AI_DIR")
    if base:
        return Path(base)
    return home() / AI_DIRNAME


def ai_python() -> Path | None:
    """Interpretador do ambiente de IA, se já estiver instalado.

    `mrq-ai/python.exe` cobre o caso do Python embutido completo que o
    instalador extrai; `Scripts/python.exe` e `bin/python`, o venv normal.
    """
    candidatos = [
        ai_dir() / "python.exe",
        ai_dir() / "Scripts" / "python.exe",
        ai_dir() / "bin" / "python",
    ]
    for candidato in candidatos:
        if candidato.is_file():
            return candidato
    return None


def is_frozen() -> bool:
    """True quando rodando dentro de um executável gerado pelo PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def python_cmd() -> str | None:
    """Comando do interpretador a usar para `-m <módulo>`.

    Devolve `None` se congelado e não houver Python no PATH — nesse caso os
    backends externos simplesmente não estão disponíveis (e o `doctor` diz
    como instalar).
    """
    # O ambiente de IA, quando instalado, é o interpretador certo para os
    # backends de separação: é onde o demucs e o torch realmente estão.
    ia = ai_python()
    if ia is not None:
        return str(ia)
    if not is_frozen():
        return sys.executable
    for name in CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def module_command(module: str, *args: str) -> list[str] | None:
    """`[python, '-m', module, *args]`, ou None se não há interpretador."""
    python = python_cmd()
    if not python:
        return None
    return [python, "-m", module, *args]


def interpreter_note() -> str:
    """Frase para o `doctor` explicar de onde vêm os backends."""
    ia = ai_python()
    if ia is not None:
        return f"usando o ambiente de IA {ai_dir()}"
    if not is_frozen():
        return f"usando o interpretador atual ({sys.executable})"
    python = python_cmd()
    if python:
        return f"executável portátil; backends externos via {python}"
    return (
        "executável portátil e nenhum Python no PATH: só o backend DSP está "
        "disponível. Instale Python e depois `pip install demucs` para IA."
    )
