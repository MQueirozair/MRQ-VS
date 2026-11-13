"""Permite `python -m mrqvs ...` (equivalente a `mrq-vs ...`)."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
