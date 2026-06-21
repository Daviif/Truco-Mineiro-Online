"""Bot do Truco Mineiro: um cliente TCP real (fala o mesmo protocolo de
common/protocol.py que o cli_client.py e o web_bridge.py), só que em vez de
um humano decidindo as jogadas, usa `bot.estrategia` (Minimax + Alfa-Beta
sobre determinizações, mais heurísticas de aposta) para jogar sozinho.

Uso: python3 bot/cliente_bot.py [host] [porta] [nickname] [modo]
"""

import os
import random
import socket
import sys
import threading

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import estrategia
from common import constants
from common.protocol import MessageReader, encode

HOST_PADRAO = "127.0.0.1"
PORTA_PADRAO = 5000
MODO_PADRAO = 2

# O bot decide instantaneamente, mas reagir sem nenhum atraso deixa o jogo
# ilegível para um humano na mesa (cartas e pedidos de truco "instantâneos").
# Toda ação do bot passa por este atraso artificial antes de ser enviada.
RETARDO_MIN_SEGUNDOS = 1.4
RETARDO_MAX_SEGUNDOS = 3.2


def _parse_cartas_csv(csv):
    if not csv:
        return []
    return [par.split(":") for par in csv.split(",")]


class ClienteBot:
    def __init__(self, host, porta, nickname, modo):
        self.nickname_desejado = nickname
        self.modo = modo
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, porta))
        self._reader = MessageReader()
        self._ativo = True

        self.nickname = None
        self.jogadores = []
        self.equipe_de = {}
        self.modo_real = None

        self.mao = []
        self.mao_de_ferro_ativa = False
        self.vez = None
        self.valor_mao = None
        self.pedido_pendente = None
        self.pedido_corte = None
        self.mao_especial = None
        self.placar = {0: 0, 1: 0}

        self.cartas_rodada_atual = []
        self.jogadas_completas_na_mao = {}
        self.resultados_rodadas_na_mao = []
        self.cartas_parceiros = {}

    # -- transporte ---------------------------------------------------------

    def enviar(self, tipo, *campos):
        try:
            self.sock.sendall(encode(tipo, *campos))
        except OSError:
            self._ativo = False

    def escutar(self):
        try:
            while self._ativo:
                dados = self.sock.recv(4096)
                if not dados:
                    self._log("Conexão encerrada pelo servidor.")
                    break
                for tipo, campos in self._reader.feed(dados):
                    self._processar(tipo, campos)
        except OSError:
            pass
        finally:
            self._ativo = False

    def fechar(self):
        self._ativo = False
        try:
            self.sock.close()
        except OSError:
            pass

    def _log(self, mensagem):
        nome = self.nickname or self.nickname_desejado
        print(f"[Bot {nome}] {mensagem}")

    def _agendar(self, callback):
        """Agenda `callback` para depois de um atraso aleatório, sem travar
        a thread que recebe mensagens do servidor (`escutar`/`_processar`):
        o atraso roda numa thread própria do `threading.Timer`, e o callback
        revalida o estado mais atual do bot antes de agir (pode já ter
        mudado entre o agendamento e a execução)."""
        atraso = random.uniform(RETARDO_MIN_SEGUNDOS, RETARDO_MAX_SEGUNDOS)
        threading.Timer(atraso, callback).start()

    # -- processamento de mensagens do servidor ------------------------------

    def _processar(self, tipo, campos):
        if tipo == constants.LOGIN_OK:
            self.nickname = campos[0]
            self._log("login efetuado. Entrando na mesa...")
            self.enviar(constants.ENTRAR_MESA, str(self.modo))
        elif tipo == constants.ERRO:
            self._log(f"erro do servidor: {campos[0]}")
        elif tipo == constants.MESA_STATUS:
            self._tratar_mesa_status(campos)
        elif tipo == constants.PAPEIS:
            self._tratar_papeis(campos)
        elif tipo == constants.PEDIDO_CORTE:
            self._tratar_pedido_corte(campos)
        elif tipo == constants.MAO_ESPECIAL:
            self._tratar_mao_especial(campos)
        elif tipo == constants.INICIO_PARTIDA:
            self._tratar_inicio_partida(campos)
        elif tipo == constants.CARTAS_PARCEIROS:
            self._tratar_cartas_parceiros(campos)
        elif tipo == constants.ESTADO_RODADA:
            self._tratar_estado_rodada(campos)
        elif tipo == constants.RESULTADO_RODADA:
            self._tratar_resultado_rodada(campos)
        elif tipo == constants.RESULTADO_MAO:
            self._tratar_resultado_mao(campos)
        elif tipo == constants.PEDIDO_TRUCO:
            self._tratar_pedido_truco(campos)
        elif tipo == constants.FIM_PARTIDA:
            self._log(f"FIM DE PARTIDA — equipe {campos[0]} venceu.")
        elif tipo == constants.JOGADOR_SAIU:
            self._log(f"jogador '{campos[0]}' saiu da mesa.")

    def _tratar_mesa_status(self, campos):
        id_mesa, status, jogadores_csv = campos
        self.jogadores = jogadores_csv.split(",") if jogadores_csv else []
        if status == "EM_ANDAMENTO" and self.jogadores:
            self.modo_real = len(self.jogadores)
            self.equipe_de = {j: i % 2 for i, j in enumerate(self.jogadores)}
            self._log(f"mesa {id_mesa} em andamento com {self.jogadores}.")

    def _tratar_papeis(self, campos):
        pe, mao_lider, contra_pe = campos
        # início de uma nova mão: zera o que foi visto na mão anterior.
        self.pedido_corte = None
        self.mao_especial = None
        self.mao_de_ferro_ativa = False
        self.jogadas_completas_na_mao = {}
        self.resultados_rodadas_na_mao = []
        self.cartas_rodada_atual = []
        self.cartas_parceiros = {}
        self._log(f"nova mão: pé={pe} mão={mao_lider} contra-pé={contra_pe}")

    def _tratar_pedido_corte(self, campos):
        self.pedido_corte = campos[0]
        if self.pedido_corte == self.nickname:
            self._agendar(self._executar_corte)

    def _executar_corte(self):
        if not self._ativo or self.pedido_corte != self.nickname:
            return
        direcao = estrategia.decidir_corte()
        self._log(f"cortando o baralho: {direcao}")
        self.enviar(constants.CORTAR, direcao)

    def _sou_responsavel_pela_equipe(self):
        """Em 4/6/8 jogadores, cada equipe tem mais de um jogador, e todos
        recebem o mesmo PEDIDO_TRUCO/MAO_ESPECIAL. Só um pode responder —
        senão o segundo chega atrasado e o servidor rejeita com
        APOSTA_INVALIDA/FASE_INVALIDA (o pedido já foi resolvido pelo
        primeiro). Cada bot decide, sem combinar com o time, que só quem tem
        a menor posição na mesa entre os companheiros responde."""
        minha_equipe = self.equipe_de.get(self.nickname)
        membros = [j for j in self.jogadores if self.equipe_de.get(j) == minha_equipe]
        return not membros or membros[0] == self.nickname

    def _tratar_mao_especial(self, campos):
        tipo_mao, equipe_decisora = campos
        self.mao_especial = {"tipo": tipo_mao, "equipe_decisora": equipe_decisora}
        self.mao_de_ferro_ativa = tipo_mao == constants.TIPO_MAO_DE_FERRO
        if (
            tipo_mao == constants.TIPO_MAO_DE_10
            and int(equipe_decisora) == self.equipe_de.get(self.nickname)
            and self._sou_responsavel_pela_equipe()
        ):
            self._agendar(self._executar_decisao_mao_10)

    def _executar_decisao_mao_10(self):
        if not self._ativo or self.mao_especial is None:
            return
        decisao = estrategia.decidir_mao_10(self.mao, self.modo_real)
        self._log(f"mão de 10 — decisão: {decisao}")
        self.enviar(constants.DECIDIR_MAO_10, decisao)

    def _tratar_inicio_partida(self, campos):
        mao_csv, vez, valor = campos
        self.mao = mao_csv.split(",") if mao_csv else []
        self.vez = vez
        self.valor_mao = valor
        self.pedido_pendente = None
        self.pedido_corte = None
        self.cartas_rodada_atual = []
        self._log(f"cartas distribuídas: {self.mao}")
        self._agir_se_for_minha_vez()

    def _tratar_cartas_parceiros(self, campos):
        texto = campos[0] if campos else ""
        self.cartas_parceiros = {}
        for item in texto.split("|") if texto else []:
            nick, cartas_csv = item.split(":", 1)
            self.cartas_parceiros[nick] = cartas_csv.split(",")
        self._log(f"vejo a mão dos parceiros: {self.cartas_parceiros}")

    def _maos_conhecidas_restantes(self):
        """Versão de `self.cartas_parceiros` com as cartas que esses
        parceiros já jogaram nesta mão removidas (a mensagem chega com a
        mão completa, no momento da distribuição)."""
        if not self.cartas_parceiros:
            return {}
        jogadas_nesta_rodada = {}
        for nick, carta in self.cartas_rodada_atual:
            jogadas_nesta_rodada.setdefault(nick, []).append(carta)
        resultado = {}
        for nick, cartas in self.cartas_parceiros.items():
            restante = list(cartas)
            for carta in self.jogadas_completas_na_mao.get(nick, []) + jogadas_nesta_rodada.get(nick, []):
                if carta in restante:
                    restante.remove(carta)
            resultado[nick] = restante
        return resultado

    def _tratar_estado_rodada(self, campos):
        vez, cartas_csv, valor = campos
        self.cartas_rodada_atual = _parse_cartas_csv(cartas_csv)
        self.vez = vez
        self.valor_mao = valor
        self.pedido_pendente = None
        self._agir_se_for_minha_vez()

    def _tratar_resultado_rodada(self, campos):
        cartas_csv, vencedor = campos
        for nick, carta in _parse_cartas_csv(cartas_csv):
            self.jogadas_completas_na_mao.setdefault(nick, []).append(carta)
        self.resultados_rodadas_na_mao.append(None if vencedor == "EMPATE" else int(vencedor))
        self.cartas_rodada_atual = []

    def _tratar_resultado_mao(self, campos):
        _vencedor, placar0, placar1 = campos
        self.placar = {0: int(placar0), 1: int(placar1)}

    def _tratar_pedido_truco(self, campos):
        equipe, valor = campos
        self.pedido_pendente = {"equipe": int(equipe), "valor": int(valor)}
        minha_equipe = self.equipe_de.get(self.nickname)
        if self.pedido_pendente["equipe"] != minha_equipe and self._sou_responsavel_pela_equipe():
            self._agendar(self._executar_resposta_pedido)

    def _executar_resposta_pedido(self):
        if not self._ativo or self.pedido_pendente is None:
            return
        valor = self.pedido_pendente["valor"]
        pode_aumentar = valor < constants.VALOR_DOZE
        decisao = estrategia.decidir_resposta_pedido(self.mao, self.modo_real, pode_aumentar)
        self._log(f"respondendo pedido de {valor}: {decisao}")
        if decisao == "ACEITAR":
            self.enviar(constants.ACEITAR)
        elif decisao == "AUMENTAR":
            self.enviar(constants.AUMENTAR)
        else:
            self.enviar(constants.CORRER)

    # -- minha vez de jogar ---------------------------------------------------

    def _agir_se_for_minha_vez(self):
        if self.vez != self.nickname:
            return
        if self.pedido_pendente is not None or self.pedido_corte is not None:
            return
        self._agendar(self._executar_minha_vez)

    def _executar_minha_vez(self):
        if not self._ativo or self.vez != self.nickname:
            return
        if self.pedido_pendente is not None or self.pedido_corte is not None:
            return

        if self.mao_de_ferro_ativa:
            # ninguém (nem eu) sabe o valor das próprias cartas: jogada às
            # cegas, por posição.
            posicao = random.randint(1, len(self.mao))
            self._log(f"mão de ferro: jogando carta às cegas na posição {posicao}")
            self.enviar(constants.JOGAR_CARTA, str(posicao))
            self.mao.pop(posicao - 1)
            return

        if (
            self.valor_mao == str(constants.VALOR_INICIAL)
            and self.mao_especial is None
            and estrategia.deve_chamar_truco(self.mao, self.modo_real)
        ):
            self._log(f"mão forte ({self.mao}) — chamando truco antes de jogar.")
            self.enviar(constants.TRUCO)
            return

        carta = estrategia.escolher_carta(
            self.mao,
            self.nickname,
            self.jogadores,
            self.equipe_de,
            self.modo_real,
            self.jogadas_completas_na_mao,
            self.cartas_rodada_atual,
            self.resultados_rodadas_na_mao,
            self._maos_conhecidas_restantes(),
        )
        self._log(f"jogando {carta} (mão atual: {self.mao})")
        self.enviar(constants.JOGAR_CARTA, carta)
        self.mao.remove(carta)


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_PADRAO
    porta = int(sys.argv[2]) if len(sys.argv) > 2 else PORTA_PADRAO
    nickname = sys.argv[3] if len(sys.argv) > 3 else f"Bot{random.randint(100, 999)}"
    modo = int(sys.argv[4]) if len(sys.argv) > 4 else MODO_PADRAO

    bot = ClienteBot(host, porta, nickname, modo)
    thread = threading.Thread(target=bot.escutar, daemon=True)
    thread.start()

    bot.enviar(constants.LOGIN, nickname)
    print(f"[Bot {nickname}] conectado a {host}:{porta}, pedindo mesa de {modo} jogadores.")

    try:
        while thread.is_alive():
            thread.join(timeout=1.0)
    except KeyboardInterrupt:
        pass
    finally:
        bot.fechar()


if __name__ == "__main__":
    main()
