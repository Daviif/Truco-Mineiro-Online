# Capturas de tráfego (Pessoa A — Fase 2)

Coloque aqui os artefatos da análise de tráfego no Wireshark.

## Onde salvar o quê

- `captura_truco.pcapng` — a captura completa (do SYN ao FIN), gerada com o
  roteiro da Fase 2 (ver `docs/EVIDENCIAS_PESSOA_A.md`).
- `prints/` — os 5 prints exigidos pela seção 7 do enunciado:
  - `1_handshake.png` — Three-Way Handshake (SYN → SYN,ACK → ACK)
  - `2_portas.png` — portas de origem/destino (servidor = 5000)
  - `3_tcp_stream.png` — Follow TCP Stream com as mensagens do protocolo
  - `4_troca_dados.png` — troca cliente↔servidor (pergunta/resposta)
  - `5_encerramento.png` — encerramento da conexão (FIN,ACK)

## Como gerar o tráfego a capturar

```
# Terminal 1
python server/server.py
# Terminal 2 (depois de iniciar a gravação no Wireshark, filtro tcp.port == 5000)
python testes/gera_trafego.py
```
