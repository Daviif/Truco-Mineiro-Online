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

# Quantas determinizações (sorteios das mãos adversárias) resolver por
# decisão. Mais amostras => decisão mais robusta, porém mais lenta.
AMOSTRAS_DETERMINIZACAO = 24

# Profundidade máxima da busca Minimax dentro de cada amostra, em número de
# jogadas (cartas postas na mesa). Acima disso, usa-se a heurística _eval.
PROFUNDIDADE_MAXIMA = 10

# Limiares (0..~1.5) da heurística de força de mão, usados nas decisões de
# aposta (não passam pela busca: avaliar o comportamento de aposta do
# adversário exigiria modelar a estratégia dele, fora do escopo do curso).
LIMIAR_CHAMAR_TRUCO = 0.78
LIMIAR_AUMENTAR = 0.88
LIMIAR_ACEITAR = 0.55
LIMIAR_JOGAR_MAO_10 = 0.60


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


def decidir_mao_10(minha_mao, modo):
    return "JOGAR" if avaliar_forca_mao(minha_mao, modo) >= LIMIAR_JOGAR_MAO_10 else "CORRER"


def decidir_resposta_pedido(minha_mao, modo, pode_aumentar):
    """Decide a resposta a um TRUCO/AUMENTAR do adversário: aceitar, correr
    ou (se a mão estiver muito forte e ainda houver teto) reaumentar."""
    forca = avaliar_forca_mao(minha_mao, modo)
    if pode_aumentar and forca >= LIMIAR_AUMENTAR:
        return "AUMENTAR"
    if forca >= LIMIAR_ACEITAR:
        return "ACEITAR"
    return "CORRER"


def deve_chamar_truco(minha_mao, modo):
    return avaliar_forca_mao(minha_mao, modo) >= LIMIAR_CHAMAR_TRUCO


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
    soma_minha = sum(
        _forca_normalizada(c, modo) for j, cartas in no.maos.items() if equipe_de[j] == minha_equipe for c in cartas
    )
    soma_adversaria = sum(
        _forca_normalizada(c, modo) for j, cartas in no.maos.items() if equipe_de[j] != minha_equipe for c in cartas
    )
    return soma_minha - soma_adversaria


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
    """
    if len(minha_mao) == 1:
        return minha_mao[0]

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
    while amostras_validas < AMOSTRAS_DETERMINIZACAO and tentativas < AMOSTRAS_DETERMINIZACAO * 3:
        tentativas += 1
        if sum(tamanhos.values()) != len(desconhecidas):
            break  # estado inconsistente (não deveria ocorrer); evita sortear errado

        maos = _sortear_maos_desconhecidas(desconhecidas, outros_para_sortear, tamanhos)
        for nick, cartas in maos_conhecidas.items():
            maos[nick] = list(cartas)
        maos[meu_nickname] = list(minha_mao)
        no_raiz = _NoBusca(maos, ordem, vez_index, list(cartas_rodada_atual), list(resultados_rodadas_concluidas))

        total_restante = sum(len(c) for c in maos.values()) - len(cartas_rodada_atual)
        profundidade = min(PROFUNDIDADE_MAXIMA, total_restante)

        for carta in minha_mao:
            novo_no = _aplicar_jogada(no_raiz, meu_nickname, carta, equipe_de, modo)
            valor = _minimax(novo_no, equipe_de, minha_equipe, modo, profundidade - 1, float("-inf"), float("inf"))
            pontuacao[carta] += valor
        amostras_validas += 1

    if amostras_validas == 0:
        return max(minha_mao, key=lambda c: forca_carta(c, modo))

    return max(pontuacao, key=pontuacao.get)
