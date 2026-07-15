"""Estratégia de jogo dos bots: Minimax com poda Alfa-Beta sobre
determinizações das cartas desconhecidas, mais heurísticas para apostas.

O truco tem árvore de jogo pequena (no máximo 3 cartas por jogador, no
máximo 3 rodadas por mão), mas é um jogo de **informação imperfeita**: o bot
não vê a mão dos adversários, então não dá pra rodar Minimax direto sobre o
estado real (não existe um único `Result(s, a)` que o bot conheça).

A solução usada aqui é a clássica para jogos de cartas com informação
oculta ("Perfect Information Monte Carlo"): a partir do que já é público
(minha mão, cartas já jogadas nesta mão), sorteamos várias distribuições
plausíveis das cartas que os adversários podem ter — cada sorteio
("determinização") é um jogo de informação *perfeita* comum, que pode ser
resolvido com Minimax + Alfa-Beta normalmente. A jogada escolhida é a que
tiver melhor valor médio entre as amostras (na prática, uma média ponderada
das crenças sobre o estado real, a mesma ideia do slide "jogos com
incerteza").

Como o time é sempre dividido em exatamente 2 lados (equipe 0 e equipe 1,
mesmo com 4/6/8 jogadores), o jogo cabe perfeitamente no molde MAX/MIN de
dois agentes: cada jogador, ao jogar, é nó MAX se for da minha equipe ou nó
MIN se for da equipe adversária.

Quando a quantidade de jogadas restantes na mão é grande (início de mão nos
modos de 6/8 jogadores), a árvore completa fica grande demais para resolver
exatamente; nesse caso a busca é cortada numa profundidade máxima e uma
função de avaliação heurística substitui o valor exato — a mesma ideia de
"Minimax com profundidade limitada + Eval(s)" usada em jogos grandes.
"""

import random

from server.game import MANILHAS_POR_MODO, forca_carta, montar_baralho, resolver_mao

# Presets de dificuldade: cada um é um config completo (busca + apostas),
# passado explicitamente pra cada função de decisão (default MEDIO, pra
# quem já chama essas funções sem o argumento novo continuar funcionando
# sem mudança de comportamento).
#
# Lógica por trás dos números: no FACIL, menos amostras/profundidade =
# busca mais rasa = joga carta um pouco pior tecnicamente; limiares mais
# altos = só aposta com mão muito boa = padrão fácil de explorar por um
# humano. No DIFICIL é o oposto: busca mais robusta e mais disposto a
# apostar com mão mediana (pressão), comportamento de jogador experiente.
# `sigma_ruido` e `prob_blefe` ver `_forca_com_ruido`/`deve_chamar_truco`.
DIFICULDADES = {
    "FACIL": dict(
        amostras=10,
        profundidade_maxima=6,
        limiar_chamar_truco=0.92,
        limiar_aumentar=0.97,
        limiar_aceitar=0.70,
        limiar_mao_10=0.75,
        sigma_ruido=0.18,
        prob_blefe=0.03,
    ),
    "MEDIO": dict(
        amostras=24,
        profundidade_maxima=10,
        limiar_chamar_truco=0.78,
        limiar_aumentar=0.88,
        limiar_aceitar=0.55,
        limiar_mao_10=0.60,
        sigma_ruido=0.08,
        prob_blefe=0.08,
    ),
    "DIFICIL": dict(
        amostras=40,
        profundidade_maxima=14,
        limiar_chamar_truco=0.70,
        limiar_aumentar=0.85,
        limiar_aceitar=0.48,
        limiar_mao_10=0.55,
        sigma_ruido=0.04,
        prob_blefe=0.14,
    ),
}

_CONFIG_PADRAO = DIFICULDADES["MEDIO"]

# margem (na mesma escala 0..~1.5 de avaliar_forca_mao) abaixo do limiar de
# truco a partir da qual uma mão é "fraca o bastante" pra blefe deliberado
# valer a pena cogitar (ver deve_chamar_truco).
MARGEM_BLEFE = 0.15


def _forca_normalizada(carta, modo):
    return forca_carta(carta, modo) / 1010.0


def avaliar_forca_mao(cartas, modo):
    """Heurística (0..~1.5) da qualidade de uma mão de até 3 cartas: pondera
    a carta mais forte, dá um peso menor às demais e bonifica manilhas."""
    if not cartas:
        return 0.0
    forcas = sorted((_forca_normalizada(c, modo) for c in cartas), reverse=True)
    manilhas = sum(1 for c in cartas if c in MANILHAS_POR_MODO[modo])
    base = forcas[0]
    extra = sum(forcas[1:]) * 0.4
    bonus_manilha = manilhas * 0.15
    return base + extra + bonus_manilha


def decidir_corte():
    """O contra-pé não tem nenhuma informação sobre como o baralho foi
    embaralhado: subir ou descer é, de fato, uma escolha arbitrária."""
    return random.choice(["SUBIR", "DESCER"])


def _forca_com_ruido(cartas, modo, config):
    """Ruído gaussiano na força "verdadeira" da mão antes de comparar com
    limiar: sozinho já quebra o determinismo das decisões de aposta (duas
    mãos de força quase igual podem decidir diferente, como a variação de
    humor/leitura de jogo de um humano). `avaliar_forca_mao` continua sendo
    a avaliação "verdadeira" — só a política de decisão é que fica
    probabilística."""
    return avaliar_forca_mao(cartas, modo) + random.gauss(0, config["sigma_ruido"])


def decidir_mao_10(minha_mao, modo, config=None):
    config = config or _CONFIG_PADRAO
    forca = _forca_com_ruido(minha_mao, modo, config)
    return "JOGAR" if forca >= config["limiar_mao_10"] else "CORRER"


def decidir_resposta_pedido(minha_mao, modo, pode_aumentar, config=None, ajuste_limiar_aceitar=0.0):
    """Decide a resposta a um TRUCO/AUMENTAR do adversário: aceitar, correr
    ou (se a mão estiver muito forte e ainda houver teto) reaumentar.

    `ajuste_limiar_aceitar`: deslocamento (pra baixo) do limiar de aceitar,
    vindo da modelagem do adversário em `cliente_bot.py` — equipe que
    historicamente pede e depois perde a mão (sinal fraco de blefe, ver
    `ClienteBot._taxa_blefe_estimada`) passa a ser mais "chamada".
    """
    config = config or _CONFIG_PADRAO
    forca = _forca_com_ruido(minha_mao, modo, config)
    if pode_aumentar and forca >= config["limiar_aumentar"]:
        return "AUMENTAR"
    if forca >= config["limiar_aceitar"] - ajuste_limiar_aceitar:
        return "ACEITAR"
    return "CORRER"


def deve_chamar_truco(minha_mao, modo, config=None):
    config = config or _CONFIG_PADRAO
    forca_real = avaliar_forca_mao(minha_mao, modo)
    forca = forca_real + random.gauss(0, config["sigma_ruido"])
    if forca >= config["limiar_chamar_truco"]:
        return True
    # blefe deliberado: mão genuinamente fraca (não só "ruído desfavorável")
    # ainda assim chama truco com probabilidade fixa baixa — é o que
    # realmente simula blefe, não só ruído. Blefar sempre que a mão for
    # fraca seria um padrão aprendível por um humano; uma frequência baixa
    # e fixa é o que torna a estratégia não-explorável no longo prazo
    # (estratégia mista / equilíbrio de Nash em forma simplificada).
    mao_fraca = forca_real < config["limiar_chamar_truco"] - MARGEM_BLEFE
    return mao_fraca and random.random() < config["prob_blefe"]


# -- busca Minimax + Alfa-Beta sobre uma amostra (informação perfeita) ------


def _ordem_a_partir_de(jogadores, jogador):
    i = jogadores.index(jogador)
    return jogadores[i:] + jogadores[:i]


class _NoBusca:
    """Estado de uma simulação: quem tem quais cartas, quem joga agora, o
    que já foi jogado na rodada em andamento e o resultado das rodadas já
    concluídas nesta mão (para alimentar `resolver_mao`)."""

    __slots__ = ("maos", "ordem", "vez_index", "cartas_rodada", "resultados")

    def __init__(self, maos, ordem, vez_index, cartas_rodada, resultados):
        self.maos = maos
        self.ordem = ordem
        self.vez_index = vez_index
        self.cartas_rodada = cartas_rodada
        self.resultados = resultados

    @property
    def jogador_da_vez(self):
        return self.ordem[self.vez_index]


def _aplicar_jogada(no, jogador, carta, equipe_de, modo):
    maos = dict(no.maos)
    maos[jogador] = [c for c in maos[jogador] if c != carta]
    cartas_rodada = no.cartas_rodada + [(jogador, carta)]
    vez_index = (no.vez_index + 1) % len(no.ordem)

    if len(cartas_rodada) < len(no.ordem):
        return _NoBusca(maos, no.ordem, vez_index, cartas_rodada, no.resultados)

    # rodada completa: decide quem venceu (mesma regra de server.game)
    melhor_por_equipe = {}
    for j, c in cartas_rodada:
        eq = equipe_de[j]
        f = forca_carta(c, modo)
        if eq not in melhor_por_equipe or f > melhor_por_equipe[eq][0]:
            melhor_por_equipe[eq] = (f, c)
    f0 = melhor_por_equipe.get(0, (-1, None))[0]
    f1 = melhor_por_equipe.get(1, (-1, None))[0]
    if f0 > f1:
        vencedor_rodada = 0
    elif f1 > f0:
        vencedor_rodada = 1
    else:
        vencedor_rodada = None

    resultados = no.resultados + [vencedor_rodada]
    if vencedor_rodada is not None:
        jogador_vencedor = next(j for j, _ in cartas_rodada if equipe_de[j] == vencedor_rodada)
        nova_ordem = _ordem_a_partir_de(no.ordem, jogador_vencedor)
    else:
        # empate: mantém quem já ia jogar (mesmo comportamento de Partida._finalizar_rodada)
        nova_ordem = no.ordem

    return _NoBusca(maos, nova_ordem, 0, [], resultados)


def _eval_heuristico(no, equipe_de, minha_equipe, modo):
    """Avaliação heurística (corte de profundidade) de um estado: não soma
    a força de todas as cartas de cada equipe — numa rodada só a carta mais
    forte da equipe compete de verdade, o resto é secundário. Mesma lógica
    de peso de `avaliar_forca_mao` (carta mais forte com peso total + resto
    com peso reduzido), só que aplicada por equipe em vez de por jogador —
    mantém a heurística de busca consistente com a heurística de apostas."""

    def valor_equipe(equipe):
        cartas = [c for j, mao in no.maos.items() if equipe_de[j] == equipe for c in mao]
        if not cartas:
            return 0.0
        forcas = sorted((_forca_normalizada(c, modo) for c in cartas), reverse=True)
        return forcas[0] + sum(forcas[1:]) * 0.4

    return valor_equipe(minha_equipe) - valor_equipe(1 - minha_equipe)


def _minimax(no, equipe_de, minha_equipe, modo, profundidade, alfa, beta):
    vencedor_mao = resolver_mao(no.resultados)
    if vencedor_mao is not None:
        return 1.0 if vencedor_mao == minha_equipe else -1.0
    if profundidade <= 0:
        return _eval_heuristico(no, equipe_de, minha_equipe, modo)

    jogador = no.jogador_da_vez
    maximizando = equipe_de[jogador] == minha_equipe
    # melhor jogada primeiro (carta mais forte) ajuda a poda Alfa-Beta a
    # cortar mais ramos, tanto em nós MAX quanto em nós MIN.
    cartas = sorted(no.maos[jogador], key=lambda c: forca_carta(c, modo), reverse=True)

    melhor = float("-inf") if maximizando else float("inf")
    for carta in cartas:
        novo_no = _aplicar_jogada(no, jogador, carta, equipe_de, modo)
        valor = _minimax(novo_no, equipe_de, minha_equipe, modo, profundidade - 1, alfa, beta)
        if maximizando:
            melhor = max(melhor, valor)
            alfa = max(alfa, melhor)
        else:
            melhor = min(melhor, valor)
            beta = min(beta, melhor)
        if alfa >= beta:
            break  # poda: o resto dos ramos não pode mudar a decisão do nó pai
    return melhor


def _sortear_maos_desconhecidas(cartas_desconhecidas, jogadores, tamanhos):
    baralho = list(cartas_desconhecidas)
    random.shuffle(baralho)
    maos = {}
    for jogador in jogadores:
        n = tamanhos[jogador]
        maos[jogador] = [baralho.pop() for _ in range(n)]
    return maos


def escolher_carta(
    minha_mao,
    meu_nickname,
    jogadores,
    equipe_de,
    modo,
    jogadas_completas_na_mao,
    cartas_rodada_atual,
    resultados_rodadas_concluidas,
    maos_conhecidas=None,
    config=None,
):
    """Escolhe a carta da minha mão com melhor valor médio via Minimax +
    Alfa-Beta sobre várias determinizações das mãos adversárias.

    `jogadas_completas_na_mao`: dict nickname -> lista de cartas que esse
    jogador já jogou em rodadas já CONCLUÍDAS nesta mão (não inclui a
    rodada em andamento).
    `cartas_rodada_atual`: lista [(nickname, carta), ...] já jogados na
    rodada em andamento, na ordem em que foram jogados.
    `resultados_rodadas_concluidas`: lista de 0/1/None, uma entrada por
    rodada já concluída nesta mão (mesmo formato de `Partida.resultados_rodadas`)
    — precisa entrar na busca porque `resolver_mao` usa o resultado da
    *primeira* rodada da mão para desempate em caso de 3 rodadas empatadas.
    `maos_conhecidas`: dict nickname -> cartas restantes desse jogador,
    quando conhecidas com certeza (ex.: na mão de 10, quem é o
    jogador-vidente recebe a mão completa dos parceiros — ver
    `CARTAS_PARCEIROS` no protocolo). Esses jogadores entram fixos em toda
    determinização, sem sorteio, e suas cartas saem do conjunto de
    desconhecidas.
    `config`: preset de dificuldade (ver `DIFICULDADES`); controla só
    `amostras`/`profundidade_maxima` aqui (os limiares de aposta não se
    aplicam à escolha de carta).
    """
    if len(minha_mao) == 1:
        return minha_mao[0]

    config = config or _CONFIG_PADRAO
    maos_conhecidas = maos_conhecidas or {}
    minha_equipe = equipe_de[meu_nickname]
    outros = [j for j in jogadores if j != meu_nickname]
    outros_para_sortear = [j for j in outros if j not in maos_conhecidas]

    jogadas_nesta_rodada = {}
    for nick, carta in cartas_rodada_atual:
        jogadas_nesta_rodada.setdefault(nick, []).append(carta)

    conhecidas = set(minha_mao)
    for cartas in jogadas_completas_na_mao.values():
        conhecidas.update(cartas)
    for cartas in jogadas_nesta_rodada.values():
        conhecidas.update(cartas)
    for cartas in maos_conhecidas.values():
        conhecidas.update(cartas)

    baralho = montar_baralho(modo)
    desconhecidas = [c for c in baralho if c not in conhecidas]

    tamanhos = {
        j: 3 - len(jogadas_completas_na_mao.get(j, [])) - len(jogadas_nesta_rodada.get(j, []))
        for j in outros_para_sortear
    }

    lider = cartas_rodada_atual[0][0] if cartas_rodada_atual else meu_nickname
    ordem = _ordem_a_partir_de(jogadores, lider)
    vez_index = len(cartas_rodada_atual)

    pontuacao = {carta: 0.0 for carta in minha_mao}
    amostras_validas = 0
    tentativas = 0
    amostras = config["amostras"]
    while amostras_validas < amostras and tentativas < amostras * 3:
        tentativas += 1
        if sum(tamanhos.values()) != len(desconhecidas):
            break  # estado inconsistente (não deveria ocorrer); evita sortear errado

        maos = _sortear_maos_desconhecidas(desconhecidas, outros_para_sortear, tamanhos)
        for nick, cartas in maos_conhecidas.items():
            maos[nick] = list(cartas)
        maos[meu_nickname] = list(minha_mao)
        no_raiz = _NoBusca(maos, ordem, vez_index, list(cartas_rodada_atual), list(resultados_rodadas_concluidas))

        total_restante = sum(len(c) for c in maos.values()) - len(cartas_rodada_atual)
        profundidade = min(config["profundidade_maxima"], total_restante)

        for carta in minha_mao:
            novo_no = _aplicar_jogada(no_raiz, meu_nickname, carta, equipe_de, modo)
            valor = _minimax(novo_no, equipe_de, minha_equipe, modo, profundidade - 1, float("-inf"), float("inf"))
            pontuacao[carta] += valor
        amostras_validas += 1

    if amostras_validas == 0:
        return max(minha_mao, key=lambda c: forca_carta(c, modo))

    return max(pontuacao, key=pontuacao.get)
