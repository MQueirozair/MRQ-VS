"""Testes do empacotamento: o que o usuário baixa tem que funcionar."""

import json
import sys
import zipfile
from pathlib import Path

import pytest

from mrqvs import release


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    dest = tmp_path_factory.mktemp("dist")
    pyz = release.build_pyz(dest)
    bundle = release.build_zip(pyz, "linux-x64")
    return pyz, bundle


def test_pyz_roda_e_responde(built):
    pyz, _ = built
    import subprocess

    proc = subprocess.run([sys.executable, str(pyz), "--version"], capture_output=True, text=True)
    assert proc.returncode == 0
    assert release.VERSION in proc.stdout


def test_zip_contem_o_necessario_para_instalar(built):
    _, bundle = built
    with zipfile.ZipFile(bundle) as zf:
        names = set(zf.namelist())
        assert any(n.endswith(".pyz") for n in names)
        assert "LEIA-ME.txt" in names
        assert "LICENSE" in names
        guia = zf.read("LEIA-ME.txt").decode("utf-8")
        assert "doctor" in guia and "ffmpeg" in guia and "demucs" in guia


def test_manifesto_tem_hash_de_cada_arquivo(built, tmp_path):
    pyz, bundle = built
    target = release.manifest([pyz, bundle])
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["versao"] == release.VERSION
    nomes = {a["nome"] for a in data["arquivos"]}
    assert nomes == {pyz.name, bundle.name}
    for arquivo in data["arquivos"]:
        assert len(arquivo["sha256"]) == 64
        assert arquivo["bytes"] > 0


def test_smoke_test_aprova_o_pacote_gerado(built):
    pyz, _ = built
    assert release.smoke_test(pyz) == []


def test_instaladores_existem_e_apontam_para_o_repo():
    root = Path(__file__).resolve().parents[1]
    for name in ("install.sh", "install.ps1"):
        text = (root / name).read_text(encoding="utf-8")
        assert "MQueirozair/MRQ-VS" in text
        assert "releases/latest/download" in text
    # os nomes dos assets têm que ser os mesmos que o workflow publica
    workflow = (root / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    for asset in ("mrq-vs-windows-x64.exe", "mrq-vs-macos-arm64", "mrq-vs-linux-x64"):
        assert asset in workflow, asset


def test_serve_funciona_dentro_do_pyz(built):
    """Regressão: no .pyz não existe caminho de arquivo real.

    O `_page()` lia `Path(__file__).with_name("index.html")` e isso quebrava
    `mrq-vs serve` no pacote portátil — o único caminho em que o usuário final
    roda. O fallback por `pkgutil` tem que continuar funcionando.
    """
    import subprocess

    pyz, _ = built
    script = (
        "import sys; sys.path.insert(0, %r);"
        "import mrqvs.web; page = mrqvs.web._page();"
        "assert '<!doctype html>' in page.lower(), 'html invalido';"
        "print(len(page))" % str(pyz)
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert int(proc.stdout.strip()) > 5000
