#!/usr/bin/env python3
"""Recria o projeto de demonstração que aparece no preview do navegador.

Por que existe: o preview servido pela Arena roda numa cópia do repositório, e
a pasta de saída (`out/`) não é preservada entre sessões. Sem isso, quem abre o
preview encontra a tela vazia — a lista de músicas fica sem nada para clicar e
qualquer verificação da interface vira teoria. O script gera um projeto de
verdade, pequeno (~11 MB, 12 s de áudio), e registra na biblioteca do programa.

O áudio NÃO é versionado: é saída de pipeline, e o `.gitignore` já barra `out/`.
O que fica no repositório é este arquivo, que reconstrói tudo em ~2 s.

Uso:
    .venv/bin/python scripts/demo-preview.py

O resultado é `demo-projeto/LouvorDemo-96BPM/` + `-apoio/`, com projeto
multitrack (`projeto.mrqvs.json`), cifra nos três formatos, MIDI, ficha A4 e
letra. A pasta é registrada em `biblioteca.json` (na raiz do projeto, também
ignorada pelo Git), então a lista "Minhas músicas" da tela mostra o item
assim que a página carrega.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from mrqvs import biblioteca, demo, project, runtime  # noqa: E402

DESTINO = RAIZ / "demo-projeto"
SEGUNDOS = 12.0


def main() -> int:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)

    dados = demo.build()
    sr = dados["sample_rate"]
    mix = np.asarray(dados["mix"], dtype=np.float32)
    amostras = min(mix.size, int(SEGUNDOS * sr))
    entrada = DESTINO / "Louvor Demo.wav"
    sf.write(entrada, mix[:amostras], sr)

    opcoes = project.ProjectOptions(
        source=str(entrada),
        out_dir=DESTINO,
        stems=["vocals", "drums", "bass", "other"],
        fmt="wav",
        bits=16,
        click=True,
        guia=False,
        title="Louvor Demo",
    )
    project.run(opcoes, progress=lambda _msg: None)

    pasta = DESTINO / "LouvorDemo-96BPM"
    apoio = DESTINO / "LouvorDemo-96BPM-apoio"
    if not (apoio / "projeto.mrqvs.json").is_file():
        print("erro: o pipeline não gravou o projeto multitrack", file=sys.stderr)
        return 1

    # A biblioteca é índice, não cópia: apontar para a pasta do repo basta.
    indice = runtime.home() / biblioteca.ARQUIVO
    indice.write_text(json.dumps({"versoes": []}), encoding="utf-8")
    biblioteca.registrar(
        pasta,
        apoio=apoio,
        titulo="Louvor Demo",
        bpm=96,
        tom="C maior",
        motor="dsp-fallback/dsp-fallback",
        duracao=SEGUNDOS,
        origem="demonstração do preview",
    )

    tamanho = sum(f.stat().st_size for f in DESTINO.rglob("*") if f.is_file())
    print(f"ok: {pasta.relative_to(RAIZ)}")
    print(f"    {len(list(DESTINO.rglob('*.wav')))} WAV · {tamanho / 1e6:.1f} MB · "
          f"{len(list(apoio.iterdir()))} arquivos de apoio")
    print("    registrado na biblioteca: abra a tela e clique em 'Louvor Demo'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
