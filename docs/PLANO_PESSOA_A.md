# Plano de Execução — Pessoa A (Análise de Tráfego + Testes Funcionais)

Runbook em fases para a parte da **Pessoa A** do Trabalho Prático de Redes 1
(Truco Mineiro Online). Cada fase é autocontida: dá pra executar em sessões
separadas. Objetivo final: entregar as **evidências técnicas** (captura
Wireshark + logs dos testes + lista de limitações) para a Pessoa B montar o
relatório SBC.

> **Fatos do sistema (confirmados no código):**
> - Servidor: `python server/server.py [porta]` — escuta em `0.0.0.0:5000`
>   (padrão), **uma thread por cliente** (conexões simultâneas),
>   `Ctrl+C` encerra. Ref: [server/server.py:48](../server/server.py#L48).
> - Cliente CLI: `python client/cli_client.py [host] [porta]` — conecta em
>   `127.0.0.1:5000` (padrão). Ref: [client/cli_client.py:132](../client/cli_client.py#L132).
> - Protocolo: **texto puro**, uma mensagem por linha `TIPO;campo;...\n`.
>   Ex.: `LOGIN;ana`, `JOGAR_CARTA;4P`. Ref: [docs/PROTOCOLO.md](PROTOCOLO.md).
> - Detecção de desconexão: servidor detecta e avisa os outros com
>   `JOGADOR_SAIU;<nick>`. Ref: [server/client_session.py:331](../server/client_session.py#L331).
> - Erros: servidor responde `ERRO;<motivo>` sem travar. 17 motivos em
>   [common/constants.py:65](../common/constants.py#L65).
> - **Windows:** usar `python` (não `python3`).

---

## Fase 0 — Referências e "comandos permitidos" (leia antes de tudo)

Esta é a base factual. NÃO invente comandos ou mensagens — use só os desta lista.

**Comandos para subir o sistema:**
```
python server/server.py            # Terminal 1 (servidor, porta 5000)
python client/cli_client.py        # Terminal 2 e 3 (clientes)
```

**Comandos do cliente (digitados no prompt `>` do CLI):**
`login <nick>`, `mesas`, `entrar <2|4|6|8>`, `jogar <carta>`,
`cortar <subir|descer>`, `decidir <jogar|correr>`, `truco`, `aceitar`,
`correr`, `aumentar`, `sair`, `ajuda`.

**Mensagens do protocolo que vão aparecer no Wireshark** (payload TCP, texto):
- Cliente→Servidor: `LOGIN`, `LISTAR_MESAS`, `ENTRAR_MESA`, `JOGAR_CARTA`,
  `TRUCO`, `ACEITAR`, `CORRER`, `AUMENTAR`, `CORTAR`, `DECIDIR_MAO_10`, `SAIR`.
- Servidor→Cliente: `LOGIN_OK`, `MESAS`, `MESA_STATUS`, `PAPEIS`,
  `PEDIDO_CORTE`, `INICIO_PARTIDA`, `ESTADO_RODADA`, `RESULTADO_RODADA`,
  `RESULTADO_MAO`, `PEDIDO_TRUCO`, `FIM_PARTIDA`, `JOGADOR_SAIU`, `ERRO`.

**Motivos de erro úteis para testar** (`ERRO;<motivo>`): `NICKNAME_EM_USO`,
`NAO_LOGADO`, `MODO_INVALIDO`, `FORA_DE_TURNO`, `CARTA_INVALIDA`,
`MENSAGEM_INVALIDA`, `NAO_EM_MESA`.

**Verificação da Fase 0:** você consegue subir servidor + 2 clientes, fazer
`login`/`entrar 2` em ambos e ver a partida começar. Se isso funciona, siga.

---

## Fase 1 — Preparar o ambiente de captura

**1.1 Instalar o Wireshark**
- Baixar em https://www.wireshark.org/download.html.
- Durante a instalação, **marcar a instalação do Npcap** e, na tela do Npcap,
  marcar **"Support loopback traffic capture"** (essencial — sem isso não se
  captura `127.0.0.1` no Windows).

**1.2 Escolher a estratégia de captura** (escolha UMA):
- **Opção Loopback (mais simples):** tudo na mesma máquina (`127.0.0.1`).
  No Wireshark, capturar na interface **"Adapter for loopback traffic capture"**.
- **Opção Duas máquinas (handshake mais "limpo"):** servidor num PC, cliente
  em outro na mesma rede. Rodar o cliente com o IP do servidor:
  `python client/cli_client.py <IP_DO_SERVIDOR> 5000`. Capturar na interface
  Wi-Fi/Ethernet. (O servidor já escuta em `0.0.0.0`, então aceita conexões
  externas — pode ser preciso liberar a porta 5000 no firewall.)

**1.3 Filtro de captura/exibição:** usar `tcp.port == 5000` para isolar só o
tráfego da aplicação.

**Verificação da Fase 1:** abrir o Wireshark, ver a interface escolhida
listada, e ao subir o servidor + conectar um cliente aparecerem pacotes com
o filtro `tcp.port == 5000` aplicado.

---

## Fase 2 — Capturar a análise de tráfego (item obrigatório do enunciado, seção 7)

Objetivo: um único `.pcap` que contenha, do começo ao fim, uma sessão que
demonstre os 5 itens exigidos. **Sugestão: comece a captura ANTES de conectar
o cliente** (para pegar o handshake) e pare DEPOIS do `sair` (para pegar o
encerramento).

**Roteiro da sessão a capturar:**
1. Iniciar captura no Wireshark (filtro `tcp.port == 5000`).
2. Terminal 1: `python server/server.py`.
3. Terminal 2: `python client/cli_client.py` → `login ana` → `entrar 2`.
4. Terminal 3: `python client/cli_client.py` → `login bia` → `entrar 2`.
5. Jogar algumas rodadas (`cortar descer`, `jogar <carta>`, talvez `truco`).
6. Encerrar um cliente com `sair`.
7. Parar a captura.

**O que identificar e printar no relatório (entregar à Pessoa B):**

| # | Item exigido | Como achar no Wireshark |
|---|---|---|
| 1 | **Three-Way Handshake** | Primeiros 3 pacotes da conexão: `[SYN]` → `[SYN, ACK]` → `[ACK]`. Printar as 3 linhas. |
| 2 | **Portas de origem/destino** | Coluna Source/Destination Port: servidor = **5000**; cliente = porta efêmera alta (ex.: 5xxxx). Mostrar num pacote. |
| 3 | **Mensagens do protocolo** | Clicar num pacote com dados → botão direito → **Follow → TCP Stream**. Aparecem `LOGIN;ana`, `JOGAR_CARTA;4P`, `RESULTADO_MAO;...` em texto legível. **Print do TCP Stream.** |
| 4 | **Troca efetiva de dados** | No TCP Stream, mostrar o vai-e-vem (cliente em cor, servidor em outra). Comentar o `[PSH, ACK]` carregando o payload. |
| 5 | **Encerramento da conexão** | Últimos pacotes: `[FIN, ACK]` / `[ACK]` (encerramento normal) ou `[RST]`. Printar. |

**Anti-erros (NÃO faça):**
- Não capturar na interface errada (sem loopback → 0 pacotes em localhost).
- Não esquecer de iniciar a captura ANTES de conectar (perde o handshake).
- Não confundir o handshake TCP (SYN/SYN-ACK/ACK) com o `LOGIN` da aplicação —
  são camadas diferentes; explicar isso no relatório rende ponto.

**Verificação da Fase 2:** o `.pcap` salvo contém, em ordem, handshake →
mensagens de texto do protocolo → encerramento; e você tem 5 prints (um por
item da tabela).

---

## Fase 3 — Testes funcionais documentados (enunciado, seção 7)

Executar os 4 cenários e **salvar as evidências** (print/copiar a saída dos
terminais do servidor e do cliente). Para cada cenário registrar: o que foi
feito, o que se esperava, o que aconteceu.

**Cenário 1 — Uso normal (partida completa)**
- Subir servidor + 2 clientes, jogar até `FIM_PARTIDA`.
- Evidência: log do cliente mostrando o fluxo até `[FIM DE PARTIDA] equipe X venceu`.

**Cenário 2 — Desconexão inesperada**
- No meio da partida, **fechar a janela** de um cliente (ou `Ctrl+C`), sem usar
  `sair` — simula queda.
- Esperado: o servidor detecta o socket fechado e envia `JOGADOR_SAIU;<nick>`
  aos outros; o servidor **não trava** e segue aceitando conexões.
- Evidência: log do outro cliente mostrando `[Aviso] o jogador '<nick>' saiu da mesa.`
- Ref. do mecanismo: [server/client_session.py:331](../server/client_session.py#L331).

**Cenário 3 — Tratamento de erros** (provocar vários `ERRO;<motivo>`)
- Comando antes do login → esperado `ERRO;NAO_LOGADO`.
- `login ana` em dois clientes com o mesmo nick → `ERRO;NICKNAME_EM_USO`.
- `entrar 3` (modo inválido) → `ERRO;MODO_INVALIDO`.
- `jogar 4P` fora da sua vez → `ERRO;FORA_DE_TURNO`.
- `jogar ZZ` (carta que não tem) → `ERRO;CARTA_INVALIDA`.
- Esperado geral: servidor responde o erro e **continua funcionando**.
- Evidência: log do cliente mostrando cada `[ERRO] <motivo>`.

**Cenário 4 — Limitações encontradas** (anotar honestamente — o FAQ do
enunciado diz que isso dá nota)
- Ex.: sem reconexão (quem cai não volta à mesma partida); nick não persiste
  entre execuções; sem autenticação/criptografia; se um jogador sai no meio,
  a mesa é desfeita em vez de continuar; etc.
- Anotar 3–5 limitações reais observadas durante os testes.

**Verificação da Fase 3:** você tem logs salvos dos 4 cenários e uma lista de
limitações escrita.

---

## Fase 4 — Consolidar e entregar para a Pessoa B

Organizar tudo numa pasta (ex.: `entregas/pessoa_A/`):
- ☐ `captura.pcap` (arquivo do Wireshark).
- ☐ `prints_wireshark/` — 5 imagens (handshake, portas, TCP stream/mensagens,
  troca de dados, encerramento), cada uma com uma legenda de 1 linha.
- ☐ `logs_testes/` — saída dos 4 cenários funcionais.
- ☐ `limitacoes.md` — lista das limitações observadas.
- ☐ Um parágrafo rascunho ligando o que foi visto aos conceitos de aula
  (TCP confiável, handshake, multiplexação por porta, conexões simultâneas,
  byte stream + framing por `\n`).

**Handoff:** avisar a Pessoa B que o material da seção "Testes e Análise de
Tráfego" e "Limitações" está pronto.

---

## Verificação final (checklist da Pessoa A)

- ☐ Wireshark + Npcap (loopback) instalados e captura funcionando.
- ☐ `.pcap` com handshake + mensagens do protocolo + encerramento.
- ☐ 5 prints identificando os itens da seção 7 do enunciado.
- ☐ Logs dos 4 cenários funcionais (normal, desconexão, erros, limitações).
- ☐ `limitacoes.md` com 3–5 itens reais.
- ☐ Material entregue/compartilhado com a Pessoa B.
- ☐ Você consegue **explicar na apresentação**: o que é o Three-Way Handshake,
  por que a porta do servidor é fixa (5000) e a do cliente é efêmera, e como o
  servidor detecta uma desconexão.
