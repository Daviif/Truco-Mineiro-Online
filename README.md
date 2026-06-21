# Truco Mineiro Online

Aplicação cliente/servidor sobre sockets TCP que implementa o Truco
Mineiro escalável (2, 4, 6 ou 8 jogadores), desenvolvida para o Trabalho
Prático de Redes de Computadores 1 (Opção B — Aplicação em Rede).

## Requisitos

- Python 3.9+ (sem dependências externas — só biblioteca padrão).

## Estrutura do projeto

```
common/            protocolo de aplicação (encode/decode, constantes)
server/            servidor central (TCP, mesas, motor de regras do truco)
client/
  cli_client.py    cliente de terminal
  web_bridge.py    bridge web (cliente TCP real + servidor HTTP/SSE local)
  web/             página servida pelo bridge (HTML/CSS/JS)
bot/
  estrategia.py    IA dos bots (Minimax + Alfa-Beta sobre determinizações)
  cliente_bot.py   cliente TCP que joga sozinho usando bot/estrategia.py
docs/PROTOCOLO.md  especificação do protocolo de aplicação
docs/IA_BOTS.md    estratégia de busca competitiva usada pelos bots
```

## Como executar

Todos os comandos abaixo devem ser executados a partir da raiz do
repositório.

### 1. Servidor

```
python3 server/server.py [porta]
```

Porta padrão: `5000`. O servidor aceita conexões simultâneas (uma thread
por cliente) e fica escutando até ser interrompido com `Ctrl+C`.

### 2. Cliente de terminal (CLI)

```
python3 client/cli_client.py [host] [porta]
```

Padrão: `127.0.0.1 5000`. Depois de conectar, digite `ajuda` para ver os
comandos disponíveis (`login`, `mesas`, `entrar <2|4|6|8>`, `jogar <carta>`,
`cortar <subir|descer>`, `decidir <jogar|correr>`, `truco`, `aceitar`,
`correr`, `aumentar`, `sair`).

Antes de cada mão, o servidor pede para o **contra-pé** cortar o baralho
(`cortar subir` ou `cortar descer`) — quem não for o contra-pé só
acompanha. Quando uma equipe chega a 10 pontos, vira "mão de 10" (truco
bloqueado) e essa equipe usa `decidir jogar` ou `decidir correr`; se as
duas equipes chegarem a 10, é "mão de ferro" (cartas viradas — jogue por
posição, ex: `jogar 1`).

Para jogar uma partida completa, abra um terminal com o servidor e dois
(ou mais, conforme o modo) terminais com `cli_client.py`.

### 3. Cliente web (bônus de compatibilidade multiplataforma)

```
python3 client/web_bridge.py [host_servidor] [porta_servidor] [porta_http]
```

Padrão: `127.0.0.1 5000 8080`. Esse processo **é** o cliente TCP de
verdade (abre o socket com o servidor exatamente como o `cli_client.py`)
e também expõe uma página local em `http://127.0.0.1:8080` — abra essa
URL em qualquer navegador para jogar. Cada jogador deve rodar o seu
próprio `web_bridge.py` (uma porta HTTP por jogador).

### 4. Bot de IA (joga sozinho)

```
python3 bot/cliente_bot.py [host] [porta] [nickname] [modo]
```

Padrão: `127.0.0.1 5000 Bot<aleatório> 2`. O bot é um cliente TCP como
qualquer outro: conecta, entra numa mesa do modo pedido e joga
automaticamente (Minimax + Alfa-Beta sobre cartas adversárias sorteadas —
ver [`docs/IA_BOTS.md`](docs/IA_BOTS.md)). Para jogar **contra** o bot,
basta abrir a mesma mesa pelo lado humano (CLI ou web) com o **mesmo modo**
antes ou depois de iniciar o bot — quem entrar primeiro cria a mesa
"aguardando" daquele modo, e o bot/humano seguinte completa o mesmo
assento. Em modos de 4/6/8, é só somar bots e humanos até completar a mesa
(ex.: 1 humano + 3 bots para uma mesa de 4).

## Exemplo de sessão (2 jogadores, CLI)

Terminal 1:
```
python3 server/server.py
```

Terminal 2:
```
python3 client/cli_client.py
> login ana
> entrar 2
```

Terminal 3:
```
python3 client/cli_client.py
> login bia
> entrar 2
```

A partir daí o servidor distribui as mãos automaticamente e os comandos
`jogar`, `truco`, `aceitar`, `correr` e `aumentar` controlam o jogo.

## Protocolo de aplicação

Ver [`docs/PROTOCOLO.md`](docs/PROTOCOLO.md) para a especificação completa
dos tipos de mensagem, formato e exemplos de troca de mensagens.
