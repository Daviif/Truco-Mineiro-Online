# Bots de IA — Busca Competitiva (Minimax, Alfa-Beta e Decisão sob Incerteza)

Este documento descreve a estratégia usada pelos bots em `bot/`, no
contexto da unidade "Busca Competitiva — Jogos, Minimax, Poda Alfa-Beta e
Decisão Estratégica" (CSI457/CSI701 — IA).

## 1. O truco como problema de busca competitiva

Um jogo competitivo determinístico, por turnos e de soma zero pode ser
formulado como `⟨S, s0, Players, Actions, Result, Terminal, Utility⟩`. Para
uma **rodada** de truco (uma carta na mesa por jogador), isso mapeia direto:

- `S`: combinações de cartas já jogadas na rodada/mão atual;
- `Players`: os jogadores da mesa (2, 4, 6 ou 8);
- `Actions(s)`: as cartas que ainda restam na mão de quem tem a vez;
- `Result(s, a)`: estado depois da jogada (e, se completar a rodada, depois
  de resolvê-la);
- `Terminal(s)`: a mão termina quando `resolver_mao` (`server/game.py`)
  decide um vencedor (2 ou 3 rodadas resolvidas);
- `Utility(s)`: `+1` se minha equipe venceu a mão, `-1` se a equipe
  adversária venceu.

Mesmo com 4, 6 ou 8 jogadores, a equipe de cada jogador é sempre **0 ou
1** (`posicao % 2`), então o jogo continua cabendo no molde de dois
agentes: cada jogada é um nó **MAX** (se for de um jogador da minha equipe)
ou **MIN** (se for da equipe adversária) — exatamente a estrutura de
árvore de jogo MAX/MIN do material, só que com mais "assentos" alternando
entre os dois mesmos papéis.

## 2. O obstáculo: informação imperfeita

Minimax puro pressupõe **informação perfeita**: para calcular
`V(Result(s, a))` é preciso conhecer o estado resultante de verdade. No
truco, o bot só vê a própria mão e as cartas já jogadas — a mão dos
adversários é oculta. Isso é exatamente o caso citado no material como
"jogos com incerteza" (pôquer, informação oculta): a solução ali sugerida é
tratar o desconhecido como uma distribuição de crença e raciocinar em
termos de valor esperado.

## 3. A solução: Minimax + Alfa-Beta sobre determinizações (PIMC)

Implementado em `bot/estrategia.py`, função `escolher_carta`:

1. **Determinização**: a partir do que é público (minha mão + cartas já
   jogadas nesta mão por todos), calcula-se o conjunto de cartas
   *desconhecidas* (o resto do baralho do modo). Sorteia-se uma distribuição
   plausível dessas cartas entre os adversários, respeitando quantas cartas
   cada um ainda tem na mão. Isso transforma o jogo de informação oculta em
   um jogo comum de **informação perfeita**.
2. **Minimax + poda Alfa-Beta**: dentro de cada amostra (sorteio), resolve-se
   a árvore exatamente como no material — `α` e `β` cortam ramos que não
   podem mudar a decisão do nó pai. As cartas candidatas são ordenadas da
   mais forte para a mais fraca antes de explorar (heurística de
   ordenação de movimentos), o que aumenta a poda em ambos os tipos de nó.
3. **Repetição e agregação**: o passo 1–2 se repete `AMOSTRAS_DETERMINIZACAO`
   vezes (padrão: 24); o valor de cada carta candidata é a média entre as
   amostras. A carta escolhida é a de maior valor médio — a jogada mais
   robusta considerando todas as distribuições plausíveis da mão
   adversária, não uma aposta em um único cenário.

### Árvores grandes: corte de profundidade + avaliação heurística

No início de uma mão em modos de 6/8 jogadores, a árvore completa (até 24
jogadas) é grande demais para resolver exatamente em todas as amostras. A
busca usa a mesma ideia do material para jogos grandes (xadrez, damas, Go):
corta-se a busca numa profundidade máxima (`PROFUNDIDADE_MAXIMA`, padrão
10) e, ao atingi-la, usa-se uma função de avaliação heurística
`Eval(s) ≈ Utility(s)` em vez do valor exato — a diferença entre a força
normalizada das cartas que sobraram para a minha equipe e para a equipe
adversária. Quando a mão tem poucas jogadas restantes (2 e 4 jogadores, ou
o fim de uma mão de 6/8), a árvore é pequena o bastante para ser resolvida
até o fim, sem precisar da heurística.

## 4. Decisões de aposta: heurística, não busca

Truco, aceitar, correr, aumentar, mão de 10 e corte do baralho **não**
passam pela busca Minimax — são decididos por uma heurística simples de
"força da mão" (`avaliar_forca_mao`): combina a força normalizada da melhor
carta, um peso menor para as demais e um bônus por manilha. A decisão
compara essa força com limiares fixos (`LIMIAR_CHAMAR_TRUCO`,
`LIMIAR_AUMENTAR`, `LIMIAR_ACEITAR`, `LIMIAR_JOGAR_MAO_10`).

Por quê não busca também aqui? Modelar corretamente a resposta do
adversário a um pedido de aposta exigiria estimar a estratégia (e o blefe)
dele — um problema de teoria dos jogos bem mais amplo que o escopo de
Minimax/Alfa-Beta do curso. A heurística é uma simplificação deliberada,
documentada aqui para deixar clara a fronteira do que é busca adversarial
"de livro" e o que é regra de bolso.

O corte do baralho (`decidir_corte`) é deliberadamente aleatório: o
contra-pé não tem nenhuma informação que torne subir ou descer
melhor que o outro.

## 5. Mão de ferro: não há decisão possível

Na mão de ferro as cartas são viradas — nem o próprio jogador sabe o valor
delas até a revelação. Como não existe informação alguma para embasar
busca ou heurística, o bot joga **às cegas**, por posição sorteada
uniformemente entre as cartas restantes (`ClienteBot._agir_se_for_minha_vez`,
ramo `mao_de_ferro_ativa`).

## 6. Arquitetura

- `bot/estrategia.py`: lógica pura (sem rede). Reusa `forca_carta`,
  `resolver_mao`, `montar_baralho` e `MANILHAS_POR_MODO` direto de
  `server/game.py` — as regras de comparação de cartas não são duplicadas,
  só a simulação da progressão da rodada/mão é reimplementada (de forma
  hipotética, sobre estados sorteados, sem tocar a partida real).
- `bot/cliente_bot.py`: um cliente TCP de verdade, no mesmo molde de
  `client/cli_client.py` e `client/web_bridge.py` — fala o protocolo de
  `common/protocol.py` normalmente; a única diferença é que decide as
  jogadas chamando `bot.estrategia` em vez de esperar entrada de um humano.

## 7. Limitação de coordenação em equipe (corrigida)

Em 4/6/8 jogadores, cada equipe tem 2 ou mais jogadores, e o servidor avisa
**todos** os membros da equipe sobre um `PEDIDO_TRUCO` ou uma
`MAO_ESPECIAL` pendente. Sem cuidado, cada bot da equipe tentaria responder
e o segundo (mais lento) seria rejeitado pelo servidor com
`APOSTA_INVALIDA`/`FASE_INVALIDA` (o pedido já teria sido resolvido pelo
primeiro). Isso não corrompe o estado do jogo, mas é uma resposta errada.

A correção (`ClienteBot._sou_responsavel_pela_equipe`) faz cada bot decidir
sozinho, sem combinar com o companheiro, que só quem tem a **menor posição
na mesa** entre os membros da equipe responde por apostas e decisões de
equipe — todos os bots concordam nessa regra porque todos conhecem a mesma
lista de jogadores (ordem de assento), então nunca há conflito.

## 8. Como rodar

```
python3 bot/cliente_bot.py [host] [porta] [nickname] [modo]
```

Padrão: `127.0.0.1 5000 Bot<aleatório> 2`. Pode-se misturar bots com
jogadores humanos (`cli_client.py` / `web_bridge.py`) na mesma mesa — para
o servidor, um bot é só mais um cliente TCP.

Validado com partidas completas (servidor + bots reais via socket, sem
mocks) nos modos 2, 4 e 8 jogadores, incluindo escaladas de aposta até o
valor 12, corte de baralho e mão de ferro — sem nenhum erro de protocolo.

## 9. Parâmetros ajustáveis

Todos no topo de `bot/estrategia.py`:

| Parâmetro | Padrão | Efeito |
|---|---|---|
| `AMOSTRAS_DETERMINIZACAO` | 24 | Mais amostras = decisão mais robusta, porém mais lenta. |
| `PROFUNDIDADE_MAXIMA` | 10 | Profundidade da busca antes de cair na heurística. |
| `LIMIAR_CHAMAR_TRUCO` | 0.78 | Força de mão mínima para pedir truco por iniciativa própria. |
| `LIMIAR_AUMENTAR` | 0.88 | Força de mão mínima para reaumentar em vez de só aceitar. |
| `LIMIAR_ACEITAR` | 0.55 | Força de mão mínima para aceitar (abaixo disso, corre). |
| `LIMIAR_JOGAR_MAO_10` | 0.60 | Força de mão mínima para jogar a mão de 10 (abaixo, corre). |
