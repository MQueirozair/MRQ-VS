# Pacote Windows portátil (sem instalar Python)

Esta pasta guarda a **receita** do zip `mrq-vs-*-windows-x64.zip`, para que o
pacote possa ser reconstruído sem depender de memória ou de CI.

| arquivo | papel |
|---|---|
| `launcher.c` | código-fonte do `mrq-vs.exe` (PE x86-64) |
| `run.py` | ponto de entrada; resolve `sys.path` e DLLs sozinho |
| `diag.py` | autoteste (`mrq-diag.cmd`) — arquivos, stdlib, numpy, áudio |
| `mrq-vs.cmd` / `mrq-diag.cmd` | atalhos de linha de comando |
| `mrq-vs.exe` | binário pronto (compilado com `zig cc -target x86_64-windows-gnu`) |

## Layout do zip

```
mrq-vs.exe            launcher (duplo clique -> janela do app)
mrq-vs.cmd            mesmo efeito, sem aviso do SmartScreen
mrq-diag.cmd          autoteste completo
runtime\              Python 3.13 embeddable (python_embed / data.zip)
  python313._pth      -> python313.zip / . / .. / ..\lib
app\                  mrq_vs.pyz (zipapp), run.py, diag.py
lib\                  numpy + numpy.libs (OpenBLAS), soundfile,
                      _soundfile_data\libsndfile_x64.dll, cffi,
                      typing_extensions, ffmpeg.exe, yt_dlp\
```

## Duplo clique = janela

`mrq-vs` sem argumentos chama `mrqvs.app.run()` (não o `--help`): escolhe uma
porta livre, sobe o servidor local e abre o navegador na interface. Fechar a
janela preta (ou Ctrl+C) encerra. O comportamento antigo — imprimir a ajuda do
argparse — parecia "não abriu nada" para quem não usa terminal.

`lib/` entra no `PATH` dentro de `run.py`, e é isso que faz `ffmpeg.exe` e
`python -m yt_dlp` funcionarem ali dentro sem instalar nada.

## As três armadilhas do Python embeddable (custaram 3 builds)

1. **`python313._pth` só aceita caminhos.** Colocar código Python nele faz o
   `python.exe` subir e sair sem executar nada.
2. **Quando `._pth` existe, `sys.path` é exatamente o que está escrito.**
   Esquecer a linha `.` (a própria pasta `runtime\`) faz todo `.pyd` da stdlib
   desaparecer — o sintoma é `ModuleNotFoundError: unicodedata`.
3. **DLL não é achada só por estar na pasta.** É preciso
   `os.add_dll_directory()`; `numpy.libs\*.dll` e `libsndfile_x64.dll` são
   carregados explicitamente em `run.py`.

Além disso: o wheels do `numpy` **precisa** da pasta `numpy.libs/` (é lá que
mora a OpenBLAS) — remover "arquivos desnecessários" quebra o pacote.

## Reconstruir

```bash
# 1) stdlib embutida (fonte: pacote PyPI python-embed, data.zip cp313/)
unzip python_embed/data.zip -d windist          # vira windist/runtime

# 2) ._pth: somente caminhos
printf 'python313.zip\r\n.\r\n..\r\n..\\lib\r\n' > windist/runtime/python313._pth

# 3) bibliotecas de terceiros (wheels win_amd64 cp313)
pip download --only-binary :all: --platform win_amd64 --python-version 3.13 \
    --implementation cp -d wheels numpy soundfile cffi typing_extensions
for w in wheels/*.whl; do unzip -qo "$w" -d windist/lib; done

# 4) o programa
python -m zipapp stage -o windist/app/mrq_vs.pyz

# 5) launcher
zig cc -target x86_64-windows-gnu -O2 -o windist/mrq-vs.exe windows/launcher.c

# 6) zip
zip -qr9 mrq-vs-0.1.1-windows-x64.zip windist -x "*.pyc"
```

## Testar sem Windows

`run.py` foi escrito para não depender do `._pth`; por isso dá para validar com:

```bash
python3 -I -S app/run.py --version
python3 -I -S app/run.py --doctor
echo "" | python3 -S app/diag.py     # autoteste completo
```

Se passar em `-I -S`, passa no embeddable (mesmo `sys.path`, sem `site`).
