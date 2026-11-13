"""Entrypoint do executável portátil (PyInstaller).

Separado de `__main__.py` de propósito: o PyInstaller precisa de um script
real, e aqui garantimos que a exceção final saia com código legível e sem
traceback gigante na cara do usuário que só clicou duas vezes no .exe.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":  # pragma: no cover - exercitado só no binário
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrompido.", file=sys.stderr)
        sys.exit(130)
