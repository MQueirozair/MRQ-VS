"""Icone do MRQ VS em todos os formatos que o sistema precisa.

Por que um modulo e nao so um arquivo solto: cada lugar pede um formato
diferente. O Windows quer .ico (com varios tamanhos dentro), a janela do
Tkinter quer PNG ou .ico, a pagina web usa o atalho /favicon.ico e o
instalador quer um PNG grande. Manter cinco copias a mao significa uma delas
ficar velha - foi assim que o logo antigo sobreviveu em dois lugares.

Uma unica fonte (assets/icone-original.png) e derivados gerados daqui, com
`regerar()`. O .ico e montado a mao (cabecalho + PNGs embutidos, formato
suportado desde o Windows Vista) para nao depender de Pillow - o pacote
portatil nao leva Pillow e nao vale 12 MB so por causa de um icone.

Se o ImageMagick estiver disponivel usamos ele para o redimensionamento
(bem melhor que o nearest-neighbor manual); se nao estiver, o PNG grande e
reduzido por media de blocos, o que basta para 16-256 px de um desenho chapado.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

#: tamanhos que o Windows pede de um .ico (o Explorer usa 16, 32, 48 e 256)
TAMANHOS_ICO = (16, 24, 32, 48, 64, 128, 256)


def raiz() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def fonte() -> Path:
    """PNG original entregue pelo usuário (a maior resolução disponível)."""
    return raiz() / "assets" / "icone-original.png"


def pasta_web() -> Path:
    return Path(__file__).resolve().parent / "web"


def _tem_magick() -> str:
    for exe in ("magick", "convert"):
        achado = shutil.which(exe)
        if achado:
            return achado
    return ""


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    import zlib

    crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)


def _redimensionar_png_puro(origem: Path, destino: Path, lado: int) -> bool:
    """Redimensiona um PNG RGBA/RGB 8-bit não-entrelaçado usando apenas Python + zlib."""
    import zlib

    dados = origem.read_bytes()
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    pos = 8
    largura = altura = profundidade = cor = entrelacado = 0
    idat_partes: list[bytes] = []
    while pos + 8 <= len(dados):
        tam = struct.unpack(">I", dados[pos : pos + 4])[0]
        tipo = dados[pos + 4 : pos + 8]
        corpo = dados[pos + 8 : pos + 8 + tam]
        pos += 12 + tam
        if tipo == b"IHDR":
            largura, altura, profundidade, cor, _comp, _filt, entrelacado = struct.unpack(
                ">IIBBBBB", corpo[:13]
            )
        elif tipo == b"IDAT":
            idat_partes.append(corpo)
        elif tipo == b"IEND":
            break
    canais = {2: 3, 6: 4}.get(cor, 0)
    if profundidade != 8 or entrelacado != 0 or canais == 0 or largura <= 0 or altura <= 0:
        return False
    if largura == lado and altura == lado:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, destino)
        return destino.is_file()

    bruto = zlib.decompress(b"".join(idat_partes))
    passo = largura * canais
    linhas: list[bytearray] = []
    cursor = 0
    ant = bytearray(passo)
    for _ in range(altura):
        filtro = bruto[cursor]
        linha = bytearray(bruto[cursor + 1 : cursor + 1 + passo])
        cursor += 1 + passo
        if filtro == 1:  # Sub
            for x in range(canais, passo):
                linha[x] = (linha[x] + linha[x - canais]) & 0xFF
        elif filtro == 2:  # Up
            for x in range(passo):
                linha[x] = (linha[x] + ant[x]) & 0xFF
        elif filtro == 3:  # Average
            for x in range(passo):
                esq = linha[x - canais] if x >= canais else 0
                linha[x] = (linha[x] + ((esq + ant[x]) >> 1)) & 0xFF
        elif filtro == 4:  # Paeth
            for x in range(passo):
                a = linha[x - canais] if x >= canais else 0
                b = ant[x]
                c = ant[x - canais] if x >= canais else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                linha[x] = (linha[x] + pr) & 0xFF
        elif filtro != 0:
            return False
        linhas.append(linha)
        ant = linha

    # Média de blocos (ou amostragem bilinear simples quando ampliando)
    saida = bytearray()
    for ny in range(lado):
        saida.append(0)  # filtro None
        y0 = ny * altura / lado
        y1 = (ny + 1) * altura / lado
        iy0 = int(y0)
        iy1 = max(iy0 + 1, min(altura, int(y1 + 0.9999)))
        for nx in range(lado):
            x0 = nx * largura / lado
            x1 = (nx + 1) * largura / lado
            ix0 = int(x0)
            ix1 = max(ix0 + 1, min(largura, int(x1 + 0.9999)))
            acc = [0] * 4
            cont = 0
            for yy in range(iy0, iy1):
                ln = linhas[yy]
                for xx in range(ix0, ix1):
                    base = xx * canais
                    acc[0] += ln[base]
                    acc[1] += ln[base + 1]
                    acc[2] += ln[base + 2]
                    acc[3] += ln[base + 3] if canais == 4 else 255
                    cont += 1
            for c_idx in range(4):
                saida.append((acc[c_idx] + cont // 2) // max(1, cont))

    ihdr = struct.pack(">IIBBBBB", lado, lado, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(saida), 9))
        + _png_chunk(b"IEND", b"")
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(png)
    return destino.is_file()


def _redimensionar(origem: Path, destino: Path, lado: int) -> bool:
    """Reduz a origem para `lado`x`lado`. Devolve False se nada foi gerado."""
    try:
        from PIL import Image

        with Image.open(origem) as img:
            rgba = img.convert("RGBA").resize((lado, lado), Image.Resampling.LANCZOS)
            destino.parent.mkdir(parents=True, exist_ok=True)
            rgba.save(destino, format="PNG")
            return destino.is_file()
    except Exception:  # noqa: BLE001 - Pillow é opcional
        pass

    magick = _tem_magick()
    if magick:
        cmd = [magick]
        if magick.endswith("magick"):
            cmd += ["convert"]
        # -background none preserva o canto arredondado transparente
        cmd += [
            str(origem), "-resize", f"{lado}x{lado}",
            "-gravity", "center", "-extent", f"{lado}x{lado}",
            "-strip", f"PNG32:{destino}",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            return destino.is_file()
        except (subprocess.SubprocessError, OSError):
            pass

    try:
        if _redimensionar_png_puro(origem, destino, lado):
            return True
    except Exception:  # noqa: BLE001
        pass

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, destino)
        return destino.is_file()
    except OSError:
        return False


def gerar_ico(destino: Path, origem: Path | None = None) -> Path:
    """Monta um .ico multi-resolução com PNGs embutidos (Vista+)."""
    origem = origem or fonte()
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporarios: list[tuple[int, Path]] = []
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="icone-"))
    try:
        for lado in TAMANHOS_ICO:
            alvo = tmp / f"{lado}.png"
            if _redimensionar(origem, alvo, lado):
                temporarios.append((lado, alvo))
        if not temporarios:
            raise RuntimeError("nao foi possivel gerar nenhum tamanho do icone")

        # ICONDIR: reservado(2) tipo(2=icone) quantidade(2)
        cabecalho = struct.pack("<HHH", 0, 1, len(temporarios))
        entradas = b""
        dados = b""
        offset = 6 + 16 * len(temporarios)
        for lado, caminho in temporarios:
            conteudo = caminho.read_bytes()
            # 0 significa 256 no campo de largura/altura do formato ICO
            dimensao = 0 if lado >= 256 else lado
            entradas += struct.pack(
                "<BBBBHHII", dimensao, dimensao, 0, 0, 1, 32, len(conteudo), offset
            )
            dados += conteudo
            offset += len(conteudo)
        destino.write_bytes(cabecalho + entradas + dados)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return destino


def regerar() -> dict[str, str]:
    """Gera todos os derivados a partir de assets/icone-original.png."""
    origem = fonte()
    if not origem.is_file():
        raise FileNotFoundError(f"icone original ausente: {origem}")
    gerados: dict[str, str] = {}

    web = pasta_web()
    web.mkdir(parents=True, exist_ok=True)
    # favicon da pagina e o mesmo arquivo do .ico do Windows
    ico = gerar_ico(web / "favicon.ico", origem)
    gerados["web/favicon.ico"] = str(ico)
    # PNG 512 para a tela (cabeçalho) e para o instalador
    grande = web / "icone-512.png"
    if _redimensionar(origem, grande, 512):
        gerados["web/icone-512.png"] = str(grande)
    pequeno = web / "icone-192.png"
    if _redimensionar(origem, pequeno, 192):
        gerados["web/icone-192.png"] = str(pequeno)

    windows = raiz() / "windows"
    if windows.is_dir():
        gerados["windows/mrq-vs.ico"] = str(gerar_ico(windows / "mrq-vs.ico", origem))
    return gerados


if __name__ == "__main__":  # pragma: no cover
    for chave, valor in regerar().items():
        print(f"{chave}: {valor}")
