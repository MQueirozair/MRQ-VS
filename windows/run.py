"""Ponto de entrada do pacote Windows (chamado pelo mrq-vs.exe).

Por que este arquivo existe: o Python embeddable e uma build restrita. O
`python313._pth` aceita SOMENTE caminhos, e quando ele existe o sys.path e
exatamente o que esta escrito la. Este script nao confia nisso: ele mesmo

  * descobre a pasta do pacote a partir do proprio arquivo,
  * coloca `lib` e `app\\mrq_vs.pyz` no sys.path,
  * registra a pasta das DLLs no Windows (numpy/lib, runtime),
  * so entao importa o programa.

Assim o mesmo pacote funciona com ._pth correto, incompleto ou ausente.
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# diz ao pacote onde ele mora: a pasta de IA (`mrq-ai/`) é criada aqui,
# e não dentro de `app/` (que muda quando o programa é atualizado).
os.environ.setdefault("MRQVS_HOME", BASE)
APP_ZIP = os.path.join(BASE, "app", "mrq_vs.pyz")
LIB = os.path.join(BASE, "lib")
RUNTIME = os.path.join(BASE, "runtime")

# 1) caminhos de importacao (o zipapp vem primeiro para nao pegar lixo)
for path in (APP_ZIP, LIB):
    if path not in sys.path:
        sys.path.insert(0, path)

# 2) ferramentas embutidas (ffmpeg.exe, yt-dlp.exe) precisam estar no PATH
#    para o subprocess achar — DLL nao e PATH, sao coisas diferentes.
for pasta in (LIB, os.path.join(LIB, "tools")):
    if os.path.isdir(pasta) and pasta not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")

# 3) no Windows, dependencia de DLL so e achada em pastas registradas
if sys.platform == "win32":
    for pasta in (LIB, os.path.join(LIB, "numpy.libs"), RUNTIME, os.path.join(LIB, "_soundfile_data")):
        if not os.path.isdir(pasta):
            continue
        try:
            os.add_dll_directory(pasta)
        except (AttributeError, OSError):
            pass
    # carrega as DLLs pelo nome completo: e o caminho mais confiavel quando o
    # .pyd e importado por caminho absoluto (numpy.libs -> OpenBLAS)
    try:
        import ctypes
        import glob

        for padrao in (
            os.path.join(LIB, "numpy.libs", "*.dll"),
            os.path.join(RUNTIME, "*.dll"),
            os.path.join(LIB, "*.dll"),
        ):
            for dll in sorted(glob.glob(padrao)):
                try:
                    ctypes.WinDLL(dll)
                except OSError:
                    pass
    except ImportError:
        pass

try:
    from mrqvs.cli import main
except Exception:  # noqa: BLE001 - aqui a mensagem vale mais que o traceback
    import traceback

    print("MRQ VS nao conseguiu carregar o proprio codigo.", file=sys.stderr)
    print(file=sys.stderr)
    traceback.print_exc()
    print(
        "\nDica: rode mrq-diag.cmd para um diagnostico completo."
        "\nCausa mais comum: zip descompactado pela metade (as pastas 'lib',"
        " 'app' e 'runtime' precisam estar ao lado do mrq-vs.exe).",
        file=sys.stderr,
    )
    raise SystemExit(3)

if __name__ == "__main__":
    sys.exit(main())
