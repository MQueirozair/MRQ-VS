"""Relatórios do projeto: Markdown para humanos, JSON para máquinas, playlist.

O relatório é a peça que faz o programa ser **confiável**: ele diz o que foi
medido, com quanto de confiança, o que é stem nativo de IA e o que é
derivação aproximada, qual licença/limite se aplica ao modelo e o que fazer
quando o resultado não serve.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .stems import STEMS


def _fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes, secs = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _human_size(path: Path) -> str:
    size = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def write_reports(
    folder: Path,
    info,
    analysed,
    written: dict[str, Path],
    notes: dict,
    fmt: str,
    sample_rate: int,
) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    md = _write_markdown(folder, info, analysed, written, notes, fmt, sample_rate)
    js = _write_json(folder, info, analysed, written, notes, fmt, sample_rate)
    _write_playlist(folder, written)
    _write_cue(folder, analysed, written)
    return md, js


def _write_markdown(folder, info, analysed, written, notes, fmt, sample_rate) -> Path:
    tempo = analysed.tempo
    key = analysed.key
    lines: list[str] = []
    add = lines.append

    add(f"# {folder.name}")
    add("")
    if (folder / "capa.jpg").is_file():
        # a imagem aparece no topo do relatório: reconhecer o projeto de bate-pronto
        add("![capa do vídeo](capa.jpg)")
        add("")
    add(f"Gerado por **MRQ VS** em {time.strftime('%d/%m/%Y %H:%M')}.")
    add("")
    add("## Identificação")
    add("")
    add(f"- **Título usado:** {info.title}")
    if getattr(info, "original_title", "") and info.original_title != info.title:
        add(f"- **Título original do vídeo:** {info.original_title}")
    if info.channel:
        add(f"- **Canal/artista:** {info.channel}")
    if info.webpage_url:
        add(f"- **Fonte:** {info.webpage_url}")
    add(f"- **Duração:** {_fmt_time(analysed.duration)}")
    add("")
    add("## Análise musical")
    add("")
    add(f"- **BPM:** {tempo.bpm:.1f} — {tempo.grid_note()} (confiança {tempo.confidence:.2f})")
    if tempo.bpm > 0:
        add(f"  - Grade de batidas: {len(tempo.beat_times)} tempos, "
            f"primeiro em {tempo.beat_times[0]:.3f} s" if tempo.beat_times else "  - Grade não calculada")
    add(f"- **Tonalidade:** {key.label()} (confiança {key.confidence:.2f})"
        + (f" · Camelot **{key.camelot()}**" if key.camelot() != "?" else ""))
    add(f"- **Loudness médio:** {analysed.loudness_db:.1f} dBFS · **pico:** {analysed.peak_db:.1f} dBFS")
    compasso = notes.get("compasso") or 4
    conf_compasso = notes.get("compasso_confianca") or 0.0
    add(f"- **Compasso:** {compasso}/4 (estimado, confiança {conf_compasso:.2f})"
        + (" — _sem acento claro na gravação; confira antes de usar_" if conf_compasso < 0.3 else ""))
    if not notes.get("compasso_modelo"):
        # Sem o modelo, o compasso vem da heurística de acento. Vale dizer
        # como melhorar, porque errar o "um" estraga o clique a música toda.
        add("- **Compasso por modelo:** não — para downbeats detectados por"
            " rede neural (bem melhor em música sem bateria), instale"
            " `pip install beat-this` e processe de novo.")
    add("")

    # acordes por compasso: a banda lê daqui, e o projeto.cue não carrega
    # harmonia — por isso a tabela é o registro oficial dos acordes.
    acordes = notes.get("acordes") or []
    if acordes:
        add("### Acordes por compasso")
        add("")
        add("| # | Início | Compasso | Acorde | Confiança |")
        add("|---|--------|----------|--------|-----------|")
        for i, a in enumerate(acordes, 1):
            add(f"| {i} | {_fmt_time(a.get('inicio', 0.0))} | {a.get('compasso', 1)} | "
                f"**{a.get('acorde', '?')}** | {float(a.get('confianca', 0.0)):.2f} |")
        add("")
        add("_Acordes estimados por croma + nota do baixo. Em trechos com instrumentação "
            "densa ou afinação fora do padrão (440 Hz) a estimativa pode errar: use como "
            "ponto de partida, não como transcrição._")
        add("")
    if analysed.sections:
        add("### Estrutura detectada")
        add("")
        add("| # | Início | Fim | Seção | Loudness |")
        add("|---|--------|-----|-------|----------|")
        for i, s in enumerate(analysed.sections, 1):
            add(f"| {i} | {_fmt_time(s.start)} | {_fmt_time(s.end)} | {s.label} | "
                f"{s.loudness_db:.1f} dB |")
        add("")
        add("_Rótulos iguais (A, A, B...) indicam trechos com material semelhante; "
            "não são nomes de seção (verso/refrão) — o programa não transcreve letra._")
        add("")

    add("## Stems exportados")
    add("")
    add(f"Formato **{fmt.upper()}**, {sample_rate} Hz. "
        f"Backend: `{notes['backend']}`.")
    add("")
    add("| # | Stem | Tipo | Arquivo | Tamanho |")
    add("|---|------|------|---------|---------|")
    for i, (stem, path) in enumerate(sorted(written.items(), key=lambda kv: kv[1].name), 1):
        if stem == "mix":
            kind = "soma de conferência"
            label = "Mix completo"
        else:
            meta = STEMS.get(stem)
            label = meta.label if meta else stem
            if meta and meta.derived_from:
                kind = "aproximado (derivado)"
            elif notes["backend"].startswith("dsp-fallback"):
                kind = "aproximado (DSP, sem IA)"
            elif notes["backend"].startswith("spleeter"):
                kind = "modelo leve (Spleeter)"
            else:
                kind = "nativo do modelo"
        add(f"| {i} | {label} | {kind} | `{path.name}` | {_human_size(path)} |")
    add("")
    add("**Nativo** = saiu do modelo de separação. **Derivado** = calculado por "
        "processamento de sinal em cima de um stem nativo; serve para trabalhar, "
        "não é a mesma coisa que separação por IA.")
    add("")

    if notes.get("warnings"):
        add("## Avisos desta execução")
        add("")
        for w in notes["warnings"]:
            add(f"- {w}")
        add("")

    add("## Como usar esta pasta")
    add("")
    add("1. `stems/` — importe as faixas na DAW (Reaper, Ableton, FL, Logic). "
        "Todas começam no mesmo instante, então alinham sem esforço.")
    add("2. `projeto.m3u` — playlist; `projeto.cue` — marcadores das seções detectadas.")
    add("3. `clique.wav` — metrônomo na grade do BPM detectado, para gravar por cima.")
    add("4. `projeto.json` — mesmos dados em formato de máquina (útil para scripts).")
    add("")
    add("### Se o resultado não ficou bom")
    add("")
    add("- Voz “vazando” no instrumental: normal em material com muita reverb; "
        "experimente `--model htdemucs_ft` (mais lento, melhor em voz).")
    add("- Bateria e baixo misturados: confira se o BPM está na oitava certa "
        "(`--bpm 96`, por exemplo); o resto não muda.")
    add("- Guitarra/piano fracos: o modelo de 6 stems é o elo mais fraco do Demucs; "
        "considere rodar de novo com `--model htdemucs` e tratar guitarra como `other`.")
    add("")
    add("## Licença dos modelos (leia antes de publicar)")
    add("")
    add("- **Demucs** (Meta): código MIT, **pesos com uso voltado a pesquisa**. "
        "Para uso comercial do áudio separado, verifique os termos atuais do repositório.")
    add("- **Spleeter** (Deezer): MIT.")
    add("- **audio-separator / MDX**: cada modelo tem sua licença; os arquivos "
        "`.onnx` baixados trazem os termos no próprio repositório de origem.")
    add("- O áudio de entrada continua sendo obra de terceiros: separar não dá "
        "direito de redistribuir a gravação.")
    add("")
    path = folder / "relatorio.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_json(folder, info, analysed, written, notes, fmt, sample_rate) -> Path:
    payload = {
        "gerador": "MRQ VS",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "video": info.as_dict(),
        "pasta": folder.name,
        "audio": {
            "sample_rate": sample_rate,
            "duracao": analysed.duration,
            "canais": 2,
            "formato_exportado": fmt,
            "loudness_dbfs": analysed.loudness_db,
            "pico_dbfs": analysed.peak_db,
        },
        "analise": {
            "bpm": analysed.tempo.bpm,
            "bpm_confianca": analysed.tempo.confidence,
            "batidas": analysed.tempo.beat_times,
            "tonalidade": analysed.key.label(),
            "tonalidade_confianca": round(analysed.key.confidence, 3),
            "camelot": analysed.key.camelot(),
            "secoes": [
                {"inicio": s.start, "fim": s.end, "rotulo": s.label, "loudness_db": s.loudness_db}
                for s in analysed.sections
            ],
            # compasso e acordes: o que a "faixa de guia" do CueWee mostra
            # embaixo dos stems. Sem isso o projeto.json nao servia para montar
            # a guia nem para conferir a harmonia da musica.
            "compasso": notes.get("compasso", 4),
            "compasso_confianca": notes.get("compasso_confianca", 0.0),
            "acordes": notes.get("acordes", []),
            # Tudo que o Studio desenha: grade de batidas, compasso, acordes
            # com tempo de entrada e secoes nomeadas. Fica no projeto.json
            # para a tela abrir a musica sem reanalisar nada.
            "estudio": notes.get("studio") or {},
        },
        "separacao": {
            "backend": notes["backend"],
            "stems_nativos": notes["native_stems"],
            "stems_derivados": notes["derived_stems"],
            "pedidos_sem_suporte": notes["missing"],
        },
        "arquivos": {k: v.name for k, v in written.items()},
        "avisos": notes["warnings"],
    }
    path = folder / "projeto.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_playlist(folder: Path, written: dict[str, Path]) -> None:
    import os

    lines = ["#EXTM3U"]
    for stem, path in sorted(written.items(), key=lambda kv: kv[1].name):
        label = "Mix completo" if stem == "mix" else (STEMS.get(stem).label if stem in STEMS else stem)
        lines.append(f"#EXTINF:-1,{label}")
        try:
            rel = os.path.relpath(path, folder).replace("\\", "/")
        except ValueError:
            rel = str(path)
        lines.append(rel)
    (folder / "projeto.m3u").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_cue(folder: Path, analysed, written: dict[str, Path]) -> None:
    """CUE com as seções detectadas — abre no Reaper/Audacity como marcadores."""
    import os

    mix = next((p for k, p in written.items() if k == "mix"), None)
    if mix is None or not analysed.sections:
        return
    try:
        rel_mix = os.path.relpath(mix, folder).replace("\\", "/")
    except ValueError:
        rel_mix = str(mix)
    fmt_tag = "MP3" if mix.suffix.lower() == ".mp3" else "WAVE"
    lines = [f'FILE "{rel_mix}" {fmt_tag}', f'TITLE "{folder.name}"']
    for i, section in enumerate(analysed.sections, 1):
        minutes = int(section.start // 60)
        seconds = section.start - minutes * 60
        frames = int(round((seconds - int(seconds)) * 75)) % 75
        lines.append(f"  TRACK {i:02d} AUDIO")
        lines.append(f'    TITLE "Seção {section.label} ({i})"')
        lines.append(f"    INDEX 01 {minutes:02d}:{int(seconds):02d}:{frames:02d}")
    (folder / "projeto.cue").write_text("\n".join(lines) + "\n", encoding="utf-8")


def summary_text(result) -> str:
    """Resumo de uma linha para o terminal."""
    tempo = result.analysis.tempo
    return (
        f"{result.folder.name} · {tempo.bpm:.0f} BPM · "
        f"{result.analysis.key.label()} · {len(result.stems_written)} arquivos · "
        f"{result.backend} · {result.elapsed:.0f}s"
    )
