"""Cliente de terminal do Truco Mineiro.

Uso: python3 client/cli_client.py [host] [porta]
"""

import os
import socket
import sys
import threading

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import constants
from common.protocol import MessageReader, encode

HOST_PADRAO = "127.0.0.1"
PORTA_PADRAO = 5000


class ClienteCLI:
    def __init__(self, host, porta):
        self.host = host
        self.porta = porta
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, porta))
        self._reader = MessageReader()
        self._ativo = True

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
                    print("\n[Conexão encerrada pelo servidor]")
                    break
                for tipo, campos in self._reader.feed(dados):
                    self._exibir(tipo, campos)
        except OSError:
            pass
        finally:
            self._ativo = False

    def _exibir(self, tipo, campos):
        if tipo == constants.LOGIN_OK:
            print(f"\n[OK] Login efetuado como '{campos[0]}'.")
        elif tipo == constants.ERRO:
            print(f"\n[ERRO] {campos[0]}")
        elif tipo == constants.MESAS:
            texto = campos[0] if campos else ""
            if not texto:
                print("\n[Mesas] Nenhuma mesa aberta no momento.")
            else:
                print("\n[Mesas] " + " | ".join(texto.split("|")))
        elif tipo == constants.MESA_STATUS:
            id_mesa, status, jogadores_csv = campos
            print(f"\n[Mesa {id_mesa}] status={status} jogadores=({jogadores_csv})")
        elif tipo == constants.PAPEIS:
            pe, mao, contra_pe = campos
            print(f"\n[Papéis] pé (embaralha/dá): {pe} | mão (joga primeiro): {mao} | contra-pé (corta): {contra_pe}")
        elif tipo == constants.PEDIDO_CORTE:
            print(f"\n[Corte] aguardando '{campos[0]}' cortar o baralho (comando: cortar subir|descer)")
        elif tipo == constants.MAO_ESPECIAL:
            tipo_mao, equipe_decisora = campos
            if tipo_mao == constants.TIPO_MAO_DE_FERRO:
                print("\n[Mão de ferro] ambas as equipes com 10+! Cartas viradas, truco bloqueado. Jogue por posição: jogar 1|2|3")
            else:
                print(
                    f"\n[Mão de 10] equipe {equipe_decisora} está com 10+! Truco bloqueado. "
                    "Essa equipe decide: decidir jogar|correr"
                )
        elif tipo == constants.INICIO_PARTIDA:
            mao_csv, vez, valor = campos
            print(f"\n[Nova mão] Sua mão: {mao_csv} | Vez de: {vez} | Valor da mão: {valor}")
        elif tipo == constants.CARTAS_PARCEIROS:
            texto = campos[0] if campos else ""
            partes = " | ".join(item.replace(":", ": ") for item in texto.split("|")) if texto else ""
            print(f"\n[Mão de 10] Você vê a mão dos parceiros: {partes}")
        elif tipo == constants.ESTADO_RODADA:
            vez, cartas_csv, valor, _equipe_apostou = campos
            mesa_str = cartas_csv if cartas_csv else "(nenhuma carta jogada ainda)"
            print(f"\n[Rodada] Na mesa: {mesa_str} | Vez de: {vez} | Valor da mão: {valor}")
        elif tipo == constants.RESULTADO_RODADA:
            cartas_csv, vencedor = campos
            print(f"\n[Resultado da rodada] {cartas_csv} -> equipe vencedora: {vencedor}")
        elif tipo == constants.RESULTADO_MAO:
            vencedor, placar0, placar1 = campos
            print(f"\n[Resultado da mão] equipe {vencedor} venceu! Placar -> equipe 0: {placar0} x equipe 1: {placar1}")
        elif tipo == constants.PEDIDO_TRUCO:
            equipe, valor = campos
            print(f"\n[Pedido] equipe {equipe} pediu aposta valendo {valor}! Responda com: aceitar | correr | aumentar")
        elif tipo == constants.FIM_PARTIDA:
            print(f"\n[FIM DE PARTIDA] equipe {campos[0]} venceu a partida!")
        elif tipo == constants.JOGADOR_SAIU:
            print(f"\n[Aviso] o jogador '{campos[0]}' saiu da mesa.")
        elif tipo == constants.CHAT:
            nick = campos[0]
            texto = ";".join(campos[1:])
            print(f"\n[Chat] {nick}: {texto}")
        else:
            print(f"\n[?] {tipo};{';'.join(campos)}")
        print("> ", end="", flush=True)

    def fechar(self):
        self._ativo = False
        try:
            self.sock.close()
        except OSError:
            pass


def imprimir_ajuda():
    print(
        "Comandos disponíveis:\n"
        "  login <nickname>        - login avulso, sem conta nem senha (igual sempre foi)\n"
        "  registrar <email> <senha> <nickname> [curso]\n"
        "                          - cria uma conta (e já loga); curso só importa se o\n"
        "                            email for institucional da UFOP\n"
        "  entrarconta <email> <senha>\n"
        "                          - login numa conta já cadastrada\n"
        "  mesas                   - lista as mesas disponíveis\n"
        "  entrar <modo>           - entra/cria uma mesa para 2, 4, 6 ou 8 jogadores\n"
        "  jogar <carta>           - joga uma carta da sua mão (código, ex: jogar 4P; ou posição 1/2/3 na mão de ferro)\n"
        "  cortar <subir|descer>   - corta o baralho (só quem é o contra-pé)\n"
        "  decidir <jogar|correr>  - decide a mão de 10 (só a equipe com 10+ pontos)\n"
        "  truco                   - pede truco\n"
        "  aceitar                 - aceita o pedido de aposta pendente\n"
        "  correr                  - corre do pedido de aposta pendente\n"
        "  aumentar                - reaumenta o pedido de aposta pendente\n"
        "  chat <mensagem>         - envia mensagem no chat da mesa\n"
        "  sair                    - encerra a conexão\n"
        "  ajuda                   - mostra esta mensagem"
    )


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_PADRAO
    porta = int(sys.argv[2]) if len(sys.argv) > 2 else PORTA_PADRAO

    cliente = ClienteCLI(host, porta)
    thread_escuta = threading.Thread(target=cliente.escutar, daemon=True)
    thread_escuta.start()

    print(f"Conectado a {host}:{porta}. Digite 'ajuda' para ver os comandos.")
    imprimir_ajuda()

    try:
        while cliente._ativo:
            try:
                linha = input("> ").strip()
            except EOFError:
                break
            if not linha:
                continue
            partes = linha.split(maxsplit=1)
            comando = partes[0].lower()
            argumento = partes[1] if len(partes) > 1 else ""

            if comando == "login":
                cliente.enviar(constants.LOGIN, argumento)
            elif comando == "registrar":
                partes_conta = argumento.split(maxsplit=3)
                if len(partes_conta) < 3:
                    print("Uso: registrar <email> <senha> <nickname> [curso]")
                else:
                    email, senha, nickname = partes_conta[0], partes_conta[1], partes_conta[2]
                    curso = partes_conta[3] if len(partes_conta) > 3 else ""
                    cliente.enviar(constants.REGISTRAR, email, senha, nickname, curso)
            elif comando == "entrarconta":
                partes_conta = argumento.split()
                if len(partes_conta) != 2:
                    print("Uso: entrarconta <email> <senha>")
                else:
                    cliente.enviar(constants.ENTRAR_CONTA, partes_conta[0], partes_conta[1])
            elif comando == "mesas":
                cliente.enviar(constants.LISTAR_MESAS)
            elif comando == "entrar":
                cliente.enviar(constants.ENTRAR_MESA, argumento)
            elif comando == "jogar":
                cliente.enviar(constants.JOGAR_CARTA, argumento)
            elif comando == "cortar":
                cliente.enviar(constants.CORTAR, argumento.strip().upper())
            elif comando == "decidir":
                cliente.enviar(constants.DECIDIR_MAO_10, argumento.strip().upper())
            elif comando == "truco":
                cliente.enviar(constants.TRUCO)
            elif comando == "aceitar":
                cliente.enviar(constants.ACEITAR)
            elif comando == "correr":
                cliente.enviar(constants.CORRER)
            elif comando == "aumentar":
                cliente.enviar(constants.AUMENTAR)
            elif comando == "chat":
                if argumento:
                    cliente.enviar(constants.CHAT, argumento)
            elif comando in ("sair", "exit", "quit"):
                cliente.enviar(constants.SAIR)
                break
            elif comando == "ajuda":
                imprimir_ajuda()
            else:
                print(f"Comando desconhecido: '{comando}'. Digite 'ajuda'.")
    except KeyboardInterrupt:
        pass
    finally:
        cliente.fechar()


if __name__ == "__main__":
    main()
