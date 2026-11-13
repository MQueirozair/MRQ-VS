"""Normalização de título/artista e geração do nome de pasta do projeto.

Regra pedida: pasta = `Nome Abreviado + BPM`, ex.:

    "Bohemian Rhapsody (Official Video) - Queen"  @ 71.4 BPM
        ->  "BohemianRhapsody-Queen-71BPM"

O BPM vai arredondado (é o que o usuário reconhece: 71, não 71.4), e o nome
é encurtado em fronteira de palavra para no máximo `max_slug` caracteres.
Nada de depender do sistema de arquivos: a mesma função decide o nome da
pasta e o prefixo dos stems, então o resultado é previsível e repetível.
"""

from __future__ import annotations

import re
import unicodedata

# Rótulos que aparecem no título do YouTube e não são parte do nome da música.
_NOISE_PATTERNS = [
    r"\(official\s*(music\s*)?video\)",
    r"\[official\s*(music\s*)?video\]",
    r"\(official\s*audio\)",
    r"\[official\s*audio\]",
    r"\(lyric\s*video\)",
    r"\[lyric\s*video\]",
    r"\(letra\)",
    r"\(legend[ea]do\)",
    r"\(clipe\s*oficial\)",
    r"\(v[ií]deo\s*oficial\)",
    r"\([aá]udio\s*oficial\)",
    r"\(4k\)",
    r"\(hd\)",
    r"\[hd\]",
    r"\(remastered\)",
    r"\(remaster\)",
    r"\[remastered\]",
    r"\(official\s*videoclip\)",
    r"\(hq\)",
    r"\|\s*(?:lyric|official|music|video|legendado|tradu[çc][ãa]o)[^|]*$",
    r"\s+-\s+(?:lyric\s*video|official\s*(?:music\s*)?video|official\s*audio)$",
    r"\b(?:video|clipe|lyric\s*video)\s+oficial\b",
    r"\blegendado\b",
    r"\b(?:hd|4k|hq)\b",
]
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)

# Separadores comuns entre artista e título nos metadados do YouTube.
_SEPARATORS = [" - ", " – ", " — ", " | ", ": "]


#: `ç` e `ø`/`ł` **não** são decompostos por NFKD — precisam de mapa explícito,
#: senão "Coração" viraria "Coraao" em vez de "Coracao".
_EXTRA_FOLDS = str.maketrans({"ç": "c", "Ç": "C", "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ñ": "n", "Ñ": "N"})


def strip_accents(text: str) -> str:
    """Remove acentos preservando as letras (ã -> a, ç -> c, ñ -> n)."""
    normalized = unicodedata.normalize("NFKD", text.translate(_EXTRA_FOLDS))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def clean_title(raw: str) -> str:
    """Tira lixo promocional do título do vídeo ('(Official Video)', etc.)."""
    text = _NOISE_RE.sub(" ", raw or "")
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" -–—|")
    return text.strip()


def split_artist_title(raw: str) -> tuple[str, str]:
    """Devolve (titulo, artista) — artista vazio se o título não separar.

    Convenção predominante no YouTube é "Artista - Título" (ex.: "Coldplay -
    Yellow"), mas a ordem inversa ("Título - Artista") também aparece — em
    especial em vídeos de lyric/official audio. Como adivinhar pelo texto é
    chute, a regra é: o campo de **autor/canal** do vídeo decide. Se ele
    aparece em um dos lados, esse lado é o artista; senão vale a convenção
    "Artista - Título". Quem chama pode passar `channel` para desempatar.
    """
    text = clean_title(raw)
    for sep in _SEPARATORS:
        if sep in text:
            left, _, right = text.partition(sep)
            left, right = left.strip(), right.strip()
            if left and right:
                return right, left
    return text, ""


def pick_artist_title(raw_title: str, channel: str = "") -> tuple[str, str]:
    """Versão que usa o nome do canal para desempatar a ordem título/artista."""
    text = clean_title(raw_title)
    chan = _norm(clean_title(channel))
    for sep in _SEPARATORS:
        if sep in text:
            left, _, right = text.partition(sep)
            left, right = left.strip(), right.strip()
            if not (left and right):
                continue
            norm_left, norm_right = _norm(left), _norm(right)
            if chan and (chan in norm_right or norm_right in chan) and chan:
                return left, right
            if chan and (chan in norm_left or norm_left in chan):
                return right, left
            return right, left  # convenção "Artista - Título"
    return text, clean_title(channel)


def _norm(text: str) -> str:
    """Forma comparável: sem acento, minúscula, só letras e dígitos."""
    return re.sub(r"[^a-z0-9]", "", strip_accents(text).lower())


def slugify(text: str, max_len: int = 60) -> str:
    """ASCII, sem espaços/pontuação, sem perder a legibilidade do título."""
    text = strip_accents(clean_title(text))
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"[\s_-]+", " ", text).strip()
    words = text.split()
    out: list[str] = []
    length = 0
    for word in words:
        extra = len(word) + (1 if out else 0)
        if length + extra > max_len:
            break
        out.append(word)
        length += extra
    if not out and words:  # palavra única maior que o limite
        out = [words[0][:max_len]]
    return "".join(out)


def bpm_tag(bpm: float) -> str:
    """71.4 -> '71BPM'; 128 -> '128BPM'; 0/desconhecido -> 'BPMdesconhecido'."""
    if not bpm or bpm <= 0:
        return "BPMdesconhecido"
    return f"{int(round(bpm))}BPM"


def project_folder_name(raw_title: str, bpm: float, max_len: int = 90, channel: str = "") -> str:
    """Nome da pasta do projeto: título abreviado + BPM.

    O limite é generoso (90) porque o nome carrega o BPM no fim, que não pode
    ser cortado — por isso o slug é orçado com o sufixo já descontado.
    """
    suffix = bpm_tag(bpm)
    budget = max(8, max_len - len(suffix) - 1)
    title, artist = pick_artist_title(raw_title, channel) if channel else split_artist_title(raw_title)
    base = slugify(f"{artist} {title}" if artist else title, max_len=budget)
    if not base:
        base = "Instrumento"
    return f"{base}-{suffix}"


def stem_filename(prefix: str, stem_id: str, extension: str) -> str:
    """`<prefixo>_<nº>_<stem>.<ext>` — ordem numérica garante ordem de faixa."""
    from .stems import STEM_ORDER  # import tardio: evita ciclo

    index = STEM_ORDER.index(stem_id) + 1 if stem_id in STEM_ORDER else 99
    return f"{prefix}_{index:02d}_{stem_id}.{extension.lstrip('.')}"
