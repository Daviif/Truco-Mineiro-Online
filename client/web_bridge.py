"""Bridge web do Truco Mineiro.

Este processo É o cliente TCP de verdade: abre um socket TCP com o
server.py e fala o protocolo da aplicação (common/protocol.py), exatamente
como o cli_client.py. Além disso, sobe um servidor HTTP local (stdlib,
ThreadingHTTPServer) que serve a página em client/web/ e repassa as ações
do navegador para o socket TCP, empurrando o estado para a página via
Server-Sent Events (SSE). O navegador nunca fala com o servidor de truco
diretamente — só com este processo, por padrão em localhost.

Uso: python3 client/web_bridge.py [host_servidor] [porta_servidor] [porta_http] [host_http]

`host_http` é opcional (padrão `127.0.0.1`, só local). Passe `0.0.0.0` para
aceitar conexões de fora — por exemplo, rodando este processo num servidor
remoto e abrindo a página de outra máquina. Sem autenticação própria: quem
acessa a porta HTTP herda a sessão já logada no servidor de truco, então só
abra pra fora numa rede/firewall em que você confia.
"""

import json
import os
import queue
import random
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import constants
from common.protocol import MessageReader, encode

HOST_SERVIDOR_PADRAO = "127.0.0.1"
PORTA_SERVIDOR_PADRAO = 5000
PORTA_HTTP_PADRAO = 8080
# só localhost por padrão: o bridge não tem autenticação própria (quem
# acessa a página HTTP herda a sessão já logada no servidor de truco), então
# abrir isso pra fora exige passar o 4º argumento explicitamente.
HOST_HTTP_PADRAO = "127.0.0.1"

DIR_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_BOT = os.path.join(RAIZ_PROJETO, "bot", "cliente_bot.py")

ARQUIVOS_ESTATICOS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


class EstadoCompartilhado:
    """Estado atual do jogador, populado pelas mensagens recebidas do socket TCP."""

    def __init__(self):
        self.lock = threading.Lock()
        self.dados = {
            "nickname": None,
            "logado": False,
            "mesa": None,
            "papeis": None,
            "pedido_corte": None,
            "mao_especial": None,
            "mao_de_ferro_ativa": False,
            "mao": [],
            "vez": None,
            "valor_mao": None,
            "cartas_mesa": [],
            "placar": {"0": 0, "1": 0},
            "pedido_pendente": None,
            "ultimo_resultado_rodada": None,
            "ultimo_resultado_mao": None,
            "fim_partida": None,
            "mesas_disponiveis": [],
            "erro": None,
            "aviso": None,
            "modo_solicitado": None,
            "cartas_parceiros": None,
        }
        self._assinantes = []

    def assinar(self):
        fila = queue.Queue()
        with self.lock:
            self._assinantes.append(fila)
            fila.put(dict(self.dados))
        return fila

    def desassinar(self, fila):
        with self.lock:
            if fila in self._assinantes:
                self._assinantes.remove(fila)

    def atualizar(self, **mudancas):
        with self.lock:
            self.dados.update(mudancas)
            snapshot = dict(self.dados)
            assinantes = list(self._assinantes)
        for fila in assinantes:
            fila.put(snapshot)

    def remover_carta_da_mao(self, carta):
        """Remoção otimista: o servidor só reenvia a mão completa no início
        de cada mão (INICIO_PARTIDA), não a cada jogada. Sem isso, a carta
        jogada continuaria aparecendo como clicável na página."""
        with self.lock:
            nova_mao = [c for c in self.dados["mao"] if c != carta]
        self.atualizar(mao=nova_mao)

    def remover_posicao_da_mao(self, posicao):
        """Mesma remoção otimista, mas por posição (mão de ferro): as cartas
        na mão são só placeholders ('?'), então não há valor para comparar."""
        with self.lock:
            mao = list(self.dados["mao"])
            indice = posicao - 1
            if 0 <= indice < len(mao):
                mao.pop(indice)
        self.atualizar(mao=mao)


class ClienteTCP:
    """Cliente TCP real do protocolo do truco, usado pelo bridge."""

    def __init__(self, host, porta, estado):
        self.estado = estado
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, porta))
        self._reader = MessageReader()

    def enviar(self, tipo, *campos):
        try:
            self.sock.sendall(encode(tipo, *campos))
            return True
        except OSError:
            return False

    def escutar(self):
        try:
            while True:
                dados = self.sock.recv(4096)
                if not dados:
                    self.estado.atualizar(aviso="Conexão com o servidor de truco encerrada.")
                    break
                for tipo, campos in self._reader.feed(dados):
                    self._processar(tipo, campos)
        except OSError:
            pass

    def _processar(self, tipo, campos):
        if tipo == constants.LOGIN_OK:
            self.estado.atualizar(logado=True, nickname=campos[0], erro=None)
        elif tipo == constants.ERRO:
            self.estado.atualizar(erro=campos[0])
        elif tipo == constants.MESAS:
            texto = campos[0] if campos else ""
            mesas = []
            if texto:
                for item in texto.split("|"):
                    id_, modo, ocupacao, status = item.split(":")
                    mesas.append({"id": id_, "modo": modo, "ocupacao": ocupacao, "status": status})
            self.estado.atualizar(mesas_disponiveis=mesas)
        elif tipo == constants.MESA_STATUS:
            id_mesa, status, jogadores_csv = campos
            jogadores = jogadores_csv.split(",") if jogadores_csv else []
            self.estado.atualizar(mesa={"id": id_mesa, "status": status, "jogadores": jogadores})
        elif tipo == constants.PAPEIS:
            pe, mao_lider, contra_pe = campos
            # zera a mão/jogada exibidas: a partir daqui o jogo está em
            # corte ou decisão de mão especial, e as cartas/turno da mão
            # anterior não existem mais até o próximo INICIO_PARTIDA. Sem
            # isso, a mão antiga ficava visível (e, por um bug relacionado,
            # clicável) durante toda a fase de corte/decisão.
            self.estado.atualizar(
                papeis={"pe": pe, "mao": mao_lider, "contra_pe": contra_pe},
                pedido_corte=None,
                mao_especial=None,
                mao_de_ferro_ativa=False,
                cartas_parceiros=None,
                pedido_pendente=None,
                mao=[],
                cartas_mesa=[],
                vez=None,
                valor_mao=None,
            )
        elif tipo == constants.PEDIDO_CORTE:
            self.estado.atualizar(pedido_corte=campos[0])
        elif tipo == constants.MAO_ESPECIAL:
            tipo_mao, equipe_decisora = campos
            self.estado.atualizar(
                mao_especial={"tipo": tipo_mao, "equipe_decisora": equipe_decisora},
                mao_de_ferro_ativa=(tipo_mao == constants.TIPO_MAO_DE_FERRO),
            )
        elif tipo == constants.INICIO_PARTIDA:
            mao_csv, vez, valor = campos
            self.estado.atualizar(
                mao=mao_csv.split(",") if mao_csv else [],
                vez=vez,
                valor_mao=valor,
                cartas_mesa=[],
                pedido_pendente=None,
                pedido_corte=None,
                ultimo_resultado_rodada=None,
                fim_partida=None,
            )
        elif tipo == constants.CARTAS_PARCEIROS:
            texto = campos[0] if campos else ""
            parceiros = []
            if texto:
                for item in texto.split("|"):
                    nick, cartas_csv = item.split(":", 1)
                    parceiros.append({"nickname": nick, "cartas": cartas_csv.split(",")})
            self.estado.atualizar(cartas_parceiros=parceiros)
        elif tipo == constants.ESTADO_RODADA:
            vez, cartas_csv, valor = campos
            cartas = [par.split(":") for par in cartas_csv.split(",")] if cartas_csv else []
            self.estado.atualizar(vez=vez, cartas_mesa=cartas, valor_mao=valor, pedido_pendente=None)
        elif tipo == constants.RESULTADO_RODADA:
            cartas_csv, vencedor = campos
            self.estado.atualizar(ultimo_resultado_rodada={"cartas": cartas_csv, "vencedor": vencedor})
        elif tipo == constants.RESULTADO_MAO:
            vencedor, placar0, placar1 = campos
            self.estado.atualizar(
                ultimo_resultado_mao={"vencedor": vencedor, "placar0": placar0, "placar1": placar1},
                placar={"0": placar0, "1": placar1},
                pedido_pendente=None,
            )
        elif tipo == constants.PEDIDO_TRUCO:
            equipe, valor = campos
            self.estado.atualizar(pedido_pendente={"equipe": equipe, "valor": valor})
        elif tipo == constants.FIM_PARTIDA:
            self.estado.atualizar(fim_partida=campos[0])
        elif tipo == constants.JOGADOR_SAIU:
            self.estado.atualizar(aviso=f"O jogador '{campos[0]}' saiu da mesa.")


def criar_handler(estado, cliente_tcp, host_servidor, porta_servidor):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, formato, *args):
            pass  # silencia o log padrão do http.server

        def do_GET(self):
            if self.path == "/events":
                self._tratar_sse()
                return
            entrada = ARQUIVOS_ESTATICOS.get(self.path)
            if entrada is None:
                self.send_response(404)
                self.end_headers()
                return
            nome_arquivo, content_type = entrada
            caminho = os.path.join(DIR_WEB, nome_arquivo)
            try:
                with open(caminho, "rb") as f:
                    corpo = f.read()
            except OSError:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _tratar_sse(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            fila = estado.assinar()
            try:
                while True:
                    snapshot = fila.get()
                    linha = f"data: {json.dumps(snapshot)}\n\n"
                    self.wfile.write(linha.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                estado.desassinar(fila)

        def _jogar_carta(self, carta_ou_posicao):
            sucesso = cliente_tcp.enviar(constants.JOGAR_CARTA, carta_ou_posicao)
            if sucesso:
                if estado.dados.get("mao_de_ferro_ativa"):
                    try:
                        estado.remover_posicao_da_mao(int(carta_ou_posicao))
                    except ValueError:
                        pass
                else:
                    estado.remover_carta_da_mao(carta_ou_posicao)
            return sucesso

        def _entrar_mesa(self, modo_txt):
            try:
                estado.atualizar(modo_solicitado=int(modo_txt))
            except ValueError:
                pass
            return cliente_tcp.enviar(constants.ENTRAR_MESA, modo_txt)

        def _completar_com_bots(self):
            """Spawna bots reais (bot/cliente_bot.py, clientes TCP de verdade,
            cada um seu próprio processo) para preencher os assentos que
            faltam na mesa atual. Não é um caso especial do servidor: pro
            servidor, cada bot é só mais um cliente TCP entrando na mesa."""
            modo = estado.dados.get("modo_solicitado")
            mesa = estado.dados.get("mesa")
            if modo is None or mesa is None:
                return False
            faltantes = modo - len(mesa.get("jogadores", []))
            for _ in range(max(0, faltantes)):
                nickname_bot = f"Bot{random.randint(10000, 99999)}"
                subprocess.Popen(
                    [sys.executable, SCRIPT_BOT, host_servidor, str(porta_servidor), nickname_bot, str(modo)]
                )
            return True

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            corpo = self.rfile.read(tamanho) if tamanho else b"{}"
            try:
                payload = json.loads(corpo.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                payload = {}

            rotas = {
                "/login": lambda: cliente_tcp.enviar(constants.LOGIN, payload.get("nickname", "")),
                "/listar_mesas": lambda: cliente_tcp.enviar(constants.LISTAR_MESAS),
                "/entrar_mesa": lambda: self._entrar_mesa(payload.get("modo", "")),
                "/completar_com_bots": lambda: self._completar_com_bots(),
                "/jogar_carta": lambda: self._jogar_carta(payload.get("carta", "")),
                "/cortar": lambda: cliente_tcp.enviar(constants.CORTAR, payload.get("direcao", "")),
                "/decidir_mao_10": lambda: cliente_tcp.enviar(constants.DECIDIR_MAO_10, payload.get("decisao", "")),
                "/truco": lambda: cliente_tcp.enviar(constants.TRUCO),
                "/aceitar": lambda: cliente_tcp.enviar(constants.ACEITAR),
                "/correr": lambda: cliente_tcp.enviar(constants.CORRER),
                "/aumentar": lambda: cliente_tcp.enviar(constants.AUMENTAR),
                "/sair": lambda: cliente_tcp.enviar(constants.SAIR),
            }
            acao = rotas.get(self.path)
            if acao is None:
                self.send_response(404)
                self.end_headers()
                return
            acao()
            self.send_response(204)
            self.end_headers()

    return Handler


def main():
    host_servidor = sys.argv[1] if len(sys.argv) > 1 else HOST_SERVIDOR_PADRAO
    porta_servidor = int(sys.argv[2]) if len(sys.argv) > 2 else PORTA_SERVIDOR_PADRAO
    porta_http = int(sys.argv[3]) if len(sys.argv) > 3 else PORTA_HTTP_PADRAO
    host_http = sys.argv[4] if len(sys.argv) > 4 else HOST_HTTP_PADRAO

    estado = EstadoCompartilhado()
    cliente_tcp = ClienteTCP(host_servidor, porta_servidor, estado)
    threading.Thread(target=cliente_tcp.escutar, daemon=True).start()

    handler = criar_handler(estado, cliente_tcp, host_servidor, porta_servidor)
    httpd = ThreadingHTTPServer((host_http, porta_http), handler)
    print(f"Bridge conectado ao servidor de truco em {host_servidor}:{porta_servidor}")
    if host_http == "0.0.0.0":
        print(f"Abra http://<IP desta máquina>:{porta_http} no navegador.")
    else:
        print(f"Abra http://{host_http}:{porta_http} no navegador.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge encerrado.")


if __name__ == "__main__":
    main()
