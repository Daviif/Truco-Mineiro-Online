"""Gerador de trafego controlado para a captura no Wireshark (Fase 1/2).

Produz UMA sessao de protocolo pequena, completa e legivel entre dois
jogadores (ana e bia), na ordem ideal para a captura:

  handshake TCP -> LOGIN -> ENTRAR_MESA -> PAPEIS/PEDIDO_CORTE -> CORTAR
  -> INICIO_PARTIDA -> uma JOGAR_CARTA de cada jogador -> SAIR (FIN/close).

Assim a captura contem, em ordem e sem ruido: abertura da conexao, varias
mensagens de aplicacao (em texto) e o encerramento. Rode o servidor, comece
a gravar no Wireshark (filtro tcp.port == 5000) e entao rode este script.

Uso:
    python testes/gera_trafego.py [host] [porta]
Padrao: 127.0.0.1 5000
"""

import socket
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5000


class Jogador:
    def __init__(self, nick):
        self.nick = nick
        self.sock = socket.create_connection((HOST, PORTA))
        self.sock.settimeout(2.0)
        self._buf = b""
        self.mao = []          # cartas na mao (de INICIO_PARTIDA)
        self.vez = None        # de quem eh a vez (ultimo INICIO/ESTADO)

    def envia(self, texto):
        self.sock.sendall((texto + "\n").encode("utf-8"))
        print(f"{self.nick:>4} -> {texto}")

    def le(self, segundos=1.2):
        """Le mensagens por um tempo, imprime e atualiza mao/vez."""
        fim = time.time() + segundos
        recebidas = []
        while time.time() < fim:
            try:
                dados = self.sock.recv(4096)
            except socket.timeout:
                break
            if not dados:
                break
            self._buf += dados
            while b"\n" in self._buf:
                linha, self._buf = self._buf.split(b"\n", 1)
                texto = linha.decode("utf-8", errors="replace").strip()
                if not texto:
                    continue
                recebidas.append(texto)
                print(f"     S->{self.nick}: {texto}")
                self._atualiza(texto)
        return recebidas

    def _atualiza(self, texto):
        partes = texto.split(";")
        tipo = partes[0]
        if tipo == "INICIO_PARTIDA":
            self.mao = partes[1].split(",") if partes[1] else []
            self.vez = partes[2]
        elif tipo == "ESTADO_RODADA":
            self.vez = partes[1]

    def fecha(self):
        try:
            self.sock.close()
        except OSError:
            pass


def main():
    print(f"# Gerando trafego de protocolo em {HOST}:{PORTA}\n")

    ana = Jogador("ana")
    bia = Jogador("bia")
    print(f"# portas efemeras: ana={ana.sock.getsockname()[1]} "
          f"bia={bia.sock.getsockname()[1]} | servidor={PORTA}\n")

    # 1) Registro (LOGIN) e entrada na mesa (ENTRAR_MESA)
    ana.envia("LOGIN;ana"); ana.le()
    ana.envia("ENTRAR_MESA;2"); ana.le()
    bia.envia("LOGIN;bia"); bia.le()
    bia.envia("ENTRAR_MESA;2")
    bia.le(); ana.le()  # ambos recebem PAPEIS + PEDIDO_CORTE

    # 2) Corte do baralho pelo contra-pe -> distribui as cartas
    #    PAPEIS;pe;mao;contra_pe  (em 2 jogadores, mao == contra-pe == bia)
    bia.envia("CORTAR;DESCER")
    bia.le(); ana.le()  # ambos recebem INICIO_PARTIDA com suas maos

    # 3) Uma jogada de cada: quem for a "vez" joga a 1a carta da mao
    primeiro = ana if ana.vez == "ana" else bia
    segundo = bia if primeiro is ana else ana
    if primeiro.mao:
        primeiro.envia(f"JOGAR_CARTA;{primeiro.mao[0]}")
        primeiro.le(); segundo.le()
    if segundo.mao:
        segundo.envia(f"JOGAR_CARTA;{segundo.mao[0]}")
        segundo.le(); primeiro.le()

    # 4) Encerramento limpo (SAIR -> servidor fecha o socket -> FIN/close)
    ana.envia("SAIR")
    bia.envia("SAIR")
    time.sleep(0.3)
    ana.fecha()
    bia.fecha()
    print("\n# Sessao encerrada. Pare a captura no Wireshark agora.")


if __name__ == "__main__":
    main()
