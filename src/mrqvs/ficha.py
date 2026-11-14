"""Ficha da música: cifra + letra + seções numa página A4 pronta para imprimir.

Por que HTML e não PDF: gerar PDF de verdade exige biblioteca (weasyprint,
reportlab) que pesa dezenas de MB e traz dependências de sistema. O navegador
que o programa já abre imprime em PDF com `Ctrl+P` — inclusive com "salvar
como PDF" — e a ficha sai igual em qualquer máquina. O arquivo é **um só**,
com o CSS embutido: dá para mandar no grupo da banda e abrir no celular sem
internet.

O que a ficha contém, e por que:

* **cabeçalho** — título, artista, tom (e o tom gravado quando transposta),
  BPM, compasso e a contagem de compassos. É o que o músico confere antes de
  começar;
* **seções** — nome + compasso de entrada de cada uma, na ordem;
* **cifra + letra** — a cifra por seção, com a letra sincronizada embaixo do
  compasso em que começa. Acorde estimado com baixa confiança sai com `?` e
  a legenda explica; nada é arredondado para parecer certeza;
* **avisos** — o que foi estimado e não deve ser tratado como fato;
* **rodapé** — como o arquivo foi gerado (versão do programa e data), para
  quem recebe saber de onde veio.
"""

from __future__ import annotations

import html
import time
from pathlib import Path

from . import cifra as cifra_mod
from . import letra as letra_mod


def _esc(texto) -> str:
    return html.escape(str(texto if texto is not None else ""), quote=True)


CSS = """
:root{--tinta:#14181d;--fraco:#5b6672;--linha:#d7dde4;--fundo:#fff;--destaque:#0f62fe}
*{box-sizing:border-box}
body{margin:0;background:#eef1f4;color:var(--tinta);
     font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Ubuntu,sans-serif;line-height:1.45}
.folha{background:var(--fundo);max-width:820px;margin:18px auto;padding:34px 40px 28px;
       box-shadow:0 1px 3px rgba(0,0,0,.14)}
header{border-bottom:2px solid var(--tinta);padding-bottom:12px;margin-bottom:18px}
h1{margin:0 0 2px;font-size:23px;letter-spacing:-.01em}
.artista{color:var(--fraco);font-size:14px;margin-bottom:10px}
.meta{display:flex;flex-wrap:wrap;gap:8px;font-size:12.5px}
.meta span{border:1px solid var(--linha);border-radius:999px;padding:2px 9px}
.meta b{font-weight:650}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--fraco);
   margin:22px 0 8px;border-bottom:1px solid var(--linha);padding-bottom:4px}
.secoes{display:flex;flex-wrap:wrap;gap:6px;font-size:12.5px}
.secoes span{border:1px solid var(--linha);border-radius:4px;padding:2px 8px}
.secoes .n{color:var(--fraco);margin-left:5px;font-variant-numeric:tabular-nums}
.bloco{margin:16px 0 0;break-inside:avoid}
.bloco h3{font-size:13px;margin:0 0 6px;display:flex;justify-content:space-between;
          border-left:3px solid var(--destaque);padding-left:8px}
.bloco h3 small{color:var(--fraco);font-weight:500}
table.cifra{width:100%;border-collapse:collapse;font-size:13px}
table.cifra td{padding:1px 6px 1px 0;vertical-align:top}
td.num{width:34px;color:var(--fraco);font-variant-numeric:tabular-nums;font-size:11.5px;padding-top:3px}
td.acorde{font-weight:700;color:var(--destaque);white-space:nowrap;padding-right:14px}
td.acorde.incerto{color:#a06000}
td.acorde.incerto::after{content:" ?";font-weight:600}
td.letra{color:var(--tinta)}
tr.sem-letra td.letra{color:var(--fraco);font-style:italic}
.vazio{color:var(--fraco);font-size:12.5px;font-style:italic}
.avisos{margin:18px 0 0;padding:10px 14px;border-left:3px solid #c9a227;background:#fffbf0;
        font-size:12px;color:#4a3f22}
.avisos ul{margin:4px 0 0;padding-left:18px}
footer{margin-top:26px;padding-top:10px;border-top:1px solid var(--linha);
       color:var(--fraco);font-size:11px;display:flex;justify-content:space-between;gap:12px}
@media print{
  body{background:#fff}
  .folha{box-shadow:none;margin:0;max-width:none;padding:0}
  header{margin-bottom:10px}
  .bloco{break-inside:avoid}
  h2{break-after:avoid}
  @page{size:A4;margin:16mm}
}
"""


def _tom(cifra: cifra_mod.Cifra, projeto=None) -> str:
    exibido = cifra.tom_exibido or "—"
    if cifra.transposicao and cifra.tom:
        return f"{exibido} (gravado em {cifra.tom})"
    if projeto is not None and not cifra.tom:
        return "— (não identificado)"
    return exibido


def _secoes_html(projeto, cifra: cifra_mod.Cifra) -> str:
    itens = []
    secoes = list(getattr(projeto, "secoes", None) or [])
    if secoes:
        for s in secoes:
            nome = str(s.get("nome") or s.get("rotulo") or "Seção")
            inicio = float(s.get("start", s.get("inicio", 0.0)) or 0.0)
            compasso = ""
            mapa = getattr(projeto, "mapa", None)
            if mapa is not None and getattr(mapa, "duracao", 0):
                compasso = str(mapa.compasso_de(inicio) + 1)
            itens.append(
                f"<span>{_esc(nome)}<i class=\"n\">c.{_esc(compasso or '?')}</i></span>"
            )
    elif cifra.secoes:
        for secao in cifra.secoes:
            numero = secao.linhas[0].numero if secao.linhas else "?"
            itens.append(f"<span>{_esc(secao.nome)}<i class=\"n\">c.{numero}</i></span>")
    return "".join(itens) or "<span class=\"vazio\">sem seções detectadas</span>"


def _bloco(secao: cifra_mod.SecaoCifra, letra_da_linha: dict[int, str]) -> str:
    linhas = []
    for ln in secao.linhas:
        # linha sem acorde E sem letra não vira linha da tabela: na ficha
        # impressa, uma parede de "N.C." só ocupa papel
        texto_letra = letra_da_linha.get(ln.numero, ln.letra)
        if not ln.acorde and not texto_letra:
            continue
        classe_acorde = "acorde incerto" if ln.incerto else "acorde"
        rotulo = ln.acorde if ln.acorde else "N.C."
        linhas.append(
            "<tr{cls}><td class=\"num\">{num}</td>"
            "<td class=\"{ca}\">{acorde}</td>"
            "<td class=\"letra\">{letra}</td></tr>".format(
                cls="" if texto_letra else " class=\"sem-letra\"",
                num=ln.numero,
                ca=classe_acorde,
                acorde=_esc(rotulo),
                letra=_esc(texto_letra) if texto_letra else "—",
            )
        )
    if not linhas:
        return ""
    inicio = secao.linhas[0].numero if secao.linhas else "?"
    fim = secao.linhas[-1].numero if secao.linhas else "?"
    return (
        "<section class=\"bloco\">"
        f"<h3>{_esc(secao.nome)}<small>compassos {inicio}–{fim}</small></h3>"
        "<table class=\"cifra\">" + "".join(linhas) + "</table></section>"
    )


def _letra_por_compasso(
    letra: letra_mod.Letra, cifra: cifra_mod.Cifra, projeto=None
) -> dict[int, str]:
    """{número do compasso: texto da linha que começa nele}.

    Sem mapa de tempo, a letra é encaixada pela janela `inicio`/`fim` da
    própria cifra — o mesmo dado que desenhou os compassos, então letra e
    cifra não podem discordar.
    """
    mapa = getattr(projeto, "mapa", None) if projeto is not None else None
    saida: dict[int, str] = {}
    if letra.vazia:
        return saida
    linhas = cifra.linhas
    if not linhas:
        return saida
    for item in letra.linhas:
        if not item.texto:
            continue
        if mapa is not None and getattr(mapa, "duracao", 0) and item.tempo > 0:
            numero = mapa.compasso_de(item.tempo) + 1
        else:
            numero = min(
                linhas,
                key=lambda ln: abs(ln.inicio - item.tempo),
            ).numero
        anterior = saida.get(numero)
        saida[numero] = (anterior + " " + item.texto).strip() if anterior else item.texto
    return saida


def gerar(projeto, cifra: cifra_mod.Cifra | None = None, letra: letra_mod.Letra | None = None) -> str:
    """HTML completo da ficha (autocontido, imprimível)."""
    cifra = cifra or projeto.cifra_obj()
    letra = letra if letra is not None else projeto.letra_obj()
    mapa = getattr(projeto, "mapa", None)

    titulo = projeto.titulo or Path(str(projeto.pasta)).name or "Sem título"
    meta = [
        f"<span>Tom <b>{_esc(_tom(cifra, projeto))}</b></span>",
        f"<span>BPM <b>{_esc(f'{cifra.bpm:.0f}' if cifra.bpm else '—')}</b></span>",
        f"<span>Compasso <b>{_esc(f'{cifra.numerador}/{cifra.denominador}')}</b></span>",
    ]
    if mapa is not None and getattr(mapa, "duracao", 0):
        meta.append(f"<span>Duração <b>{_esc(_mmss(mapa.duracao))}</b></span>")
        meta.append(f"<span>{_esc(mapa.total_compassos())} compassos</span>")
    if not getattr(mapa, "preciso", True) if mapa is not None else False:
        meta.append("<span>régua <b>extrapolada do BPM</b></span>")
    if letra and not letra.vazia:
        meta.append(
            f"<span>Letra <b>{_esc(_metodo_legivel(letra))}</b></span>"
        )
    if projeto.artista:
        meta.insert(0, f"<span>Artista <b>{_esc(projeto.artista)}</b></span>")

    letra_compasso = _letra_por_compasso(letra, cifra, projeto) if letra else {}
    blocos = "".join(_bloco(secao, letra_compasso) for secao in cifra.secoes)
    if not blocos:
        blocos = "<p class=\"vazio\">Nenhum acorde na cifra. Corrija no editor e gere a ficha de novo.</p>"

    avisos = list(cifra.avisos) + list(getattr(letra, "avisos", []) if letra else [])
    for aviso in getattr(projeto, "avisos", [])[:6]:
        if aviso not in avisos:
            avisos.append(str(aviso))
    bloco_avisos = ""
    if avisos:
        itens = "".join(f"<li>{_esc(a)}</li>" for a in avisos)
        bloco_avisos = (
            "<div class=\"avisos\"><b>O que foi estimado</b><ul>" + itens + "</ul></div>"
        )

    gerado = time.strftime("%d/%m/%Y %H:%M")
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(titulo)} — cifra</title>
<style>{CSS}</style></head>
<body><div class="folha">
<header>
  <h1>{_esc(titulo)}</h1>
  {f'<div class="artista">{_esc(projeto.artista)}</div>' if projeto.artista else ''}
  <div class="meta">{''.join(meta)}</div>
</header>
<h2>Forma</h2>
<div class="secoes">{_secoes_html(projeto, cifra)}</div>
<h2>Cifra</h2>
{blocos}
{bloco_avisos}
<footer>
  <span>MRQ Audio Studio · gerado em {gerado}</span>
  <span>? = acorde com baixa confiança · N.C. = sem acorde</span>
</footer>
</div></body></html>
"""


def _metodo_legivel(letra: letra_mod.Letra) -> str:
    return {
        "motor": "transcrita pelo motor",
        "importada": "importada com tempo",
        "energia": "alinhada por energia (estimada)",
    }.get(letra.metodo, "sem tempo definido")


def _mmss(segundos: float) -> str:
    total = int(round(max(0.0, float(segundos or 0))))
    return f"{total // 60}:{total % 60:02d}"


def escrever(projeto, destino: Path | None = None) -> Path:
    """Grava a ficha em `-apoio` e devolve o caminho."""
    destino = Path(destino) if destino else Path(projeto.apoio) / "ficha.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(gerar(projeto), encoding="utf-8")
    return destino
