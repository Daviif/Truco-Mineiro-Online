# Evidências — Pessoa A (Análise de Tráfego + Testes)

Documento de registro das evidências coletadas pela Pessoa A, fase a fase.
Serve de matéria-prima para as seções "Testes e Análise de Tráfego" e
"Limitações" do relatório SBC. Ambiente: Windows 11, Python 3.14.0.

---

## Fase 0 — Verificação do ambiente e do protocolo ✅ (concluída)

**Objetivo:** confirmar, na prática, que o servidor sobe, aceita conexões
simultâneas, registra jogadores e conduz o início de uma partida — validando
os "comandos permitidos" e o formato do protocolo antes de gravar no Wireshark.

**Como foi verificado:** script [testes/verifica_fase0.py](../testes/verifica_fase0.py),
que abre **dois sockets TCP** com o servidor (`127.0.0.1:5000`) e fala o
protocolo de aplicação diretamente (igual ao `cli_client.py`), sem depender do
terminal interativo. Como reproduzir:

```
# Terminal 1
python server/server.py
# Terminal 2
python testes/verifica_fase0.py
```

**Saída obtida (sessão real):**

```
[OK] Duas conexoes TCP abertas com 127.0.0.1:5000
     ana:  porta local (efemera) = 57960
     bia:  porta local (efemera) = 57961
     servidor: porta = 5000

ana -> LOGIN;ana / ENTRAR_MESA;2
   S->ana: LOGIN_OK;ana
   S->ana: MESA_STATUS;2;AGUARDANDO;ana

bia -> LOGIN;bia / ENTRAR_MESA;2
   S->bia: LOGIN_OK;bia
   S->bia: MESA_STATUS;2;EM_ANDAMENTO;ana,bia
   S->bia: PAPEIS;ana;bia;bia
   S->bia: PEDIDO_CORTE;bia
   S->ana: MESA_STATUS;2;EM_ANDAMENTO;ana,bia
   S->ana: PAPEIS;ana;bia;bia
   S->ana: PEDIDO_CORTE;bia

bia -> CORTAR;DESCER (contra-pe corta o baralho)
   S->bia: INICIO_PARTIDA;7P,AE,2C;bia;2
   S->ana: INICIO_PARTIDA;AP,7E,KP;bia;2

ana -> COMANDO_QUE_NAO_EXISTE (teste de robustez)
   S->ana: ERRO;MENSAGEM_INVALIDA

=== RESULTADO DA VERIFICACAO ===
[PASS] Servidor anunciou PAPEIS (pe/mao/contra-pe)
[PASS] Partida iniciou (INICIO_PARTIDA com a mao)
[PASS] Comando invalido gerou ERRO sem derrubar a conexao
```

**Fatos confirmados (para o relatório):**

| Fato | Evidência |
|---|---|
| Servidor escuta em porta fixa **5000** | conexões aceitas em `127.0.0.1:5000` |
| Clientes usam **portas efêmeras** altas | ana=57960, bia=57961 (variam a cada execução) |
| **Conexões simultâneas** (multiplexação) | dois sockets ativos ao mesmo tempo, uma thread por cliente no servidor |
| **Registro por nickname** | `LOGIN;ana` → `LOGIN_OK;ana` |
| Protocolo é **texto**, formato `TIPO;campo;...` | todas as mensagens acima são strings legíveis |
| **Robustez**: entrada inválida não derruba o servidor | `COMANDO_QUE_NAO_EXISTE` → `ERRO;MENSAGEM_INVALIDA`, conexão segue viva |

**Descoberta relevante sobre o fluxo (importante para a captura):**
a partida **não distribui as cartas assim que a mesa enche**. A sequência real é:

```
ENTRAR_MESA (2º jogador)  ->  MESA_STATUS (EM_ANDAMENTO)
                          ->  PAPEIS (pe; mao; contra-pe)
                          ->  PEDIDO_CORTE (aguarda o contra-pe)
CORTAR;DESCER             ->  INICIO_PARTIDA (cartas distribuídas)
```

Ou seja, `INICIO_PARTIDA` só chega **depois** do `CORTAR`. Isso deve ser
mostrado e explicado na análise do Wireshark (Fase 2).

**Status do ambiente para as próximas fases:**
- ✅ Python 3.14.0 funcionando (`python`, não `python3`).
- ✅ Servidor/clientes/protocolo validados.
- ❌ **Wireshark e Npcap ainda NÃO instalados** (verificado em 13/07/2026) —
  primeiro passo da Fase 1.

---

## Fase 1 — Preparação do ambiente de captura ✅ (concluída)

**Estado do ambiente (verificado em 13/07/2026):**
- ❌ Wireshark **não instalado** (`C:\Program Files\Wireshark\` ausente).
- ❌ Npcap **não instalado** (sem driver em `System32\Npcap`, `tshark` fora do PATH).
- ✅ Gerador de tráfego pronto e **testado**: [testes/gera_trafego.py](../testes/gera_trafego.py).

### 1.1 Instalar o Wireshark + Npcap (passo manual — pendente)

1. Baixar o instalador em https://www.wireshark.org/download.html (Windows x64).
2. Executar. Durante a instalação, o Wireshark oferece instalar o **Npcap** —
   **aceitar**.
3. Na janela do **Npcap**, marcar **"Support loopback traffic capture"**
   (sem isso NÃO é possível capturar `127.0.0.1` no Windows). Deixar
   "Install Npcap in WinPcap API-compatible Mode" marcado.
4. Concluir e, se pedir, **reiniciar o PC** (o driver de loopback do Npcap às
   vezes só aparece após reiniciar).

**Verificação da instalação:** abrir o Wireshark; na lista de interfaces deve
aparecer **"Adapter for loopback traffic capture"** (ou "Npcap Loopback
Adapter"). Se não aparecer, reiniciar o PC.

### 1.2 Estratégia de captura escolhida

Como todo o sistema roda em `127.0.0.1`, usar a **captura em loopback**:
- Interface: **"Adapter for loopback traffic capture"**.
- Filtro de exibição: `tcp.port == 5000`.

_(Alternativa, se o loopback der problema: rodar servidor e cliente em duas
máquinas na mesma rede e capturar na interface Wi-Fi/Ethernet — ver
[PLANO_PESSOA_A.md](PLANO_PESSOA_A.md), Fase 1.2.)_

### 1.3 Gerar tráfego para a captura (pronto ✅)

Para não depender de digitar comandos à mão durante a gravação, use o
gerador — ele produz uma sessão pequena e completa (abertura → mensagens de
protocolo → encerramento) com **um único comando**:

```
# Terminal 1
python server/server.py
# Terminal 2 (rodar DEPOIS de iniciar a gravação no Wireshark)
python testes/gera_trafego.py
```

**Saída de referência (sessão real gerada e testada em 13/07/2026):**

```
 ana -> LOGIN;ana
     S->ana: LOGIN_OK;ana
 ana -> ENTRAR_MESA;2
     S->ana: MESA_STATUS;1;AGUARDANDO;ana
 bia -> LOGIN;bia
 bia -> ENTRAR_MESA;2
     S->bia: MESA_STATUS;1;EM_ANDAMENTO;ana,bia
     S->bia: PAPEIS;ana;bia;bia
     S->bia: PEDIDO_CORTE;bia
 bia -> CORTAR;DESCER
     S->bia: INICIO_PARTIDA;KE,AO,7C;bia;2
     S->ana: INICIO_PARTIDA;6P,QO,5C;bia;2
 bia -> JOGAR_CARTA;KE
     S->bia: ESTADO_RODADA;ana;bia:KE;2;
 ana -> JOGAR_CARTA;6P
     S->ana: RESULTADO_RODADA;bia:KE,ana:6P;1
 ana -> SAIR
 bia -> SAIR
```

Essa sessão contém tudo o que a Fase 2 precisa capturar: o **handshake** (ao
abrir os dois sockets), várias **mensagens de aplicação em texto** e o
**encerramento** (após `SAIR`).

**Verificação da Fase 1 (fazer após instalar o Wireshark):**
1. Iniciar a gravação no Wireshark na interface de loopback com filtro
   `tcp.port == 5000`.
2. Rodar `python server/server.py` e depois `python testes/gera_trafego.py`.
3. Confirmar que aparecem pacotes na captura (SYN inicial + pacotes com
   payload de texto). Se aparecer, a Fase 1 está concluída → seguir p/ Fase 2.

**Fase 1 CONCLUÍDA ✅ (13/07/2026):** Wireshark 4.6.7 instalado, interface
"Adapter for loopback traffic capture" disponível, captura em `127.0.0.1`
funcionando (confirmado tráfego porta 5000 ↔ portas efêmeras dos clientes,
com pacotes `[PSH, ACK]` carregando o payload de texto do protocolo).

---

## Fase 2 — Captura de tráfego ✅ (concluída)

Objetivo: **um `.pcap` limpo, do começo ao fim**, e **5 prints** cobrindo os
itens exigidos na seção 7 do enunciado.

### Passo a passo da captura limpa

1. No Wireshark, se houver captura rodando, **pare** (quadrado vermelho).
2. Clique na **barbatana azul (nova captura)** na interface **"Adapter for
   loopback traffic capture"** — começa uma captura nova e vazia.
3. Na barra de filtro de exibição, digite `tcp.port == 5000` e Enter.
4. **Só agora** gere o tráfego (a ordem importa — assim pega o handshake):
   ```
   # Terminal 1
   python server/server.py
   # Terminal 2
   python testes/gera_trafego.py
   ```
5. Quando o gerador imprimir "Sessao encerrada", **pare a captura** (quadrado
   vermelho).
6. Salve: **File → Save As** → `capturas/captura_truco.pcapng`.

### Os 5 prints a coletar (seção 7 do enunciado)

| # | Item | Onde/como achar | O que printar |
|---|---|---|---|
| 1 | **Three-Way Handshake** | Os 3 primeiros pacotes da captura: coluna Info mostra `[SYN]`, `[SYN, ACK]`, `[ACK]` (portas efêmera→5000). | As 3 linhas + a árvore TCP do SYN aberta (mostrando Flags). |
| 2 | **Portas origem/destino** | Qualquer pacote: painel do meio → expandir **Transmission Control Protocol** → `Source Port` / `Destination Port`. | Um pacote cliente→servidor (Dst Port **5000**) e a porta efêmera de origem. |
| 3 | **Mensagens do protocolo** | Botão direito num pacote `[PSH, ACK]` com dados → **Follow → TCP Stream**. | A janela do TCP Stream com `LOGIN;ana`, `INICIO_PARTIDA;...`, `JOGAR_CARTA;...` legíveis. |
| 4 | **Troca efetiva de dados** | No mesmo TCP Stream: texto do cliente em vermelho, do servidor em azul. | Print mostrando o vai-e-vem (pergunta/resposta). |
| 5 | **Encerramento da conexão** | Últimos pacotes da conexão: `[FIN, ACK]` / `[ACK]` (ou `[RST]`). | As linhas finais com as flags FIN. |

### Dicas
- **Legenda cada print** com 1 linha (ex.: "Fig. 3 — Three-Way Handshake: SYN
  → SYN,ACK → ACK entre a porta 51394 do cliente e a porta 5000 do servidor").
- Para achar o handshake rápido: **Statistics → Conversations → aba TCP**
  mostra cada conexão; dê duplo-clique numa para filtrar só ela.
- O encapsulamento aparece como **Null/Loopback** (normal em captura de
  loopback no Windows) — não é erro.

**Verificação da Fase 2:** `.pcap` salvo contendo SYN no início e FIN no fim,
mais os 5 prints coletados e legendados.

**Status: ✅ Concluída.** `.pcap` salvo em `capturas/captura-truco.pcapng` e os
5 prints coletados em `capturas/prints/` (`1_handshake.png`, `2_portas.png`,
`3_tcp_stream.png`, `4_troca_dados.png`, `5_encerramento.png`), cobrindo os 5
itens da tabela acima.

## Fase 3 — Testes funcionais ✅ (concluída, exceto captura de prints)

Os cenários da seção 7 do enunciado foram **executados e registrados**. Os
cenários 2 e 3 são automatizados por [testes/testes_funcionais.py](../testes/testes_funcionais.py);
o cenário 1 por [testes/gera_trafego.py](../testes/gera_trafego.py) /
[testes/verifica_fase0.py](../testes/verifica_fase0.py); o cenário 4 é análise
escrita (abaixo).

Como reproduzir:
```
python server/server.py
python testes/testes_funcionais.py
```

### Cenário 1 — Uso normal ✅
Partida de 2 jogadores do login ao fim, com corte, distribuição e jogadas —
ver saída em Fase 0/Fase 1 (mensagens `LOGIN_OK` → `MESA_STATUS` → `PAPEIS`
→ `INICIO_PARTIDA` → `JOGAR_CARTA` → `RESULTADO_RODADA`). Partida completa
até `FIM_PARTIDA` também já observada (dois bots jogando).

### Cenário 2 — Desconexão inesperada ✅
Cliente `ana` é derrubado com **fechamento abrupto do socket (RST via
SO_LINGER=0)**, simulando queda — sem enviar `SAIR`. Saída real:
```
=== CENARIO 2: DESCONEXAO INESPERADA ===
   ana e bia numa mesa, partida em andamento.
   -> ana CAI (fechamento abrupto do socket, sem SAIR)
      S->bia: JOGADOR_SAIU;ana
   [PASS] servidor detectou a queda e avisou bia com JOGADOR_SAIU
   [PASS] servidor continuou no ar (novo cliente logou apos a queda)
```
**Conclusão:** o servidor detecta a desconexão (o `recv()` retorna vazio /
erro de socket em [server/client_session.py:27](../server/client_session.py#L27)),
executa `_desconectar()` avisando os demais com `JOGADOR_SAIU`, e **continua
no ar** aceitando novas conexões. (Requisito "detectar desconexões", seção 5.)

### Cenário 3 — Tratamento de erros ✅
Seis erros provocados, todos respondidos com `ERRO;<motivo>` **sem derrubar o
servidor nem a conexão**. Saída real:
```
   LISTAR_MESAS sem login  -> ERRO;NAO_LOGADO
   LOGIN;ana duplicado     -> ERRO;NICKNAME_EM_USO
   ENTRAR_MESA;3           -> ERRO;MODO_INVALIDO
   XPTO_NAO_EXISTE         -> ERRO;MENSAGEM_INVALIDA
   JOGAR fora da vez       -> ERRO;FORA_DE_TURNO
   JOGAR carta inexistente -> ERRO;CARTA_INVALIDA
```
**Conclusão:** entradas inválidas geram resposta de erro padronizada e a
sessão segue viva (requisito "tratar falhas de comunicação", seção 5).

### Cenário 4 — Limitações encontradas
Limitações reais identificadas (honestas — o FAQ do enunciado valoriza isto):

1. **Sem reconexão à partida:** se um jogador cai no meio da mão, ele avisa
   `JOGADOR_SAIU` mas não há como voltar à mesma partida; a mesa fica
   comprometida. Não há timeout/substituição por bot no lugar do que caiu.
2. **Nickname não persiste:** o registro é só em memória (dicionário no
   servidor); ao reiniciar o servidor, tudo se perde. Não há cadastro/senha
   no fluxo básico (há um bônus de autenticação separado no projeto).
3. **Sem criptografia:** o protocolo trafega em **texto puro** (visível no
   Wireshark). Ótimo para a análise didática, mas inseguro em rede real —
   um bônus possível seria TLS.
4. **`LISTAR_MESAS` não é "lista de usuários" pura:** o enunciado fala em
   listar usuários conectados; aqui a listagem é por **mesas** (id/modo/
   ocupação/status), adequada ao jogo, mas é uma adaptação a registrar.
5. **Encerramento por porta única:** cada `web_bridge.py` usa uma porta HTTP
   fixa (8080); para vários jogadores web simultâneos na mesma máquina é
   preciso subir cada bridge numa porta diferente.

**Verificação da Fase 3:** os 3 cenários automatizáveis retornam PASS e a
lista de limitações está escrita. ✅

---

## Resumo do progresso da Pessoa A

| Fase | Status |
|---|---|
| 0 — Verificação do ambiente/protocolo | ✅ Concluída |
| 1 — Preparação da captura (Wireshark/Npcap) | ✅ Concluída |
| 2 — Captura de tráfego (.pcap + 5 prints) | ✅ Concluída |
| 3 — Testes funcionais (4 cenários) | ✅ Concluída (executados e registrados) |

**Pendências manuais da Pessoa A:** nenhuma — todas as fases (0 a 4) estão
executadas e registradas neste arquivo.

## Fase 4 — Consolidação e entrega para a Pessoa B ✅ (concluída)

Artefatos organizados e prontos para o relatório:

- **Scripts de teste** (reproduzíveis): [testes/verifica_fase0.py](../testes/verifica_fase0.py),
  [testes/gera_trafego.py](../testes/gera_trafego.py),
  [testes/testes_funcionais.py](../testes/testes_funcionais.py).
- **Logs de evidência** (saídas reais): `logs_testes/cenario_1_uso_normal.txt`,
  `logs_testes/cenarios_2_e_3_erros_desconexao.txt`.
- **Pasta de capturas**: `capturas/` (com `README.md` indicando onde salvar o
  `.pcap` e os 5 prints) — a preencher na Fase 2.
- **Texto pronto do relatório**: [docs/RELATORIO_SECAO_TESTES.md](RELATORIO_SECAO_TESTES.md)
  — seção "Testes e Análise de Tráfego" + "Limitações" + "Relação com os
  conceitos da disciplina", com marcadores `[FIGURA N]` para os prints.

**Handoff para a Pessoa B:** a seção de testes/tráfego está redigida e só
depende das 5 figuras da Fase 2 para ficar completa. A Pessoa B pode já
incorporar o texto ao relatório SBC e encaixar as figuras quando a Pessoa A
coletar os prints.
