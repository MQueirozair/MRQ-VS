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

import socket
import sys
import threading
import time
import webbrowser
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
    comandos = ["open", "xdg-open"] if sys.platform == "darwin" else ["xdg-open"]
    for cmd in comandos:
        try:
            subprocess.Popen([cmd, caminho], stdout=subprocess.DEVNULL,  # noqa: S603
                             stderr=subprocess.DEVNULL)
            return
        except OSError:
            continue
    raise RuntimeError("nenhum abridor de pasta disponível neste sistema")


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
