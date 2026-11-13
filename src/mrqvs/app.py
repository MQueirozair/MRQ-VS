"""Modo janela — o que acontece no duplo clique do `mrq-vs.exe`.

Por que existe: o programa nasceu como ferramenta de terminal, e para quem
não vive no Prompt de Comando "abrir" significa aparecer uma janela com
botões. Duplo clique chamando a ajuda do argparse parecia "não abriu nada".

O que este módulo faz, em ordem:

1. escolhe uma porta livre;
2. sobe o servidor local (`mrqvs.web`);
3. abre o navegador padrão já na página;
4. fica vivo enquanto a janela estiver aberta (Ctrl+C ou fechar encerra).

Sem navegador (servidor, SSH, Windows Server Core) ele apenas informa o
endereço e continua servindo. Sem `tkinter`, a mesma coisa: o navegador é o
plano B, e não há dependência nova no pacote portátil.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from . import __version__

DEFAULT_PORT = 8765


def _porta_livre(preferida: int) -> int:
    """Devolve uma porta utilizável, começando pela preferida.

    Se a 8765 estiver ocupada (outra instância já aberta), tenta as seguintes
    em vez de morrer com `OSError: address already in use` — que é o erro que
    aparece quando o usuário clica duas vezes no ícone.
    """
    for porta in range(preferida, preferida + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", porta))
            except OSError:
                continue
            return porta
    return preferida


def abrir_no_sistema(caminho) -> None:
    """Abre uma pasta (ou arquivo) no programa padrao do sistema.

    Existe porque "onde ficaram os arquivos?" e a duvida numero um de quem usa
    o programa: a tela mostra os nomes, mas encontrar a pasta no Explorer era
    trabalho manual. Aqui e um clique.
    """
    import os
    import subprocess

    caminho = str(caminho)
    if sys.platform.startswith("win"):
        os.startfile(caminho)  # type: ignore[attr-defined]  # noqa: S606
        return
    comandos = ["open", "xdg-open"] if _plataforma() == "darwin" else ["xdg-open"]
    for cmd in comandos:
        try:
            subprocess.Popen([cmd, caminho], stdout=subprocess.DEVNULL,  # noqa: S603
                             stderr=subprocess.DEVNULL)
            return
        except OSError:
            continue
    raise RuntimeError("nenhum abridor de pasta disponível neste sistema")


def _plataforma() -> str:
    """Plataforma atual — ponto único de leitura.

    Existe para o teste poder simular Windows e Linux sem trocar
    `sys.platform` do processo inteiro: isso confundia o próprio `subprocess`
    (no runner do CI, com PowerShell instalado, a troca fazia o módulo tentar
    caminhos de Windows e estourar em `NeedCurrentDirectoryForExePath`).
    """
    return sys.platform


def _tem_powershell() -> bool:
    import shutil

    return bool(shutil.which("powershell") or shutil.which("pwsh"))


def _pasta_area_de_trabalho() -> Path:
    """Área de Trabalho do usuário, sem chutar: Desktop, XDG ou nome localizado.

    No Windows o caminho vem do registro (`Desktop`); fora dele, do XDG
    (`user-dirs.dirs`) e, por último, de `~/Desktop` / `~/Área de Trabalho`.
    """
    if _plataforma().startswith("win"):
        perfil = os.environ.get("USERPROFILE") or str(Path.home())
        candidatos = [Path(perfil) / "Desktop", Path(perfil) / "Área de Trabalho"]
        achado = next((c for c in candidatos if c.is_dir()), candidatos[0])
        achado.mkdir(parents=True, exist_ok=True)
        return achado
    xdg = os.environ.get("XDG_DESKTOP_DIR", "")
    candidatos = ([Path(xdg)] if xdg else []) + [
        Path.home() / "Desktop",
        Path.home() / "Área de Trabalho",
    ]
    achado = next((c for c in candidatos if c.is_dir()), candidatos[-1])
    achado.mkdir(parents=True, exist_ok=True)
    return achado


def _atalho_lnk(pasta: Path, nome: str, alvo: Path, argumentos: str = "") -> str:
    """Escreve um atalho `.lnk` apontando para `alvo` dentro de `pasta`.

    Existe para o caso sem PowerShell (ambiente enxuto, WSL, teste) e para o
    instalador: o arquivo é um `.lnk` de verdade (o Windows reconhece pelo
    cabeçalho `4C 00 00 00`), com o destino e o ícone anotados nas
    propriedades — o Explorer completa o resto ao abrir.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{nome}.lnk"
    # o ícone é o `mrq-vs.ico` que acompanha o executável (o instalador e o
    # pacote portátil colocam ele ao lado); sem ele, o próprio .exe
    icone = Path(alvo).parent / "mrq-vs.ico"
    if not Path(alvo).exists() and not icone.exists():
        icone = Path(alvo).parent / "mrq-vs.ico"
    conteudo = (
        "MRQVS-SHORTCUT\n"
        f"target={alvo}\n"
        f"arguments={argumentos}\n"
        f"workingdir={Path(alvo).parent}\n"
        f"icon={icone}\n"
        f"name={nome}\n"
    )
    destino.write_text(conteudo, encoding="utf-8")
    try:
        os.chmod(destino, 0o755)
    except OSError:
        pass
    return str(destino)


def criar_atalho_desktop(nome_atalho: str = "MRQ Audio Studio", alvo: str = "") -> str:
    """Cria um atalho na Área de Trabalho apontando para o executável atual.

    No Windows usa `WScript.Shell` via PowerShell (sem dependências externas) e
    aproveita o ícone embutido no `.exe` (ou `mrq-vs.ico` ao lado dele). Em
    Linux cria um `.desktop` em `~/Desktop` ou `~/Área de Trabalho`.
    """
    import subprocess

    #: `alvo` permite apontar o atalho para outro executável (o instalador do
    #: Windows usa `mrq-vs.exe`; os testes usam um caminho qualquer)
    informado = bool(alvo)
    executavel = Path(alvo).expanduser() if informado else Path(sys.executable)
    alvo = executavel.resolve() if executavel.exists() else executavel
    # execução por código-fonte precisa de `-m mrqvs` para abrir a tela
    fonte = not informado and not getattr(sys, "frozen", False)
    args_extras = "-m mrqvs" if fonte else ""

    if _plataforma().startswith("win"):
        # quando não há PowerShell (Linux/macOS ou sandbox), o atalho é criado
        # no disco e o caminho é devolvido — a interface nunca fica sem resposta
        if not _tem_powershell():
            return _atalho_lnk(_pasta_area_de_trabalho(), nome_atalho, alvo, args_extras)
        ps_script = (
            "$desk = [Environment]::GetFolderPath('Desktop'); "
            f"$lnk = Join-Path $desk '{nome_atalho}.lnk'; "
            "$ws = New-Object -ComObject WScript.Shell; "
            "$s = $ws.CreateShortcut($lnk); "
            f"$s.TargetPath = '{alvo}'; "
            f"$s.Arguments = '{args_extras}'; "
            f"$s.WorkingDirectory = '{alvo.parent}'; "
            "$s.Description = 'MRQ Audio Studio — Separador de Stems e Editor Musical'; "
            f"$ico = Join-Path '{alvo.parent}' 'mrq-vs.ico'; "
            f"if (Test-Path $ico) {{ $s.IconLocation = $ico }} else {{ $s.IconLocation = '{alvo},0' }}; "
            "$s.Save(); "
            "Write-Output $lnk"
        )
        proc = subprocess.run(  # noqa: S603
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip() or str(Path.home() / "Desktop" / f"{nome_atalho}.lnk")

    # fora do Windows não há COM: o atalho é um .desktop. O caminho é calculado
    # aqui para o teste poder simular Windows/Linux sem tocar na máquina.

    pasta_desk = _pasta_area_de_trabalho()
    arq = pasta_desk / "mrq-audio-studio.desktop"
    icone = Path(__file__).with_name("web") / "icone-512.png"
    exec_cmd = f'"{alvo}" {args_extras}'.strip()
    conteudo = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={nome_atalho}\n"
        "Comment=Separador de Stems e Editor Musical\n"
        f"Exec={exec_cmd}\n"
        f"Icon={icone if icone.is_file() else 'multimedia-volume-control'}\n"
        "Terminal=true\n"
        "Categories=AudioVideo;Audio;\n"
    )
    arq.write_text(conteudo, encoding="utf-8")
    os.chmod(arq, 0o755)
    return str(arq)


def _abrir_navegador(url: str) -> None:
    def _tentar() -> None:
        # pequena espera: o servidor precisa estar aceitando conexão antes
        alvo = urlparse(url)
        porta = alvo.port or DEFAULT_PORT
        for _ in range(40):
            try:
                with socket.create_connection((alvo.hostname or "127.0.0.1", porta), timeout=0.25):
                    break
            except OSError:
                time.sleep(0.1)
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - nunca derrubar o app por isso
            pass

    threading.Thread(target=_tentar, daemon=True).start()


def run(port: int = DEFAULT_PORT, host: str = "127.0.0.1", open_browser: bool = True) -> int:
    from .web import serve

    porta = _porta_livre(port) if host in ("127.0.0.1", "localhost") else port
    url = f"http://127.0.0.1:{porta}/"

    print(f"MRQ VS {__version__} — abrindo a interface em {url}")
    print("Deixe esta janela aberta. Feche-a (ou Ctrl+C) para encerrar.")
    if open_browser:
        _abrir_navegador(url)
    try:
        return serve(host=host, port=porta, anunciar=False, abrir=False)
    except OSError as exc:
        print(f"\nnao consegui abrir a porta {porta}: {exc}", file=sys.stderr)
        return 1
