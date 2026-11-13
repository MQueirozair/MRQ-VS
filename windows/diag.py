"""mrq-diag.py — autoteste do pacote Windows.

Roda com o Python EMBUTIDO do pacote e responde, de uma vez, tudo o que
precisamos saber quando algo da errado na maquina do usuario:

    mrq-diag.cmd          (duplo clique tambem funciona)

Cada linha comeca com [ok] / [FALHA] / [info]. Nada aqui depende do
Python do sistema — e o mesmo interpretador embutido que roda o programa.
"""

import os
import platform
import sys
import traceback

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ZIP = os.path.join(BASE, "app", "mrq_vs.pyz")
LIB = os.path.join(BASE, "lib")

falhas = []


def ok(msg):
    print("[ok]    " + msg)


def bad(msg):
    falhas.append(msg)
    print("[FALHA] " + msg)


def info(msg):
    print("[info]  " + msg)


print("MRQ VS - diagnostico do pacote")
print("=" * 60)
info(f"Windows: {platform.platform()}")
info(f"Python embutido: {sys.version.split()[0]} ({sys.executable})")
info(f"Pasta do pacote: {BASE}")
print()

print("1) Arquivos obrigatorios")
obrigatorios = [
    ("app\\mrq_vs.pyz", APP_ZIP),
    ("lib\\numpy", os.path.join(LIB, "numpy")),
    ("lib\\numpy.libs", os.path.join(LIB, "numpy.libs")),
    ("lib\\soundfile.py", os.path.join(LIB, "soundfile.py")),
    ("lib\\libsndfile", os.path.join(LIB, "_soundfile_data", "libsndfile_x64.dll" if sys.platform == "win32" else "libsndfile_x86_64.so")),
    ("runtime\\unicodedata.pyd", os.path.join(BASE, "runtime", "unicodedata.pyd")),
    ("lib\\ffmpeg.exe", os.path.join(LIB, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")),
    ("lib\\yt_dlp", os.path.join(LIB, "yt_dlp")),
]
for rotulo, caminho in obrigatorios:
    if os.path.exists(caminho):
        ok(rotulo)
    else:
        bad(rotulo + " NAO ENCONTRADO -> descompacte o zip inteiro")
print()

print("2) Módulos da biblioteca padrão (stdlib)")
for nome in ("os", "json", "re", "urllib.request", "http.server", "argparse", "pathlib", "unicodedata", "hashlib", "zipfile", "sqlite3", "ssl"):
    try:
        __import__(nome)
        ok(nome)
    except Exception as exc:
        bad(f"{nome}: {exc}")
print()

print("3) sys.path efetivo")
for p in sys.path:
    info(p)
print()

for caminho in (LIB, APP_ZIP):
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

print("4) Terceiros")
for nome in ("numpy", "soundfile", "cffi"):
    try:
        mod = __import__(nome)
        ok(f"{nome} {getattr(mod, '__version__', '?')}")
    except Exception as exc:
        bad(f"{nome}: {type(exc).__name__}: {exc}")
        traceback.print_exc()
print()

print("5) O programa carrega?")
try:
    from mrqvs import __version__ as versao
    from mrqvs.cli import build_parser

    build_parser()
    ok(f"mrqvs {versao} importado e CLI montada")
except Exception:
    bad("o pacote mrqvs nao carregou (traceback abaixo)")
    traceback.print_exc()
print()

print("6) Áudio (libsndfile)")
try:
    import numpy as np
    import soundfile as sf

    info(f"libsndfile: {sf.__libsndfile_version__}")
    caminho = os.path.join(BASE, "_teste_diag.wav")
    sf.write(caminho, np.zeros(1600, dtype="float32"), 16000)
    dados, taxa = sf.read(caminho)
    os.remove(caminho)
    ok(f"gravar e ler WAV ({len(dados)} amostras a {taxa} Hz)")
except Exception as exc:
    bad(f"audio: {type(exc).__name__}: {exc}")
    traceback.print_exc()
print()

print("7) Ferramentas de midia (ffmpeg e yt-dlp embutidos)")
import shutil
import subprocess

ffmpeg = None
for candidato in (os.path.join(LIB, "ffmpeg.exe"), os.path.join(LIB, "ffmpeg")):
    if os.path.exists(candidato):
        ffmpeg = candidato
        break
if ffmpeg:
    try:
        r = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=60)
        primeira = (r.stdout or r.stderr).splitlines()[0] if (r.stdout or r.stderr) else "?"
        ok(f"ffmpeg executa: {primeira}")
    except Exception as exc:
        bad(f"ffmpeg existe em {ffmpeg} mas nao executa: {exc}")
else:
    achado = shutil.which("ffmpeg")
    if achado:
        ok(f"ffmpeg no PATH: {achado}")
    else:
        info("ffmpeg nao encontrado: MP3/MP4 indisponiveis (o resto funciona)")

try:
    sys.path.insert(0, LIB)
    import yt_dlp

    ok(f"yt-dlp (modulo): {yt_dlp.version.__version__}")
except Exception as exc:
    achado = shutil.which("yt-dlp")
    if achado:
        ok(f"yt-dlp (binario): {achado}")
    else:
        info(f"yt-dlp nao encontrado (download do YouTube indisponivel): {exc}")
print()

print("=" * 60)
if falhas:
    print(f"RESULTADO: {len(falhas)} problema(s) encontrados.")
    for f in falhas:
        print("  - " + f)
else:
    print("RESULTADO: TUDO OK. O programa esta pronto para uso.")
print()
input("Pressione Enter para fechar...")
