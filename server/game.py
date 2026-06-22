"""Motor de regras do Truco Mineiro: baralho, manilhas, comparação de cartas,
resolução de rodadas/mãos e placar.

Não depende de rede — é usado pelo servidor para ser a única fonte de
verdade do estado da partida.
"""

import random

from common import constants

NAIPES = ("P", "C", "E", "O")  # Paus, Copas, Espadas, Ouros
RANKS_BASE = ("A", "2", "3", "4", "5", "6", "7", "Q", "J", "K")

# Sequência tradicional (cartas não-manilha), da mais forte para a mais fraca.
SEQUENCIA = ("3", "2", "A", "K", "J", "Q", "7", "6", "5", "4")

# Manilhas fixas por modo (mais forte -> mais fraca), conforme a proposta.
MANILHAS_POR_MODO = {
    2: ("4P", "7C", "AE", "7O"),
    4: ("4P", "7C", "AE", "7O"),
    6: ("JK1", "JK2", "10O", "7P", "4E", "4P", "7C", "AE", "7O"),
    8: ("JK1", "JK2", "10O", "9O", "8O", "7P", "4E", "4P", "7C", "AE", "7O"),
}

# Cartas extras por modo, além do baralho tradicional de 40 cartas.
CARTAS_EXTRAS_POR_MODO = {
    2: (),
    4: (),
    6: ("JK1", "JK2", "10O"),
    8: ("JK1", "JK2", "10O", "9O", "8O"),
}

CARTAS_POR_JOGADOR = 3
RODADAS_POR_MAO = 3

# Escalação de apostas: TRUCO sempre pede o primeiro nível; AUMENTAR avança
# para o próximo nível da lista.
ESCALACAO = (
    constants.VALOR_TRUCO,
    constants.VALOR_SEIS,
    constants.VALOR_NOVE,
    constants.VALOR_DOZE,
)


def montar_baralho(modo):
    """Monta o baralho completo (lista de códigos de carta) para o modo dado."""
    baralho = [rank + naipe for rank in RANKS_BASE for naipe in NAIPES]
    baralho.extend(CARTAS_EXTRAS_POR_MODO[modo])
    return baralho


def rank_de(carta):
    """Retorna o rank de uma carta, ex: '4P' -> '4', '10O' -> '10'."""
    if carta.startswith("JK"):
        return carta
    return carta[:-1]


def naipe_de(carta):
    if carta.startswith("JK"):
        return None
    return carta[-1]


def forca_carta(carta, modo):
    """Retorna a força da carta no modo dado (maior valor = carta mais forte).

    Manilhas sempre vencem cartas não-manilha. Entre não-manilhas, a força
    segue a sequência tradicional; cartas de mesmo rank (naipes diferentes)
    têm a mesma força e empatam a rodada.
    """
    manilhas = MANILHAS_POR_MODO[modo]
    if carta in manilhas:
        return 1000 + (len(manilhas) - manilhas.index(carta))
    rank = rank_de(carta)
    if rank not in SEQUENCIA:
        raise ValueError(f"carta desconhecida: {carta}")
    return 100 + (len(SEQUENCIA) - SEQUENCIA.index(rank))


def comparar_cartas(carta_a, carta_b, modo):
    """Compara duas cartas: retorna 1 se a > b, -1 se b > a, 0 se empate."""
    fa, fb = forca_carta(carta_a, modo), forca_carta(carta_b, modo)
    if fa > fb:
        return 1
    if fb > fa:
        return -1
    return 0


def resolver_mao(resultados):
    """Decide a equipe vencedora da mão a partir dos resultados das rodadas.

    `resultados` é uma lista de até 3 itens, cada um 0 (equipe 0 venceu a
    rodada), 1 (equipe 1 venceu) ou None (rodada empatada). Retorna 0 ou 1
    se a mão já está decidida, ou None se ainda são necessárias mais rodadas.
    """
    if len(resultados) < 2:
        return None

    primeiro, segundo = resultados[0], resultados[1]

    if primeiro is not None and primeiro == segundo:
        return primeiro
    if primeiro is not None and segundo is None:
        return primeiro
    if primeiro is None and segundo is not None:
        return segundo

    if len(resultados) < 3:
        return None

    terceiro = resultados[2]
    if terceiro is not None:
        return terceiro
    if primeiro is not None:
        return primeiro
    # As três rodadas empataram: por convenção, quem jogou primeiro na
    # primeira rodada (equipe 0, "mão") vence.
    return 0


class ErroJogo(Exception):
    """Erro de regra do jogo (jogada inválida, fora de turno, etc.)."""

    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


# Fases pelas quais uma mão passa antes/durante o jogo das cartas.
FASE_DECISAO_MAO_10 = "DECISAO_MAO_10"
FASE_CORTE = "CORTE"
FASE_JOGANDO = "JOGANDO"

class Partida:
    """Estado completo de uma partida de truco em uma mesa.

    `jogadores` é a lista de nicknames na ordem física da mesa (fixa durante
    toda a partida). `equipe_de` mapeia cada nickname à sua equipe (0 ou 1).
    Para 2 jogadores, cada jogador é a sua própria equipe (0 e 1); para
    4/6/8, jogadores se alternam entre as equipes 0 e 1 conforme a posição.

    A cada mão o baralho passa para o jogador à direita: ele se torna o
    novo "pé" (quem embaralha e dá as cartas). O "contra-pé" (jogador antes
    do pé) corta o baralho antes de cada distribuição; o "mão" (jogador
    depois do pé) é quem joga primeiro em cada mão.
    """

    def __init__(self, modo, jogadores, equipe_de):
        self.modo = modo
        self.jogadores = list(jogadores)
        self.equipe_de = dict(equipe_de)
        self.placar = {0: 0, 1: 0}
        self.indice_pe = 0
        self.vencedor_partida = None
        self._preparar_nova_mao()

    # -- papéis (pé / mão / contra-pé) --------------------------------------

    @property
    def indice_mao(self):
        return (self.indice_pe + 1) % len(self.jogadores)

    @property
    def indice_contra_pe(self):
        return (self.indice_pe - 1) % len(self.jogadores)

    @property
    def pe(self):
        return self.jogadores[self.indice_pe]

    @property
    def mao(self):
        return self.jogadores[self.indice_mao]

    @property
    def contra_pe(self):
        return self.jogadores[self.indice_contra_pe]

    @property
    def jogador_vidente_mao_10(self):
        """Na mão de 10, quem pode ver as cartas dos parceiros: o "mão" se
        ele for da equipe decisora, senão o próximo jogador (em ordem de
        assento) da equipe decisora depois do "mão" — sempre existe e é
        único, já que as equipes se alternam a cada assento. Em 2 jogadores
        cada um é sua própria equipe (sem parceiros), então não se aplica."""
        if not self.eh_mao_de_10 or len(self.jogadores) < 4:
            return None
        idx_mao = self.indice_mao
        jogador_mao = self.jogadores[idx_mao]
        if self.equipe_de[jogador_mao] == self.equipe_mao_10:
            return jogador_mao
        return self.jogadores[(idx_mao + 1) % len(self.jogadores)]

    # -- gerência de mãos -------------------------------------------------

    def _preparar_nova_mao(self):
        """Prepara uma nova mão: zera o estado de rodada e já manda pra fase
        de corte — o corte e a distribuição acontecem sempre primeiro, até
        na mão de 10/ferro. Na mão de 10, é só depois de já ver a própria
        mão (e, pra quem tem direito, a dos parceiros) que a equipe decide
        jogar ou correr (ver `_distribuir_cartas`/`decidir_mao_10`)."""
        self.mao_de = {jogador: [] for jogador in self.jogadores}
        self.ordem_atual = None
        self.vez_index = 0
        self.rodada_atual = 0
        self.cartas_rodada = []
        self.resultados_rodadas = []
        self.valor_mao = constants.VALOR_INICIAL
        self.pedido_pendente = None
        # equipe cuja proposta está em vigor (a última que teve um pedido de
        # aposta aceito); só a outra equipe pode pedir para aumentar de novo,
        # e pode fazê-lo em qualquer momento da mão, não só na hora do pedido.
        self.equipe_apostou = None
        self.mao_finalizada = False
        self._baralho_pendente = None

        self.eh_mao_de_ferro = False
        self.eh_mao_de_10 = False
        self.equipe_mao_10 = None
        self.bloqueio_truco = False

        equipes_em_especial = [eq for eq, pts in self.placar.items() if pts >= constants.PONTUACAO_MAO_ESPECIAL]
        if len(equipes_em_especial) == 2:
            self.eh_mao_de_ferro = True
            self.bloqueio_truco = True
        elif len(equipes_em_especial) == 1:
            self.eh_mao_de_10 = True
            self.bloqueio_truco = True
            self.equipe_mao_10 = equipes_em_especial[0]

        self.fase = FASE_CORTE
        self._preparar_baralho()

    def _preparar_baralho(self):
        baralho = montar_baralho(self.modo)
        random.shuffle(baralho)
        self._baralho_pendente = baralho

    def decidir_mao_10(self, nickname, decisao):
        if self.fase != FASE_DECISAO_MAO_10:
            raise ErroJogo(constants.ERRO_FASE_INVALIDA)
        equipe = self.equipe_de[nickname]
        if equipe != self.equipe_mao_10:
            raise ErroJogo(constants.ERRO_NAO_E_EQUIPE_DECISORA)

        if decisao == constants.DECISAO_CORRER:
            equipe_vencedora = 1 - self.equipe_mao_10
            self._finalizar_mao(equipe_vencedora, constants.VALOR_MAO_DE_10_CORRER)
            return {
                "vencedor_mao": equipe_vencedora,
                "placar": dict(self.placar),
                "fim_partida": self.vencedor_partida,
            }
        if decisao == constants.DECISAO_JOGAR:
            # as cartas já foram distribuídas (ver `_distribuir_cartas`) —
            # só falta liberar a jogada normal.
            self.fase = FASE_JOGANDO
            return None
        raise ErroJogo(constants.ERRO_MENSAGEM_INVALIDA)

    def cortar(self, nickname, direcao):
        if self.fase != FASE_CORTE:
            raise ErroJogo(constants.ERRO_FASE_INVALIDA)
        if nickname != self.contra_pe:
            raise ErroJogo(constants.ERRO_NAO_E_CONTRAPE)
        baralho = self._baralho_pendente
        if direcao == constants.CORTE_SUBIR:
            baralho = list(reversed(baralho))
        elif direcao != constants.CORTE_DESCER:
            raise ErroJogo(constants.ERRO_MENSAGEM_INVALIDA)
        self._distribuir_cartas(baralho)

    def _distribuir_cartas(self, baralho):
        ordem = self.jogadores[self.indice_mao:] + self.jogadores[: self.indice_mao]
        for jogador in ordem:
            self.mao_de[jogador] = [baralho.pop() for _ in range(CARTAS_POR_JOGADOR)]
        self.ordem_atual = ordem
        self.vez_index = 0
        # na mão de 10, a equipe só decide jogar/correr depois de já ver as
        # cartas (a sua e, quem tem direito, a dos parceiros) — joga só
        # libera de verdade quando `decidir_mao_10` escolhe "jogar".
        self.fase = FASE_DECISAO_MAO_10 if self.eh_mao_de_10 else FASE_JOGANDO
        self._baralho_pendente = None

    @property
    def jogador_da_vez(self):
        return self.ordem_atual[self.vez_index]

    def _proxima_vez(self):
        self.vez_index = (self.vez_index + 1) % len(self.ordem_atual)

    # -- jogadas ------------------------------------------------------------

    def jogar_carta(self, nickname, carta_ou_posicao):
        if self.vencedor_partida is not None:
            raise ErroJogo(constants.ERRO_PARTIDA_FINALIZADA)
        if self.fase != FASE_JOGANDO:
            raise ErroJogo(constants.ERRO_FASE_INVALIDA)
        if self.pedido_pendente is not None:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        if nickname != self.jogador_da_vez:
            raise ErroJogo(constants.ERRO_FORA_DE_TURNO)

        mao = self.mao_de[nickname]
        if self.eh_mao_de_ferro:
            # cartas viradas para baixo: o jogador escolhe pela posição
            # (1, 2 ou 3), não pelo código da carta, já que nem ele sabe o
            # que tem até revelar.
            try:
                posicao = int(carta_ou_posicao)
            except (TypeError, ValueError):
                raise ErroJogo(constants.ERRO_CARTA_INVALIDA)
            if posicao < 1 or posicao > len(mao):
                raise ErroJogo(constants.ERRO_CARTA_INVALIDA)
            carta = mao.pop(posicao - 1)
        else:
            carta = carta_ou_posicao
            if carta not in mao:
                raise ErroJogo(constants.ERRO_CARTA_INVALIDA)
            mao.remove(carta)

        self.cartas_rodada.append((nickname, carta))
        self._proxima_vez()

        resultado_rodada = None
        if len(self.cartas_rodada) == len(self.jogadores):
            resultado_rodada = self._finalizar_rodada()
        return resultado_rodada

    def _finalizar_rodada(self):
        melhor_por_equipe = {}
        for jogador, carta in self.cartas_rodada:
            equipe = self.equipe_de[jogador]
            forca = forca_carta(carta, self.modo)
            if equipe not in melhor_por_equipe or forca > melhor_por_equipe[equipe][0]:
                melhor_por_equipe[equipe] = (forca, carta)

        forca0 = melhor_por_equipe.get(0, (-1, None))[0]
        forca1 = melhor_por_equipe.get(1, (-1, None))[0]
        if forca0 > forca1:
            vencedor_rodada = 0
        elif forca1 > forca0:
            vencedor_rodada = 1
        else:
            vencedor_rodada = None

        self.resultados_rodadas.append(vencedor_rodada)
        cartas_da_rodada = list(self.cartas_rodada)
        self.cartas_rodada = []
        self.rodada_atual += 1

        vencedor_mao = resolver_mao(self.resultados_rodadas)
        if vencedor_mao is not None:
            self._finalizar_mao(vencedor_mao, self._valor_credito(vencedor_mao))
        elif self.rodada_atual < RODADAS_POR_MAO:
            # quem ganhou a rodada começa a próxima; em empate, mantém quem já ia jogar
            if vencedor_rodada is not None:
                jogador_vencedor = next(
                    j for j, _ in cartas_da_rodada if self.equipe_de[j] == vencedor_rodada
                )
                self.ordem_atual = self._ordem_a_partir_de(jogador_vencedor)
                self.vez_index = 0

        return {
            "vencedor_rodada": vencedor_rodada,
            "cartas": cartas_da_rodada,
            "vencedor_mao": vencedor_mao,
            "placar": dict(self.placar),
            "fim_partida": self.vencedor_partida if vencedor_mao is not None else None,
        }

    def _ordem_a_partir_de(self, jogador):
        i = self.jogadores.index(jogador)
        return self.jogadores[i:] + self.jogadores[:i]

    def _valor_credito(self, equipe_vencedora):
        """Valor em pontos da mão atual para a equipe vencedora.

        Na mão de 10, se a equipe que estava com 10+ pontos jogar e perder,
        a equipe adversária ganha um valor maior (4) do que o normal.
        """
        if self.eh_mao_de_10 and equipe_vencedora != self.equipe_mao_10:
            return constants.VALOR_MAO_DE_10_DERROTA
        return self.valor_mao

    def _finalizar_mao(self, equipe_vencedora, valor):
        self.placar[equipe_vencedora] += valor
        self.mao_finalizada = True
        if self.placar[equipe_vencedora] >= constants.PONTUACAO_VITORIA:
            self.vencedor_partida = equipe_vencedora
        else:
            self.indice_pe = (self.indice_pe + 1) % len(self.jogadores)
            self._preparar_nova_mao()

    # -- apostas --------------------------------------------------------------

    def chamar_truco(self, nickname):
        """Pede para a mão valer o próximo nível da escalação.

        Não precisa ser logo em seguida do pedido anterior: depois que uma
        equipe aceita um truco, a equipe adversária pode pedir para aumentar
        de novo em qualquer momento da mesma mão (ex: aceitou o truco na
        1ª rodada, pede seis na 3ª). Só não pode ser a mesma equipe que já
        está com a proposta em vigor — essa precisa esperar a adversária
        responder antes de poder pedir de novo.
        """
        if self.bloqueio_truco:
            raise ErroJogo(constants.ERRO_TRUCO_BLOQUEADO)
        if self.fase != FASE_JOGANDO:
            raise ErroJogo(constants.ERRO_FASE_INVALIDA)
        if nickname != self.jogador_da_vez:
            raise ErroJogo(constants.ERRO_FORA_DE_TURNO)
        if self.pedido_pendente is not None:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        equipe_solicitante = self.equipe_de[nickname]
        if self.equipe_apostou == equipe_solicitante:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        if self.valor_mao == constants.VALOR_INICIAL:
            proximo_valor = ESCALACAO[0]
        else:
            try:
                indice_atual = ESCALACAO.index(self.valor_mao)
            except ValueError:
                raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
            if indice_atual + 1 >= len(ESCALACAO):
                raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
            proximo_valor = ESCALACAO[indice_atual + 1]
        self._abrir_pedido(nickname, proximo_valor)

    def aumentar(self, nickname):
        if self.pedido_pendente is None:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        equipe_solicitante = self.equipe_de[nickname]
        if equipe_solicitante == self.pedido_pendente["equipe_solicitante"]:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        valor_pendente = self.pedido_pendente["valor_pedido"]
        try:
            indice_atual = ESCALACAO.index(valor_pendente)
        except ValueError:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        if indice_atual + 1 >= len(ESCALACAO):
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        # reaumentar aceita implicitamente o valor que estava pendente antes de pedir mais
        self.valor_mao = valor_pendente
        self.pedido_pendente = None
        self._abrir_pedido(nickname, ESCALACAO[indice_atual + 1])

    def _abrir_pedido(self, nickname, novo_valor):
        if self.vencedor_partida is not None:
            raise ErroJogo(constants.ERRO_PARTIDA_FINALIZADA)
        equipe_solicitante = self.equipe_de[nickname]
        if self.pedido_pendente is not None and self.pedido_pendente["equipe_solicitante"] == equipe_solicitante:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        self.pedido_pendente = {
            "equipe_solicitante": equipe_solicitante,
            "valor_anterior": self.valor_mao,
            "valor_pedido": novo_valor,
        }

    def aceitar(self, nickname):
        if self.pedido_pendente is None:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        equipe = self.equipe_de[nickname]
        if equipe == self.pedido_pendente["equipe_solicitante"]:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        self.valor_mao = self.pedido_pendente["valor_pedido"]
        self.equipe_apostou = self.pedido_pendente["equipe_solicitante"]
        self.pedido_pendente = None

    def correr(self, nickname):
        if self.pedido_pendente is None:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        equipe = self.equipe_de[nickname]
        if equipe == self.pedido_pendente["equipe_solicitante"]:
            raise ErroJogo(constants.ERRO_APOSTA_INVALIDA)
        equipe_vencedora = self.pedido_pendente["equipe_solicitante"]
        valor_ganho = self.pedido_pendente["valor_anterior"]
        self.pedido_pendente = None
        self._finalizar_mao(equipe_vencedora, valor_ganho)
        return {
            "vencedor_mao": equipe_vencedora,
            "placar": dict(self.placar),
            "fim_partida": self.vencedor_partida,
        }
