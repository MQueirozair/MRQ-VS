"""Gerador de instaladores portáteis (Windows / macOS / Linux).

Por que existe: o produto é "baixe e use", e o alvo mais chato é justamente a
máquina do músico, que não tem Python configurado. Este script monta três
coisas, todas testáveis aqui:

1. **Pacote portátil** (`dist/mrq-vs-<sistema>-<arch>.zip`): o `.pyz`
   (zipapp com todo o código) + guia de instalação + licença. Roda em
   qualquer sistema que tenha Python 3.9+ — é a versão que eu consigo gerar
   e executar nesta sandbox, então é ela que vai anexada ao release junto
   com os binários nativos compilados no CI.
2. **Manifesto** (`dist/release-manifest.json`): nome, sha256 e tamanho de
   cada arquivo, para o `install.sh`/`install.ps1` não baixarem lixo.
3. **Checagem final**: roda o pacote gerado de verdade (`--version`, `stems`,
   um pipeline completo na demo) antes de declarar sucesso.

Uso:
    python -m mrqvs.release            # gera em dist/
    python -m mrqvs.release --no-zip   # só o manifesto/checagem
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "src" / "mrqvs"
DIST = ROOT / "dist"
def _version() -> str:
    from mrqvs import __version__

    return __version__


VERSION = _version()


def conferir_nome_do_pacote(nome: str, tag: str) -> None:
    """Recusa publicar um zip com nome de plataforma diferente do conteúdo.

    Existe por um erro real: `mrq-vs-0.1.19-linux-x64.zip` foi renomeado
    para `windows-x64` na entrega. O arquivo abria, era um zip válido — só
    não era o programa Windows que o nome prometia. Um nome errado é pior
    que um build faltando, porque ninguém descobre até o usuário reclamar.
    """
    if not nome.startswith("mrq-vs-"):
        return
    for sistema in ("windows", "macos", "linux"):
        if f"-{sistema}-" in nome and not tag.startswith(sistema):
            raise SystemExit(
                f"nome de pacote enganoso: {nome} diz {sistema}, mas o conteúdo é {tag}."
                f"\nO pacote desta máquina ({tag}) não pode ser publicado como {sistema}."
                f"\nPara o Windows completo, use o GitHub Actions (build.yml) ou windows/README.md."
            )


def _platform_tag() -> str:
    system = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine)
    return f"{system}-{arch}"


def build_pyz(dest: Path) -> Path:
    """Empacota `src/mrqvs` num zipapp executável."""
    staging = Path(tempfile.mkdtemp(prefix="mrqvs-pyz-"))
    shutil.copytree(PKG, staging / "mrqvs", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # O index.html precisa entrar no zipapp: sem ele o `serve` falha no
    # pacote portátil (o sistema de arquivos não tem esse caminho).
    assert (staging / "mrqvs" / "web" / "index.html").is_file()
    # O icone entra pelo mesmo motivo: a pagina pede /favicon.ico, a rota
    # le por pkgutil e, sem o arquivo no zip, a aba do navegador fica sem
    # icone - e ninguem percebe, porque nao da erro nenhum.
    for nome_icone in ("favicon.ico", "icone-192.png", "icone-512.png"):
        assert (staging / "mrqvs" / "web" / nome_icone).is_file(), (
            f"{nome_icone} fora do pacote (rode: python -m mrqvs.icone)"
        )
    (staging / "__main__.py").write_text(
        "import sys\nfrom mrqvs.cli import main\n\nsys.exit(main())\n", encoding="utf-8"
    )
    target = dest / f"mrq-vs-{VERSION}.pyz"
    subprocess.run(
        [sys.executable, "-m", "zipapp", str(staging), "-o", str(target), "-p", "/usr/bin/env python3"],
        check=True,
    )
    shutil.rmtree(staging, ignore_errors=True)
    return target


def guide_text(tag: str) -> str:
    return f"""MRQ VS {VERSION} — pacote portátil ({tag})
{'=' * 60}

Este pacote não instala nada no sistema. Três passos:

1. Precisa de Python 3.9 ou mais novo (https://python.org).
   No Windows, marque "Add python.exe to PATH" no instalador.

2. Confira as dependências:
       python mrq-vs-{VERSION}.pyz doctor

   Se faltar numpy/soundfile:
       python -m pip install numpy soundfile

3. Pronto. Use direto:
       python mrq-vs-{VERSION}.pyz "https://youtu.be/XXXXXXXXXXX"
       python mrq-vs-{VERSION}.pyz serve        # interface no navegador

Recomendado instalar como comando fixo:
       python -m pip install "numpy" "soundfile" "yt-dlp"
       python mrq-vs-{VERSION}.pyz --version

Para separação por IA (qualidade Moises):
       python -m pip install demucs        (≈2 GB, traz torch)

Dependências externas (não dá para empacotar em Python):
  ffmpeg  -> necessário para MP3/MP4 e para ler o áudio do YouTube
     Windows: winget install Gyan.FFmpeg
     macOS:   brew install ffmpeg
     Linux:   sudo apt install ffmpeg
  yt-dlp  -> baixar do YouTube (pip install -U yt-dlp)

Sem ffmpeg/yt-dlp e sem demucs o programa ainda abre, analisa arquivos locais,
separa no modo DSP e exporta WAV; ele avisa exatamente o que falta.

Licença do código: MIT (ver LICENSE). Os pesos do Demucs têm licença própria.
"""


def build_zip(pyz: Path, tag: str, out_dir: Path | None = None) -> Path:
    dest = out_dir or pyz.parent or DIST
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"mrq-vs-{VERSION}-{tag}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pyz, pyz.name)
        zf.writestr("LEIA-ME.txt", guide_text(tag))
        zf.writestr(
            "QUAL-PACOTE-E-ESTE.txt",
            "Este pacote contem apenas o arquivo .pyz (zipapp).\n"
            "\n"
            f"Ele NAO e o pacote Windows autonomo: exige Python 3.10+ instalado\n"
            f"e roda no terminal (python mrq-vs-{VERSION}.pyz).\n"
            "\n"
            "O pacote Windows completo (Python embutido + numpy + soundfile +\n"
            "ffmpeg + yt-dlp, abre com duplo clique no mrq-vs.exe) e gerado no\n"
            "GitHub Actions pelo workflow .github/workflows/build.yml, ou pela\n"
            "receita em windows/README.md.\n",
        )
        for extra in ("LICENSE", "README.md"):
            if (ROOT / extra).is_file():
                zf.write(ROOT / extra, extra)
    return target


def smoke_test(pyz: Path) -> list[str]:
    """Roda o pacote gerado de verdade: versão, catálogo e um pipeline."""
    problems: list[str] = []
    for args in (["--version"], ["stems"], ["doctor"]):
        proc = subprocess.run([sys.executable, str(pyz), *args], check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            problems.append(f"{' '.join(args)} -> código {proc.returncode}: {proc.stderr.strip()[:300]}")

    # O icone e a biblioteca tem de viajar dentro do .pyz. Faltando o
    # favicon a aba fica sem icone (silencioso); faltando a biblioteca o
    # usuario perde a lista de musicas salvas sem ver erro nenhum.
    with zipfile.ZipFile(pyz) as zf:
        nomes = set(zf.namelist())
    for obrigatorio in (
        "mrqvs/web/favicon.ico",
        "mrqvs/web/icone-192.png",
        "mrqvs/web/icone-512.png",
        # a guia falada depende destes: sem eles a guia cai na melodia
        "mrqvs/web/voz/palavras/1.wav",
        "mrqvs/web/voz/palavras/intro.wav",
        "mrqvs/biblioteca.py",
        "mrqvs/mixdown.py",
    ):
        if obrigatorio not in nomes:
            problems.append(f"pacote sem {obrigatorio} (fora do .pyz)")
    with tempfile.TemporaryDirectory(prefix="mrqvs-smoke-") as tmp:
        demo_dir = Path(tmp) / "_demo"
        from mrqvs import demo as demo_mod

        source = demo_mod.write(demo_dir / "demo_mix.wav")
        demo = Path(tmp) / "demo.wav"
        if source.is_file():
            shutil.copy2(source, demo)
            shutil.rmtree(demo_dir, ignore_errors=True)
            env = {**__import__("os").environ, "MRQVS_HOME": str(Path(tmp) / "_home")}
            proc = subprocess.run(
                [sys.executable, str(pyz), str(demo), "--out", tmp, "--format", "wav"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            if proc.returncode != 0:
                problems.append(f"pipeline -> {proc.returncode}: {proc.stderr.strip()[:300]}")
            else:
                # A saída agora são DUAS pastas: a de áudio (só os arquivos de
                # som, que é o que o usuário quer) e a "-apoio" (relatório,
                # capa, clique). O teste tem de conferir as duas, senão passa
                # num pacote onde a pasta de áudio ficou vazia.
                pastas = [
                    p for p in Path(tmp).iterdir()
                    if p.is_dir() and "BPM" in p.name and not p.name.endswith("-apoio")
                ]
                if not pastas:
                    problems.append("pipeline rodou mas não criou pasta com BPM no nome")
                else:
                    pasta = pastas[0]
                    if not list(pasta.glob("*.wav")):
                        problems.append("pasta de áudio criada sem stems")
                    if not (Path(tmp) / f"{pasta.name}-apoio").is_dir():
                        problems.append("não criou a pasta -apoio com relatório")
                    # e a pasta de áudio não pode conter nada além de áudio
                    estranhos = [
                        f.name for f in pasta.iterdir()
                        if f.is_file() and f.suffix.lower() not in
                        (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".aac")
                    ]
                    if estranhos:
                        problems.append(f"pasta de áudio tem arquivo não-áudio: {estranhos[:3]}")
    return problems


def manifest(files: list[Path], out_dir: Path | None = None) -> Path:
    entries = []
    for path in files:
        data = path.read_bytes()
        entries.append(
            {
                "nome": path.name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    payload = {
        "produto": "MRQ VS",
        "versao": VERSION,
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "arquivos": entries,
    }
    dest = out_dir or DIST
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "release-manifest.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    DIST.mkdir(exist_ok=True)
    tag = _platform_tag()
    print(f"MRQ VS {VERSION} — gerando pacote para {tag}")

    pyz = build_pyz(DIST)
    print(f"  pyz: {pyz.name} ({pyz.stat().st_size / 1024:.0f} KB)")

    files = [pyz]
    if "--no-zip" not in argv:
        bundle = build_zip(pyz, tag)
        print(f"  pacote: {bundle.name} ({bundle.stat().st_size / 1024:.0f} KB)")
        files.append(bundle)

    print("  testando o pacote gerado…")
    problems = smoke_test(pyz)
    if problems:
        print("  FALHOU:")
        for problem in problems:
            print(f"    - {problem}")
        return 1
    print("  ok: versão, catálogo, doctor e pipeline completo")

    target = manifest(files)
    print(f"  manifesto: {target.name}")
    for entry in json.loads(target.read_text(encoding="utf-8"))["arquivos"]:
        print(f"    {entry['sha256'][:16]}…  {entry['bytes']:>9} B  {entry['nome']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
