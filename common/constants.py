"""Constantes do protocolo de aplicação do Truco Mineiro."""

# Cliente -> Servidor
LOGIN = "LOGIN"
# autenticação por conta (opcional — LOGIN;nickname avulso continua existindo
# sem mudança nenhuma, pra visitantes e bots): REGISTRAR cria a conta (e já
# loga), ENTRAR_CONTA loga numa conta existente.
REGISTRAR = "REGISTRAR"
ENTRAR_CONTA = "ENTRAR_CONTA"
LISTAR_MESAS = "LISTAR_MESAS"
ENTRAR_MESA = "ENTRAR_MESA"
JOGAR_CARTA = "JOGAR_CARTA"
TRUCO = "TRUCO"
ACEITAR = "ACEITAR"
CORRER = "CORRER"
AUMENTAR = "AUMENTAR"
CORTAR = "CORTAR"
DECIDIR_MAO_10 = "DECIDIR_MAO_10"
SAIR = "SAIR"
CHAT = "CHAT"

# Servidor -> Cliente
LOGIN_OK = "LOGIN_OK"
MESAS = "MESAS"
MESA_STATUS = "MESA_STATUS"
PAPEIS = "PAPEIS"
PEDIDO_CORTE = "PEDIDO_CORTE"
MAO_ESPECIAL = "MAO_ESPECIAL"
INICIO_PARTIDA = "INICIO_PARTIDA"
CARTAS_PARCEIROS = "CARTAS_PARCEIROS"
ESTADO_RODADA = "ESTADO_RODADA"
RESULTADO_RODADA = "RESULTADO_RODADA"
RESULTADO_MAO = "RESULTADO_MAO"
PEDIDO_TRUCO = "PEDIDO_TRUCO"
FIM_PARTIDA = "FIM_PARTIDA"
JOGADOR_SAIU = "JOGADOR_SAIU"
ERRO = "ERRO"

# Direção do corte do baralho (CORTAR;direcao)
CORTE_DESCER = "DESCER"  # pega de cima, distribui na ordem embaralhada
CORTE_SUBIR = "SUBIR"  # pega de baixo, distribui na ordem invertida

# Decisão da equipe na mão de 10 (DECIDIR_MAO_10;decisao)
DECISAO_JOGAR = "JOGAR"
DECISAO_CORRER = "CORRER"

# Tipos de mão especial (MAO_ESPECIAL;tipo;...)
TIPO_MAO_DE_10 = "MAO_DE_10"
TIPO_MAO_DE_FERRO = "MAO_DE_FERRO"

# Modos de jogo suportados (número de jogadores)
MODOS_SUPORTADOS = (2, 4, 6, 8)

# Convenção de nickname (não faz parte do protocolo em si) usada por todo
# bot pra se identificar: permite ao servidor reconhecer mesas que só têm
# bots (sem nenhum humano) e desfazê-las quando o último humano sai.
PREFIXO_NICKNAME_BOT = "Bot"

# Valores de aposta
VALOR_INICIAL = 2
VALOR_TRUCO = 4
VALOR_SEIS = 6
VALOR_NOVE = 10
VALOR_DOZE = 12

PONTUACAO_VITORIA = 12

# Pontuação a partir da qual a mão de 10 (ou mão de ferro, se ambas) entra em vigor
PONTUACAO_MAO_ESPECIAL = 10

# Pontos cedidos pela equipe da mão de 10 quando ela escolhe correr
VALOR_MAO_DE_10_CORRER = VALOR_INICIAL
# Pontos ganhos pelo adversário quando a equipe da mão de 10 joga e perde
VALOR_MAO_DE_10_DERROTA = 4

# Motivos de erro padronizados (ERRO;motivo)
ERRO_NICKNAME_EM_USO = "NICKNAME_EM_USO"
ERRO_EMAIL_EM_USO = "EMAIL_EM_USO"
ERRO_EMAIL_INVALIDO = "EMAIL_INVALIDO"
ERRO_SENHA_FRACA = "SENHA_FRACA"
ERRO_CREDENCIAIS_INVALIDAS = "CREDENCIAIS_INVALIDAS"
ERRO_NAO_LOGADO = "NAO_LOGADO"
ERRO_MODO_INVALIDO = "MODO_INVALIDO"
ERRO_MESA_CHEIA = "MESA_CHEIA"
ERRO_JA_EM_MESA = "JA_EM_MESA"
ERRO_NAO_EM_MESA = "NAO_EM_MESA"
ERRO_FORA_DE_TURNO = "FORA_DE_TURNO"
ERRO_CARTA_INVALIDA = "CARTA_INVALIDA"
ERRO_APOSTA_INVALIDA = "APOSTA_INVALIDA"
ERRO_PARTIDA_NAO_INICIADA = "PARTIDA_NAO_INICIADA"
ERRO_PARTIDA_FINALIZADA = "PARTIDA_FINALIZADA"
ERRO_MENSAGEM_INVALIDA = "MENSAGEM_INVALIDA"
ERRO_TRUCO_BLOQUEADO = "TRUCO_BLOQUEADO"
ERRO_NAO_E_CONTRAPE = "NAO_E_CONTRAPE"
ERRO_NAO_E_EQUIPE_DECISORA = "NAO_E_EQUIPE_DECISORA"
ERRO_FASE_INVALIDA = "FASE_INVALIDA"
