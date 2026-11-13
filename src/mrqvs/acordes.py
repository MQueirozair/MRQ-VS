"""Acordes por compasso: a base da "faixa de Guia" colorida do CueWee.

O que aparece nas fotos do CueWee e uma faixa com o acorde escrito em cada
compasso (E, F#m7, D, A/C#...). Isso vem de deteccao de acordes, e a mesma
informacao serve para tres coisas aqui:

1. escrever o acorde no relatorio e no `projeto.json`;
2. tocar um pad de referencia junto do click (opcional);
3. dar nome musical ao compasso que o usuario esta ouvindo.

Metodo: croma (energia por classe de nota) por compasso, comparado com
modelos de acorde maior/menor e suas setimas. E o metodo classico
(Temperley / "chordino" simplificado). Nao e tao bom quanto um modelo
treinado, e o codigo diz isso — "estimado" e a palavra usada na tela.
"""

from __future__ import annotations

NOTAS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

#: Intervalos (em semitons da fundamental) de cada tipo de acorde aceito.
TIPOS: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),          # maior
    "m": (0, 3, 7),         # menor
    "7": (0, 4, 7, 10),     # dominante
    "m7": (0, 3, 7, 10),    # menor com setima
    "maj7": (0, 4, 7, 11),  # maior com setima maior
    "sus4": (0, 5, 7),
}


#: Grafia de bemol. O CueWee escreve "Bb, Eb, Ab" e não "A#, D#, G#" —
#: músico lê bemol em cifra de tom bemol, e a tela do Studio mostra a cifra
#: do jeito que se escreve no papel. Qual das duas usar depende do TOM da
#: música (F maior pede Bb, A maior pede A#).
NOTAS_BEMOL = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")

#: Tons (pela tônica) que a teoria escreve com bemol.
TONS_BEMOL = {5, 10, 3, 8, 1, 6}  # F, Bb, Eb, Ab, Db, Gb


def usar_bemol(tonalidade: str) -> bool:
    """A tonalidade ("F maior", "Bb menor", "D menor"...) pede cifra com bemol?

    Recebe o rótulo que o analisador já produz. Decide pela armadura de clave:
    tons menores usam a armadura da relativa maior (`+3` semitons: Ré menor ->
    Fá maior -> bemol; Fá# menor -> Lá maior -> sustenido).
    """
    if not tonalidade:
        return False
    partes = tonalidade.split()
    nome = partes[0]
    menor = (len(partes) > 1 and partes[1].lower().startswith("men")) or nome.endswith("m")
    if nome.endswith("m") and len(nome) > 1:
        nome = nome[:-1]
    if nome in ("Db", "Eb", "Gb", "Ab", "Bb"):
        return True
    if nome in ("C#", "D#", "F#", "G#", "A#"):
        return False
    indice = NOTAS.index(nome) if nome in NOTAS else (
        NOTAS_BEMOL.index(nome) if nome in NOTAS_BEMOL else None
    )
    if indice is None:
        return False
    relativo_maior = (indice + 3) % 12 if menor else indice
    return relativo_maior in TONS_BEMOL


def nomes_do_acorde(tonica: int, tipo: str, bemol: bool = False) -> str:
    """Nome do acorde. `bemol=True` escreve A# como Bb (ver `NOTAS_BEMOL`)."""
    tabela = NOTAS_BEMOL if bemol else NOTAS
    return tabela[tonica % 12] + tipo


#: Notas "de cor" (setima, nona, quarta) pesam MENOS que as estruturais.
#: Sem isso, um espalhamento de ruido harmonico faz "Dsus4" ganhar de "G" mesmo
#: quando a fundamental e a quinta estao claras.
PESO_ESTRUTURAL = 1.0
PESO_COR = 0.55


def _modelo(tonica: int, tipo: str) -> list[float]:
    """Mascara do acorde: fundamental, terca e quinta valem mais.

    O ruido harmonico de um acorde real espalha energia nas notas vizinhas.
    Com todos os graus pesando igual, o acorde "de passagem" vence por acaso;
    pesando a estrutura, vence quem realmente sustenta o compasso.
    """
    vetor = [0.0] * 12
    for indice, intervalo in enumerate(TIPOS[tipo]):
        peso = PESO_ESTRUTURAL if indice < 3 else PESO_COR
        vetor[(tonica + intervalo) % 12] = peso
    return vetor


#: Peso de uma nota que NAO pertence ao acorde, na pontuacao.
#: Antes eu pontuava so os acertos e dividia pelo numero de notas — e isso
#: dava empate entre "G" (G+B+D, com A e E de fora) e "Dsus4" (D+G+A, com B
#: de fora): os dois explicavam quase a mesma energia. O ouvido resolve isso
#: pelo que SOBRA: ouvir um B forte no meio de D-G-A grita "isto e Sol, nao
#: Re". Pontuar negativamente as notas estranhas e o que separa os dois.
PENALIDADE_ESTRANHA = 0.45
#: Peso do voto do baixo. Alto de proposito: a nota que o baixo toca e o sinal
#: mais confiavel que existe para dizer QUAL acorde e, e e o que um musico
#: olha primeiro. Sem esta forca, F e Dm (que tem as mesmas notas) empatavam.
PESO_BAIXO = 2.5


#: Quanto da FUNDAMENTAL precisa estar presente para o acorde valer. Sem
#: isso, "Dsus4" ganhava de "G" com um Re de 0,05 na mistura, só porque Sol e
#: Lá já estavam lá — um acorde sem tônica audível não é esse acorde.
MINIMO_TONICA = 0.20


#: A quinta pode faltar sem deixar de ser o acorde (um G sem o Ré continua
#: sendo Sol). Sem isso, um harmônico de nona (Lá num acorde de Sol) era lido
#: como "sus4" e um Fá com Lá alto virava "Fsus4" nos testes.
PESO_QUINTA = 0.45


def _modelo_pontuado(nota: int, tipo: str) -> tuple[list[float], int]:
    """Modelo do acorde + índice da fundamental, com a quinta valendo menos."""
    base = _modelo(nota, tipo)
    pesos = list(base)
    if len(TIPOS.get(tipo, "")) >= 3:
        quinta = (nota + TIPOS[tipo][2]) % 12
        pesos[quinta] = PESO_QUINTA
    return pesos, nota


def _media(croma: list[float], modelo: list[float], tonica: int = 0) -> float:
    """Energia explicada pelo acorde menos a energia que sobra fora dele.

    `tonica` é o índice da fundamental (o modelo recebido já vem deslocado,
    então não dá para deduzi-la dele). Ela entra como portão: acorde cuja
    fundamental quase não aparece na mistura não compete — foi o que separou
    Sol de Dsus4 na demo, em que o baixo toca Sol mas as notas de apoio são
    as mesmas.
    """
    dentro = _forca(croma, modelo)
    fora = sum(croma) - dentro
    peso = sum(1.0 for v in modelo if v > 0)
    if not peso:
        return 0.0
    base = (dentro - PENALIDADE_ESTRANHA * fora) / peso
    total = sum(croma) or 1e-9
    if croma[tonica] / total < MINIMO_TONICA:
        base *= 0.55  # existe, mas perde para quem tem fundamental
    return base


def _forca(croma: list[float], modelo: list[float]) -> float:
    """Quanto do croma cai exatamente nas notas do acorde, sem penalizar o resto.

    Antes eu dividia pela soma do modelo (media), o que premiava acordes de
    UMA nota: dois de tres graus batendo davam medias parecidas com tres de
    tres num acorde maior de quatro notas. Somando apenas o que acerta, o
    acorde que explica mais energia ganha — que e o que o ouvido faz.
    """
    return sum(croma[i] * modelo[i] for i in range(12))


#: Tipos "estruturais": o acorde sem enfeite. A setima entra depois, e so
#: quando a nota esta realmente presente (somar nota nunca pode ser de graca:
#: com soma pura, acrescentar a setima SEMPRE aumenta a nota e todo acorde
#: sairia com 7).
TRÍADES = ("", "m", "sus4")
EXTENSOES = ("7", "m7", "maj7")


def identificar(
    croma: list[float], baixo: list[float] | None = None, bemol: bool = False
) -> tuple[str, float]:
    """Qual acorde melhor explica este croma. Devolve (nome, confianca).

    `baixo` e o croma da faixa grave (65-165 Hz). Sem ele, F e Dm sao
    indistinguiveis para um detector de croma (as duas tem F e A); com ele,
    a nota que o baixo toca decide. E o mesmo motivo pelo qual um musico
    olha a mao esquerda.
    """
    total = sum(croma)
    if total <= 0:
        return "", 0.0
    normalizado = [c / total for c in croma]
    baixo_norm: list[float] = []
    if baixo is not None and sum(baixo) > 0:
        total_baixo = sum(baixo)
        baixo_norm = [b / total_baixo for b in baixo]
    # O croma decide as NOTAS; o baixo decide a FUNDAMENTAL. Somar o espectro
    # do baixo ao croma (tentativa anterior) nao funcionou: o baixo tem
    # vazamento para os semitons vizinhos, e um G# de 0,05 virava "terceira
    # menor" e transformava Sol maior em Sol menor. Por isso o baixo entra
    # depois, como bonus na raiz — e nao como nota.
    combinado = normalizado

    melhor, melhor_nota, melhor_tipo = -1.0, 0, ""
    for nota in range(12):
        for tipo in TRÍADES:
            # `_forca` da o total; dividir pelo peso deixa a comparacao justa
            # entre acordes de 2 e de 3 notas (Dm = F+A+pouco D nao pode
            # ganhar de um G cheio so porque pontua parecido)
            pesos, tonica = _modelo_pontuado(nota, tipo)
            forca = _media(combinado, pesos, tonica)
            if baixo_norm:
                forca += PESO_BAIXO * baixo_norm[nota] * 0.1
            if forca > melhor:
                melhor, melhor_nota, melhor_tipo = forca, nota, tipo

    # setima: so entra se aquela nota tiver presenca real no compasso
    for tipo in EXTENSOES:
        notas = TIPOS[tipo]
        setima = (melhor_nota + notas[-1]) % 12
        fundamental = combinado[melhor_nota]
        if fundamental > 0 and combinado[setima] >= fundamental * 0.55:
            pesos, tonica = _modelo_pontuado(melhor_nota, tipo)
            forca = _media(combinado, pesos, tonica)
            if baixo_norm:
                forca += PESO_BAIXO * baixo_norm[melhor_nota] * 0.1
            if forca > melhor + 0.02:
                melhor, melhor_tipo = forca, tipo

    # confianca: destacar-se do segundo colocado — a pergunta real e "esse
    # acorde esta certo?", e um empate tecnico vale menos que vitoria clara
    segunda = 0.0
    for nota in range(12):
        for tipo in TRÍADES:
            if (nota, tipo) == (melhor_nota, melhor_tipo):
                continue
            pesos, tonica = _modelo_pontuado(nota, tipo)
            valor = _media(combinado, pesos, tonica)
            if baixo_norm:
                valor += PESO_BAIXO * baixo_norm[nota] * 0.1
            segunda = max(segunda, valor)
    margem = max(0.0, melhor - segunda)
    confianca = min(1.0, melhor * 0.7 + margem * 5)
    return nomes_do_acorde(melhor_nota, melhor_tipo, bemol), round(confianca, 2)


def por_compasso(
    audio,
    sample_rate: int,
    batidas: list[float],
    compasso: int = 4,
    tonalidade: str = "",
) -> list[dict]:
    """Acorde estimado em cada compasso.

    `audio` e (frames, canais) ou (frames,) em float. Usa so a soma dos canais:
    croma estereo nao melhora a estimativa o suficiente para pagar a conta.

    `tonalidade` ("F maior") decide a grafia da cifra: em F maior, o acorde de
    A# se escreve Bb, como numa partitura e como o CueWee escreve.
    """
    import numpy as np

    bemol = usar_bemol(tonalidade)

    sinal = np.asarray(audio, dtype=np.float32)
    if sinal.ndim > 1:
        sinal = sinal.mean(axis=1)
    if sinal.size == 0 or not batidas:
        return []

    janela = max(1024, int(0.093 * sample_rate))  # ~93 ms, em qualquer taxa
    # croma do compasso inteiro por media dos quadros: acorde de passagem
    # aparece, mas o que sustenta o compasso domina
    resultados: list[dict] = []
    for i in range(0, len(batidas) - compasso + 1, compasso):
        inicio = batidas[i]
        fim = batidas[i + compasso] if i + compasso < len(batidas) else inicio + 1.0
        a = max(0, int(inicio * sample_rate))
        b = min(sinal.size, int(fim * sample_rate))
        if b - a < janela:
            continue
        trecho = sinal[a:b]
        croma = _croma(trecho, janela, sample_rate)
        grave = _nota_do_baixo(trecho, sample_rate)
        nome, confianca = identificar(croma, grave, bemol=bemol)
        if not nome:
            continue
        resultados.append(
            {
                "inicio": round(inicio, 2),
                "fim": round(fim, 2),
                "compasso": i // compasso + 1,
                "acorde": nome,
                "confianca": confianca,
            }
        )
    return resultados


def _nota_do_baixo(trecho, sample_rate: int) -> list[float]:
    """Croma do baixo por janela LONGA.

    Por que nao reaproveitar `_croma` com uma faixa grave: a resolucao de
    frequencia e inversamente proporcional ao tamanho da janela. Com 93 ms
    (a janela do croma geral) a resolucao e ~11 Hz, e Sol (98 Hz) fica
    indistinguivel de La (110) e de Fa (87) — na demo, o baixo em Sol saia
    como Fa+La empatados. Com 0,5 s a resolucao cai para ~2 Hz e a nota
    aparece limpa.

    Pega o pico da faixa do baixo por janela e vota na classe de nota. Nao
    soma o espectro inteiro da faixa: os harmonicos de outros instrumentos
    caem ali e puxariam o voto.
    """
    import numpy as np

    sinal = np.asarray(trecho, dtype=np.float32)
    if sinal.size < 4096:
        return [0.0] * 12
    # Janela de ~0,25 s (em vez de uma janela unica de 0,74 s): com uma so,
    # o baixo que aparece por menos de meio segundo simplesmente nao entrava
    # no quadro — o teste com baixo em Fa devolvia La# por causa disso. A
    # 0,25 s a resolucao fica em ~4 Hz, suficiente para separar Sol de La
    # (12 Hz) e ainda caber uma nota curta.
    janela = int(0.25 * sample_rate)
    janela = min(2 ** int(np.log2(janela)), 2 ** int(np.log2(max(4096, sinal.size))))
    passo = max(1024, janela // 2)
    votos = np.zeros(12, dtype=np.float64)
    for ini in range(0, max(1, sinal.size - janela) + 1, passo):
        quadro = sinal[ini : ini + janela]
        if quadro.size < janela:
            break
        espectro = np.abs(np.fft.rfft(quadro * np.hanning(quadro.size)))
        freqs = np.fft.rfftfreq(quadro.size, 1.0 / sample_rate)
        # 40 Hz (Mi1, a corda mais grave do baixo de 4 cordas) a 160 Hz
        # (Mi3). O teto fica abaixo de Fa3 (174 Hz) para o violão nao disputar
        # a região, e o piso abaixo de 55 Hz para o Dó2 (65 Hz) não ficar
        # colado na borda — nota na borda da faixa perde para a vizinha.
        mascara = (freqs >= 40.0) & (freqs <= 160.0)
        if not mascara.any():
            continue
        # Rampa suave só nas bordas (plena entre 50 e 145 Hz). Um sino
        # inteiro atenuava o baixo grave de verdade; sem rampa nenhuma, uma
        # nota FORA da faixa (Fa3 = 174 Hz) vaza para a borda e vira o pico.
        # A rampa resolve os dois: mata o vazamento sem matar o grave real.
        indices = np.flatnonzero(mascara)
        rampa = np.interp(freqs[indices], [40.0, 50.0, 145.0, 160.0], [0.0, 1.0, 1.0, 0.0])
        faixa = np.zeros_like(espectro)
        faixa[indices] = espectro[indices] * rampa
        pico = int(np.argmax(faixa))
        energia = float(faixa[pico])
        if energia <= 0:
            continue
        # Descarta quadros sem grave de verdade: sem este filtro, um quadro
        # so com vozes e violao "vota" com o vazamento da banda e inventa um
        # baixo que nao existe.
        if energia < 0.05 * float(espectro.max()):
            continue
        # media dos 3 bins em volta do pico: o pico sozinho oscila com o
        # vibrato do baixista e troca de nota sem a nota ter mudado
        media = float(faixa[max(0, pico - 1) : pico + 2].mean())
        # interpolacao parabolica: em 55-165 Hz cada bin vale 2 Hz, e 1 bin
        # de erro ja troca Sol por La. A parabola acha o pico real dentro do bin.
        freq = float(freqs[pico])
        if 0 < pico < len(faixa) - 1:
            a, b, c = (float(np.log1p(faixa[pico + k])) for k in (-1, 0, 1))
            denom = a - 2 * b + c
            if abs(denom) > 1e-12:
                deslocamento = 0.5 * (a - c) / denom
                deslocamento = max(-0.5, min(0.5, deslocamento))
                passo_hz = float(freqs[1] - freqs[0])
                freq += deslocamento * passo_hz
        classe = int(round(12 * np.log2(freq / 440.0))) % 12
        votos[(classe + 9) % 12] += media
    total = votos.sum()
    return (votos / total).tolist() if total > 0 else [0.0] * 12


def _croma(
    trecho, janela: int, sample_rate: int = 44100, faixa: tuple[float, float] | None = None
) -> list[float]:
    import numpy as np

    passo = janela // 2
    acumulado = np.zeros(12, dtype=np.float64)
    quadros = 0
    for ini in range(0, max(1, trecho.size - janela), passo):
        quadro = trecho[ini : ini + janela]
        if quadro.size < janela:
            break
        espectro = np.abs(np.fft.rfft(quadro * np.hanning(janela)))
        freqs = np.fft.rfftfreq(janela, 1.0 / sample_rate)
        # de 65 Hz (Dó2) a 2 kHz: fora disso e ruido de borda do espectro
        for bin_freq, energia in zip(freqs, espectro):
            baixo, alto = faixa if faixa else (65.0, 2000.0)
            if energia <= 0 or bin_freq < baixo or bin_freq > alto:
                continue
            nota = int(round(12 * np.log2(bin_freq / 440.0))) % 12
            # 440 Hz = Lá = índice 9 na tabela NOTAS. Soma pela AMPLITUDE
            # (não pela energia): energia ao quadrado faz o baixo, que é
            # forte, decidir o acorde sozinho — foi por isso que a demo
            # prevista como C-G-Am-F saía como C-Dsus4-Am-Dm.
            acumulado[(nota + 9) % 12] += float(np.sqrt(energia))
        quadros += 1
    if quadros:
        acumulado /= quadros
    return acumulado.tolist()


# ---------------------------------------------------------------------------
# Compasso (4/4 ou 3/4)
# ---------------------------------------------------------------------------
#: Modelo de downbeat opcional. `beat_this` (CPJKU, licença MIT) é um
#: transformer treinado que devolve batidas E downbeats de verdade — o
#: primeiro tempo de cada compasso por modelo, não por heurística. Ele custa
#: torch + ~300 MB de pesos, então é opcional: sem ele, `compasso()` usa a
#: heurística de acento, que funciona e é honesta sobre a confiança.
DOWNBEAT_MODELO = "beat_this"


def downbeat_disponivel() -> bool:
    """O modelo de compasso está instalado e importável?"""
    try:
        import beat_this.inference  # noqa: F401
    except Exception:  # noqa: BLE001 - qualquer falha = indisponível
        return False
    return True


def compasso_com_modelo(
    caminho_audio, timeout: int = 300
) -> tuple[int, float, list[float]] | None:
    """Compasso e downbeats pelo `beat_this`. None se não estiver instalado.

    Devolve (tempos_por_compasso, confiança, downbeats_em_segundos).

    Por que vale a pena mesmo sendo um download grande: errar o 1º tempo é
    o pior erro possível para quem usa clique no palco — o metrônomo acentua
    o tempo errado a música inteira. A heurística de acento acerta o compasso
    na maioria dos louvores/pop, mas não em música sem bateria.
    """
    if not downbeat_disponivel():
        return None
    try:
        from beat_this.inference import File2Beats

        modelo = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
        batidas, downbeats = modelo(str(caminho_audio))
    except Exception:  # noqa: BLE001 - modelo quebrado não derruba o projeto
        return None

    batidas = [float(b) for b in batidas]
    downbeats = [float(d) for d in downbeats]
    if len(batidas) < 8 or len(downbeats) < 3:
        return None
    # O compasso é a distância média ENTRE downbeats, em batidas. Se a
    # distância varia muito, o modelo está inseguro (mudança de compasso,
    # rubato): devolve confiança baixa em vez de fingir precisão.
    indices = []
    for d in downbeats:
        mais_perto = min(range(len(batidas)), key=lambda i: abs(batidas[i] - d))
        indices.append(mais_perto)
    passos = [b - a for a, b in zip(indices, indices[1:]) if b > a]
    if not passos:
        return None
    passos.sort()
    mediana = passos[len(passos) // 2]
    if mediana not in (2, 3, 4):
        # 6/8 e 12/8 existem, mas o clique deles é 2 ou 3 por tempo; escrever
        # "6/4" na tela confundiria mais do que ajudaria.
        mediana = 4 if mediana > 4 else mediana
    iguais = sum(1 for p in passos if p == mediana)
    confianca = round(iguais / len(passos), 2)
    return int(mediana), confianca, downbeats


def batidas_do_modelo(caminho_audio) -> list[float]:
    """Grade de batidas do `beat_this` (vazia se o modelo não estiver lá).

    Separado de `compasso_com_modelo` para o projeto reaproveitar a mesma
    execução do modelo — rodar o transformer duas vezes custaria o dobro.
    """
    if not downbeat_disponivel():
        return []
    try:
        from beat_this.inference import File2Beats

        modelo = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
        batidas, _ = modelo(str(caminho_audio))
        return [float(b) for b in batidas]
    except Exception:  # noqa: BLE001
        return []


def compasso(
    audio, sample_rate: int, bpm: float, batidas: list[float] | None = None
) -> tuple[int, float]:
    """Quantos tempos tem o compasso. Devolve (tempos, confiança).

    Como funciona: a cada batida mede-se a energia de ataque (diferença de
    energia entre o quadro da batida e o anterior). Em 4/4, as batidas 1 e 3
    tendem a ser mais fortes que 2 e 4; em 3/4 so a 1 se destaca. Somando a
    energia por posição no ciclo e comparando ciclos de 2, 3 e 4 batidas, o
    ciclo certo acumula um pico numa posição só.

    Isso erra em música com acento fraco (pad, balada sem bateria) — e é por
    isso que a função devolve confiança em vez de afirmar. A tela mostra o
    compasso com a confiança e o relatório diz que é estimado.
    """
    import numpy as np

    if not batidas or len(batidas) < 8 or bpm <= 0:
        return 4, 0.0
    sinal = np.asarray(audio, dtype=np.float32)
    if sinal.ndim > 1:
        sinal = sinal.mean(axis=1)
    if sinal.size == 0:
        return 4, 0.0

    janela = max(256, int(0.02 * sample_rate))
    forcas: list[float] = []
    for batida in batidas:
        centro = int(batida * sample_rate)
        antes = max(0, centro - janela)
        depois = min(sinal.size, centro + janela)
        if depois - antes < 2:
            forcas.append(0.0)
            continue
        energia = float(np.sum(np.abs(sinal[antes:depois])))
        forcas.append(energia)
    serie = np.asarray(forcas, dtype=np.float64)
    # normaliza pelo tamanho: batidas no fim do arquivo têm a mesma chance
    if serie.max() > 0:
        serie = serie / serie.max()

    def pico_de(ciclo: int) -> float:
        """Força da posição mais forte, relativa à média do ciclo."""
        posicoes = [serie[i::ciclo].mean() for i in range(ciclo)]
        media = sum(posicoes) / ciclo
        return max(posicoes) / media if media > 0 else 1.0

    # 4/4 e 3/4 são os compassos reais; 2/4 fica de fora de propósito: sem
    # bateria (ou com bumbo em 1 e 3) ele imita 4/4 com metade dos dados e
    # ganha por acidente — foi o que aconteceu na primeira versão do teste.
    pico4 = pico_de(4) if len(serie) >= 12 else 1.0
    pico3 = pico_de(3) if len(serie) >= 9 else 1.0
    if pico4 <= 1.0001 and pico3 <= 1.0001:
        return 4, 0.0  # sem acento nenhum: assume o mais comum, sem confiança

    # O 3/4 precisa ser claramente melhor: em música sem acento, 4/4 é a
    # aposta segura (a maioria dos louvores e pop é 4/4).
    if pico3 > pico4 * 1.15:
        return 3, round(max(0.0, min(1.0, (pico3 - 1.0) * 2.5)), 2)
    return 4, round(max(0.0, min(1.0, (pico4 - 1.0) * 2.5)), 2)
