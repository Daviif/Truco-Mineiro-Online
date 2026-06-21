"""Sessão de um cliente conectado ao servidor: parsing de mensagens,
despacho para a lógica de jogo e notificação dos demais jogadores da mesa."""

from common import constants
from common.protocol import MessageReader, encode
from server import game

TAMANHO_BUFFER = 4096


class ClientSession:
    def __init__(self, conn, endereco, servidor):
        self.conn = conn
        self.endereco = endereco
        self.servidor = servidor
        self.nickname = None
        self._reader = MessageReader()

    # -- transporte ---------------------------------------------------------

    def enviar(self, tipo, *campos):
        try:
            self.conn.sendall(encode(tipo, *campos))
        except OSError:
            pass

    def executar(self):
        try:
            while True:
                dados = self.conn.recv(TAMANHO_BUFFER)
                if not dados:
                    break
                for tipo, campos in self._reader.feed(dados):
                    self._tratar_mensagem(tipo, campos)
        except OSError:
            pass
        finally:
            self._desconectar()
            try:
                self.conn.close()
            except OSError:
                pass

    def _tratar_mensagem(self, tipo, campos):
        handler = self._HANDLERS.get(tipo)
        if handler is None:
            self.enviar(constants.ERRO, constants.ERRO_MENSAGEM_INVALIDA)
            return
        try:
            handler(self, campos)
        except game.ErroJogo as erro:
            self.enviar(constants.ERRO, erro.motivo)

    # -- handlers de mensagens do cliente ------------------------------------

    def _h_login(self, campos):
        if self.nickname is not None:
            self.enviar(constants.ERRO, constants.ERRO_MENSAGEM_INVALIDA)
            return
        if not campos or not campos[0].strip():
            self.enviar(constants.ERRO, constants.ERRO_MENSAGEM_INVALIDA)
            return
        nickname = campos[0].strip()
        if not self.servidor.registrar(nickname, self):
            self.enviar(constants.ERRO, constants.ERRO_NICKNAME_EM_USO)
            return
        self.nickname = nickname
        self.enviar(constants.LOGIN_OK, nickname)

    def _h_listar_mesas(self, campos):
        if not self._exigir_login():
            return
        mesas = self.servidor.room_manager.listar()
        texto = "|".join(
            f"{m['id']}:{m['modo']}:{len(m['jogadores'])}/{m['modo']}:{m['status']}"
            for m in mesas
        )
        self.enviar(constants.MESAS, texto)

    def _h_entrar_mesa(self, campos):
        if not self._exigir_login():
            return
        if self.servidor.room_manager.mesa_do_jogador(self.nickname) is not None:
            self.enviar(constants.ERRO, constants.ERRO_JA_EM_MESA)
            return
        if not campos:
            self.enviar(constants.ERRO, constants.ERRO_MODO_INVALIDO)
            return
        try:
            modo = int(campos[0])
        except ValueError:
            self.enviar(constants.ERRO, constants.ERRO_MODO_INVALIDO)
            return
        try:
            mesa = self.servidor.room_manager.entrar(modo, self.nickname)
        except ValueError:
            self.enviar(constants.ERRO, constants.ERRO_MODO_INVALIDO)
            return

        with mesa.lock:
            self._notificar_status_mesa(mesa)
            if mesa.partida is not None:
                self._anunciar_nova_mao(mesa)

    def _h_jogar_carta(self, campos):
        mesa = self._exigir_mesa_em_andamento()
        if mesa is None:
            return
        if not campos or not campos[0]:
            self.enviar(constants.ERRO, constants.ERRO_CARTA_INVALIDA)
            return
        carta_ou_posicao = campos[0]
        # a notificação precisa ocorrer com a mesa ainda travada: ela lê
        # estado mutável de mesa.partida (vez, cartas da rodada), e soltar o
        # lock antes de notificar permite que a próxima jogada mude esse
        # estado entre o cálculo do resultado e o broadcast (corrida real,
        # observada com 6/8 jogadores onde as jogadas chegam quase juntas).
        with mesa.lock:
            resultado = mesa.partida.jogar_carta(self.nickname, carta_ou_posicao)
            if resultado is None:
                self._notificar_estado_rodada(mesa)
            else:
                self._notificar_fim_rodada(mesa, resultado)

    def _h_cortar(self, campos):
        mesa = self._exigir_mesa_em_andamento()
        if mesa is None:
            return
        if not campos or not campos[0]:
            self.enviar(constants.ERRO, constants.ERRO_MENSAGEM_INVALIDA)
            return
        with mesa.lock:
            mesa.partida.cortar(self.nickname, campos[0])
            self._notificar_inicio_mao(mesa)

    def _h_decidir_mao_10(self, campos):
        mesa = self._exigir_mesa_em_andamento()
        if mesa is None:
            return
        if not campos or not campos[0]:
            self.enviar(constants.ERRO, constants.ERRO_MENSAGEM_INVALIDA)
            return
        with mesa.lock:
            resultado = mesa.partida.decidir_mao_10(self.nickname, campos[0])
            if resultado is None:
                # decidiu jogar: a mão segue para a fase de corte
                self._notificar_pedido_corte(mesa)
            else:
                # decidiu correr: a mão termina sem distribuir cartas
                self._finalizar_mao_e_notificar(mesa, resultado)

    def _h_truco(self, campos):
        mesa = self._exigir_mesa_em_andamento()
        if mesa is None:
            return
        with mesa.lock:
            mesa.partida.chamar_truco(self.nickname)
            self._notificar_pedido(mesa)

    def _h_aumentar(self, campos):
        mesa = self._exigir_mesa_em_andamento()
        if mesa is None:
            return
        with mesa.lock:
            mesa.partida.aumentar(self.nickname)
            self._notificar_pedido(mesa)

    def _h_aceitar(self, campos):
        mesa = self._exigir_mesa_em_andamento()
        if mesa is None:
            return
        with mesa.lock:
            mesa.partida.aceitar(self.nickname)
            self._notificar_estado_rodada(mesa)

    def _h_correr(self, campos):
        mesa = self._exigir_mesa_em_andamento()
        if mesa is None:
            return
        with mesa.lock:
            resultado = mesa.partida.correr(self.nickname)
            self._notificar_fim_mao(mesa, resultado)

    def _h_sair(self, campos):
        self._desconectar()

    _HANDLERS = {
        constants.LOGIN: _h_login,
        constants.LISTAR_MESAS: _h_listar_mesas,
        constants.ENTRAR_MESA: _h_entrar_mesa,
        constants.JOGAR_CARTA: _h_jogar_carta,
        constants.TRUCO: _h_truco,
        constants.AUMENTAR: _h_aumentar,
        constants.ACEITAR: _h_aceitar,
        constants.CORRER: _h_correr,
        constants.CORTAR: _h_cortar,
        constants.DECIDIR_MAO_10: _h_decidir_mao_10,
        constants.SAIR: _h_sair,
    }

    # -- validações comuns ----------------------------------------------------

    def _exigir_login(self):
        if self.nickname is None:
            self.enviar(constants.ERRO, constants.ERRO_NAO_LOGADO)
            return False
        return True

    def _exigir_mesa_em_andamento(self):
        if not self._exigir_login():
            return None
        mesa = self.servidor.room_manager.mesa_do_jogador(self.nickname)
        if mesa is None:
            self.enviar(constants.ERRO, constants.ERRO_NAO_EM_MESA)
            return None
        if mesa.partida is None:
            self.enviar(constants.ERRO, constants.ERRO_PARTIDA_NAO_INICIADA)
            return None
        return mesa

    # -- notificações para a mesa ---------------------------------------------

    def _notificar_status_mesa(self, mesa):
        jogadores_csv = ",".join(mesa.jogadores)
        for jogador in mesa.jogadores:
            self.servidor.enviar_para(jogador, constants.MESA_STATUS, mesa.id, mesa.status, jogadores_csv)

    def _notificar_papeis(self, mesa):
        partida = mesa.partida
        for jogador in mesa.jogadores:
            self.servidor.enviar_para(jogador, constants.PAPEIS, partida.pe, partida.mao, partida.contra_pe)

    def _notificar_pedido_corte(self, mesa):
        for jogador in mesa.jogadores:
            self.servidor.enviar_para(jogador, constants.PEDIDO_CORTE, mesa.partida.contra_pe)

    def _notificar_mao_especial(self, mesa):
        partida = mesa.partida
        tipo = constants.TIPO_MAO_DE_FERRO if partida.eh_mao_de_ferro else constants.TIPO_MAO_DE_10
        equipe_decisora = partida.equipe_mao_10 if partida.eh_mao_de_10 else ""
        for jogador in mesa.jogadores:
            self.servidor.enviar_para(jogador, constants.MAO_ESPECIAL, tipo, equipe_decisora)

    def _anunciar_nova_mao(self, mesa):
        """Anuncia o início de uma nova mão: papéis (pé/mão/contra-pé) e, a
        seguir, a fase em que ela começa (decisão de mão de 10, ou corte do
        baralho direto para mãos normais e mão de ferro)."""
        partida = mesa.partida
        self._notificar_papeis(mesa)
        if partida.fase == game.FASE_DECISAO_MAO_10:
            self._notificar_mao_especial(mesa)
        else:
            if partida.eh_mao_de_ferro:
                self._notificar_mao_especial(mesa)
            self._notificar_pedido_corte(mesa)

    def _notificar_inicio_mao(self, mesa):
        partida = mesa.partida
        for jogador in mesa.jogadores:
            if partida.eh_mao_de_ferro:
                mao_csv = ",".join("?" for _ in partida.mao_de[jogador])
            else:
                mao_csv = ",".join(partida.mao_de[jogador])
            self.servidor.enviar_para(
                jogador, constants.INICIO_PARTIDA, mao_csv, partida.jogador_da_vez, partida.valor_mao
            )
        self._notificar_cartas_parceiros(mesa)

    def _notificar_cartas_parceiros(self, mesa):
        """Na mão de 10, revela as cartas dos parceiros para quem tem
        direito de vê-las (ver Partida.jogador_vidente_mao_10)."""
        partida = mesa.partida
        vidente = partida.jogador_vidente_mao_10
        if vidente is None:
            return
        parceiros = [
            jogador
            for jogador in mesa.jogadores
            if partida.equipe_de[jogador] == partida.equipe_mao_10 and jogador != vidente
        ]
        if not parceiros:
            return
        texto = "|".join(f"{jogador}:{','.join(partida.mao_de[jogador])}" for jogador in parceiros)
        self.servidor.enviar_para(vidente, constants.CARTAS_PARCEIROS, texto)

    def _notificar_estado_rodada(self, mesa):
        partida = mesa.partida
        cartas_csv = ",".join(f"{j}:{c}" for j, c in partida.cartas_rodada)
        for jogador in mesa.jogadores:
            self.servidor.enviar_para(
                jogador, constants.ESTADO_RODADA, partida.jogador_da_vez, cartas_csv, partida.valor_mao
            )

    def _notificar_pedido(self, mesa):
        partida = mesa.partida
        pedido = partida.pedido_pendente
        for jogador in mesa.jogadores:
            self.servidor.enviar_para(
                jogador, constants.PEDIDO_TRUCO, pedido["equipe_solicitante"], pedido["valor_pedido"]
            )

    def _notificar_fim_rodada(self, mesa, resultado):
        cartas_csv = ",".join(f"{j}:{c}" for j, c in resultado["cartas"])
        vencedor_rodada = resultado["vencedor_rodada"]
        vencedor_rodada_str = vencedor_rodada if vencedor_rodada is not None else "EMPATE"
        for jogador in mesa.jogadores:
            self.servidor.enviar_para(jogador, constants.RESULTADO_RODADA, cartas_csv, vencedor_rodada_str)

        if resultado["vencedor_mao"] is not None:
            self._finalizar_mao_e_notificar(mesa, resultado)
        else:
            self._notificar_estado_rodada(mesa)

    def _notificar_fim_mao(self, mesa, resultado):
        self._finalizar_mao_e_notificar(mesa, resultado)

    def _finalizar_mao_e_notificar(self, mesa, resultado):
        placar = resultado["placar"]
        for jogador in mesa.jogadores:
            self.servidor.enviar_para(
                jogador, constants.RESULTADO_MAO, resultado["vencedor_mao"], placar[0], placar[1]
            )
        if resultado["fim_partida"] is not None:
            for jogador in mesa.jogadores:
                self.servidor.enviar_para(jogador, constants.FIM_PARTIDA, resultado["fim_partida"])
        else:
            self._anunciar_nova_mao(mesa)

    # -- desconexão -----------------------------------------------------------

    def _desconectar(self):
        if self.nickname is None:
            return
        mesa = self.servidor.room_manager.remover_jogador(self.nickname)
        if mesa is not None:
            for jogador in mesa.jogadores:
                self.servidor.enviar_para(jogador, constants.JOGADOR_SAIU, self.nickname)
        self.servidor.remover(self.nickname)
        self.nickname = None
