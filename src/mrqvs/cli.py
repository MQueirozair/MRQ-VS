"""Interface de linha de comando (`mrq-vs`).

Exemplos que cobrem o uso real:

    mrq-vs "https://youtu.be/XXXX"                 # WAV, todos os stems
    mrq-vs link --format mp3 --stems vocals,drums,bass,other
    mrq-vs link --model htdemucs_6s --format mp4 --normalize
    mrq-vs arquivo.m4a --bpm 96 --out C:\\Musica
    mrq-vs projeto lista minhatrilha/              # faixas do projeto multitrack
    mrq-vs projeto mix minhatrilha/ --destino mix.wav
    mrq-vs projeto exportar minhatrilha/            # cifra, MIDI, letra e ficha
    mrq-vs projeto transpor minhatrilha/ --semitons -2
    mrq-vs projeto letra minhatrilha/ letra.txt     # alinha a letra ao áudio
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


def cmd_projeto(argv: list[str]) -> int:
    """`mrq-vs projeto` — edita e exporta o multitrack sem abrir a interface.

    Por que existe: quem usa terminal quer exportar a cifra em lote, gerar o
    MIDI para a DAW ou renderizar o mix com as edições já salvas. Todas as
    ações aqui chamam o MESMO módulo que a tela usa (`projeto_vs`), então não
    há um segundo caminho que possa divergir.
    """
    import json as _json

    from . import letra as letra_mod
    from . import projeto_vs as pv

    parser = argparse.ArgumentParser(
        prog="mrq-vs projeto",
        description="Projeto multitrack: listar faixas, mixar, exportar cifra/MIDI e letra.",
    )
    parser.add_argument(
        "acao",
        nargs="?",
        default="lista",
        choices=["lista", "mix", "stems", "exportar", "transpor", "corrigir", "letra", "marcar"],
    )
    parser.add_argument("pasta", nargs="?", help="pasta do projeto (a de áudio ou a -apoio)")
    parser.add_argument("--destino", default="", help="arquivo/pasta de saída (mix e stems)")
    parser.add_argument("--semitons", type=int, default=0, help="transposição da cifra (só acordes)")
    parser.add_argument("--compasso", default="", help="corrige a fórmula: 4/4, 6/8, 3/4...")
    parser.add_argument("--tempo", type=float, default=None, help="tempo (s) para o marcador")
    parser.add_argument("--nome", default="", help="nome do marcador")
    parser.add_argument("--letra", default="", help="arquivo .lrc/.srt/.txt com a letra (ação letra)")
    parser.add_argument("--json", action="store_true", help="imprime o resultado em JSON")
    args = parser.parse_args(argv)

    if not args.pasta:
        print("erro: informe a pasta do projeto", file=sys.stderr)
        return 2

    pasta = Path(args.pasta).expanduser()
    if not pasta.is_dir():
        print(f"erro: pasta não encontrada: {pasta}", file=sys.stderr)
        return 2

    def abrir() -> "pv.ProjetoVS":
        # aceita tanto a pasta de áudio quanto a `-apoio`: o usuário não
        # deveria precisar saber qual das duas tem o arquivo de projeto
        candidatos = [pasta]
        if (pasta.parent / f"{pasta.name}-apoio").is_dir():
            candidatos.insert(0, pasta.parent / f"{pasta.name}-apoio")
        for candidata in candidatos:
            if (candidata / pv.ARQUIVO_PROJETO).is_file():
                return pv.ProjetoVS.carregar(candidata)
        raise pv.ProjetoInvalido(
            f"não há {pv.ARQUIVO_PROJETO} em {pasta} nem em {pasta.name}-apoio. "
            "Separe a música primeiro (mrq-vs <fonte>) ou abra-a uma vez na interface."
        )

    try:
        projeto = abrir()
    except pv.ProjetoInvalido as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1

    if args.acao == "lista":
        print(f"{projeto.titulo or projeto.pasta.name} — {projeto.artista or 'artista desconhecido'}")
        print(
            f"  {projeto.mapa.bpm:.0f} BPM · {projeto.mapa.numerador}/{projeto.mapa.denominador}"
            f" · {projeto.mapa.total_compassos()} compassos · "
            f"{projeto.mapa.total_compassos() and 'grade ' + ('detectada' if projeto.mapa.preciso else 'extrapolada')}"
        )
        for faixa in projeto.faixas_ordenadas:
            estado = "mudo" if faixa.mudo else ("solo" if faixa.solo else "    ")
            existe = "ok " if projeto.caminho_da_faixa(faixa) else "AUSENTE"
            print(
                f"  {faixa.ordem:>2} {estado} {existe} {faixa.nome:<14} "
                f"vol {faixa.volume * 100:3.0f}%  pan {faixa.pan:+.1f}  {faixa.arquivo}"
            )
        if projeto.marcadores:
            print("  marcadores: " + ", ".join(f"{m.nome}@{m.tempo:.1f}s" for m in projeto.marcadores))
        avisos = [a for a in projeto.avisos if a][:5]
        if avisos:
            print("  avisos:")
            for aviso in avisos:
                print(f"    ! {aviso}")
        return 0

    if args.acao == "mix":
        destino = Path(args.destino) if args.destino else None
        try:
            resultado = projeto.renderizar(destino=destino)
        except (pv.ProjetoInvalido, OSError) as exc:
            print(f"erro: {exc}", file=sys.stderr)
            return 1
        print(
            f"mix: {resultado['arquivo']} ({resultado['duracao']}s, "
            f"{len(resultado['faixas'])} faixas, pico {resultado['pico_saida']})"
        )
        if resultado["ausentes"]:
            print("aviso: faixas sem arquivo: " + ", ".join(resultado["ausentes"]), file=sys.stderr)
        return 0

    if args.acao == "stems":
        pasta_saida = Path(args.destino) if args.destino else None
        try:
            resultado = projeto.renderizar_stems(pasta=pasta_saida)
        except (pv.ProjetoInvalido, OSError) as exc:
            print(f"erro: {exc}", file=sys.stderr)
            return 1
        for chave, caminho in resultado["arquivos"].items():
            print(f"  {chave}: {caminho}")
        return 0

    if args.acao == "exportar":
        try:
            arquivos = projeto.exportar_apoio()
        except OSError as exc:
            print(f"erro: {exc}", file=sys.stderr)
            return 1
        projeto.salvar()
        for chave, caminho in sorted(arquivos.items()):
            print(f"  {chave}: {caminho}")
        return 0

    if args.acao == "transpor":
        if not args.semitons:
            print("erro: informe --semitons (ex.: -2 ou +3)", file=sys.stderr)
            return 2
        # `% 12`: transpor -2 é o mesmo que +10 no papel. O áudio NÃO muda
        # aqui — é só a cifra (o aviso da tela e a ficha dizem isso).
        projeto.cifra = projeto.cifra_obj().transposta(args.semitons % 12).as_dict()
        projeto.salvar()
        cifra = projeto.cifra_obj()
        print(
            f"cifra transposta {args.semitons:+d} semitons — tom: {cifra.tom_exibido or '?'}"
            "  (o áudio não foi alterado; use o editor para ouvir transposto)"
        )
        print(cifra.resumo)
        return 0

    if args.acao == "corrigir":
        if not args.compasso:
            print("erro: informe --compasso 6/8, por exemplo", file=sys.stderr)
            return 2
        try:
            num, den = (int(p) for p in args.compasso.replace("/", " ").split())
        except ValueError:
            print("erro: use o formato N/D (4/4, 3/4, 6/8, 7/8)", file=sys.stderr)
            return 2
        projeto.mapa = projeto.mapa.com_formula(num, den)
        projeto.salvar()
        print(f"fórmula corrigida para {num}/{den} ({projeto.mapa.total_compassos()} compassos)")
        return 0

    if args.acao == "marcar":
        if args.tempo is None:
            print("erro: informe --tempo em segundos", file=sys.stderr)
            return 2
        marcador = projeto.marcar(args.tempo, args.nome or "")
        projeto.salvar()
        print(f"marcador: {marcador.nome} @ {marcador.tempo:.2f}s (compasso {marcador.compasso})")
        return 0

    # letra
    if not args.letra:
        print("erro: informe o arquivo de letra (.lrc, .srt ou .txt)", file=sys.stderr)
        return 2
    origem = Path(args.letra).expanduser()
    try:
        if origem.is_file():
            letra = letra_mod.ler_arquivo(origem)
        else:
            print(f"erro: arquivo de letra não encontrado: {origem}", file=sys.stderr)
            return 2
    except letra_mod.LetraInvalida as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    audio = next(
        (projeto.caminho_da_faixa(f) for f in projeto.faixas if f.id in ("vocals", "mix") and projeto.caminho_da_faixa(f)),
        None,
    )
    if audio is not None:
        import soundfile as sf

        dados, taxa = sf.read(str(audio), dtype="float32", always_2d=True)
        letra = letra_mod.alinhar(
            letra, dados, taxa, duracao=projeto.mapa.duracao, mapa=projeto.mapa
        )
    letra.titulo = letra.titulo or projeto.titulo
    letra.artista = letra.artista or projeto.artista
    projeto.letra = letra.as_dict()
    projeto.salvar()
    letra_mod.salvar(letra, projeto.apoio)
    for chave, caminho in letra.escrever(projeto.apoio, base="letra").items():
        print(f"  letra_{chave}: {caminho}")
    for aviso in letra.avisos:
        print(f"  ! {aviso}")
    _ = _json
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Subcomandos "de verdade" (não são fontes de mídia).
    if argv and argv[0] in (
        "doctor", "stems", "models", "serve", "app", "ia", "ai", "atalho", "projeto",
    ):
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
        if command == "projeto":
            return cmd_projeto(rest)
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
