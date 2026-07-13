# Rascunho — Seção "Testes e Análise de Tráfego" (para o relatório SBC)

Texto pronto para a Pessoa B encaixar no relatório final. As figuras marcadas
com `[FIGURA N]` correspondem aos prints salvos em `capturas/prints/` (a serem
coletados na Fase 2). Ajuste a numeração das figuras conforme o restante do
relatório.

---

## Testes e Análise de Tráfego

Esta seção documenta os testes realizados sobre a aplicação de Truco Mineiro
Online e a análise do tráfego TCP capturado com o Wireshark. Todos os testes
foram executados em ambiente local (`127.0.0.1`), com o servidor escutando na
porta **5000** e os clientes utilizando portas efêmeras atribuídas pelo
sistema operacional.

### Metodologia

O tráfego foi capturado na interface *Adapter for loopback traffic capture*
(Npcap), necessária para observar comunicação em `127.0.0.1` no Windows,
aplicando o filtro de exibição `tcp.port == 5000`. Para gerar uma sessão
reprodutível e limpa foi utilizado o script `testes/gera_trafego.py`, que
estabelece duas conexões (jogadores *ana* e *bia*), executa o fluxo completo
do protocolo (registro, entrada em mesa, corte, distribuição e jogada) e
encerra as conexões — cobrindo, em uma única captura, a abertura, a troca de
dados e o encerramento das conexões.

### Análise no Wireshark

**Estabelecimento da conexão (Three-Way Handshake).** A conexão TCP inicia-se
com o *three-way handshake*: o cliente envia um segmento `SYN`, o servidor
responde com `SYN, ACK` e o cliente confirma com `ACK`. Esse mecanismo
sincroniza os números de sequência iniciais de cada lado e estabelece a
conexão antes de qualquer dado da aplicação ser trocado, evidenciando a
natureza **orientada a conexão** do TCP.

`[FIGURA 1 — Three-Way Handshake: SYN → SYN,ACK → ACK entre a porta efêmera do cliente e a porta 5000 do servidor]`

**Portas de origem e destino (multiplexação).** O servidor mantém uma porta
fixa e bem conhecida pela aplicação (**5000**), enquanto cada cliente recebe
uma porta de origem **efêmera** distinta (por exemplo, 51394 e 51395 em
execuções observadas). É essa combinação (IP origem, porta origem, IP destino,
porta destino) que identifica unicamente cada conexão, permitindo ao servidor
atender **múltiplos clientes simultâneos** sobre a mesma porta 5000 —
conceito de **multiplexação** da camada de transporte.

`[FIGURA 2 — Detalhe do cabeçalho TCP mostrando Source Port (efêmera) e Destination Port 5000]`

**Mensagens do protocolo de aplicação.** Como o protocolo é textual (formato
`TIPO;campo1;campo2\n`), o conteúdo das mensagens é diretamente legível na
opção *Follow → TCP Stream* do Wireshark. Observam-se as mensagens definidas
pelo grupo, como `LOGIN;ana`, `ENTRAR_MESA;2`, `INICIO_PARTIDA;...`,
`JOGAR_CARTA;KE` e `RESULTADO_RODADA;...`, demonstrando a correspondência
direta entre o protocolo especificado e os bytes efetivamente transmitidos.

`[FIGURA 3 — Follow TCP Stream exibindo as mensagens do protocolo em texto]`

**Troca efetiva de dados.** Os segmentos que carregam dados da aplicação
aparecem com a flag `PSH, ACK` e comprimento de payload não nulo (`Len > 0`),
enquanto os segmentos de confirmação puros surgem como `ACK` com `Len=0`.
A alternância entre requisições do cliente e respostas do servidor evidencia
a comunicação bidirecional e o mecanismo de **entrega confiável** do TCP (todo
segmento de dados é reconhecido por um ACK).

`[FIGURA 4 — Troca cliente↔servidor: segmentos PSH,ACK com dados e seus ACKs]`

**Encerramento da conexão.** Ao final da sessão, a conexão é encerrada com a
troca de segmentos `FIN, ACK` / `ACK`, liberando os recursos de ambos os
lados de forma ordenada.

`[FIGURA 5 — Encerramento da conexão TCP (FIN, ACK)]`

### Análise Funcional

Os cenários abaixo foram automatizados nos scripts `testes/testes_funcionais.py`,
`testes/gera_trafego.py` e `testes/verifica_fase0.py`, cujas saídas completas
estão em `logs_testes/`.

**Cenário 1 — Uso normal.** Duas conexões realizam o fluxo completo: registro
(`LOGIN`/`LOGIN_OK`), entrada em mesa (`ENTRAR_MESA` → `MESA_STATUS`),
anúncio de papéis (`PAPEIS`), corte do baralho (`CORTAR` → `INICIO_PARTIDA`)
e jogadas (`JOGAR_CARTA` → `RESULTADO_RODADA`), até o fim da partida
(`FIM_PARTIDA`). O comportamento observado corresponde integralmente ao
protocolo especificado.

**Cenário 2 — Desconexão inesperada.** Um cliente foi encerrado de forma
abrupta (fechamento do socket com `RST`, simulando queda), sem enviar a
mensagem `SAIR`. O servidor **detectou a desconexão** — a chamada `recv()`
retorna vazio/erro — e notificou o outro jogador com `JOGADOR_SAIU;ana`,
permanecendo em operação e aceitando novas conexões (um cliente adicional
conseguiu se registrar em seguida). Isso demonstra o requisito de **detecção
de desconexões e robustez** do servidor.

**Cenário 3 — Tratamento de erros.** Seis situações de erro foram provocadas,
todas respondidas com uma mensagem `ERRO;<motivo>` padronizada, sem
interromper o servidor nem a conexão do cliente:

| Ação | Resposta do servidor |
|---|---|
| Comando antes do login | `ERRO;NAO_LOGADO` |
| `LOGIN` com nickname já em uso | `ERRO;NICKNAME_EM_USO` |
| `ENTRAR_MESA;3` (modo inexistente) | `ERRO;MODO_INVALIDO` |
| Comando desconhecido | `ERRO;MENSAGEM_INVALIDA` |
| Jogar fora do próprio turno | `ERRO;FORA_DE_TURNO` |
| Jogar carta que não está na mão | `ERRO;CARTA_INVALIDA` |

**Limitações encontradas.**
1. **Ausência de reconexão:** um jogador que cai no meio da partida não pode
   retornar à mesma mão; a mesa fica comprometida e não há substituição
   automática.
2. **Estado apenas em memória:** o registro de nicknames e mesas não é
   persistido; ao reiniciar o servidor, todo o estado é perdido.
3. **Comunicação sem criptografia:** o protocolo trafega em texto puro
   (visível no Wireshark), o que é didaticamente conveniente porém inadequado
   a um ambiente de produção — uma evolução natural seria o uso de TLS.
4. **Listagem orientada a mesas:** em vez de uma lista global de usuários, a
   aplicação expõe a lista de **mesas** (`LISTAR_MESAS`), decisão adequada ao
   domínio do jogo, mas que difere do exemplo genérico do enunciado.

### Relação com os conceitos da disciplina

Os testes evidenciam, na prática, conceitos centrais estudados: o
**estabelecimento e o encerramento orientados a conexão** do TCP (handshake e
FIN), a **multiplexação/demultiplexação** por portas (uma porta de servidor
atendendo várias conexões identificadas por portas efêmeras distintas), a
**entrega confiável** (segmentos de dados sempre reconhecidos por ACKs) e o
tratamento do TCP como um **fluxo de bytes** — que motivou, na aplicação, o
enquadramento de mensagens por delimitador (`\n`) implementado no
`MessageReader`, garantindo que mensagens fragmentadas ou concatenadas em um
mesmo segmento sejam remontadas corretamente.
