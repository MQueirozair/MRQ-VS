"""Interface de linha de comando (`mrq-vs`).

Exemplos que cobrem o uso real:

    mrq-vs "https://youtu.be/XXXX"                 # WAV, todos os stems
    mrq-vs link --format mp3 --stems vocals,drums,bass,other
    mrq-vs link --model htdemucs_6s --format mp4 --normalize
    mrq-vs arquivo.m4a --bpm 96 --out C:\\Musica
    mrq-vs doctor                                 # o que está instalado
    mrq-vs stems                                  # catálogo de stems
    mrq-vs serve                                  # interface no navegador
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, export, project, separator
from .stems import MODEL_STEMS, STEM_ORDER, STEMS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mrq-vs",
        description="MRQ VS — separa um vídeo de música em stems, detecta BPM e organiza a pasta.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("source", nargs="?", help="URL do YouTube (ou de outro site) ou arquivo de áudio local")
    parser.add_argument("--version", action="version", version=f"MRQ VS {__version__}")

    group = parser.add_argument_group("stems")
    group.add_argument(
        "--stems",
        default="auto",
        help=f"lista separada por vírgula, ou 'auto' (padrão), ou 'all'. Disponíveis: {', '.join(STEM_ORDER)}",
    )
    group.add_argument("--model", default="", help="modelo de separação (padrão depende do backend instalado)")
    group.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "demucs", "audio-separator", "openunmix", "spleeter", "dsp-fallback"],
    )
    group.add_argument(
        "--rapido",
        "--dois-stems",
        dest="dois_stems",
        action="store_true",
        help="modo rápido: separa apenas voz + instrumental",
    )
    group.add_argument(
        "--device", default="auto", choices=["auto", "cpu", "cuda"], help="dispositivo do torch"
    )
    group.add_argument("--list-models", action="store_true", help="mostra os modelos conhecidos e seus stems")

    group = parser.add_argument_group("saída")
    group.add_argument("--format", dest="fmt", default="wav", type=str.lower, choices=list(export.FORMATS))
    group.add_argument("--bits", type=int, default=24, choices=[16, 24, 32], help="profundidade do WAV")
    group.add_argument("--bitrate", default="", help="ex.: 320k (mp3) / 256k (mp4)")
    group.add_argument("--normalize", action="store_true", help="normaliza cada arquivo para -1 dBFS")
    group.add_argument("--out", default="out", help="pasta onde o projeto será criado (padrão: ./out)")
    group.add_argument("--title", default="", help="sobrescreve o título usado no nome da pasta")
    group.add_argument("--artist", default="", help="sobrescreve o artista (tags e nome da pasta)")
    group.add_argument("--max-name", type=int, default=90, help="tamanho máximo do nome da pasta")

    group = parser.add_argument_group("análise")
    group.add_argument("--bpm", type=float, default=None, help="força o BPM (quando a detecção erra a oitava)")
    group.add_argument("--no-click", action="store_true", help="não gerar clique.wav")
    group.add_argument(
        "--subdivisao", type=int, default=1, choices=[1, 2, 3, 4],
        help="subdivisões do clique por tempo (1 = só os tempos; 2 = colcheias)",
    )
    group.add_argument(
        "--no-guia", action="store_true",
        help="não gerar guia.wav (contagem + anúncio das seções)",
    )
    group.add_argument(
        "--contagem", type=int, default=4, choices=[1, 2, 3, 4, 5, 6, 7],
        help="quantos tempos contar antes de cada seção (padrão: 4)",
    )
    group.add_argument(
        "--no-acordes", action="store_true",
        help="não estimar acordes por compasso (mais rápido em arquivos longos)",
    )
    group.add_argument(
        "--no-lr", action="store_true",
        help="não gerar o ENSAIO_LR.wav (clique+guia à esquerda, banda à direita)",
    )

    group = parser.add_argument_group("utilidades")
    group.add_argument("--json", action="store_true", help="imprime o resultado como JSON")
    group.add_argument(
        "--dry-run", action="store_true",
        help="mostra o plano (metadados, pasta, stems) sem baixar/processar",
    )
    group.add_argument("--keep-work", action="store_true", help="mantém a pasta temporária de trabalho")
    group.add_argument("--serve", action="store_true", help="sobe a interface web (equivale ao comando 'serve')")
    group.add_argument("--port", type=int, default=8765, help="porta da interface web")
    return parser


def cmd_doctor() -> int:
    return separator.doctor()


def cmd_stems_human() -> int:
    print("Stems conhecidos\n")
    for stem in STEM_ORDER:
        info = STEMS[stem]
        kind = "derivado" if info.derived_from else "nativo"
        print(f"  {stem:<12} {info.label:<14} {kind:<9} {info.description}")
    return 0


def cmd_list_models() -> int:
    print("Modelos conhecidos\n")
    for model, stems in MODEL_STEMS.items():
        print(f"  {model:<20} {', '.join(stems)}")
    print("\nRecomendação: htdemucs_6s (6 stems, guitarra e piano) para trabalho;")
    print("htdemucs_ft para voz de melhor qualidade (≈4× mais lento);")
    print("htdemucs para o equilíbrio velocidade/qualidade.")
    return 0


def parse_stems(raw: str, model: str) -> list[str]:
    raw = (raw or "auto").strip().lower()
    if raw in ("auto", ""):
        return []
    wanted = [s.strip() for s in raw.split(",") if s.strip()]
    if "all" in wanted:
        return list(STEM_ORDER)
    return wanted


def plan_text(options: project.ProjectOptions) -> str:
    from . import media

    lines = [f"Fonte: {options.source}"]
    if options.source.startswith(("http://", "https://")):
        try:
            info = media.probe_url(options.source)
            lines.append(f"Vídeo: {info.title}")
            lines.append(f"Canal: {info.channel or '(desconhecido)'}")
            lines.append(f"Duração: {info.duration:.0f}s")
        except Exception as exc:  # noqa: BLE001 - dry-run nunca deve falhar
            lines.append(f"(não foi possível consultar metadados: {exc})")
    backend = separator.choose_backend(options.backend, tuple(options.stems), options.model)
    model = options.model or separator.DEFAULT_MODEL_FOR_BACKEND[backend]
    native, derived, missing = __import__("mrqvs.stems", fromlist=["resolve_stems"]).resolve_stems(
        options.stems, model
    )
    lines.append(f"Backend: {backend} (modelo {model})")
    lines.append(f"Stems nativos: {', '.join(native) or '-'}")
    lines.append(f"Stems derivados: {', '.join(derived) or '-'}")
    if missing:
        lines.append(f"Sem suporte: {', '.join(missing)}")
    ok, why = export.check_export_capabilities(options.fmt)
    lines.append(f"Exportação {options.fmt.upper()}: {'ok' if ok else 'BLOQUEADA'} — {why}")
    lines.append(f"Pasta de saída: {Path(options.out_root).resolve()}/<Titulo>-<BPM>BPM/")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Subcomandos "de verdade" (não são fontes de mídia).
    if argv and argv[0] in ("doctor", "stems", "models", "serve", "app", "ia", "ai", "atalho"):
        command, rest = argv[0], argv[1:]
        if command == "atalho":
            from .app import criar_atalho_desktop

            caminho = criar_atalho_desktop()
            print(f"Atalho criado em: {caminho}")
            return 0
        if command == "app":
            from .app import run as run_app

            parser = argparse.ArgumentParser(prog="mrq-vs app")
            parser.add_argument("--port", type=int, default=8765)
            parser.add_argument("--no-browser", action="store_true", help="nao abrir o navegador")
            ns = parser.parse_args(rest)
            return run_app(port=ns.port, open_browser=not ns.no_browser)
        if command in ("ia", "ai"):
            from . import ai as ai_mod

            parser = argparse.ArgumentParser(prog="mrq-vs ia")
            parser.add_argument("acao", nargs="?", default="status", choices=["status", "instalar", "remover"])
            parser.add_argument("--forcar", action="store_true")
            ns = parser.parse_args(rest)
            if ns.acao == "status":
                print("motor de IA (demucs):", "instalado" if ai_mod.esta_instalado() else "NAO instalado")
                print("pasta:", ai_mod.runtime.ai_dir())
                if not ai_mod.esta_instalado():
                    print("\n" + ai_mod.manual())
                return 0
            if ns.acao == "remover":
                ai_mod.remover()
                print("ambiente de IA removido.")
                return 0
            total = {"visto": 0.0}

            def prog(fracao: float, texto: str) -> None:
                pct = int(fracao * 100)
                if pct >= total["visto"]:
                    total["visto"] = pct
                    print(f"  [{pct:3d}%] {texto}", flush=True)

            try:
                ai_mod.instalar(progress=prog, forcar=ns.forcar)
            except ai_mod.IAError as exc:
                print(f"erro: {exc}", file=sys.stderr)
                return 1
            print("motor de IA instalado. O backend 'demucs' já está disponível.")
            return 0
        if command == "doctor":
            return separator.doctor()
        if command == "stems":
            return cmd_stems_human()
        if command == "models":
            return cmd_list_models()
        # serve
        parser = argparse.ArgumentParser(prog="mrq-vs serve")
        parser.add_argument("--port", type=int, default=8765)
        parser.add_argument("--host", default="0.0.0.0")
        ns = parser.parse_args(rest)
        from .web import serve

        return serve(host=ns.host, port=ns.port)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_models:
        return cmd_list_models()
    if args.serve:
        from .web import serve

        return serve(port=args.port, abrir=True)
    if not args.source:
        # Duplo clique no executavel cai aqui. Antes imprimia a ajuda do
        # argparse — para quem nao usa terminal isso parece "nao abriu nada".
        from .app import run as run_app

        return run_app(port=args.port)

    try:
        options = project.ProjectOptions(
            source=args.source,
            out_root=Path(args.out),
            stems=parse_stems(args.stems, args.model),
            fmt=args.fmt,
            model=args.model,
            backend=args.backend,
            device=args.device,
            bpm=args.bpm,
            title=args.title,
            artist=args.artist,
            max_name_len=args.max_name,
            normalize=args.normalize,
            bits=args.bits,
            bitrate=args.bitrate,
            click=not args.no_click,
            subdivisao=args.subdivisao,
            guia=not args.no_guia,
            contagem=args.contagem,
            acordes=not args.no_acordes,
            exportar_lr=not args.no_lr,
            dois_stems="vocals" if args.dois_stems else "",
            keep_work=args.keep_work,
        )
        options.validate()
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(plan_text(options))
        return 0

    def progress(message: str) -> None:
        if not args.json:
            print(f"  · {message}", file=sys.stderr)

    try:
        result = project.run(options, progress=progress)
    except Exception as exc:  # noqa: BLE001 - a mensagem já é acionável
        print(f"\nerro: {exc}", file=sys.stderr)
        if not args.json:
            print("\nDica: rode `mrq-vs doctor` para ver o que falta instalar.", file=sys.stderr)
        return 1

    if args.json:
        from .report import summary_text

        print(
            __import__("json").dumps(
                {
                    "pasta": str(result.folder),
                    "bpm": result.analysis.tempo.bpm,
                    "tonalidade": result.analysis.key.label(),
                    "backend": result.backend,
                    "model": result.model,
                    "arquivos": {k: str(v) for k, v in result.stems_written.items()},
                    "avisos": result.warnings,
                    "segundos": result.elapsed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        from .report import summary_text

        print("\n" + summary_text(result))
        print(f"Pasta: {result.folder}")
        if result.warnings:
            print("\nAvisos:")
            for warning in result.warnings:
                print(f"  ! {warning}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
