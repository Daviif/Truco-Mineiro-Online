"""Gerência de mesas (salas) de truco: criação, fila de espera e busca."""

import threading

from common import constants
from server.game import Partida

AGUARDANDO = "AGUARDANDO"
EM_ANDAMENTO = "EM_ANDAMENTO"
INTERROMPIDA = "INTERROMPIDA"


class Mesa:
    """Uma mesa de truco para um modo (2/4/6/8 jogadores).

    `lock` deve ser adquirido por quem for chamar métodos de `partida`
    (jogar_carta, chamar_truco, aceitar, correr, aumentar), já que threads de
    clientes diferentes podem agir sobre a mesma mesa concorrentemente.
    """

    def __init__(self, id_mesa, modo):
        self.id = id_mesa
        self.modo = modo
        self.jogadores = []  # nicknames, na ordem de entrada == posição na mesa
        self.partida = None
        self.status = AGUARDANDO
        self.lock = threading.Lock()

    @property
    def cheia(self):
        return len(self.jogadores) == self.modo

    def adicionar(self, nickname):
        if self.cheia:
            raise ValueError(constants.ERRO_MESA_CHEIA)
        self.jogadores.append(nickname)
        if self.cheia:
            self._iniciar_partida()

    def _iniciar_partida(self):
        # equipes se alternam pela posição na mesa: 0,1,0,1,... (parceiros
        # ficam em posições opostas na mesa, como na disposição tradicional).
        equipe_de = {jogador: posicao % 2 for posicao, jogador in enumerate(self.jogadores)}
        self.partida = Partida(self.modo, list(self.jogadores), equipe_de)
        self.status = EM_ANDAMENTO

    def remover(self, nickname):
        if nickname in self.jogadores:
            self.jogadores.remove(nickname)
        if self.status == EM_ANDAMENTO:
            self.status = INTERROMPIDA

    def resumo(self):
        return {
            "id": self.id,
            "modo": self.modo,
            "jogadores": list(self.jogadores),
            "status": self.status,
        }


class RoomManager:
    """Registro central de todas as mesas ativas no servidor."""

    def __init__(self):
        self._lock = threading.Lock()
        self._mesas = {}
        self._proximo_id = 1

    def listar(self):
        with self._lock:
            return [mesa.resumo() for mesa in self._mesas.values()]

    def entrar(self, modo, nickname):
        """Coloca o jogador em uma mesa aguardando daquele modo, ou cria uma nova."""
        if modo not in constants.MODOS_SUPORTADOS:
            raise ValueError(constants.ERRO_MODO_INVALIDO)
        with self._lock:
            for mesa in self._mesas.values():
                if mesa.modo == modo and mesa.status == AGUARDANDO and not mesa.cheia:
                    mesa.adicionar(nickname)
                    return mesa
            mesa = Mesa(self._proximo_id, modo)
            self._proximo_id += 1
            self._mesas[mesa.id] = mesa
            mesa.adicionar(nickname)
            return mesa

    def mesa_do_jogador(self, nickname):
        with self._lock:
            for mesa in self._mesas.values():
                if nickname in mesa.jogadores:
                    return mesa
            return None

    def remover_jogador(self, nickname):
        """Remove o jogador de sua mesa (se houver). Retorna a mesa afetada."""
        with self._lock:
            for mesa in self._mesas.values():
                if nickname in mesa.jogadores:
                    mesa.remover(nickname)
                    return mesa
            return None
