"""Testes funcionais do Truco Mineiro Online (Fase 3 do plano da Pessoa A).

Executa e documenta os cenarios exigidos na secao 7 do enunciado:
  - Cenario 2: desconexao inesperada (cliente cai; servidor detecta e avisa).
  - Cenario 3: tratamento de erros (varios ERRO;<motivo> sem derrubar o server).

(O Cenario 1 - uso normal / partida - eh demonstrado por testes/gera_trafego.py
 e testes/verifica_fase0.py; o Cenario 4 - limitacoes - eh analise escrita.)

Cada cenario imprime PASS/FALHA. Rode o servidor antes:
    python server/server.py
    python testes/testes_funcionais.py
"""

import socket
import struct
import time

HOST, PORTA = "127.0.0.1", 5000


def conecta():
    return socket.create_connection((HOST, PORTA))


def envia(sock, texto):
    sock.sendall((texto + "\n").encode("utf-8"))


def le(sock, segundos=1.0):
    """Le mensagens por 'segundos' e devolve a lista de linhas (tipos)."""
    sock.settimeout(segundos)
    buf = b""
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            dados = sock.recv(4096)
        except socket.timeout:
            break
        if not dados:
            break
        buf += dados
    return [l for l in buf.decode("utf-8", errors="replace").split("\n") if l.strip()]


def fecha_abrupto(sock):
    """Fecha o socket de forma abrupta (RST), simulando queda do cliente."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                        struct.pack("ii", 1, 0))  # linger on, timeout 0 -> RST
    except OSError:
        pass
    sock.close()


def espera(cond, msg):
    print(f"   [{'PASS' if cond else 'FALHA'}] {msg}")
    return cond


# ---------------------------------------------------------------------------
def cenario_desconexao():
    print("\n=== CENARIO 2: DESCONEXAO INESPERADA ===")
    ana, bia = conecta(), conecta()
    envia(ana, "LOGIN;ana"); le(ana)
    envia(ana, "ENTRAR_MESA;2"); le(ana)
    envia(bia, "LOGIN;bia"); le(bia)
    envia(bia, "ENTRAR_MESA;2"); le(bia); le(ana)
    print("   ana e bia numa mesa, partida em andamento.")

    print("   -> ana CAI (fechamento abrupto do socket, sem SAIR)")
    fecha_abrupto(ana)

    msgs = le(bia, 1.5)
    for m in msgs:
        print(f"      S->bia: {m}")
    ok_aviso = espera(any(m.startswith("JOGADOR_SAIU") for m in msgs),
                      "servidor detectou a queda e avisou bia com JOGADOR_SAIU")

    # servidor continua vivo? novo cliente consegue logar
    novo = conecta()
    envia(novo, "LOGIN;carlos")
    resp = le(novo)
    ok_vivo = espera(any(m.startswith("LOGIN_OK") for m in resp),
                     "servidor continuou no ar (novo cliente logou apos a queda)")
    fecha_abrupto(novo); bia.close()
    return ok_aviso and ok_vivo


# ---------------------------------------------------------------------------
def cenario_erros():
    print("\n=== CENARIO 3: TRATAMENTO DE ERROS ===")
    resultados = []

    # 3.1 comando de jogo antes do login -> NAO_LOGADO
    s = conecta()
    envia(s, "LISTAR_MESAS")
    r = le(s)
    print(f"   LISTAR_MESAS sem login -> {r}")
    resultados.append(espera("ERRO;NAO_LOGADO" in r, "comando antes do login -> ERRO;NAO_LOGADO"))

    # 3.2 nickname duplicado -> NICKNAME_EM_USO
    envia(s, "LOGIN;ana"); le(s)
    s2 = conecta()
    envia(s2, "LOGIN;ana")
    r = le(s2)
    print(f"   LOGIN;ana duplicado -> {r}")
    resultados.append(espera("ERRO;NICKNAME_EM_USO" in r, "nick repetido -> ERRO;NICKNAME_EM_USO"))

    # 3.3 modo invalido -> MODO_INVALIDO
    envia(s2, "LOGIN;bia"); le(s2)
    envia(s2, "ENTRAR_MESA;3")
    r = le(s2)
    print(f"   ENTRAR_MESA;3 -> {r}")
    resultados.append(espera("ERRO;MODO_INVALIDO" in r, "modo invalido -> ERRO;MODO_INVALIDO"))

    # 3.4 comando desconhecido -> MENSAGEM_INVALIDA
    envia(s2, "XPTO_NAO_EXISTE")
    r = le(s2)
    print(f"   XPTO_NAO_EXISTE -> {r}")
    resultados.append(espera("ERRO;MENSAGEM_INVALIDA" in r, "comando desconhecido -> ERRO;MENSAGEM_INVALIDA"))

    # 3.5 jogar fora de turno / carta invalida (precisa de partida em andamento)
    #     ana e bia entram numa mesa nova de 2
    envia(s, "ENTRAR_MESA;2"); le(s)
    envia(s2, "ENTRAR_MESA;2"); le(s2); le(s)
    # descobrir quem NAO eh a vez apos o corte
    envia(s2, "CORTAR;DESCER")  # contra-pe em 2 jogadores eh o 2o a entrar? tentamos ambos
    ini_s = le(s); ini_s2 = le(s2)
    # tenta cortar pelo outro se ainda em fase de corte
    if not any(m.startswith("INICIO_PARTIDA") for m in ini_s + ini_s2):
        envia(s, "CORTAR;DESCER")
        ini_s = le(s); ini_s2 = le(s2)
    todas = ini_s + ini_s2
    ini = next((m for m in todas if m.startswith("INICIO_PARTIDA")), None)
    if ini:
        vez = ini.split(";")[2]
        # quem nao eh a vez tenta jogar -> FORA_DE_TURNO
        fora = s2 if vez == "ana" else s   # supondo s=ana, s2=bia
        # obtem a mao de quem esta fora pela sua propria INICIO_PARTIDA
        minha = next((m for m in (ini_s2 if fora is s2 else ini_s) if m.startswith("INICIO_PARTIDA")), None)
        carta = minha.split(";")[1].split(",")[0] if minha else "AP"
        envia(fora, f"JOGAR_CARTA;{carta}")
        r = le(fora)
        print(f"   JOGAR fora da vez -> {r}")
        resultados.append(espera(any("FORA_DE_TURNO" in m for m in r),
                                 "jogar fora da vez -> ERRO;FORA_DE_TURNO"))
        # quem eh a vez joga carta inexistente -> CARTA_INVALIDA
        davez = s if fora is s2 else s2
        envia(davez, "JOGAR_CARTA;ZZ")
        r = le(davez)
        print(f"   JOGAR carta inexistente -> {r}")
        resultados.append(espera(any("CARTA_INVALIDA" in m for m in r),
                                 "jogar carta que nao tem -> ERRO;CARTA_INVALIDA"))
    else:
        print("   [aviso] nao consegui iniciar a partida para testar FORA_DE_TURNO/CARTA_INVALIDA")

    s.close(); s2.close()
    return all(resultados)


def main():
    print("# TESTES FUNCIONAIS - Truco Mineiro Online")
    print(f"# alvo: {HOST}:{PORTA}")
    ok2 = cenario_desconexao()
    ok3 = cenario_erros()
    print("\n=== RESUMO ===")
    print(f"Cenario 2 (desconexao inesperada): {'PASS' if ok2 else 'FALHA'}")
    print(f"Cenario 3 (tratamento de erros):   {'PASS' if ok3 else 'FALHA'}")
    print("\nTodos os cenarios OK." if (ok2 and ok3) else "\nAlgum cenario falhou - ver acima.")


if __name__ == "__main__":
    main()
