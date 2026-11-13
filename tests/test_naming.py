import pytest

from mrqvs import naming


@pytest.mark.parametrize(
    "raw,esperado",
    [
        ("Coldplay - Yellow (Official Video)", "ColdplayYellow"),
        ("Evidências - Chitãozinho & Xororó (Clipe Oficial)", "EvidenciasChitaozinhoXororo"),
        ("Queen – Bohemian Rhapsody [Remastered]", "QueenBohemianRhapsody"),  # travessão
        ("Video Without Artist", "VideoWithoutArtist"),
    ],
)
def test_nome_de_pasta_artista_antes_do_titulo(raw, esperado):
    assert naming.project_folder_name(raw, 128).startswith(esperado)


def test_bpm_no_final_do_nome():
    assert naming.project_folder_name("Yellow - Coldplay", 95.6).endswith("-96BPM")
    assert naming.project_folder_name("Yellow - Coldplay", 128.0).endswith("-128BPM")


def test_bpm_desconhecido_nao_perde_o_sufixo():
    name = naming.project_folder_name("Qualquer Coisa", 0)
    assert name.endswith("BPMdesconhecido")


def test_canal_desempata_ordem_titulo_artista():
    # Aqui o padrão do YouTube ("Artista - Título") está invertido: o canal
    # aparece à esquerda, então o nome só sai certo com o desempate.
    name = naming.project_folder_name("Bohemian Rhapsody - Queen", 72, channel="Queen")
    assert name.startswith("QueenBohemianRhapsody")


def test_nome_respeita_limite_de_tamanho():
    raw = "Um Titulo Gigantesco Com Muitas Palavras Que Nao Acaba Nunca " * 2
    for limit in (20, 40, 90):
        name = naming.project_folder_name(raw, 100, max_len=limit)
        assert len(name) <= limit + len("-100BPM")


def test_slug_sem_acento_sem_espaco():
    assert naming.slugify("Ação, Coração & Paixão!") == "AcaoCoracaoPaixao"


def test_titulo_limpo_remove_sujeira_de_youtube():
    assert naming.clean_title("Song (Official Music Video) [HD]") == "Song"
    assert naming.clean_title("Song | Lyric Video") == "Song"


def test_stem_filename_ordena_por_catalogo():
    assert naming.stem_filename("proj", "vocals", "wav") == "proj_01_vocals.wav"
    assert naming.stem_filename("proj", "drums", "mp3") == "proj_03_drums.mp3"


def test_bpm_tag_arredonda():
    assert naming.bpm_tag(95.5) == "96BPM"
    assert naming.bpm_tag(0) == "BPMdesconhecido"
    assert naming.bpm_tag(None) == "BPMdesconhecido"
