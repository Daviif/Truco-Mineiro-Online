"""Servidor central do Truco Mineiro: aceita conexões TCP simultâneas,
registra jogadores por nickname e mantém a mesa/estado de jogo de cada um."""

import os
import socket
import sys
import threading

if __name__ == "__main__":
    # permite rodar com `python3 server/server.py` sem instalar o pacote
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import contas
from server.client_session import ClientSession
from server.room_manager import RoomManager

HOST_PADRAO = "0.0.0.0"
PORTA_PADRAO = 5000


class Servidor:
    """Registro central de sessões de cliente conectadas e das mesas."""

    def __init__(self, host=HOST_PADRAO, porta=PORTA_PADRAO):
        self.host = host
        self.porta = porta
        self.room_manager = RoomManager()
        self.contas = contas.ContasRepositorio()
        self._sessoes = {}  # nickname -> ClientSession
        self._lock = threading.Lock()

    def registrar(self, nickname, sessao):
        """Registra um nickname novo. Retorna False se já estiver em uso."""
        with self._lock:
            if nickname in self._sessoes:
                return False
            self._sessoes[nickname] = sessao
            return True

    def remover(self, nickname):
        with self._lock:
            self._sessoes.pop(nickname, None)

    def enviar_para(self, nickname, tipo, *campos):
        with self._lock:
            sessao = self._sessoes.get(nickname)
        if sessao is not None:
            sessao.enviar(tipo, *campos)

    def desconectar_forcado(self, nickname):
        """Fecha a conexão de um jogador à força (usado pra desligar bots
        que sobraram numa mesa sem nenhum humano — sem humano pra jogar
        contra, a própria sessão do bot encerra o processo dele)."""
        with self._lock:
            sessao = self._sessoes.get(nickname)
        if sessao is not None:
            sessao.fechar()

    def executar(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor_socket:
            servidor_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            servidor_socket.bind((self.host, self.porta))
            servidor_socket.listen()
            print(f"Servidor de Truco Mineiro escutando em {self.host}:{self.porta}")
            try:
                while True:
                    conn, endereco = servidor_socket.accept()
                    sessao = ClientSession(conn, endereco, self)
                    thread = threading.Thread(target=sessao.executar, daemon=True)
                    thread.start()
            except KeyboardInterrupt:
                print("\nServidor encerrado.")


def main():
    porta = PORTA_PADRAO
    if len(sys.argv) > 1:
        porta = int(sys.argv[1])
    Servidor(HOST_PADRAO, porta).executar()


if __name__ == "__main__":
    main()
