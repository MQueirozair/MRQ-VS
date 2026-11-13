"""Capa do vídeo dentro do projeto.

Por que existe: a pasta gerada tem áudio, relatório e — nas versões anteriores
— nenhuma pista visual de qual vídeo era. Quem trabalha com 30 projetos quer
reconhecer pelo olho, não pelo nome do arquivo. O yt-dlp já devolve a URL da
thumbnail nos metadados, então o custo é baixar uma imagem pequena.

Três regras:

* **nunca falhar o projeto por causa da capa**: qualquer erro vira aviso;
* preferir a imagem maior (a capa do vídeo, não quadros aleatórios);
* gravar como `capa.jpg` — o nome importa, é o que o `relatorio.md` cita e o
  que a interface busca em `/api/cover`.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

#: o YouTube serve 120x90 por padrão; maxresdefault é 1280x720
_QUALIDADES = ("maxresdefault", "hqdefault", "mqdefault")
_UA = "Mozilla/5.0 (compatible; MRQ-VS)"


def download(url: str, destino: Path, timeout: int = 30) -> Path | None:
    """Baixa a capa para `destino`. Devolve o caminho ou None (sem drama)."""
    if not url:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    for candidata in _variantes(url):
        try:
            pedido = urllib.request.Request(candidata, headers={"User-Agent": _UA})
            with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
                dados = resposta.read(8 * 1024 * 1024)
            if len(dados) < 1024:
                continue
            destino.write_bytes(dados)
            return destino
        except Exception:  # noqa: BLE001 - capa é opcional, nunca crítica
            continue
    return None


def _variantes(url: str) -> list[str]:
    """Tenta a capa em resolução maior antes das pequenas.

    O yt-dlp às vezes entrega `hqdefault.jpg`; trocar o nome do arquivo é o
    jeito barato de pedir a mesma imagem em 1280x720. Se não existir, o
    próprio YouTube devolve 404 e o laço segue para a próxima.
    """
    base = url.split("?")[0]
    if "/vi/" in base or "ytimg" in base:
        prefixo = base.rsplit("/", 1)[0]
        variantes = [f"{prefixo}/{q}.jpg" for q in _QUALIDADES]
        return [url, *[v for v in variantes if v != url]]
    return [url]


def para_media_url(arquivo: Path, out_root: Path) -> str:
    """URL que a interface usa para exibir a capa."""
    from urllib.parse import quote

    resolvido = Path(arquivo).resolve()
    try:
        relativo = resolvido.relative_to(Path(out_root).resolve())
        return f"/api/cover?p={quote(relativo.as_posix(), safe='/')}"
    except ValueError:
        pass
    # A música pode estar fora de `out/` (pasta de dados do usuário, na
    # biblioteca). A rota /api/cover aceita caminho absoluto apenas quando a
    # capa existe e pertence a uma pasta autorizada; caminhos arbitrários fora
    # das pastas conhecidas devolvem "".
    if not resolvido.is_file():
        return ""
    from . import web

    if not web._pode_servir(resolvido):
        return ""
    return f"/api/cover?p={quote(resolvido.as_posix(), safe='/')}"
