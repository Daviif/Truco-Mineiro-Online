"""Bot do Truco Mineiro: um cliente TCP real (fala o mesmo protocolo de
common/protocol.py que o cli_client.py e o web_bridge.py), só que em vez de
um humano decidindo as jogadas, usa `bot.estrategia` (Minimax + Alfa-Beta
sobre determinizações, mais heurísticas de aposta) para jogar sozinho.

Uso: python3 bot/cliente_bot.py [host] [porta] [nickname] [modo] [dificuldade]

`dificuldade` é opcional (`FACIL`, `MEDIO` ou `DIFICIL`, padrão `MEDIO` — ver
`bot.estrategia.DIFICULDADES`): controla a profundidade/amostras da busca e
os limiares de aposta (inclusive ruído e blefe deliberado).
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
    def __init__(self, host, porta, nickname, modo, dificuldade="MEDIO"):
        if dificuldade not in estrategia.DIFICULDADES:
            opcoes = ", ".join(estrategia.DIFICULDADES)
            raise ValueError(f"dificuldade '{dificuldade}' inválida — use uma de: {opcoes}")
        self.config = estrategia.DIFICULDADES[dificuldade]
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
        # só True na janela entre as cartas distribuídas e a equipe decidir
        # jogar/correr na mão de 10 — sem isso, o bot tentava jogar carta ou
        # chamar truco mesmo com a decisão ainda pendente (cartas já
        # chegaram pelo INICIO_PARTIDA antes da decisão, desde que o corte
        # passou a vir primeiro).
        self.decisao_mao_10_pendente = False
        self.placar = {0: 0, 1: 0}

        # modelagem de adversário (por equipe, não por jogador — o protocolo
        # só identifica a equipe em PEDIDO_TRUCO/ESTADO_RODADA, não quem
        # especificamente pediu): quantas vezes cada equipe teve um pedido
        # de aposta aceito (equipe_apostou) e quantas dessas ela venceu a
        # mão. Ver `_taxa_blefe_estimada`.
        self.estatisticas_equipe = {0: {"pedidos": 0, "vitorias": 0}, 1: {"pedidos": 0, "vitorias": 0}}
        self._equipe_apostou_atual = None

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
        mudado entre o agendamento e a execução). `daemon=True` pra esse
        temporizador não manter o processo vivo se a conexão cair (ex: mesa
        desfeita pelo servidor) antes dele disparar — sem isso, o bot só
        encerrava até `RETARDO_MAX_SEGUNDOS` depois da desconexão."""
        atraso = random.uniform(RETARDO_MIN_SEGUNDOS, RETARDO_MAX_SEGUNDOS)
        temporizador = threading.Timer(atraso, callback)
        temporizador.daemon = True
        temporizador.start()

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
        self.decisao_mao_10_pendente = False
        self._equipe_apostou_atual = None
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
        self.decisao_mao_10_pendente = tipo_mao == constants.TIPO_MAO_DE_10
        if (
            tipo_mao == constants.TIPO_MAO_DE_10
            and int(equipe_decisora) == self.equipe_de.get(self.nickname)
            and self._sou_responsavel_pela_equipe()
        ):
            self._agendar(self._executar_decisao_mao_10)

    def _executar_decisao_mao_10(self):
        if not self._ativo or self.mao_especial is None:
            return
        decisao = estrategia.decidir_mao_10(self.mao, self.modo_real, self.config)
        forca = estrategia.avaliar_forca_mao(self.mao, self.modo_real)
        self._log(f"mão de 10 — força (sem ruído) {forca:.3f} — decisão: {decisao}")
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
        vez, cartas_csv, valor, equipe_apostou = campos
        self.cartas_rodada_atual = _parse_cartas_csv(cartas_csv)
        self.vez = vez
        self.valor_mao = valor
        self.pedido_pendente = None
        # ESTADO_RODADA só chega durante jogo de verdade (depois de uma
        # jogada ou de decidir "jogar" na mão de 10) — se chegou, qualquer
        # decisão de mão de 10 pendente já foi resolvida.
        self.decisao_mao_10_pendente = False
        # quem "tem a palavra" no valor atual (pedido aceito) — guardado pra
        # quando a mão terminar saber de quem é a estatística de blefe (ver
        # _tratar_resultado_mao/_taxa_blefe_estimada).
        self._equipe_apostou_atual = int(equipe_apostou) if equipe_apostou else None
        self._agir_se_for_minha_vez()

    def _tratar_resultado_rodada(self, campos):
        cartas_csv, vencedor = campos
        for nick, carta in _parse_cartas_csv(cartas_csv):
            self.jogadas_completas_na_mao.setdefault(nick, []).append(carta)
        self.resultados_rodadas_na_mao.append(None if vencedor == "EMPATE" else int(vencedor))
        self.cartas_rodada_atual = []

    def _tratar_resultado_mao(self, campos):
        vencedor, placar0, placar1 = campos
        if self._equipe_apostou_atual is not None:
            stats = self.estatisticas_equipe[self._equipe_apostou_atual]
            stats["pedidos"] += 1
            if vencedor != "EMPATE" and int(vencedor) == self._equipe_apostou_atual:
                stats["vitorias"] += 1
        self._equipe_apostou_atual = None
        self.placar = {0: int(placar0), 1: int(placar1)}
        self.decisao_mao_10_pendente = False

    def _taxa_blefe_estimada(self, equipe):
        """Estimativa (Bayes informal, com suavização de Laplace) de quão
        frequentemente a equipe pede aposta e depois perde a mão — sinal
        fraco de blefe (também pode ser só mão boa que perdeu na rodada
        seguinte por variância; por isso o ajuste que isso alimenta em
        `_executar_resposta_pedido` é pequeno e com teto). Só usa a
        estimativa com pelo menos 3 amostras — com menos que isso é só
        prior insuficiente, viés de poucos dados."""
        stats = self.estatisticas_equipe[equipe]
        pedidos = stats["pedidos"]
        if pedidos < 3:
            return 0.0
        taxa_vitoria = (stats["vitorias"] + 1) / (pedidos + 2)
        return max(0.0, 1.0 - taxa_vitoria)

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
        equipe_solicitante = self.pedido_pendente["equipe"]
        taxa_blefe = self._taxa_blefe_estimada(equipe_solicitante)
        # teto no deslocamento: a taxa medida confunde "tendência a blefar"
        # com "sorte/força geral da equipe" (perder a mão depois de pedir
        # não é prova de blefe) — um sinal ruidoso não pode mexer demais no
        # limiar, mesmo já com as >=3 amostras mínimas.
        ajuste = min(0.10, taxa_blefe * 0.15)
        decisao = estrategia.decidir_resposta_pedido(self.mao, self.modo_real, pode_aumentar, self.config, ajuste)
        forca = estrategia.avaliar_forca_mao(self.mao, self.modo_real)
        self._log(
            f"respondendo pedido de {valor} (força sem ruído {forca:.3f}, "
            f"taxa de blefe estimada da equipe {equipe_solicitante}: {taxa_blefe:.2f}): {decisao}"
        )
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
        if self.decisao_mao_10_pendente:
            return
        self._agendar(self._executar_minha_vez)

    def _executar_minha_vez(self):
        if not self._ativo or self.vez != self.nickname:
            return
        if self.pedido_pendente is not None or self.pedido_corte is not None:
            return
        if self.decisao_mao_10_pendente:
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
            and estrategia.deve_chamar_truco(self.mao, self.modo_real, self.config)
        ):
            forca = estrategia.avaliar_forca_mao(self.mao, self.modo_real)
            self._log(f"chamando truco (mão {self.mao}, força sem ruído {forca:.3f}).")
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
            self.config,
        )
        self._log(f"jogando {carta} (mão atual: {self.mao})")
        self.enviar(constants.JOGAR_CARTA, carta)
        self.mao.remove(carta)


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_PADRAO
    porta = int(sys.argv[2]) if len(sys.argv) > 2 else PORTA_PADRAO
    nickname = sys.argv[3] if len(sys.argv) > 3 else f"{constants.PREFIXO_NICKNAME_BOT}{random.randint(100, 999)}"
    modo = int(sys.argv[4]) if len(sys.argv) > 4 else MODO_PADRAO
    dificuldade = sys.argv[5] if len(sys.argv) > 5 else "MEDIO"

    bot = ClienteBot(host, porta, nickname, modo, dificuldade)
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
