# Protocolo de Aplicação — Truco Mineiro Online

Protocolo textual próprio sobre TCP, no formato sugerido pelo enunciado:
`TIPO;campo1;campo2;...`. Cada mensagem é uma linha terminada em `\n`. Os
campos são separados por `;`. Implementado em `common/protocol.py`
(codificação/decodificação) e `common/constants.py` (nomes dos tipos).

Como TCP é um fluxo de bytes sem limite de mensagem, uma única chamada de
`recv()` pode trazer 0, 1 ou várias mensagens, ou uma mensagem cortada no
meio. Por isso usamos o `MessageReader`, que bufferiza os bytes recebidos e
só devolve mensagens completas (delimitadas por `\n`).

## Representação das cartas

Uma carta é uma string `"<rank><naipe>"`, exceto os coringas. Naipes:
`P`=Paus, `C`=Copas, `E`=Espadas, `O`=Ouros. Ranks: `A,2,3,4,5,6,7,Q,J,K`
(baralho de 40, sem 8/9/10) — exceto o `10` extra de Ouros usado nos modos
de 6/8 jogadores. Coringas são `JK1` e `JK2`.

Exemplos válidos: `4P` (4 de Paus), `7C` (7 de Copas), `AE` (Ás de
Espadas), `7O` (7 de Ouros), `10O` (10 de Ouros, só nos modos de 6/8
jogadores), `JK1`/`JK2` (coringas, só nos modos de 6/8 jogadores).

## Mensagens Cliente → Servidor

| Mensagem | Campos | Finalidade |
|---|---|---|
| `LOGIN` | `nickname` | Login avulso, sem conta nem senha — só reserva o nickname pra essa conexão (usado por visitantes e bots). |
| `REGISTRAR` | `email;senha;nickname;curso` | Cria uma conta (autenticação real, bônus do TP01) e já loga — `curso` pode vir vazio, só é guardado se o email for de domínio institucional da UFOP (ver `server/contas.py`). |
| `ENTRAR_CONTA` | `email;senha` | Login numa conta já cadastrada. |
| `LISTAR_MESAS` | — | Pede a lista de mesas existentes. |
| `ENTRAR_MESA` | `modo` (2, 4, 6 ou 8) | Entra numa mesa aguardando daquele modo, ou cria uma nova. |
| `JOGAR_CARTA` | `carta` | Joga uma carta da própria mão na rodada atual. |
| `TRUCO` | — | Pede truco (primeiro nível de aposta, a partir do valor inicial). |
| `AUMENTAR` | — | Reaumenta um pedido de aposta pendente (seis/nove/doze). |
| `ACEITAR` | — | Aceita o pedido de aposta pendente (equipe adversária à solicitante). |
| `CORRER` | — | Corre do pedido de aposta pendente; a mão termina e a equipe solicitante ganha o valor anterior ao pedido. |
| `CORTAR` | `direcao` (`SUBIR` ou `DESCER`) | O contra-pé corta o baralho antes da distribuição de cada mão. |
| `DECIDIR_MAO_10` | `decisao` (`JOGAR` ou `CORRER`) | A equipe com 10+ pontos decide se joga a mão de 10 ou corre dela. |
| `SAIR` | — | Encerra a conexão de forma adequada (libera o lugar na mesa). |

## Mensagens Servidor → Cliente

| Mensagem | Campos | Finalidade |
|---|---|---|
| `LOGIN_OK` | `nickname` | Confirma o login. |
| `MESAS` | `mesas` (`id:modo:ocupação/modo:status` separados por `\|`) | Resposta a `LISTAR_MESAS`. |
| `MESA_STATUS` | `id_mesa;status;jogadores` (jogadores separados por `,`) | Estado da mesa após alguém entrar/saír. |
| `PAPEIS` | `pe;mao;contra_pe` | Anunciado no início de cada mão: quem embaralha/dá (pé), quem joga primeiro (mão) e quem corta o baralho (contra-pé). |
| `PEDIDO_CORTE` | `contra_pe` | Pede ao contra-pé para cortar o baralho (`CORTAR;SUBIR\|DESCER`) antes da distribuição. |
| `MAO_ESPECIAL` | `tipo;equipe_decisora` | `tipo` é `MAO_DE_10` (uma equipe com 10+ pontos; `equipe_decisora` decide `DECIDIR_MAO_10`) ou `MAO_DE_FERRO` (ambas com 10+; `equipe_decisora` vazio). Em ambos os casos truco fica bloqueado. |
| `INICIO_PARTIDA` | `mao;vez;valor_mao` | Início de uma mão nova: a própria mão do destinatário (`,`-separada), de quem é a vez e o valor em jogo. Na mão de ferro, vem com `?` no lugar de cada carta (oculta); o jogador joga por posição (`JOGAR_CARTA;1`, `;2` ou `;3`). |
| `CARTAS_PARCEIROS` | `parceiros` (`jogador:carta,carta,carta` separados por `\|`) | Só na mão de 10, só para o jogador-vidente (ver seção abaixo): revela a mão completa de cada parceiro. |
| `ESTADO_RODADA` | `vez;cartas_na_mesa;valor_mao;equipe_apostou` | Estado da rodada em andamento (`cartas_na_mesa` como `jogador:carta` separados por `,`). `equipe_apostou` é `0`, `1` ou vazio (ninguém apostou ainda nesta mão) — só essa equipe fica bloqueada de pedir aumento de novo; a outra pode, em qualquer momento da mão (ver seção de apostas). |
| `RESULTADO_RODADA` | `cartas;vencedor` | Resultado da rodada concluída; `vencedor` é `0`, `1` ou `EMPATE`. |
| `RESULTADO_MAO` | `vencedor;placar_equipe0;placar_equipe1` | Resultado da mão e placar atualizado. |
| `PEDIDO_TRUCO` | `equipe_solicitante;valor_pedido` | Alguém pediu truco/aumento; a equipe adversária deve responder com `ACEITAR`, `CORRER` ou `AUMENTAR`. |
| `FIM_PARTIDA` | `equipe_vencedora` | A partida acabou (alguma equipe atingiu 12 pontos). |
| `JOGADOR_SAIU` | `nickname` | Um jogador da mesa se desconectou ou saiu. |
| `ERRO` | `motivo` | Erro de protocolo ou jogada inválida (ver lista de motivos abaixo). |

Quando um jogador sai (ou cai) e não sobra nenhum humano na mesa — só
bots, identificados pelo prefixo de nickname `Bot` (`PREFIXO_NICKNAME_BOT`
em `common/constants.py`) —, o servidor desfaz a mesa e desconecta à força
os bots restantes (cada `cliente_bot.py` percebe a conexão encerrada e
termina o próprio processo sozinho). Se ainda sobrar algum humano, a mesa
continua normalmente.

## Motivos de erro (`ERRO;motivo`)

`NICKNAME_EM_USO`, `NAO_LOGADO`, `MODO_INVALIDO`, `MESA_CHEIA`,
`JA_EM_MESA`, `NAO_EM_MESA`, `FORA_DE_TURNO`, `CARTA_INVALIDA`,
`APOSTA_INVALIDA`, `PARTIDA_NAO_INICIADA`, `PARTIDA_FINALIZADA`,
`MENSAGEM_INVALIDA`, `TRUCO_BLOQUEADO` (mão de 10/ferro), `NAO_E_CONTRAPE`,
`NAO_E_EQUIPE_DECISORA`, `FASE_INVALIDA` (ex.: jogar carta antes do corte,
ou decidir a mão de 10 mais de uma vez), `EMAIL_EM_USO`, `EMAIL_INVALIDO`,
`SENHA_FRACA` (mínimo 6 caracteres), `CREDENCIAIS_INVALIDAS` (email ou
senha errados em `ENTRAR_CONTA`).

## Exemplo de troca de mensagens (2 jogadores)

```
C(ana)  -> LOGIN;ana
S       -> LOGIN_OK;ana
C(ana)  -> ENTRAR_MESA;2
S       -> MESA_STATUS;1;AGUARDANDO;ana
C(bia)  -> LOGIN;bia
S       -> LOGIN_OK;bia
C(bia)  -> ENTRAR_MESA;2
S       -> MESA_STATUS;1;EM_ANDAMENTO;ana,bia      (para ana e bia)
S       -> PAPEIS;ana;bia;bia                       (pé=ana, mão=bia, contra-pé=bia: só 2 jogadores)
S       -> PEDIDO_CORTE;bia
C(bia)  -> CORTAR;DESCER
S       -> INICIO_PARTIDA;4P,3O,5E;bia;2            (somente para ana, com a mão dela)
S       -> INICIO_PARTIDA;7O,2O,6E;bia;2            (somente para bia, com a mão dela)
C(bia)  -> JOGAR_CARTA;7O                           (bia é o "mão", joga primeiro)
S       -> ESTADO_RODADA;ana;bia:7O;2;              (para ana e bia; equipe_apostou vazio, ninguém pediu truco ainda)
C(ana)  -> JOGAR_CARTA;4P
S       -> RESULTADO_RODADA;bia:7O,ana:4P;0         (para ana e bia)
...
S       -> RESULTADO_MAO;0;2;0
S       -> PAPEIS;...                               (mão seguinte: pé passa para bia)
S       -> PEDIDO_CORTE;ana                          (corte sempre primeiro, mesmo na mão de 10/ferro)
...
C(ana)  -> CORTAR;DESCER
S       -> MAO_ESPECIAL;MAO_DE_10;0                  (só se alguém estiver com 10+; junto com INICIO_PARTIDA)
S       -> INICIO_PARTIDA;...                        (cartas já na mão; truco/jogar bloqueados até decidir)
C(...)  -> DECIDIR_MAO_10;JOGAR                       (ou CORRER)
...
S       -> FIM_PARTIDA;0
```

## Equipes

Cada jogador pertence a uma equipe (`0` ou `1`), definida pela posição de
entrada na mesa: posições pares formam a equipe `0`, ímpares a equipe `1`
(`equipe = posição % 2`). Em 2 jogadores cada um é sua própria equipe; em
4/6/8 jogadores, parceiros ficam em posições alternadas na ordem de turno
(como na disposição tradicional à mesa).

## Regras de jogo implementadas (resumo)

- Cada mão tem até 3 rodadas; quem ganha 2 rodadas (ou tem a melhor
  combinação de resultados, incluindo empates) ganha a mão. Em caso de
  empate (carta de mesmo rank, naipes diferentes — "amarrar"/"cangar"),
  não há critério de naipe: a rodada simplesmente não tem vencedor, e o
  resultado da mão cai na cascata de regras acima (quem ganhou a 1ª leva
  a mão se a 2ª empatar; se a 1ª empatar, quem ganha a 2ª leva a mão; se
  as duas primeiras empatarem, a 3ª decide; se as três empatarem, vence
  quem fez a 1ª rodada).
- Manilhas e composição do baralho variam por modo (ver `server/game.py`,
  tabelas `MANILHAS_POR_MODO` e `CARTAS_EXTRAS_POR_MODO`), conforme a
  variante mineira (sem carta "vira").
- Apostas escalam por `TRUCO` → `AUMENTAR` (seis → nove → doze). Quem
  corre concede o valor que estava em jogo antes do último pedido.
- Vitória da partida em 12 pontos.

### Pé, mão e contra-pé

A cada mão, a mesa tem três papéis fixos definidos pela posição de
assento (não pela equipe): **pé** (embaralha e dá as cartas), **mão**
(joga primeiro, é quem está à direita do pé) e **contra-pé** (corta o
baralho antes da distribuição, é quem está à esquerda do pé). A cada mão
o baralho passa para o jogador à direita do pé atual, que se torna o
novo pé (com novo mão e contra-pé decorrentes). Em 2 jogadores, mão e
contra-pé coincidem no mesmo jogador (o não-dealer).

Antes de cada distribuição, o servidor anuncia `PAPEIS` e pede o corte
com `PEDIDO_CORTE`; só o contra-pé pode responder com
`CORTAR;SUBIR` (pega de baixo) ou `CORTAR;DESCER` (pega de cima).

### Mão de 10 e mão de ferro

Quando pelo menos uma equipe atinge 10 pontos, nenhuma das duas pode
pedir truco/aumento naquela mão (`TRUCO_BLOQUEADO`):

- **Mão de 10** (só uma equipe com 10+): o corte e a distribuição
  acontecem primeiro, igual numa mão normal — só depois, com as cartas já
  na mão de cada um, o servidor manda `MAO_ESPECIAL;MAO_DE_10;equipe`
  (junto com `INICIO_PARTIDA`), e a equipe decide com
  `DECIDIR_MAO_10;JOGAR` ou `DECIDIR_MAO_10;CORRER` — já vendo o que tem
  na mão, não no escuro. Enquanto não decide, `JOGAR_CARTA`/`TRUCO` ficam
  bloqueados (`FASE_INVALIDA`).
  - Junto com `MAO_ESPECIAL`/`INICIO_PARTIDA`, o servidor manda
    `CARTAS_PARCEIROS` para **um único jogador da equipe decisora**: o
    "mão", se ele for dessa equipe; senão, o próximo jogador (em ordem de
    assento) da equipe decisora depois do "mão" — sempre existe exatamente
    um, já que as equipes se alternam a cada assento. Esse jogador vê a
    mão completa dos parceiros (a própria mão de cada um já chega junto,
    pelo `INICIO_PARTIDA` de cada um) antes da equipe decidir junto se
    joga ou corre. Não se aplica em 2 jogadores (cada um é sua própria
    equipe, sem parceiro).
  - `CORRER`: a equipe adversária ganha 2 pontos e a mão acaba — as
    cartas já tinham sido distribuídas, mas nunca chegam a ser jogadas.
  - `JOGAR` e vencer: a equipe fecha a partida em 12 pontos.
  - `JOGAR` e perder: a equipe adversária ganha 4 pontos (em vez do
    valor normal da mão) e o baralho passa.
- **Mão de ferro** (as duas equipes com 10+): o servidor manda
  `MAO_ESPECIAL;MAO_DE_FERRO;` (sem equipe decisora) e distribui as
  cartas sem revelá-las (`INICIO_PARTIDA` chega com `?,?,?` no lugar das
  cartas). O jogador joga por posição: `JOGAR_CARTA;1`, `;2` ou `;3`
  (1ª, 2ª ou 3ª carta que recebeu, sem saber o valor até ser revelada no
  `RESULTADO_RODADA`). O resto das regras de rodada/mão é igual ao normal.

## Camadas de transporte por cliente

- **CLI** (`client/cli_client.py`): cliente TCP direto, sem camadas
  intermediárias.
- **Web** (`client/web_bridge.py` + `client/web/`): o bridge é o cliente
  TCP real (fala este protocolo igual ao CLI); o navegador conversa com o
  bridge só por HTTP (POST de ações, GET `/events` via Server-Sent Events
  para receber o estado atualizado em JSON). Um único processo de bridge
  atende vários jogadores: cada navegador recebe um cookie de sessão na
  primeira visita, e o bridge abre uma conexão TCP própria por cookie —
  ou seja, várias pessoas podem usar a mesma porta/URL, cada uma com seu
  próprio login na mesa, sem precisar de um bridge por jogador.

## Autenticação de contas (bônus do TP01)

Item de bônus do enunciado. `LOGIN;nickname` (sem senha) continua existindo
do jeito que sempre esteve — contas são opcionais, aditivas, pra quem quiser
identidade de verdade (pré-requisito pro ranking, que vem numa etapa
futura). `REGISTRAR`/`ENTRAR_CONTA` persistem em SQLite
(`server/contas.py`, `server/dados/contas.db` — nunca commitado, está no
`.gitignore`):

- Senha com hash (`hashlib.pbkdf2_hmac` + salt aleatório, stdlib, sem
  bcrypt) — nunca guardada em texto puro.
- "Institucional" é decidido só pelo **domínio do email**
  (`DOMINIOS_INSTITUCIONAIS` em `server/contas.py`, ex. `ufop.edu.br`) —
  **não** prova posse real do email (exigiria confirmação por e-mail/SMTP,
  fora do escopo do bônus). `curso` só é guardado se o email for
  institucional.
- O `nickname` da conta é único globalmente (`UNIQUE` no banco) e passa a
  ser a identidade fixa do jogador — diferente do nickname avulso de hoje,
  que só precisa estar livre *naquele momento* entre as conexões ativas.
