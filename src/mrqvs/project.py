"""Orquestração: de uma URL/arquivo até a pasta final pronta para uso.

Layout de saída (tudo dentro de `<saída>/<TituloAbreviado>-<BPM>BPM/`):

    <Titulo>-<BPM>BPM/
      stems/            01_vocals.wav, 02_instrumental.wav, ... 00_mix.wav
      audio_original.wav      o mix de referência (o mesmo que entrou)
      relatorio.md            relatório legível
      capa.jpg                capa do vídeo (quando a fonte é um link)
      projeto.json            tudo que foi medido (máquina-lendo)
      projeto.m3u             playlist na ordem dos stems
      projeto.cue             faixas marcadas nas seções detectadas
      clique.wav              metrônomo na grade de batidas (bônus)
      log/                    saída crua dos backends + comandos

A pasta é criada **depois** da análise (o nome depende do BPM) e o trabalho
pesado acontece numa pasta temporária, então uma execução interrompida não
deixa meia-pasta com nome errado.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import analysis as analysis_mod
from . import acordes as acordes_mod
from . import cover, derive, dsp, export, guia as guia_mod, media, naming, report, separator
from . import stems as stems_mod


@dataclass
class ProjectOptions:
    source: str
    out_root: Path = Path("out")
    #: quando informado, a música sai aqui dentro em vez de espalhar por `out/`.
    #: O nome final é `<raiz>/<Nome>-<BPM>/`, ao lado da `<Nome>-<BPM>-apoio/`.
    #: A biblioteca usa isto para não deixar rastro de cada execução em `out/`.
    out_dir: Path | None = None
    stems: list[str] = field(default_factory=list)
    fmt: str = "wav"
    model: str = ""
    backend: str = "auto"
    device: str = "auto"
    #: força um BPM (útil quando a detecção erra a oitava)
    bpm: float | None = None
    title: str = ""
    artist: str = ""
    max_name_len: int = 90
    normalize: bool = False
    bits: int = 24
    bitrate: str = ""
    click: bool = True
    #: "vocals" = modo rápido do Demucs (2 saídas: voz + instrumental).
    #: Vazio = separação completa. É o caminho que substitui o Spleeter no
    #: uso mais comum, com ~1/3 do tempo.
    dois_stems: str = ""
    #: faixa de GUIA (contagem + anúncio de seção), como no CueWee
    guia: bool = True
    #: fala os números e o nome da seção (pt-BR) em vez de só a melodia.
    #: Quando um arquivo de voz falta, aquela entrada volta para a melodia.
    guia_voz: bool = True
    #: quantos tempos de contagem antes de cada seção
    contagem: int = 4
    #: subdivisões do clique por tempo (1 = só os tempos; 2 = colcheias)
    subdivisao: int = 1
    #: acordes estimados por compasso (entra no relatório e no projeto.json)
    acordes: bool = True
    #: exporta também o par estéreo L/R (clique+guia à esquerda, banda à
    #: direita) — é o formato de palco do CueWee, e o mais prático no in-ear
    exportar_lr: bool = True
    keep_work: bool = False
    sample_rate: int = 44100

    def validate(self) -> None:
        if not self.source:
            raise ValueError("informe uma URL do YouTube ou o caminho de um arquivo de áudio")
        if self.fmt.lower().lstrip(".") not in export.FORMATS:
            raise ValueError(f"formato inválido: {self.fmt}")
        unknown = [s for s in self.stems if s not in stems_mod.STEMS]
        if unknown:
            raise ValueError(
                f"stem desconhecido: {', '.join(unknown)}\n"
                f"disponíveis: {', '.join(stems_mod.STEM_ORDER)}"
            )
        # Falha rápido: se o formato pedido não é possível neste ambiente
        # (MP3/MP4 sem ffmpeg), não adianta baixar e separar para descobrir
        # isso no final do processo.
        ok, why = export.check_export_capabilities(self.fmt.lower().lstrip("."))
        if not ok:
            raise ValueError(f"não é possível exportar em {self.fmt.upper()}: {why}")


@dataclass
class StudioData:
    """Tudo que o Studio precisa para desenhar a timeline sem tocar em áudio.

    Por que separado do resto: a tela nova (barra de compassos, cifra que
    acompanha o play, mapa de seções) desenha MUITO rápido — ela só precisa
    de números. Deixar isso num objeto próprio evita a tentação de reprocessar
    a música quando o usuário só quer redesenhar a régua.

    Os campos são exatamente os do CueWee Studio, que foram levantados da
    documentação pública e das capturas de tela:

    - `batidas`: grade de tempos (o play usa para saber onde está o compasso)
    - `compasso`: 4/4 ou 3/4, com confiança
    - `acordes`: um por compasso, com tempo de início (a cifra anda com o play)
    - `secoes`: nome (Verso/Refrão/Ponte...), início e fim
    """

    #: segundos de cada batida
    batidas: list[float] = field(default_factory=list)
    #: numerador da fórmula: 2, 3, 4, 6 ou 12
    compasso: int = 4
    #: denominador da fórmula: 4 (semínima) ou 8 (colcheia, em 6/8 e 12/8)
    denominador: int = 4
    compasso_confianca: float = 0.0
    #: {inicio, fim, compasso, acorde, confianca}
    acordes: list[dict] = field(default_factory=list)
    #: {start, end, rotulo, nome}
    secoes: list[dict] = field(default_factory=list)
    duracao: float = 0.0
    bpm: float = 0.0
    tonalidade: str = ""

    def as_dict(self) -> dict:
        return {
            "batidas": [round(b, 4) for b in self.batidas],
            "compasso": self.compasso,
            "denominador": self.denominador,
            "compasso_confianca": self.compasso_confianca,
            "acordes": self.acordes,
            "secoes": self.secoes,
            "duracao": round(self.duracao, 2),
            "bpm": round(self.bpm, 1),
            "tonalidade": self.tonalidade,
        }


@dataclass
class ProjectResult:
    folder: Path
    media: media.MediaInfo
    analysis: analysis_mod.Analysis
    stems_written: dict[str, Path]
    backend: str
    model: str
    warnings: list[str]
    elapsed: float
    report_md: Path | None = None
    report_json: Path | None = None
    #: `capa.jpg` na pasta do projeto (None quando a fonte não tem imagem)
    cover: Path | None = None
    #: compasso estimado (4 ou 3) e a confiança da estimativa
    compasso: int = 4
    compasso_confianca: float = 0.0
    #: acordes estimados, um por compasso: {inicio, fim, compasso, acorde, confianca}
    acordes: list[dict] = field(default_factory=list)
    #: `guia.wav` na pasta de apoio (None quando a guia não foi pedida)
    guia: Path | None = None
    #: dados da timeline do Studio (batidas, compasso, acordes, seções)
    studio: StudioData = field(default_factory=StudioData)
    #: `ENSAIO_LR.wav` na pasta de áudio (clique+guia | banda); None se off
    lr: Path | None = None


class PipelineError(RuntimeError):
    pass


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "www."))


def resolve_source(source: str, workdir: Path, progress=None) -> media.MediaInfo:
    """URL -> baixa; arquivo -> usa direto. Sempre com metadados."""
    if _is_url(source):
        info = media.probe_url(source)
        info = media.download_audio(source, workdir, info, progress=progress)
        return info

    path = Path(source).expanduser()
    if not path.is_file():
        raise PipelineError(f"arquivo não encontrado: {path}")
    return media.MediaInfo(
        title=path.stem,
        channel="",
        duration=0.0,
        webpage_url=str(path.resolve()),
        audio_path=path,
    )


def run(options: ProjectOptions, progress=None) -> ProjectResult:
    """Executa o pipeline completo. Levanta erro com mensagem acionável."""
    options.validate()
    started = time.time()
    out_root = Path(options.out_root).expanduser()
    # destino já decidido (biblioteca): a música sai direto na pasta do
    # usuário, sem passar por `out/`. O fallback de `_OUT_ROOT` do servidor
    # web deixa de valer, então a tela recebe caminhos absolutos.
    out_dir = Path(options.out_dir).expanduser() if options.out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_root = out_dir
    out_root.mkdir(parents=True, exist_ok=True)
    # Pasta de trabalho FORA da árvore de saída: com `--out` num pen drive ou
    # numa pasta sincronizada (OneDrive/Drive), o material intermediário não
    # deve aparecer como projeto. Antes era ao lado de out/ e o usuário via
    # pastas `mrqvs-xxxx` cheias de WAV no meio dos projetos.
    if options.keep_work:
        workdir = Path(tempfile.mkdtemp(prefix="mrqvs-", dir=str(out_root)))
    else:
        workdir = Path(tempfile.mkdtemp(prefix="mrqvs-"))
    warnings: list[str] = []
    log_dir = workdir / "log"
    log_dir.mkdir(exist_ok=True)

    def say(message: str) -> None:
        if progress:
            progress(message)

    try:
        # 1. mídia -------------------------------------------------------
        say(f"resolvendo fonte: {options.source}")
        info = resolve_source(options.source, workdir, progress=progress)
        if info.audio_path is None:
            raise PipelineError("nenhum áudio foi obtido da fonte")
        audio_path = info.audio_path
        # 2. decodifica para float32 44.1 kHz ----------------------------
        say("decodificando o áudio…")
        mix, sample_rate = media.load_audio(audio_path, options.sample_rate)
        if getattr(mix, "size", 0) == 0:
            raise PipelineError("o áudio decodificado está vazio")
        duration = mix.shape[0] / sample_rate
        info.duration = info.duration or round(duration, 2)

        # 3. análise -----------------------------------------------------
        say("analisando (BPM, tonalidade, seções)…")
        analysed = analysis_mod.analyse(mix, sample_rate)
        if options.bpm:
            analysed.tempo.bpm = float(options.bpm)
            analysed.tempo.confidence = 1.0
            analysed.tempo.beat_times = dsp.beat_grid(sample_rate, analysed.tempo.bpm, duration)
            warnings.append(f"BPM forçado pelo usuário: {analysed.tempo.bpm:.0f}")
        warnings.extend(analysed.notes)

        # 4. nome da pasta ----------------------------------------------
        title = options.title or info.title
        artist = options.artist
        info.original_title = info.title
        if options.title:
            info.title = options.title
        folder_name = naming.project_folder_name(
            title, analysed.tempo.bpm, max_len=options.max_name_len, channel=info.channel
        )
        folder = out_root / folder_name
        if folder.exists() and any(folder.iterdir()):
            suffix = 2
            while (out_root / f"{folder_name}-{suffix}").exists():
                suffix += 1
            folder = out_root / f"{folder_name}-{suffix}"
            warnings.append(f"já existia uma pasta com esse nome; usando {folder.name}")
        folder.mkdir(parents=True, exist_ok=True)

        # 5. separação ---------------------------------------------------
        # O plano de stems depende do backend que vai rodar de verdade
        # (não do modelo "ideal"), senão a gente promete guitarra num
        # ambiente em que o backend só entrega 4 stems.
        effective_stems = list(options.stems)
        if not effective_stems and options.dois_stems == "vocals":
            effective_stems = ["vocals", "instrumental"]
        backend = separator.choose_backend(
            options.backend, tuple(effective_stems), options.model
        )
        model = options.model or separator.DEFAULT_MODEL_FOR_BACKEND[backend]
        native_requested, derived_names, missing = stems_mod.resolve_stems(
            effective_stems, model
        )
        if missing:
            warnings.append(
                "stems não disponíveis no modelo escolhido e sem como derivar: "
                + ", ".join(missing)
            )
        say(f"separando stems ({', '.join(native_requested) or 'todos'})…")
        stem_dir = workdir / "stems"
        result = separator.separate(
            audio_path,
            stem_dir,
            backend=options.backend,
            model=model,
            stems=tuple(native_requested),
            device=options.device,
            log_path=log_dir / "separacao.log",
            progress=progress,
            dois_stems=options.dois_stems,
        )
        backend_note = f"{result.backend}/{result.model}"
        if result.backend == "dsp-fallback":
            warnings.append(
                "separação feita pelo backend DSP (HPSS + máscaras): é aproximada e "
                "não substitui um modelo de IA. Instale `demucs` para qualidade de verdade."
            )

        # 6. carrega nativos e gera derivados ---------------------------
        try:
            import soundfile as sf
        except ModuleNotFoundError:
            raise dsp.MissingDependency("soundfile", "carregar os stems separados") from None

        native_audio: dict[str, object] = {}
        for stem, path in result.stems.items():
            data, sr = sf.read(str(path), dtype="float32", always_2d=False)
            if sr != sample_rate:
                data = dsp.resample_linear(data, sr, sample_rate)
            native_audio[stem] = data

        if not native_audio:
            raise PipelineError("o backend não gerou nenhum stem utilizável")

        wanted_all = list(native_requested) + list(derived_names)
        derived_audio, derive_warnings = derive.derive_stems(
            native_audio, sample_rate, wanted_all, mix=mix
        )
        warnings.extend(derive_warnings)

        selected: dict[str, object] = {}
        for name in stems_mod.STEM_ORDER:
            if name in native_audio and (not effective_stems or name in effective_stems):
                selected[name] = native_audio[name]
            elif name in derived_audio and (not effective_stems or name in effective_stems):
                selected[name] = derived_audio[name]

        if not selected:
            raise PipelineError("nenhum stem foi selecionado para exportar")

        # 7. exportação --------------------------------------------------
        export_opts = export.ExportOptions(
            fmt=options.fmt,
            bits=options.bits,
            bitrate=options.bitrate,
            normalize=options.normalize,
            title=f"{artist + ' - ' if artist else ''}{title} [{naming.bpm_tag(analysed.tempo.bpm)}]",
            artist=artist or info.channel,
            bpm=analysed.tempo.bpm,
        )
        ok, why = export.check_export_capabilities(export_opts.fmt)
        if not ok:
            raise export.FFmpegMissing(f"não é possível exportar em {export_opts.fmt.upper()}: {why}")

        # Duas pastas, por pedido explícito do usuário:
        #
        #   <Nome>-<BPM>/                  só ÁUDIO, nada mais
        #       <Nome>-<BPM>_00_mix.mp3
        #       <Nome>-<BPM>_01_vocals.mp3
        #       ...
        #   <Nome>-<BPM>-apoio/            relatório, capa, clique, json, logs
        #
        # Por que separar: ao importar na DAW ou no celular, qualquer arquivo
        # que não seja áudio atrapalha (o player tenta abrir o .md, a DAW
        # lista o .json). Antes tudo ficava junto em `<pasta>/stems/` e o
        # relatório ao lado — dava dois níveis de pasta e material misturado.
        stem_out = folder
        written = export.export_session(
            selected, sample_rate, stem_out, folder_name, export_opts, progress=progress
        )
        apoio = folder.parent / f"{folder.name}-apoio"
        apoio.mkdir(parents=True, exist_ok=True)

        # 8. capa do vídeo ----------------------------------------------
        # Fica ao lado do áudio para o projeto ser reconhecível pelo olho.
        # Falha aqui nunca derruba o projeto: só entra como aviso.
        capa = None
        if info.thumbnail:
            say("baixando a capa do vídeo…")
            capa = cover.download(info.thumbnail, apoio / "capa.jpg")
            if capa is None:
                warnings.append("não foi possível baixar a capa do vídeo (a pasta segue sem imagem)")

        # 9. artefatos de apoio -----------------------------------------
        original = apoio / "audio_original.wav"
        _write_original(mix, sample_rate, original)

        # 9b. compasso, acordes e guia ------------------------------------
        # O CueWee entrega click + guia falada em toda música. Aqui o compasso
        # e os acordes eram o que faltava para a guia fazer sentido: a
        # contagem precisa saber quantos tempos tem o compasso, e o acorde é
        # o que a banda olha de relance.
        compasso = 4
        compasso_conf = 0.0
        #: True quando o compasso veio do beat_this (rede neural), não da
        #: heurística de acento — vai para o relatório, que sugere instalar
        compasso_por_modelo = False
        acordes: list[dict] = []
        guia_path: Path | None = None
        lr: Path | None = None
        if analysed.tempo.beat_times:
            say("estimando compasso e acordes…")
            # Primeiro tenta o modelo treinado (beat_this, MIT): ele devolve
            # downbeats de verdade, e é o único jeito confiável de acertar o
            # 1º tempo em música sem bateria. Sem ele instalado, cai na
            # heurística de acento — que funciona e diz a confiança.
            modelo = acordes_mod.compasso_e_grade_do_modelo(audio_path)
            if modelo:
                compasso, compasso_conf, _downbeats, grade_modelo = modelo
                # a grade do modelo é melhor que a regular: usa as batidas
                # reais dele quando elas cobrem a música. UMA passada do modelo
                # para fórmula e grade (antes eram duas, o dobro do tempo).
                analysed.tempo.beat_times = grade_modelo or analysed.tempo.beat_times
                compasso_conf = max(compasso_conf, 0.6)
                say(f"compasso pelo modelo: {compasso} (confiança {compasso_conf:.2f})")
                compasso_por_modelo = True
            else:
                compasso, compasso_conf = acordes_mod.compasso(
                    mix, sample_rate, analysed.tempo.bpm, analysed.tempo.beat_times
                )
            if options.acordes:
                acordes = acordes_mod.por_compasso(
                    mix, sample_rate, analysed.tempo.beat_times, compasso,
                    tonalidade=analysed.key.label(),
                )
            # o clique sai DEPOIS do compasso: acentuar a cada 4 fixo erra
            # em 3/4, e o compasso so e conhecido agora.
            if options.click:
                _write_click(
                    apoio / "clique.wav",
                    sample_rate,
                    analysed.tempo.beat_times,
                    duration,
                    accent_bpm=analysed.tempo.bpm,
                    compasso=compasso,
                    subdivisao=options.subdivisao,
                )
            # 9b-1. ESTRUTURA: dar nome às seções (Intro/Verso/Refrão/...).
            # A análise separa os trechos por semelhança e chama de A/B/C; a
            # banda chama de verso e refrão, e é esse nome que a guia fala.
            # Fica antes da guia de propósito: a guia anuncia o nome musical.
            try:
                from . import estrutura as estrutura_mod

                nomeadas = estrutura_mod.nomear_secoes(
                    analysed.sections,
                    energia_de=lambda sec: getattr(sec, "loudness_db", 0.0),
                )
            except Exception as exc:  # noqa: BLE001 - nomear é heurística
                nomeadas = []
                warnings.append(f"não foi possível nomear as seções: {exc}")

            if options.guia:
                try:
                    entradas = guia_mod.compor(
                        analised_para_guia(analysed.sections, nomeadas),
                        analysed.tempo.beat_times,
                        contagem=options.contagem,
                    )
                    if entradas:
                        guia_path = apoio / "guia.wav"
                        resultado_guia = guia_mod.escrever_audio(
                            guia_path, sample_rate, entradas, duration,
                            com_voz=bool(getattr(options, "guia_voz", True)),
                        )
                        warnings.append(guia_mod.resumo(entradas, resultado_guia))
                except Exception as exc:  # noqa: BLE001 - guia é bônus
                    warnings.append(f"não foi possível gerar a guia: {exc}")

            # L/R: um arquivo estéreo com click+guia na esquerda e a banda na
            # direita. É o "renderizar L/R" do CueWee e resolve o palco: o
            # in-ear recebe só a esquerda, a mesa só a direita.
            if options.exportar_lr and options.click:
                try:
                    lr_path = folder / f"{folder.name}_ENSAIO_LR.wav"
                    clique_tmp = apoio / "clique.wav"
                    guia_tmp = guia_path
                    ensaio = _somar_audio(clique_tmp, guia_tmp, sample_rate=sample_rate)
                    guia_mod.escrever_lr(
                        lr_path, sample_rate, mix, ensaio, duration
                    )
                    lr = lr_path
                    written["ensaio_lr"] = lr_path  # entra na playlist e nos stems
                except Exception as exc:  # noqa: BLE001 - L/R é bônus
                    warnings.append(f"não foi possível exportar o L/R: {exc}")

        # 9c. dados do Studio --------------------------------------------
        # Nome de seção legível (Verso/Refrão/Ponte/Intro/Solo) em vez do
        # rótulo A/B da análise espectral. O rótulo A/B diz "estes trechos se
        # parecem", que é verdade e é útil, mas não é o que a banda chama a
        # seção. `guia.nome_da_secao` faz a tradução e admite o que não sabe.
        if nomeadas:
            secoes_studio = [n.as_dict() for n in nomeadas]
        else:
            secoes_studio = [
                {
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "rotulo": s.label,
                    "nome": guia_mod.nome_da_secao(s.label),
                }
                for s in analysed.sections
            ]
        studio = StudioData(
            batidas=list(analysed.tempo.beat_times),
            compasso=compasso,
            # 7/8 e 6/8 usam colcheia como unidade; 3/4 e 4/4 usam semínima.
            # Sem este campo o editor lia 7 batidas por compasso como 7/4 e a
            # régua ficava com o dobro do tamanho do áudio.
            denominador=8 if compasso in (6, 7, 9, 12) else 4,
            compasso_confianca=compasso_conf,
            acordes=acordes,
            secoes=secoes_studio,
            duracao=duration,
            bpm=analysed.tempo.bpm,
            tonalidade=analysed.key.label(),
        )

        notes = {
            "backend": backend_note,
            "compasso": compasso,
            "compasso_confianca": compasso_conf,
            "compasso_modelo": compasso_por_modelo,
            "acordes": acordes,
            # timeline do Studio: batidas, seções nomeadas e acordes com tempo
            "studio": studio.as_dict(),
            "native_stems": sorted(native_audio),
            "derived_stems": sorted(derived_audio),
            "warnings": warnings,
            "requested": list(options.stems),
            "missing": missing,
        }
        md_path, json_path = report.write_reports(
            folder=apoio,
            info=info,
            analysed=analysed,
            written=written,
            notes=notes,
            fmt=export_opts.fmt,
            sample_rate=sample_rate,
        )
        # Logs crus: úteis quando o usuário pede ajuda no fórum.
        (apoio / "log").mkdir(exist_ok=True)
        for log in log_dir.glob("*.log"):
            shutil.copy2(log, apoio / "log" / log.name)
        (apoio / "log" / "comando.txt").write_text(
            " ".join(["mrq-vs", "--stems", ",".join(options.stems or ["auto"]),
                      "--format", options.fmt, options.source]),
            encoding="utf-8",
        )
        return ProjectResult(
            folder=folder,
            media=info,
            analysis=analysed,
            stems_written=written,
            backend=result.backend,
            model=result.model,
            warnings=warnings,
            elapsed=round(time.time() - started, 1),
            report_md=md_path,
            report_json=json_path,
            cover=capa,
            compasso=compasso,
            compasso_confianca=compasso_conf,
            acordes=acordes,
            guia=guia_path,
            lr=lr,
            studio=studio,
        )
    finally:
        if options.keep_work:
            print(f"[mrq-vs] pasta de trabalho preservada em {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


def _write_original(mix, sample_rate: int, path: Path) -> None:
    try:
        import soundfile as sf
    except ModuleNotFoundError:
        raise dsp.MissingDependency("soundfile", "gravar o áudio original") from None
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, mix, sample_rate, subtype="PCM_16")


def _somar_audio(*fontes, sample_rate: int = 44100):
    """Soma arquivos de áudio (mono) com padding, para o lado L do L/R.

    Existe porque clique e guia são arquivos separados: o lado esquerdo do
    L/R é a soma dos dois, e somar no navegador seria pior (teria de baixar
    tudo de novo). Se algum não existir, soma o que houver.
    """
    import numpy as np

    try:
        import soundfile as sf
    except ModuleNotFoundError:
        raise dsp.MissingDependency("soundfile", "exportar em L/R") from None

    total = 0
    pedacos = []
    for fonte in fontes:
        if not fonte:
            continue
        caminho = Path(fonte)
        if not caminho.is_file():
            continue
        dados, taxa = sf.read(caminho, always_2d=True)
        if taxa != sample_rate:
            dados = dsp.resample_linear(dados, taxa, sample_rate)
        mono = dados.mean(axis=1)
        pedacos.append(mono)
        total = max(total, mono.size)
    if not pedacos:
        return None
    saida = np.zeros(total, dtype=np.float32)
    for p in pedacos:
        saida[: p.size] += p
    return saida


def analised_para_guia(secoes, nomeadas) -> list:
    """Seções com o nome musical, no formato que a guia fala.

    `guia.compor` lê ``start``/``end``/``label`` e traduz o rótulo pelo dicionário
    `NOMES_SECAO`. Aqui os rótulos são substituídos pelo NOME que a estrutura
    concluiu ("Refrão"), de forma que a contagem e o anúncio falem a palavra
    certa sem a guia precisar conhecer regra de estrutura musical.
    """
    if not nomeadas:
        return list(secoes or [])

    class _SecaoFalada:
        __slots__ = ("start", "end", "label")

        def __init__(self, inicio, fim, rotulo):
            self.start = float(inicio)
            self.end = float(fim)
            self.label = str(rotulo)

    return [_SecaoFalada(n.inicio, n.fim, n.nome) for n in nomeadas]


def _write_click(
    path: Path,
    sample_rate: int,
    beats: list[float],
    duration: float,
    accent_bpm: float = 0,
    compasso: int = 4,
    subdivisao: int = 1,
) -> None:
    """Metrônomo na grade detectada.

    Antes o acento era fixo a cada 4 tempos — dava clique fora do tempo em
    3/4 e em música que começa em anacruse. Agora quem manda é o compasso
    estimado (`compasso`), e `subdivisao` coloca colcheias/tercinas entre os
    tempos como o CueWee faz.

    Três alturas, para o ouvido separar sem pensar:
      - 1º tempo do compasso: 1760 Hz, mais forte (o "um")
      - demais tempos:        1320 Hz
      - subdivisões:          990 Hz, bem mais fracas (não competem)
    """
    import numpy as np

    try:
        import soundfile as sf
    except ModuleNotFoundError:
        raise dsp.MissingDependency("soundfile", "gerar o clique") from None
    compasso = max(1, int(compasso or 4))
    subdivisao = max(1, min(4, int(subdivisao or 1)))
    total = int(duration * sample_rate) + sample_rate // 10
    out = np.zeros(total, dtype=np.float32)
    click_len = int(0.03 * sample_rate)
    t = np.arange(click_len) / sample_rate
    env = np.exp(-t * 90.0).astype(np.float32)

    def por(golpe: float, freq: float, ganho: float) -> None:
        start = int(golpe * sample_rate)
        if start < 0 or start >= total:
            return
        tone = (np.sin(2 * np.pi * freq * t) * env * ganho).astype(np.float32)
        end = min(total, start + click_len)
        out[start:end] += tone[: end - start]

    for i, beat in enumerate(beats):
        primeiro = i % compasso == 0
        por(beat, 1760.0 if primeiro else 1320.0, 0.7 if primeiro else 0.45)
        if subdivisao > 1:
            # passo até o próximo tempo; o último tempo usa o do anterior
            if i + 1 < len(beats):
                passo = beats[i + 1] - beat
            elif i > 0:
                passo = beat - beats[i - 1]
            else:
                passo = 0.0
            for k in range(1, subdivisao):
                por(beat + passo * k / subdivisao, 990.0, 0.18)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, out, sample_rate, subtype="PCM_16")