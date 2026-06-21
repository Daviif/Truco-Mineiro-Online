"""Codificação/decodificação do protocolo de aplicação do Truco Mineiro.

Framing: uma mensagem por linha, terminada em '\\n'. Campos separados por ';'.
Exemplo: "LOGIN;marlon\\n", "JOGAR_CARTA;4P\\n".

TCP é um fluxo de bytes sem limites de mensagem, então um único recv() pode
trazer 0, 1 ou várias mensagens, ou uma mensagem partida pela metade. O
MessageReader resolve isso bufferizando os bytes recebidos e só devolvendo
mensagens completas (delimitadas por '\\n').
"""

SEPARADOR_CAMPO = ";"
TERMINADOR = "\n"


def encode(tipo, *campos):
    """Monta os bytes de uma mensagem do protocolo a partir do tipo e campos."""
    partes = [tipo, *[str(c) for c in campos]]
    linha = SEPARADOR_CAMPO.join(partes)
    return (linha + TERMINADOR).encode("utf-8")


def parse(linha):
    """Decodifica uma linha de protocolo (sem o '\\n') em (tipo, [campos])."""
    partes = linha.split(SEPARADOR_CAMPO)
    tipo = partes[0]
    campos = partes[1:]
    return tipo, campos


class MessageReader:
    """Acumula bytes recebidos de um socket e extrai mensagens completas."""

    def __init__(self):
        self._buffer = b""

    def feed(self, dados):
        """Adiciona bytes recebidos do socket e retorna lista de mensagens (tipo, campos)."""
        if not dados:
            return []
        self._buffer += dados
        mensagens = []
        while True:
            indice = self._buffer.find(b"\n")
            if indice == -1:
                break
            linha = self._buffer[:indice].decode("utf-8", errors="replace")
            self._buffer = self._buffer[indice + 1:]
            linha = linha.rstrip("\r")
            if linha:
                mensagens.append(parse(linha))
        return mensagens
