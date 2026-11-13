"""Interface web local — `mrq-vs serve`.

Por que existe: o usuário final do MRQ VS é músico, não necessariamente
confortável com terminal. A interface é uma página só (HTML/CSS/JS embutidos,
sem build, sem npm) e um servidor `http.server` com três rotas de API:

    POST /api/analyze   {url}          -> metadados + plano (sem processar)
    POST /api/run       {url, opções}  -> processa e devolve o resultado
    GET  /api/status    -> o que está instalado (backends, ffmpeg, yt-dlp)
    GET  /api/file?p=.. -> baixa um arquivo gerado (restrito à pasta de saída)
    GET  /              -> a página

O servidor roda no loopback por padrão e serve só a pasta de saída: é uma
ferramenta local, não um serviço para expor na internet. Escutar em 0.0.0.0
serve apenas para o preview do sandbox — daí o aviso no console.

Processamento é **síncrono e um job por vez**: separar música é caro, e
duas requisições simultâneas só fariam as duas ficarem lentas. A fila é um
`threading.Lock`.
"""

from __future__ import annotations

import json
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__, export, project, runtime, separator
from ..stems import MODEL_STEMS, STEM_ORDER, STEMS, recomendacao

_JOB_LOCK = threading.Lock()
_IA_LOCK = threading.Lock()
_OUT_ROOT = Path("out").resolve()
#: onde as musicas separadas ficam salvas (padrao da biblioteca)
_MUSICAS = runtime.home() / "musicas"


def _status_payload() -> dict:
    from .. import ai as ai_mod

    return {
        "versao": __version__,
        "ia": {
            # durante a instalação não vale pagar o teste do demucs (leva
            # segundos e travaria o /api/status que a tela chama toda hora)
            "instalado": False if ai_mod.ESTADO["rodando"] else ai_mod.esta_instalado(),
            "pasta": str(ai_mod.runtime.ai_dir()),
            "manual": ai_mod.manual(),
            "andamento": ai_mod.estado(),
        },
        "backends": [b.as_dict() for b in separator.detect_backends()],
        "formatos": list(export.FORMATS),
        "formatos_ok": {f: export.check_export_capabilities(f)[0] for f in export.FORMATS},
        "stems": [
            {
                "id": s,
                "label": STEMS[s].label,
                "descricao": STEMS[s].description,
                "derivado": bool(STEMS[s].derived_from),
                "cor": STEMS[s].color,
            }
            for s in STEM_ORDER
        ],
        "modelos": {m: list(s) for m, s in MODEL_STEMS.items()},
        # a tela mostra a nota de cada modelo; antes só aparecia o nome
        "modelos_nota": {
            m: recomendacao(m) for m in MODEL_STEMS
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = f"MRQVS/{__version__}"

    # -- utilidades ------------------------------------------------------
    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[web] {self.address_string()} {fmt % args}")

    # -- rotas -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            corpo = _page()
            # Carimbo de versão em toda navegação: o navegador guarda esta
            # página e, sem "no-store", continuava mostrando o HTML antigo
            # depois de atualizar o programa (o usuário reclamou de não ver
            # as opções novas com a 0.1.19 já instalada). O ?v= também
            # derruba o cache quando a versão muda.
            etiqueta = f'<meta name="mrqvs-versao" content="{__version__}">'
            if etiqueta not in corpo:
                corpo = corpo.replace("</head>", f"{etiqueta}\n</head>", 1)
            body = corpo.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/status":
            self._json(_status_payload())
        elif parsed.path == "/api/file":
            self._serve_file(parse_qs(parsed.query).get("p", [""])[0])
        elif parsed.path == "/api/cover":
            # capa: aceita caminho absoluto (musica na pasta do usuario) e
            # continua aceitando relativo a out/ (linha de comando e testes)
            self._capa(parse_qs(parsed.query).get("p", [""])[0])
        elif parsed.path == "/api/buscar":
            self._buscar(parse_qs(parsed.query).get("q", [""])[0])
        elif parsed.path == "/api/ia/estado":
            self._estado_ia()
        elif parsed.path == "/api/leve":
            self._json(self._leve_status())
        elif parsed.path == "/api/biblioteca":
            self._json({"versoes": self._biblioteca()})
        elif parsed.path in ("/favicon.ico", "/icone-192.png", "/icone-512.png"):
            self._serve_icone(parsed.path)
        elif parsed.path == "/api/edicoes":
            self._edicoes_ler(parse_qs(parsed.query).get("apoio", [""])[0])
        elif parsed.path == "/api/bib/capa":
            self._serve_capa_bib(parse_qs(parsed.query).get("p", [""])[0])
        else:
            self._json({"erro": "rota não encontrada"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        rota = urlparse(self.path).path
        if rota == "/api/analyze":
            self._analyze(self._read_json())
        elif rota == "/api/run":
            self._run(self._read_json())
        elif rota == "/api/ia/instalar":
            self._instalar_ia()
        elif rota == "/api/ia/cancelar":
            self._cancelar_ia()
        elif rota == "/api/ia/reparar":
            self._reparar_ia()
        elif rota == "/api/ia/qualidade":
            self._instalar_qualidade()
        elif rota == "/api/ia/leve":
            self._instalar_leve()
        elif rota == "/api/upload/iniciar":
            self._upload_iniciar()
        elif rota == "/api/upload/fatia":
            self._upload_fatia()
        elif rota == "/api/upload/preparar":
            self._upload_preparar()
        elif rota == "/api/biblioteca/abrir":
            self._bib_abrir(self._read_json())
        elif rota == "/api/biblioteca/remover":
            self._bib_remover(self._read_json())
        elif rota == "/api/abrir-pasta":
            self._abrir_pasta(self._read_json())
        elif rota == "/api/edicoes":
            self._edicoes_salvar(self._read_json())
        elif rota == "/api/exportar-mix":
            self._exportar_mix(self._read_json())
        else:
            self._json({"erro": "rota não encontrada"}, 404)

    # -- handlers --------------------------------------------------------
    def _analyze(self, payload: dict) -> None:
        url = (payload.get("url") or "").strip()
        if not url:
            self._json({"erro": "informe a URL do vídeo"}, 400)
            return
        from .. import media

        try:
            info = media.probe_url(url)
        except Exception as exc:  # noqa: BLE001
            self._json({"erro": str(exc)}, 502)
            return
        requested = [s for s in (payload.get("stems") or []) if s in STEMS]
        backend = separator.choose_backend(
            payload.get("backend") or "auto",
            tuple(requested),
            payload.get("model") or "",
        )
        model = payload.get("model") or separator.DEFAULT_MODEL_FOR_BACKEND[backend]
        from ..stems import resolve_stems

        native, derived, missing = resolve_stems(requested, model)
        self._json(
            {
                "video": info.as_dict(),
                # a interface mostra a capa assim que o link é conferido
                "capa_url": info.thumbnail,
                "backend": backend,
                "model": model,
                "stems_nativos": native,
                "stems_derivados": derived,
                "sem_suporte": missing,
            }
        )

    def _run(self, payload: dict) -> None:
        url = (payload.get("url") or "").strip()
        envio_id = (payload.get("envio") or "").strip()
        if not url and not envio_id:
            self._json({"erro": "informe a URL do vídeo, a música ou envie um arquivo"}, 400)
            return

        # Arquivo enviado pelo navegador: o caminho no disco é a fonte.
        if envio_id and not url:
            from .. import upload as upload_mod

            try:
                pronto = upload_mod.preparar(envio_id)
            except upload_mod.UploadError as exc:
                self._json({"erro": str(exc)}, 400)
                return
            url = str(pronto["audio"])
            # o nome do arquivo vira o título da pasta de saída
            payload = {**payload, "title": payload.get("title") or pronto["titulo"]}
        # Onde a musica fica salva. Antes ia para `out/` (relativo a pasta de
        # onde o programa foi aberto): ninguem sabia onde estava e o resultado
        # sumia da tela. Agora vai para a pasta de dados do usuario, ao lado do
        # indice da biblioteca, e a tela reabre de la com um clique.
        escolhido = (payload.get("dir") or payload.get("out") or "").strip()
        if escolhido:
            destino = Path(escolhido).expanduser()
            # pasta escolhida pelo usuario: precisa ser servivel pela tela
            _registrar_raiz(destino)
        else:
            destino = _music_home() / "musicas"
        opts = project.ProjectOptions(
            source=url,
            out_root=destino,
            out_dir=destino,
            stems=[s for s in (payload.get("stems") or []) if s in STEMS],
            fmt=(payload.get("format") or "wav").lower(),
            model=payload.get("model") or "",
            backend=payload.get("backend") or "auto",
            bpm=float(payload["bpm"]) if payload.get("bpm") else None,
            normalize=bool(payload.get("normalize")),
            bitrate=payload.get("bitrate") or "",
            bits=int(payload.get("bits") or 24),
            click=payload.get("click", True) is not False,
            subdivisao=int(payload.get("subdivisao") or 1),
            guia=payload.get("guia", True) is not False,
            contagem=int(payload.get("contagem") or 4),
            acordes=payload.get("acordes", True) is not False,
            exportar_lr=payload.get("lr", True) is not False,
            title=payload.get("title") or "",
            artist=payload.get("artist") or "",
            # modo rápido: só voz + instrumental (1/3 do tempo)
            dois_stems="vocals" if payload.get("dois_stems") else "",
        )
        if not _JOB_LOCK.acquire(blocking=False):
            self._json({"erro": "já existe um trabalho em andamento; aguarde terminar"}, 429)
            return
        try:
            result = project.run(opts)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"erro": str(exc)}, 500)
            return
        finally:
            _JOB_LOCK.release()

        files = {}
        for stem, path in result.stems_written.items():
            files[stem] = {
                "nome": path.name,
                # com destino fora de `out/` o caminho vira absoluto: a rota
                # /api/file decide pela raiz que guardou
                "url": f"/api/file?p={_relativo(path, destino)}",
                # o player precisa saber se é áudio: a pasta de saída pode
                # conter outros formatos, e `<audio>` falha em silêncio neles
                "audio": path.suffix.lower() in (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".aac"),
            }
        # guarda na biblioteca para o usuario reabrir depois com um clique.
        # Falhar aqui nao pode derrubar a tela: a musica ja esta no disco.
        try:
            from .. import biblioteca

            biblioteca.registrar(
                result.folder,
                titulo=(payload.get("title") or result.folder.name),
                bpm=result.analysis.tempo.bpm,
                tom=result.analysis.key.label(),
                motor=f"{result.backend}/{result.model}",
                origem=payload.get("url") or "",
            )
        except Exception:  # noqa: BLE001
            traceback.print_exc()

        self._json(
            {
                "pasta": str(result.folder),
                # a pasta -apoio guarda as edições do editor (edicoes.json).
                # Sem ela no payload, salvar cifra/seções não teria onde.
                "apoio": str(result.folder.parent / f"{result.folder.name}-apoio"),
                # se o usuario escolheu destino, o 1o clique registrou; se nao,
                # registra agora — senao "abrir pasta" caia em out/ e parecia
                # que os arquivos tinham sumido
                "raiz": str(destino),
                "nome_pasta": result.folder.name,
                "bpm": result.analysis.tempo.bpm,
                "bpm_confianca": result.analysis.tempo.confidence,
                "tonalidade": result.analysis.key.label(),
                "camelot": result.analysis.key.camelot(),
                "secoes": [
                    {"inicio": s.start, "fim": s.end, "rotulo": s.label}
                    for s in result.analysis.sections
                ],
                # compasso, acordes e guia: o que a faixa de guia do CueWee
                # mostra e a interface desenha (acorde em cima do compasso).
                "compasso": result.compasso,
                "denominador": result.studio.denominador,
                "compasso_confianca": result.compasso_confianca,
                "acordes": result.acordes,
                # timeline do Studio (regua de compassos, cifra que anda com
                # o play, mapa de secoes). Ver project.StudioData.
                "estudio": result.studio.as_dict(),
                "lr": (
                    f"/api/file?p={_relativo(result.lr, destino)}"
                    if result.lr
                    else ""
                ),
                "guia": (
                    f"/api/file?p={_relativo(result.guia, destino)}"
                    if result.guia
                    else ""
                ),
                "clique": (
                    f"/api/file?p={_relativo(result.folder.parent / (result.folder.name + '-apoio') / 'clique.wav', destino)}"
                    if result.folder.parent.joinpath(result.folder.name + "-apoio", "clique.wav").is_file()
                    else ""
                ),
                "backend": result.backend,
                "model": result.model,
                "arquivos": files,
                "avisos": result.warnings,
                "segundos": result.elapsed,
                "relatorio": f"/api/file?p={_relativo(result.report_md, destino)}",
                "capa": (
                    f"/api/cover?p={_relativo(result.cover, destino)}"
                    if result.cover
                    else ""
                ),
            }
        )

    def _leve_status(self) -> dict:
        """Os dois caminhos que fazem o papel do Spleeter, com disponibilidade."""
        from .. import leve, separator

        disponiveis = {s.name: s.available for s in separator.detect_backends()}
        return {
            "caminhos": [
                {
                    "chave": c.chave,
                    "nome": c.nome,
                    "motor": c.motor,
                    "precisa": c.precisa,
                    "tempo": c.tempo,
                    "qualidade": c.qualidade,
                    "quando": c.quando,
                    "disponivel": disponiveis.get(
                        "openunmix" if c.chave == "leve" else "demucs", False
                    ),
                }
                for c in leve.caminhos(
                    demucs_ok=disponiveis.get("demucs", False),
                    openunmix_ok=disponiveis.get("openunmix", False),
                )
            ],
            "comparacao": [
                {"motor": m, "instalacao": i, "sdr": s, "python313": p}
                for m, i, s, p in leve.COMPARACAO
            ],
            "resumo": leve.resumo(),
        }

    def _instalar_leve(self) -> None:
        """Instala o open-unmix em segundo plano (uma janela, sem terminal)."""
        import threading

        from .. import ai as ai_mod

        if not _IA_LOCK.acquire(blocking=False):
            self._json({"erro": "já existe uma instalação em andamento"}, 429)
            return

        def trabalhar() -> None:
            try:
                ai_mod.instalar_leve()
            except Exception:  # noqa: BLE001 - o motivo vai para ESTADO["erro"]
                pass
            finally:
                _IA_LOCK.release()

        threading.Thread(target=trabalhar, name="ia-leve", daemon=True).start()
        self._json({"ok": True, "iniciado": True, "estado": ai_mod.estado()})

    def _instalar_ia(self) -> None:
        """Inicia a instalação do motor de IA **em segundo plano**.

        Antes esta rota segurava a requisição por 10–20 minutos: o navegador
        estourava o tempo, a barra ficava animando "de mentira" e não havia
        como saber se estava andando. Agora ela responde na hora e quem
        acompanha é `/api/ia/estado`. Continua valendo "uma por vez".
        """
        import threading

        from .. import ai as ai_mod

        if not _IA_LOCK.acquire(blocking=False):
            self._json({"erro": "a instalação de IA já está em andamento"}, 429)
            return

        def trabalhar() -> None:
            try:
                ai_mod.instalar()
            except Exception:  # noqa: BLE001 - o motivo vai para ESTADO["erro"]
                pass
            finally:
                _IA_LOCK.release()

        threading.Thread(target=trabalhar, name="ia-instalar", daemon=True).start()
        self._json({"ok": True, "iniciado": True, "estado": ai_mod.estado()})

    def _reparar_ia(self) -> None:
        """Completa o que falta no ambiente de IA sem reinstalar torch.

        O caso que criou esta rota: o Demucs 4.1.0 não declara numpy como
        dependência, então a instalação "dava certo" e a separação de áudio
        morria com `ModuleNotFoundError: No module named 'numpy'`. Baixar
        1 GB de novo por causa de 18 MB seria cruel; aqui só instala o que
        falta.
        """
        import threading

        from .. import ai as ai_mod

        if not _IA_LOCK.acquire(blocking=False):
            self._json({"erro": "já existe uma instalação de IA em andamento"}, 429)
            return

        def trabalhar() -> None:
            try:
                ai_mod.reparar()
            except Exception:  # noqa: BLE001 - o motivo vai para ESTADO["erro"]
                pass
            finally:
                _IA_LOCK.release()

        threading.Thread(target=trabalhar, name="ia-reparar", daemon=True).start()
        self._json({"ok": True, "iniciado": True, "estado": ai_mod.estado()})

    def _instalar_qualidade(self) -> None:
        """Instala o motor de qualidade (BS-RoFormer) em segundo plano.

        É opcional e reaproveita o torch do motor principal — por isso não
        custa outro 1 GB. Roda em thread pelo mesmo motivo da instalação
        principal: baixar centenas de MB não pode segurar uma requisição.
        """
        import threading

        from .. import ai as ai_mod

        if not _IA_LOCK.acquire(blocking=False):
            self._json({"erro": "já existe uma instalação de IA em andamento"}, 429)
            return

        def trabalhar() -> None:
            try:
                ai_mod.instalar_qualidade()
            except Exception:  # noqa: BLE001 - o motivo vai para ESTADO["erro"]
                pass
            finally:
                _IA_LOCK.release()

        threading.Thread(target=trabalhar, name="ia-qualidade", daemon=True).start()
        self._json({"ok": True, "iniciado": True, "estado": ai_mod.estado()})

    def _buscar(self, termo: str) -> None:
        """Busca por NOME da música, como o StemRoller faz.

        Antes só aceitava link colado: quem não tinha a URL à mão precisava
        abrir o YouTube, procurar, copiar e voltar. Agora a própria caixa de
        link aceita o nome.
        """
        from .. import media

        termo = (termo or "").strip()
        if not termo:
            self._json({"erro": "digite o nome da música"}, 400)
            return
        try:
            resultados = media.buscar(termo)
        except media.MediaError as exc:
            self._json({"erro": str(exc)}, 502)
            return
        self._json({"resultados": resultados})

    # -- upload de arquivo local -----------------------------------------
    # Referência: a tela de upload do CueWee Studio (studio.cuewee.app).
    # Em vez de um POST gigante (que não mostra progresso e estoura em
    # conexão lenta), o navegador manda fatias de 2 MB e recebe o total
    # gravado em cada uma.
    def _upload_iniciar(self) -> None:
        from .. import upload as upload_mod

        dados = self._read_json()
        try:
            tamanho = int(dados.get("tamanho") or 0)
        except (TypeError, ValueError):
            tamanho = 0
        try:
            envio = upload_mod.novo_envio(dados.get("nome") or "", tamanho=tamanho)
        except upload_mod.UploadError as exc:
            self._json({"erro": str(exc)}, 400)
            return
        upload_mod.gravar_registro(
            envio["pasta"],
            {"nome": envio["nome"], "tipo": envio["tipo"],
             "titulo": dados.get("titulo") or Path(envio["nome"]).stem},
        )
        self._json(
            {
                "ok": True,
                "id": envio["id"],
                "tipo": envio["tipo"],
                "limite_mb": upload_mod.LIMITE_BYTES // (1024 * 1024),
                "limite_min": upload_mod.LIMITE_SEGUNDOS // 60,
            }
        )

    def _upload_fatia(self) -> None:
        """Recebe 2 MB por vez. Cabeçalhos evitam JSON com base64 (+33%)."""
        from .. import upload as upload_mod

        ident = self.headers.get("X-Envio-Id") or ""
        try:
            inicio = int(self.headers.get("X-Inicio") or 0)
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json({"erro": "cabeçalhos inválidos"}, 400)
            return
        if not ident or tamanho <= 0 or tamanho > 8 * 1024 * 1024:
            self._json({"erro": "fatia inválida"}, 400)
            return
        dados = self.rfile.read(tamanho)
        try:
            total = upload_mod.receber_fatia(ident, inicio, dados)
        except upload_mod.UploadError as exc:
            self._json({"erro": str(exc)}, 400)
            return
        except OSError as exc:
            self._json({"erro": f"não consegui gravar: {exc}"}, 500)
            return
        self._json({"ok": True, "total": total})

    def _upload_preparar(self) -> None:
        """Fecha o envio: valida tamanho/duração e, se for vídeo, extrai o áudio."""
        from .. import upload as upload_mod

        dados = self._read_json()
        try:
            pronto = upload_mod.preparar(dados.get("id") or "")
        except upload_mod.UploadError as exc:
            self._json({"erro": str(exc)}, 400)
            return
        self._json(
            {
                "ok": True,
                "tipo": pronto["tipo"],
                "titulo": pronto["titulo"],
                "duracao": pronto["duracao"],
                "audio": str(pronto["audio"]),
                "convertido": pronto["tipo"] == "video",
            }
        )

    def _estado_ia(self) -> None:
        from .. import ai as ai_mod

        self._json(ai_mod.estado())

    def _cancelar_ia(self) -> None:
        from .. import ai as ai_mod

        ai_mod.cancelar()
        self._json({"ok": True, "estado": ai_mod.estado()})

    # -- biblioteca / icone ----------------------------------------------
    def _biblioteca(self) -> list:
        from .. import biblioteca

        return biblioteca.listar()

    def _bib_abrir(self, payload: dict) -> None:
        """Abre uma musica ja separada, sem separar de novo."""
        from .. import biblioteca

        dados = biblioteca.abrir(str(payload.get("id") or ""))
        if dados is None:
            self._json(
                {"erro": "não achei essa música no disco — a pasta pode ter sido "
                         "movida ou apagada"}, 404
            )
            return
        self._json(dados)

    def _bib_remover(self, payload: dict) -> None:
        from .. import biblioteca

        ok = biblioteca.remover(str(payload.get("id") or ""))
        self._json({"ok": ok})

    def _edicoes_ler(self, apoio: str) -> None:
        """Edições de cifra/seções/compasso salvas pelo usuário.

        Devolve `acordes: null` quando nunca houve edição — e isso é
        importante: `null` = "use o que foi detectado", `[]` = "o usuário
        apagou todos os acordes". Tratar os dois como iguais apagaria o
        trabalho dele ao reabrir.
        """
        from .. import mixdown

        if not apoio:
            self._json({"erro": "informe a pasta -apoio"}, 400)
            return
        alvo = Path(apoio)
        if not _pode_servir(alvo):
            self._json({"erro": "pasta fora das raízes autorizadas"}, 403)
            return
        self._json(mixdown.ler_edicoes(alvo))

    def _edicoes_salvar(self, payload: dict) -> None:
        from .. import mixdown

        apoio = str(payload.get("apoio") or "")
        if not apoio or not Path(apoio).is_dir():
            self._json({"erro": "pasta -apoio não encontrada"}, 404)
            return
        alvo = Path(apoio)
        if not _pode_servir(alvo):
            self._json({"erro": "pasta fora das raízes autorizadas"}, 403)
            return
        try:
            dados = mixdown.salvar_edicoes(alvo, payload)
        except OSError as exc:
            self._json({"erro": f"não foi possível salvar: {exc}"}, 500)
            return
        self._json({"ok": True, "edicoes": dados})

    def _exportar_mix(self, payload: dict) -> None:
        """Soma as faixas como o editor está ouvindo (volume, mute, solo, pan).

        O resultado vai para a pasta de ÁUDIO da música, com nome próprio
        (`_MIX.wav`), nunca por cima de um stem: o usuário pode exportar dez
        versões e comparar.
        """
        from .. import mixdown

        pasta_str = str(payload.get("pasta") or "")
        faixas = payload.get("faixas") or []
        if not pasta_str or not Path(pasta_str).is_dir():
            self._json({"erro": "pasta da música não encontrada"}, 404)
            return
        pasta = Path(pasta_str)
        if not _pode_servir(pasta):
            self._json({"erro": "pasta fora das raízes autorizadas"}, 403)
            return
        if not isinstance(faixas, list) or not faixas:
            self._json({"erro": "nenhuma faixa para exportar"}, 400)
            return
        resolvidas: list[dict] = []
        for f in faixas:
            if not isinstance(f, dict):
                self._json({"erro": "faixa fora das pastas autorizadas"}, 403)
                return
            arq = _resolver_arquivo_servido(str(f.get("caminho") or ""), pasta_dica=pasta)
            if arq is None:
                self._json({"erro": "faixa fora das pastas autorizadas"}, 403)
                return
            copia = dict(f)
            copia["caminho"] = str(arq)
            resolvidas.append(copia)
        destino = pasta / f"{pasta.name}_MIX.wav"
        try:
            resultado = mixdown.mixar(resolvidas, destino)
        except ValueError as exc:
            self._json({"erro": str(exc)}, 400)
            return
        except Exception as exc:  # noqa: BLE001
            self._json({"erro": f"falha ao mixar: {exc}"}, 500)
            return
        resultado["url"] = f"/api/file?p={_relativo(destino, _OUT_ROOT)}"
        resultado["nome"] = destino.name
        self._json(resultado)

    def _abrir_pasta(self, payload: dict) -> None:
        """Abre a pasta no Explorer/Finder. Sem navegador: e o sistema."""
        alvo = Path(payload.get("pasta") or _OUT_ROOT)
        if not alvo.is_dir():
            self._json({"erro": "pasta não encontrada"}, 404)
            return
        try:
            from ..app import abrir_no_sistema

            abrir_no_sistema(alvo)
        except Exception as exc:  # noqa: BLE001
            self._json({"erro": f"não foi possível abrir a pasta: {exc}"}, 500)
            return
        self._json({"ok": True, "pasta": str(alvo)})

    def _serve_icone(self, rota: str) -> None:
        """Serve o icone do proprio pacote (funciona tambem dentro do .pyz)."""
        nome = rota.lstrip("/")
        dados = None
        try:
            import pkgutil

            dados = pkgutil.get_data(__name__, nome)
        except (OSError, ValueError):
            dados = None
        if not dados:
            caminho = Path(__file__).with_name(nome)
            if caminho.is_file():
                dados = caminho.read_bytes()
        if not dados:
            self._json({"erro": "ícone ausente do pacote"}, 404)
            return
        tipo = "image/x-icon" if nome.endswith(".ico") else "image/png"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(dados)

    def _serve_capa_bib(self, caminho: str) -> None:
        """Capa de uma musica da biblioteca.

        `/api/cover` so aceita caminhos dentro de `out/`; a biblioteca guarda
        musicas na pasta de dados do usuario, entao precisa de uma rota que
        aceite caminho absoluto.
        """
        alvo = Path(caminho)
        if alvo.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            self._json({"erro": "não é imagem"}, 403)
            return
        self._serve_imagem_absoluta(alvo)

    def _capa(self, caminho: str) -> None:
        """Rota /api/cover: relativo a `out/` (ou raízes conhecidas) ou absoluto autorizado."""
        alvo = Path(caminho)
        if not alvo.is_absolute():
            for raiz in (_OUT_ROOT, *_raizes_arquivos()):
                if (raiz / alvo).is_file():
                    self._serve_file(caminho, inline=True)
                    return
        self._serve_imagem_absoluta(alvo)

    def _serve_imagem_absoluta(self, alvo: Path) -> None:
        """Serve uma imagem de dentro de uma pasta conhecida/autorizada."""
        alvo = Path(alvo)
        if ".." in alvo.parts:
            self._json({"erro": "capa fora das pastas conhecidas"}, 403)
            return
        tipos = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        sufixo = alvo.suffix.lower()
        if sufixo not in tipos:
            self._json({"erro": "não é imagem"}, 403)
            return
        resolvido = alvo.resolve()
        if not _pode_servir(resolvido):
            self._json({"erro": "capa fora das pastas conhecidas"}, 403)
            return
        if not resolvido.is_file():
            self._json({"erro": "capa não encontrada"}, 404)
            return
        dados = resolvido.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", tipos[sufixo])
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "max-age=600")
        self.end_headers()
        self.wfile.write(dados)

    def _serve_file(self, relative: str, inline: bool = False) -> None:
        # um arquivo pode ser pedido pelo caminho relativo a `out/` (linha de
        # comando) ou por qualquer raiz conhecida (biblioteca). Resolver "a
        # primeira que existir" evita escolher a raiz errada quando o mesmo
        # nome de musica existe nos dois lugares.
        alvo = Path(relative)
        if ".." in alvo.parts:
            self._json({"erro": "caminho fora das pastas de saída"}, 403)
            return
        if alvo.is_absolute():
            candidatos = [alvo]
        else:
            candidatos = [_OUT_ROOT / alvo] + [r / alvo for r in _raizes_arquivos()]
        target = None
        for candidato in candidatos:
            if candidato.is_file():
                target = candidato.resolve()
                break
        if target is None:
            target = candidatos[0].resolve()
        # duas raizes: `out/` (linha de comando) e a pasta de musicas do
        # usuario (biblioteca). Fora delas, 403 — a rota nao pode virar leitor
        # de qualquer arquivo do computador.
        if not _pode_servir(target):
            self._json({"erro": "caminho fora das pastas de saída"}, 403)
            return
        if not target.is_file():
            self._json({"erro": "arquivo não encontrado"}, 404)
            return
        suffix = target.suffix.lower()
        types = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".mp4": "video/mp4",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".opus": "audio/opus",
            ".aiff": "audio/aiff",
            ".aif": "audio/aiff",
            ".md": "text/markdown; charset=utf-8",
            ".json": "application/json",
            ".m3u": "audio/x-mpegurl",
            ".cue": "text/plain; charset=utf-8",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        # Range: o player da tela nova procura posição (arrastar a régua,
        # clicar num compasso) e o <audio> só faz isso se o servidor aceitar
        # bytes parciais. Sem estes cabeçalhos o navegador baixa o arquivo
        # inteiro antes de tocar e o seek fica travado — sintoma: "clico no
        # compasso 20 e ele volta para o início".
        tamanho = target.stat().st_size
        tipo = types.get(suffix, "application/octet-stream")
        faixa = self._faixa_pedida(tamanho)
        if faixa is None and self.headers.get("Range"):
            # Range inválido (fora do arquivo): 416 é a resposta correta e o
            # player do navegador entende e para de insistir.
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{tamanho}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        inicio, fim = faixa if faixa else (0, max(0, tamanho - 1))
        trecho = 0 if tamanho == 0 else (fim - inicio + 1)
        parcial = faixa is not None
        self.send_response(
            HTTPStatus.PARTIAL_CONTENT if parcial else HTTPStatus.OK
        )
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(trecho))
        self.send_header("Accept-Ranges", "bytes")
        if parcial:
            self.send_header("Content-Range", f"bytes {inicio}-{fim}/{tamanho}")
        if inline and suffix in (".jpg", ".jpeg", ".png", ".webp"):
            self.send_header("Cache-Control", "max-age=3600")
        if suffix in (".mp3", ".mp4", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"):
            self.send_header("Content-Disposition", f'inline; filename="{target.name}"')
        self.end_headers()
        with target.open("rb") as fh:
            fh.seek(inicio)
            restante = trecho
            while restante > 0:
                bloco = fh.read(min(64 * 1024, restante))
                if not bloco:
                    break
                self.wfile.write(bloco)
                restante -= len(bloco)

    def _faixa_pedida(self, tamanho: int) -> tuple[int, int] | None:
        """Interpreta o cabeçalho `Range` (só `bytes=início-fim`).

        Devolve `None` quando não há `Range` válido ou quando o intervalo pedido
        está fora de `[0, tamanho)` (para o chamador responder 416).
        """
        cabecalho = (self.headers.get("Range") or "").strip()
        if not cabecalho.startswith("bytes=") or tamanho <= 0:
            return None
        pedido = cabecalho[6:].split(",")[0].strip()
        if "-" not in pedido:
            return None
        inicio_txt, fim_txt = pedido.split("-", 1)
        try:
            if inicio_txt:
                inicio = int(inicio_txt)
                fim = int(fim_txt) if fim_txt else tamanho - 1
                if inicio < 0 or inicio >= tamanho or fim < inicio:
                    return None
                fim = min(fim, tamanho - 1)
            else:
                # sufixo: "bytes=-5000" = os últimos 5000 bytes
                sufixo = int(fim_txt)
                if sufixo <= 0:
                    return None
                inicio = max(0, tamanho - sufixo)
                fim = tamanho - 1
        except ValueError:
            return None
        return inicio, fim


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    anunciar: bool = True,
    abrir: bool = False,
) -> int:
    """Sobe o servidor da interface.

    `anunciar=False` fica quieto (o modo janela já explicou tudo antes) e
    `abrir=True` abre o navegador — usado pelo `--serve` da linha de comando,
    que sem isso deixava o usuário procurar o endereço sozinho.
    """
    _OUT_ROOT.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    if anunciar:
        print(f"MRQ VS {__version__} — interface em http://{shown}:{port}")
        print(f"pasta de saída: {_OUT_ROOT}")
        print("Ctrl+C para parar.")
    if abrir:
        from ..app import _abrir_navegador

        _abrir_navegador(f"http://{shown}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\ntchau.")
    finally:
        httpd.server_close()
    return 0


def _music_home() -> Path:
    return runtime.home()


#: pastas extras escolhidas pelo usuario nesta sessao (campo "Onde salvar")
_RAIZES_EXTRAS: list[Path] = []


def _registrar_raiz(pasta: Path) -> None:
    alvo = Path(pasta).expanduser().resolve()
    if alvo not in _RAIZES_EXTRAS:
        _RAIZES_EXTRAS.append(alvo)


def _raizes_arquivos() -> tuple[Path, ...]:
    """Pastas de onde `/api/file` pode servir audio.

    `out/` continua valendo (linha de comando e testes) e entra a pasta de
    musicas da biblioteca. Mais a pasta que o usuario escolher em `out` no
    pedido — por isso a lista e calculada, nao uma constante.
    """
    atual = _music_home() / "musicas"
    vistas: list[Path] = []
    for p in (atual, _MUSICAS, *_RAIZES_EXTRAS):
        if p not in vistas:
            vistas.append(p)
    return tuple(vistas)


def _pode_servir(alvo: Path) -> bool:
    """Autoriza o arquivo: dentro de `out/`, das raizes escolhidas ou da
    biblioteca.

    A biblioteca entra aqui porque a musica pode ter sido salva numa pasta
    escolhida em outra sessao ("Onde salvar: D:\\multitracks"). Na sessao
    seguinte essa pasta nao esta em `_RAIZES_EXTRAS`, mas o usuario ja
    registrou a musica — se a rota negasse o audio, a lista abriria com o
    player quebrado.
    """
    alvo = Path(alvo)
    raizes = [_OUT_ROOT, *_raizes_arquivos()]
    if any(_dentro(alvo, r) for r in raizes):
        return True
    try:
        from .. import biblioteca

        for versao in biblioteca.listar(limite=500):
            pasta_bib = versao.get("pasta")
            candidatos_bib = [pasta_bib, versao.get("apoio")]
            if pasta_bib:
                p_bib = Path(pasta_bib)
                candidatos_bib.append(str(p_bib.parent / f"{p_bib.name}-apoio"))
            for raiz in candidatos_bib:
                if raiz and _dentro(alvo, Path(raiz)):
                    return True
    except Exception:  # noqa: BLE001 - biblioteca indisponivel nao autoriza
        return False
    return False


def _resolver_arquivo_servido(caminho: str, pasta_dica: Path | None = None) -> Path | None:
    """Resolve caminho absoluto ou relativo a `out/` / raízes autorizadas."""
    if not caminho:
        return None
    alvo = Path(caminho)
    if ".." in alvo.parts:
        return None
    if alvo.is_absolute():
        candidatos = [alvo]
    else:
        candidatos = [_OUT_ROOT / alvo] + [r / alvo for r in _raizes_arquivos()]
        if pasta_dica is not None:
            candidatos.extend([pasta_dica / alvo, pasta_dica.parent / alvo])
    for candidato in candidatos:
        if candidato.is_file():
            resolvido = candidato.resolve()
            if _pode_servir(resolvido):
                return resolvido
    return None


def _dentro(alvo: Path, raiz: Path) -> bool:
    try:
        Path(alvo).resolve().relative_to(Path(raiz).resolve())
        return True
    except ValueError:
        return False


def _relativo(caminho: Path, raiz: Path) -> str:
    """Caminho codificado para a rota /api/file ou /api/cover."""
    from urllib.parse import quote

    resolvido = Path(caminho).resolve()
    try:
        rel = resolvido.relative_to(Path(raiz).resolve()).as_posix()
        return quote(rel, safe="/")
    except ValueError:
        return quote(resolvido.as_posix(), safe="/")


def _page() -> str:
    """HTML da interface.

    Lido do pacote (e não embutido como string) para o arquivo ser editável
    como HTML de verdade — com syntax highlight, lint e diff legível.

    Duas leituras, nesta ordem: pelo sistema de arquivos (instalação normal e
    PyInstaller) e por `pkgutil` (quando o pacote é um zipapp/.pyz, onde não
    existe caminho real no disco). Sem a segunda, `mrq-vs serve` quebra
    justamente na distribuição portátil — bug encontrado no teste do pacote
    empacotado, e o motivo deste fallback existir.
    """
    here = Path(__file__).with_name("index.html")
    if here.is_file():
        return here.read_text(encoding="utf-8")
    try:
        import pkgutil

        data = pkgutil.get_data(__name__, "index.html")
    except (OSError, ValueError):
        data = None
    if data:
        return data.decode("utf-8")
    raise RuntimeError(
        "interface web ausente do pacote (index.html). Reinstale com: pip install -e ."
    )
