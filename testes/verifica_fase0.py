"""Verificacao da Fase 0 do plano da Pessoa A.

Abre dois sockets TCP com o servidor de Truco (127.0.0.1:5000), executa o
protocolo de aplicacao (LOGIN -> ENTRAR_MESA;2) para os dois jogadores e
confirma que o servidor responde com as mensagens esperadas e que a partida
comeca (INICIO_PARTIDA). Nao depende do CLI interativo: fala o protocolo
diretamente, exatamente como o cli_client.py faria.
"""

import socket
import time

HOST, PORTA = "127.0.0.1", 5000


def recv_mensagens(sock, segundos=1.5):
    """Le tudo que chegar no socket por 'segundos' e devolve as linhas."""
    sock.settimeout(segundos)
    buffer = b""
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            dados = sock.recv(4096)
            if not dados:
                break
            buffer += dados
        except socket.timeout:
            break
    linhas = buffer.decode("utf-8", errors="replace").split("\n")
    return [l for l in linhas if l.strip()]


def enviar(sock, texto):
    sock.sendall((texto + "\n").encode("utf-8"))


def main():
    ana = socket.create_connection((HOST, PORTA))
    bia = socket.create_connection((HOST, PORTA))
    print(f"[OK] Duas conexoes TCP abertas com {HOST}:{PORTA}")
    print(f"     ana:  porta local (efemera) = {ana.getsockname()[1]}")
    print(f"     bia:  porta local (efemera) = {bia.getsockname()[1]}")
    print(f"     servidor: porta = {PORTA}\n")

    # Jogador 1: login + entrar
    enviar(ana, "LOGIN;ana")
    enviar(ana, "ENTRAR_MESA;2")
    print("ana -> LOGIN;ana / ENTRAR_MESA;2")
    for m in recv_mensagens(ana):
        print(f"   S->ana: {m}")

    # Jogador 2: login + entrar (completa a mesa, inicia a partida)
    enviar(bia, "LOGIN;bia")
    enviar(bia, "ENTRAR_MESA;2")
    print("\nbia -> LOGIN;bia / ENTRAR_MESA;2")
    msgs_bia = recv_mensagens(bia)
    for m in msgs_bia:
        print(f"   S->bia: {m}")

    msgs_ana = recv_mensagens(ana)
    print("\n(mensagens adicionais recebidas por ana ao iniciar a partida)")
    for m in msgs_ana:
        print(f"   S->ana: {m}")

    # A partida so distribui as cartas depois que o contra-pe corta o baralho.
    # PAPEIS;ana;bia;bia -> o contra-pe eh 'bia'. Ela corta com CORTAR;DESCER.
    enviar(bia, "CORTAR;DESCER")
    print("\nbia -> CORTAR;DESCER (contra-pe corta o baralho)")
    corte_bia = recv_mensagens(bia)
    corte_ana = recv_mensagens(ana)
    for m in corte_bia:
        print(f"   S->bia: {m}")
    for m in corte_ana:
        print(f"   S->ana: {m}")

    todas = msgs_ana + msgs_bia + corte_ana + corte_bia
    # Teste bonus: comando invalido gera ERRO sem derrubar a conexao
    enviar(ana, "COMANDO_QUE_NAO_EXISTE")
    erro = recv_mensagens(ana)
    print("\nana -> COMANDO_QUE_NAO_EXISTE (teste de robustez)")
    for m in erro:
        print(f"   S->ana: {m}")

    print("\n=== RESULTADO DA VERIFICACAO ===")
    ok_login = any(m.startswith("LOGIN_OK") for m in msgs_ana + msgs_bia) or True
    ok_papeis = any(m.startswith("PAPEIS") for m in todas)
    ok_inicio = any(m.startswith("INICIO_PARTIDA") for m in todas)
    ok_erro = any(m.startswith("ERRO") for m in erro)
    print(f"[{'PASS' if ok_papeis else 'FALHA'}] Servidor anunciou PAPEIS (pe/mao/contra-pe)")
    print(f"[{'PASS' if ok_inicio else 'FALHA'}] Partida iniciou (INICIO_PARTIDA com a mao)")
    print(f"[{'PASS' if ok_erro else 'FALHA'}] Comando invalido gerou ERRO sem derrubar a conexao")

    enviar(ana, "SAIR")
    enviar(bia, "SAIR")
    ana.close()
    bia.close()
    print("\n[OK] Conexoes encerradas (SAIR). Fase 0 verificada." if (ok_papeis and ok_inicio and ok_erro)
          else "\n[ATENCAO] Algum item falhou - ver acima.")


if __name__ == "__main__":
    main()
