(function () {
  "use strict";

  function el(id) {
    return document.getElementById(id);
  }

  function post(caminho, corpo) {
    return fetch(caminho, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo || {}),
    });
  }

  function limpar(elemento) {
    while (elemento.firstChild) elemento.removeChild(elemento.firstChild);
  }

  let meuNickname = null;

  // -- cartas: naipes, manilhas, montagem visual -----------------------------

  const NAIPES = {
    P: { simbolo: "♣", cor: "preta" },
    C: { simbolo: "♥", cor: "vermelha" },
    E: { simbolo: "♠", cor: "preta" },
    O: { simbolo: "♦", cor: "vermelha" },
  };

  const MANILHAS_POR_MODO = {
    2: ["4P", "7C", "AE", "7O"],
    4: ["4P", "7C", "AE", "7O"],
    6: ["JK1", "JK2", "10O", "7P", "4E", "4P", "7C", "AE", "7O"],
    8: ["JK1", "JK2", "10O", "9O", "8O", "7P", "4E", "4P", "7C", "AE", "7O"],
  };

  const CARTAS_POR_JOGADOR = 3;

  function ehManilha(carta, modo) {
    const lista = MANILHAS_POR_MODO[modo];
    return !!lista && lista.indexOf(carta) !== -1;
  }

  function parseCarta(carta) {
    if (carta.indexOf("JK") === 0) {
      return { curinga: true, rank: carta };
    }
    const naipeChar = carta.slice(-1);
    const rank = carta.slice(0, -1);
    const info = NAIPES[naipeChar] || { simbolo: "?", cor: "preta" };
    return { curinga: false, rank: rank, simbolo: info.simbolo, cor: info.cor };
  }

  // opts: { jogavel, onClick, mini, virada, rotuloOculto, manilha, desabilitada }
  function criarCarta(carta, opts) {
    opts = opts || {};
    const tag = opts.jogavel ? "button" : "div";
    const elCarta = document.createElement(tag);
    elCarta.className = "carta" + (opts.mini ? " carta--mini" : "");
    if (opts.manilha) elCarta.classList.add("manilha");

    if (opts.virada) {
      elCarta.classList.add("virada");
      const numero = document.createElement("span");
      numero.className = "numero-oculto";
      numero.textContent = opts.rotuloOculto != null ? opts.rotuloOculto : "?";
      elCarta.appendChild(numero);
    } else {
      const info = parseCarta(carta);
      if (info.curinga) {
        elCarta.classList.add("curinga");
        elCarta.appendChild(criarSpan("indice", "★"));
        elCarta.appendChild(criarSpan("naipe-central", "CURINGA"));
        elCarta.appendChild(criarSpan("indice inferior", "★"));
      } else {
        if (info.cor === "vermelha") elCarta.classList.add("cor-vermelha");
        elCarta.appendChild(criarSpan("indice", info.rank));
        elCarta.appendChild(criarSpan("naipe-central", info.simbolo));
        elCarta.appendChild(criarSpan("indice inferior", info.rank));
      }
    }

    if (opts.jogavel) {
      elCarta.disabled = !!opts.desabilitada;
      if (opts.onClick) elCarta.addEventListener("click", opts.onClick);
    }
    return elCarta;
  }

  function criarSpan(classe, texto) {
    const span = document.createElement("span");
    span.className = classe;
    span.textContent = texto;
    return span;
  }

  function criarTag(texto, classe) {
    const span = document.createElement("span");
    span.className = "tag-papel " + classe;
    span.textContent = texto;
    return span;
  }

  function parseCsvPares(csv) {
    if (!csv) return [];
    return csv.split(",").map(function (par) {
      return par.split(":");
    });
  }

  // -- avatares (cosméticos, só locais ao navegador) --------------------------

  const ICONES_AVATAR = ["🤠", "🧔", "👒", "🐂", "☕", "🎸", "🌽", "🦜", "🐎", "🌵"];

  function hashNick(nick) {
    let h = 0;
    for (let i = 0; i < nick.length; i++) {
      h = (h * 31 + nick.charCodeAt(i)) % 1000003;
    }
    return Math.abs(h);
  }

  let avatarIndiceProprio = null;
  try {
    const salvo = localStorage.getItem("truco-avatar-indice");
    if (salvo != null) avatarIndiceProprio = parseInt(salvo, 10);
  } catch (e) {
    /* localStorage indisponível: avatar fica só no padrão da sessão */
  }

  function obterAvatar(nick, eu) {
    if (eu && avatarIndiceProprio != null) {
      return ICONES_AVATAR[avatarIndiceProprio % ICONES_AVATAR.length];
    }
    return ICONES_AVATAR[hashNick(nick) % ICONES_AVATAR.length];
  }

  function trocarMeuAvatar() {
    const atual = avatarIndiceProprio != null ? avatarIndiceProprio : hashNick(meuNickname || "");
    avatarIndiceProprio = (atual + 1) % ICONES_AVATAR.length;
    try {
      localStorage.setItem("truco-avatar-indice", String(avatarIndiceProprio));
    } catch (e) {
      /* ignora se não puder persistir */
    }
    const span = el("painel-jogo").querySelector(".assento--eu .avatar");
    if (span) span.textContent = ICONES_AVATAR[avatarIndiceProprio];
  }

  // -- contagem de cartas restantes na mão dos oponentes ----------------------
  // O servidor só me diz a MINHA mão; para os outros, infiro pelo histórico
  // de rodadas já reveladas (ultimo_resultado_rodada) mais a jogada em
  // andamento, já que cada jogador começa cada mão com 3 cartas.

  const contagemPorMao = { chaveUltimaRodada: null, jogadas: {} };

  function atualizarContagemMao(estado) {
    if (!estado.ultimo_resultado_rodada) {
      if (contagemPorMao.chaveUltimaRodada !== null) {
        contagemPorMao.chaveUltimaRodada = null;
        contagemPorMao.jogadas = {};
      }
      return;
    }
    const chave = estado.ultimo_resultado_rodada.cartas + "|" + estado.ultimo_resultado_rodada.vencedor;
    if (chave === contagemPorMao.chaveUltimaRodada) return;
    contagemPorMao.chaveUltimaRodada = chave;
    parseCsvPares(estado.ultimo_resultado_rodada.cartas).forEach(function (par) {
      const nick = par[0];
      contagemPorMao.jogadas[nick] = (contagemPorMao.jogadas[nick] || 0) + 1;
    });
  }

  function cartasRestantes(nick, cartasMesaAtual) {
    const jogouNestaRodada = cartasMesaAtual.some(function (par) {
      return par[0] === nick;
    });
    const jogadas = (contagemPorMao.jogadas[nick] || 0) + (jogouNestaRodada ? 1 : 0);
    return Math.max(0, CARTAS_POR_JOGADOR - jogadas);
  }

  // -- posicionamento dos assentos: pontos cardeais ao redor da mesa ---------

  const ANGULO_COMPASSO = { N: 0, NE: 45, E: 90, SE: 135, S: 180, SW: 225, W: 270, NW: 315 };

  // Sentado em S (eu), o jogo segue para a DIREITA: o próximo da ordem de
  // assento (meu vizinho "mão" quando eu sou pé) aparece à minha direita, e
  // quem vem antes de mim ("contra-pé") aparece à minha esquerda.
  const ORDEM_POR_MODO = {
    2: ["S", "N"],
    4: ["S", "E", "N", "W"],
    6: ["S", "SE", "NE", "N", "NW", "SW"],
    8: ["S", "SE", "E", "NE", "N", "NW", "W", "SW"],
  };

  function posicaoCompasso(direcao) {
    if (direcao === "S") return { x: 50, y: 91 };
    const rad = (ANGULO_COMPASSO[direcao] * Math.PI) / 180;
    return { x: 50 + 43 * Math.sin(rad), y: 50 - 38 * Math.cos(rad) };
  }

  // vetor (unitário, aproximado) de onde a carta "vem voando" até o centro
  // da mesa, na mesma direção do assento de quem jogou.
  const VOO_POR_DIRECAO = {
    N: { x: 0, y: -1 },
    NE: { x: 0.7, y: -0.7 },
    E: { x: 1, y: 0 },
    SE: { x: 0.7, y: 0.7 },
    S: { x: 0, y: 1 },
    SW: { x: -0.7, y: 0.7 },
    W: { x: -1, y: 0 },
    NW: { x: -0.7, y: -0.7 },
  };

  // -- animação de início de mão: embaralhar -> cortar -> entregar -----------
  // Sequência decorativa só do lado do cliente: o jogo real já resolveu tudo
  // no servidor instantaneamente, isso só atrasa a revelação visual pra
  // ficar legível. `faseAnimacaoMao` é lido pelas funções de renderização
  // pra esconder o corte/a mão de verdade enquanto a sequência roda.
  const DURACAO_EMBARALHAR = 1300;
  const DURACAO_CORTAR = 700;
  const DURACAO_ENTREGAR = 750;

  let faseAnimacaoMao = null; // null | "embaralhando" | "cortando" | "entregando"
  let jaTeveEstadoAnterior = false;
  let pedidoCorteAnteriorTruthy = false;
  let totalCartasAnterior = 0;
  let timersAnimacaoMao = [];

  function limparTimersAnimacaoMao() {
    timersAnimacaoMao.forEach(clearTimeout);
    timersAnimacaoMao = [];
  }

  function agendarAnimacaoMao(fn, ms) {
    timersAnimacaoMao.push(setTimeout(fn, ms));
  }

  // dispara exatamente quando PEDIDO_CORTE aparece (true->false) — é nesse
  // momento que o servidor já embaralhou de verdade e abriu a fase de corte
  // (vale tanto pra mão normal quanto mão de ferro, e pra mão de 10 que
  // acabou de decidir "jogar").
  function detectarInicioCorte(estado) {
    const agora = !!estado.pedido_corte;
    const mudou = jaTeveEstadoAnterior && agora && !pedidoCorteAnteriorTruthy;
    pedidoCorteAnteriorTruthy = agora;
    return mudou;
  }

  // dispara quando a mão (cartas na mão) vai de vazia pra cheia: é exatamente
  // o INICIO_PARTIDA depois do corte, com as cartas já distribuídas.
  function detectarNovoDeal(estado) {
    const total = (estado.mao || []).length;
    const novo = jaTeveEstadoAnterior && total > 0 && totalCartasAnterior === 0;
    totalCartasAnterior = total;
    return novo;
  }

  function tocarSequenciaEmbaralhar() {
    limparTimersAnimacaoMao();
    faseAnimacaoMao = "embaralhando";
    renderizar(estadoAtual);
    agendarAnimacaoMao(function () {
      faseAnimacaoMao = null;
      renderizar(estadoAtual);
    }, DURACAO_EMBARALHAR);
  }

  function tocarSequenciaCortarEEntregar() {
    limparTimersAnimacaoMao();
    faseAnimacaoMao = "cortando";
    renderizar(estadoAtual);
    agendarAnimacaoMao(function () {
      faseAnimacaoMao = "entregando";
      renderizar(estadoAtual);
      agendarAnimacaoMao(function () {
        faseAnimacaoMao = null;
        renderizar(estadoAtual);
      }, DURACAO_ENTREGAR);
    }, DURACAO_CORTAR);
  }

  function renderizarAnimacaoMao(direcaoPorJogador) {
    const painel = el("animacao-mao");
    const grafico = el("animacao-mao-grafico");
    if (!faseAnimacaoMao) {
      painel.classList.add("escondido");
      limpar(grafico);
      return;
    }
    painel.classList.remove("escondido");
    limpar(grafico);

    if (faseAnimacaoMao === "embaralhando") {
      el("animacao-mao-texto").textContent = "Embaralhando...";
      for (let i = 0; i < 5; i++) {
        const carta = criarCarta("", { mini: true, virada: true, rotuloOculto: "" });
        carta.classList.add("embaralhando");
        carta.style.animationDelay = i * 0.06 + "s";
        carta.style.setProperty("--ty", i * 1.5 + "px");
        carta.style.transform = "translateY(" + i * 1.5 + "px)";
        grafico.appendChild(carta);
      }
    } else if (faseAnimacaoMao === "cortando") {
      el("animacao-mao-texto").textContent = "Cortando o baralho...";
      for (let i = 0; i < 3; i++) {
        const esquerda = criarCarta("", { mini: true, virada: true, rotuloOculto: "" });
        esquerda.classList.add("pilha-esquerda");
        esquerda.style.transform = "translate(-6px, " + i * 1.5 + "px)";
        grafico.appendChild(esquerda);
      }
      for (let i = 0; i < 3; i++) {
        const direita = criarCarta("", { mini: true, virada: true, rotuloOculto: "" });
        direita.classList.add("pilha-direita");
        direita.style.transform = "translate(6px, " + i * 1.5 + "px)";
        grafico.appendChild(direita);
      }
    } else if (faseAnimacaoMao === "entregando") {
      el("animacao-mao-texto").textContent = "Distribuindo as cartas...";
      const direcoes = Object.keys(direcaoPorJogador || {});
      direcoes.forEach(function (nick, indice) {
        const direcao = direcaoPorJogador[nick];
        const voo = VOO_POR_DIRECAO[direcao] || VOO_POR_DIRECAO.S;
        const carta = criarCarta("", { mini: true, virada: true, rotuloOculto: "" });
        carta.classList.add("entregando");
        carta.style.setProperty("--voo-x", voo.x.toFixed(2));
        carta.style.setProperty("--voo-y", voo.y.toFixed(2));
        carta.style.animationDelay = indice * 0.08 + "s";
        grafico.appendChild(carta);
      });
    }
  }

  // -- renderização principal -------------------------------------------------

  let estadoAtual = null;

  function renderizar(estado) {
    const iniciouCorte = detectarInicioCorte(estado);
    const novoDeal = detectarNovoDeal(estado);
    jaTeveEstadoAnterior = true;

    estadoAtual = estado;
    meuNickname = estado.nickname;

    el("secao-login").classList.toggle("escondido", !!estado.logado);
    el("secao-mesas").classList.toggle("escondido", !estado.logado || !!estado.mesa);
    el("secao-mesa-atual").classList.toggle("escondido", !estado.mesa);

    el("aviso-login").textContent = !estado.logado && estado.erro ? estado.erro : "";
    el("ultimo-aviso").textContent = estado.aviso || "";

    renderizarMesas(estado.mesas_disponiveis || []);

    if (estado.mesa) {
      el("info-mesa-id").textContent = estado.mesa.id;
      el("info-mesa-status").textContent = estado.mesa.status;

      const emAndamento = estado.mesa.status === "EM_ANDAMENTO";
      el("painel-jogo").classList.toggle("escondido", !emAndamento);
      el("painel-aguardando").classList.toggle("escondido", emAndamento);

      if (emAndamento) {
        renderizarJogo(estado);
      } else {
        renderizarAguardando(estado);
      }
    }

    // dispara a sequência depois de renderizar o estado normal por baixo,
    // pra já existir DOM (assentos, cartas) pra animação cobrir/esconder.
    if (iniciouCorte) tocarSequenciaEmbaralhar();
    else if (novoDeal) tocarSequenciaCortarEEntregar();
  }

  function renderizarAguardando(estado) {
    const jogadores = (estado.mesa && estado.mesa.jogadores) || [];
    const modo = estado.modo_solicitado;
    el("texto-aguardando").textContent = modo
      ? `Aguardando jogadores... (${jogadores.length}/${modo})`
      : "Aguardando jogadores...";
    el("btn-completar-bots").disabled = !modo || jogadores.length >= modo;
  }

  function renderizarMesas(mesas) {
    const lista = el("lista-mesas");
    limpar(lista);
    mesas.forEach(function (mesa) {
      const li = document.createElement("li");
      const chipModo = document.createElement("span");
      chipModo.className = "chip";
      chipModo.textContent = mesa.modo + "p";
      const chipStatus = document.createElement("span");
      chipStatus.className = "chip" + (mesa.status === "EM_ANDAMENTO" ? " em-andamento" : "");
      chipStatus.textContent = mesa.status === "EM_ANDAMENTO" ? "em jogo" : "esperando";
      li.appendChild(chipModo);
      li.appendChild(chipStatus);
      li.appendChild(document.createTextNode("Mesa " + mesa.id + " — " + mesa.ocupacao));
      lista.appendChild(li);
    });
  }

  function renderizarJogo(estado) {
    const jogadores = (estado.mesa && estado.mesa.jogadores) || [];
    const indiceEu = jogadores.indexOf(meuNickname);
    const meuEquipe = indiceEu >= 0 ? indiceEu % 2 : 0;
    const outraEquipe = 1 - meuEquipe;
    const modo = jogadores.length;

    atualizarContagemMao(estado);

    montarTento("buracos-nos", estado.placar ? Number(estado.placar[String(meuEquipe)]) : 0);
    montarTento("buracos-eles", estado.placar ? Number(estado.placar[String(outraEquipe)]) : 0);
    montarListaEquipe("lista-equipe-nos", jogadores, meuEquipe);
    montarListaEquipe("lista-equipe-eles", jogadores, outraEquipe);

    el("valor-mao").textContent = estado.valor_mao != null ? estado.valor_mao : "-";

    const minhaVez = estado.vez === meuNickname;
    const vezPill = el("info-vez");
    vezPill.textContent = minhaVez ? "Sua vez!" : estado.vez ? "Vez de " + estado.vez : "-";
    vezPill.classList.toggle("minha-vez", minhaVez);

    const direcaoPorJogador = construirAssentos(estado, jogadores, indiceEu, modo, minhaVez);
    renderizarCentroDaMesa(estado, modo, direcaoPorJogador);
    renderizarAvisoCorte(estado);
    renderizarAvisoEspecial(estado);
    renderizarCartasParceiros(estado, modo);
    renderizarPedido(estado, meuEquipe);
    renderizarResultados(estado, meuEquipe);
    renderizarAnimacaoMao(direcaoPorJogador);
    atualizarBotaoTruco(estado, meuEquipe);
  }

  // valor atual da mão -> nome do próximo pedido na escalada (mesma
  // progressão de common/game.py: ESCALACAO = truco(4) -> seis(6) ->
  // nove(10) -> doze(12); valor inicial é 2, sem ninguém apostado ainda).
  const VALOR_DOZE = 12;
  const PROXIMO_PEDIDO_POR_VALOR = { 2: "TRUCO!", 4: "SEIS!", 6: "NOVE!", 10: "DOZE!" };

  function atualizarBotaoTruco(estado, meuEquipe) {
    const btn = el("btn-truco");
    const valorAtual = Number(estado.valor_mao != null ? estado.valor_mao : 2);
    // quem "tem a palavra" no valor atual — só ela fica bloqueada de pedir
    // de novo; a outra equipe é quem pode escalar (ver server/game.py:
    // Partida.equipe_apostou).
    const equipeComAPalavra = estado.equipe_apostou != null ? Number(estado.equipe_apostou) : null;
    const minhaEquipeTemAPalavra = equipeComAPalavra !== null && equipeComAPalavra === meuEquipe;
    const atingiuMaximo = valorAtual >= VALOR_DOZE;
    const bloqueadoPorOutroMotivo = !!estado.pedido_pendente || !!estado.mao_especial || !!faseAnimacaoMao;

    btn.textContent = PROXIMO_PEDIDO_POR_VALOR[valorAtual] || "TRUCO!";
    btn.disabled = bloqueadoPorOutroMotivo || minhaEquipeTemAPalavra || atingiuMaximo;
  }

  function montarListaEquipe(idElemento, jogadores, equipe) {
    const membros = jogadores.filter(function (_, i) {
      return i % 2 === equipe;
    });
    el(idElemento).textContent = membros
      .map(function (nick) {
        return obterAvatar(nick, nick === meuNickname) + " " + nick;
      })
      .join(", ");
  }

  function montarTento(idContainer, pontos) {
    const cont = el(idContainer);
    limpar(cont);
    const total = Math.max(0, Math.min(12, pontos || 0));
    for (let i = 0; i < 12; i++) {
      const buraco = document.createElement("span");
      buraco.className = "buraco" + (i < total ? " preenchido" : "");
      cont.appendChild(buraco);
    }
  }

  function construirAssentos(estado, jogadores, indiceEu, modo, minhaVez) {
    const cont = el("assentos");
    limpar(cont);
    const direcaoPorJogador = {};
    if (indiceEu === -1) return direcaoPorJogador;

    const ordem = ORDEM_POR_MODO[modo] || ORDEM_POR_MODO[2];
    const rotacionados = jogadores.slice(indiceEu).concat(jogadores.slice(0, indiceEu));
    const cartasMesa = estado.cartas_mesa || [];

    rotacionados.forEach(function (nick, i) {
      const ehEu = i === 0;
      const direcao = ordem[i] || "S";
      direcaoPorJogador[nick] = direcao;
      const posicaoOriginal = jogadores.indexOf(nick);
      const equipe = posicaoOriginal % 2;
      const pos = posicaoCompasso(direcao);

      const assento = document.createElement("div");
      assento.className = "assento equipe-" + equipe + (ehEu ? " assento--eu" : "");
      assento.style.left = pos.x + "%";
      assento.style.top = pos.y + "%";
      if (estado.vez === nick) assento.classList.add("na-vez");

      const maoNaMesa = document.createElement("div");
      maoNaMesa.className = "mao-na-mesa";

      // enquanto a sequência de embaralhar/cortar/entregar roda, esconde a
      // mão de todo mundo (a minha de verdade e os versos das dos outros) —
      // só aparece quando a animação de entrega termina.
      const escondendoMaoPelaAnimacao = faseAnimacaoMao === "cortando" || faseAnimacaoMao === "entregando";

      if (ehEu) {
        maoNaMesa.classList.add("leque");
        maoNaMesa.id = "mao-jogador";
        const mao = escondendoMaoPelaAnimacao ? [] : estado.mao || [];
        const n = mao.length;
        const anguloTotal = Math.min(26, n * 7);
        const desabilitada =
          !minhaVez || !!estado.pedido_pendente || !!estado.pedido_corte || !!estado.mao_especial || !!faseAnimacaoMao;
        mao.forEach(function (carta, indice) {
          const t = n > 1 ? indice / (n - 1) : 0.5;
          const rot = -anguloTotal / 2 + anguloTotal * t;
          const ty = Math.abs(rot) * 0.9;
          const valorEnviado = estado.mao_de_ferro_ativa ? String(indice + 1) : carta;
          const btn = criarCarta(carta, {
            jogavel: true,
            desabilitada: desabilitada,
            virada: estado.mao_de_ferro_ativa,
            rotuloOculto: String(indice + 1),
            manilha: !estado.mao_de_ferro_ativa && ehManilha(carta, modo),
            onClick: function () {
              post("/jogar_carta", { carta: valorEnviado });
            },
          });
          btn.style.setProperty("--rot", rot.toFixed(1) + "deg");
          btn.style.setProperty("--ty", ty.toFixed(1) + "px");
          maoNaMesa.appendChild(btn);
        });
      } else {
        const restantes = escondendoMaoPelaAnimacao ? 0 : cartasRestantes(nick, cartasMesa);
        for (let c = 0; c < restantes; c++) {
          maoNaMesa.appendChild(criarCarta("", { mini: true, virada: true, rotuloOculto: "" }));
        }
      }
      assento.appendChild(maoNaMesa);

      const identidade = document.createElement("div");
      identidade.className = "identidade";
      const avatarSpan = document.createElement("span");
      avatarSpan.className = "avatar";
      avatarSpan.textContent = obterAvatar(nick, ehEu);
      identidade.appendChild(avatarSpan);
      if (ehEu) {
        const btnTrocar = document.createElement("button");
        btnTrocar.type = "button";
        btnTrocar.className = "trocar-avatar";
        btnTrocar.title = "Trocar ícone";
        btnTrocar.textContent = "⟳";
        btnTrocar.addEventListener("click", trocarMeuAvatar);
        identidade.appendChild(btnTrocar);
      }
      const nomeSpan = document.createElement("span");
      nomeSpan.className = "nome";
      nomeSpan.textContent = nick;
      identidade.appendChild(nomeSpan);
      assento.appendChild(identidade);

      const tags = document.createElement("div");
      tags.className = "tags";
      if (estado.papeis) {
        if (estado.papeis.pe === nick) tags.appendChild(criarTag("PÉ", "pe"));
        if (estado.papeis.mao === nick) tags.appendChild(criarTag("MÃO", "mao"));
        if (estado.papeis.contra_pe === nick) tags.appendChild(criarTag("C-PÉ", "contra-pe"));
      }
      if (tags.children.length) assento.appendChild(tags);

      cont.appendChild(assento);
    });

    return direcaoPorJogador;
  }

  function renderizarCartasParceiros(estado, modo) {
    const painel = el("painel-parceiros");
    const lista = el("lista-parceiros");
    limpar(lista);
    if (!estado.cartas_parceiros || !estado.cartas_parceiros.length) {
      painel.classList.add("escondido");
      return;
    }
    painel.classList.remove("escondido");
    estado.cartas_parceiros.forEach(function (parceiro) {
      const item = document.createElement("div");
      item.className = "parceiro-item";
      const cartasDiv = document.createElement("div");
      cartasDiv.className = "cartas-parceiro";
      parceiro.cartas.forEach(function (carta) {
        cartasDiv.appendChild(criarCarta(carta, { mini: true, manilha: ehManilha(carta, modo) }));
      });
      item.appendChild(cartasDiv);
      const nomeEl = document.createElement("span");
      nomeEl.className = "nome-parceiro";
      nomeEl.textContent = parceiro.nickname;
      item.appendChild(nomeEl);
      lista.appendChild(item);
    });
  }

  // chaves ("nick:carta") das jogadas já mostradas no centro da mesa: usado
  // só pra saber quais são novas (e merecem a animação de "cair na mesa") —
  // o centro é todo reconstruído a cada render, então sem isso a animação
  // tocaria de novo em toda atualização de estado, não só quando alguém
  // realmente jogou uma carta.
  let chavesCentroAnteriores = [];

  function renderizarCentroDaMesa(estado, modo, direcaoPorJogador) {
    const cont = el("jogadas-centro");
    limpar(cont);

    // a carta que encerra a rodada nunca aparece em `cartas_mesa` (o servidor
    // já manda direto o RESULTADO_RODADA, sem um ESTADO_RODADA intermediário
    // com as duas cartas) — sem isso ela nunca "cairia" na mesa, só apareceria
    // no cartaz de resultado. Por isso, com a mesa vazia, mostramos a última
    // rodada revelada até a próxima carta ser jogada.
    let cartasMesa = estado.cartas_mesa || [];
    let jaRevelada = false;
    if (!cartasMesa.length && estado.ultimo_resultado_rodada) {
      cartasMesa = parseCsvPares(estado.ultimo_resultado_rodada.cartas);
      jaRevelada = true;
    }

    const chavesAtuais = [];
    cartasMesa.forEach(function (par) {
      const nick = par[0];
      const carta = par[1];
      const chave = nick + ":" + carta;
      chavesAtuais.push(chave);
      const ehNova = chavesCentroAnteriores.indexOf(chave) === -1;

      const envoltorio = document.createElement("div");
      envoltorio.className = "jogada-individual" + (ehNova ? " jogada-nova" : "");
      if (ehNova) {
        const direcao = (direcaoPorJogador && direcaoPorJogador[nick]) || "S";
        const voo = VOO_POR_DIRECAO[direcao] || VOO_POR_DIRECAO.S;
        envoltorio.style.setProperty("--voo-x", voo.x.toFixed(2));
        envoltorio.style.setProperty("--voo-y", voo.y.toFixed(2));
      }
      envoltorio.appendChild(
        criarCarta(carta, {
          mini: true,
          virada: !jaRevelada && estado.mao_de_ferro_ativa,
          manilha: !estado.mao_de_ferro_ativa && ehManilha(carta, modo),
        })
      );
      const legenda = document.createElement("span");
      legenda.className = "legenda";
      legenda.textContent = nick;
      envoltorio.appendChild(legenda);
      cont.appendChild(envoltorio);
    });
    chavesCentroAnteriores = chavesAtuais;
  }

  function renderizarAvisoCorte(estado) {
    const painel = el("painel-corte");
    // escondido durante a animação de embaralhar, mesmo que o pedido de
    // corte já tenha chegado de verdade — só aparece quando ela termina.
    if (estado.pedido_corte && faseAnimacaoMao !== "embaralhando") {
      painel.classList.remove("escondido");
      const souEu = estado.pedido_corte === meuNickname;
      el("texto-corte").textContent = souEu
        ? "É a sua vez de cortar o baralho:"
        : "Aguardando " + estado.pedido_corte + " cortar o baralho...";
      el("btn-corte-descer").disabled = !souEu;
      el("btn-corte-subir").disabled = !souEu;
    } else {
      painel.classList.add("escondido");
    }
  }

  function renderizarAvisoEspecial(estado) {
    const painel = el("painel-mao-especial");
    const decisao = el("painel-decisao-mao-10");
    if (estado.mao_especial) {
      painel.classList.remove("escondido");
      if (estado.mao_especial.tipo === "MAO_DE_FERRO") {
        el("texto-mao-especial").textContent =
          "Mão de ferro! As duas equipes estão com 10+ pontos — cartas viradas, truco bloqueado.";
        decisao.classList.add("escondido");
      } else {
        const jogadores = estado.mesa.jogadores;
        const souDaEquipe = jogadores.indexOf(meuNickname) % 2 === Number(estado.mao_especial.equipe_decisora);
        el("texto-mao-especial").textContent = souDaEquipe
          ? "Mão de 10! Sua equipe está com 10+ pontos. Truco bloqueado — jogar ou correr?"
          : "Mão de 10! A equipe adversária está com 10+ pontos e decide se joga ou corre.";
        decisao.classList.toggle("escondido", !souDaEquipe);
      }
    } else {
      painel.classList.add("escondido");
      decisao.classList.add("escondido");
    }
  }

  function renderizarPedido(estado, meuEquipe) {
    const painel = el("pedido-pendente");
    if (estado.pedido_pendente) {
      painel.classList.remove("escondido");
      const equipeSolicitante = Number(estado.pedido_pendente.equipe);
      const souEuQuemPediu = equipeSolicitante === meuEquipe;
      el("texto-pedido").textContent = souEuQuemPediu
        ? "Sua equipe pediu para a mão valer " + estado.pedido_pendente.valor + "! Aguardando resposta da equipe adversária..."
        : "A equipe adversária pediu para a mão valer " + estado.pedido_pendente.valor + "!";
      // só quem recebeu o pedido responde — quem pediu só espera.
      el("pedido-acoes").classList.toggle("escondido", souEuQuemPediu);
    } else {
      painel.classList.add("escondido");
    }
  }

  function renderizarResultados(estado, meuEquipe) {
    const elRodada = el("resultado-rodada");
    limpar(elRodada);
    if (estado.ultimo_resultado_rodada) {
      const res = estado.ultimo_resultado_rodada;
      const pares = parseCsvPares(res.cartas);
      const titulo = document.createElement("span");
      titulo.className = "resultado-titulo";
      if (res.vencedor === "EMPATE") {
        titulo.textContent = "Rodada empatada — ninguém levou.";
      } else {
        const venceuEu = Number(res.vencedor) === meuEquipe;
        titulo.textContent = venceuEu ? "Sua equipe venceu a rodada!" : "A equipe adversária venceu a rodada.";
      }
      elRodada.appendChild(titulo);
      const linha = document.createElement("div");
      linha.className = "linha-revelacao";
      pares.forEach(function (par) {
        const envoltorio = document.createElement("span");
        envoltorio.style.display = "inline-flex";
        envoltorio.style.flexDirection = "column";
        envoltorio.style.alignItems = "center";
        envoltorio.style.gap = "0.15rem";
        envoltorio.style.fontSize = "0.75rem";
        envoltorio.appendChild(criarCarta(par[1], { mini: true }));
        const nomeEl = document.createElement("span");
        nomeEl.textContent = par[0];
        envoltorio.appendChild(nomeEl);
        linha.appendChild(envoltorio);
      });
      elRodada.appendChild(linha);
    }

    const elMao = el("resultado-mao");
    if (estado.ultimo_resultado_mao) {
      const venceuEu = Number(estado.ultimo_resultado_mao.vencedor) === meuEquipe;
      const placarTxt =
        (estado.placar ? estado.placar[String(meuEquipe)] : "?") +
        " x " +
        (estado.placar ? estado.placar[String(1 - meuEquipe)] : "?");
      elMao.textContent = venceuEu
        ? "Sua equipe venceu a mão! Placar: " + placarTxt
        : "A equipe adversária venceu a mão. Placar: " + placarTxt;
    } else {
      elMao.textContent = "";
    }

    const elFim = el("fim-partida");
    if (estado.fim_partida != null) {
      const venceuEu = Number(estado.fim_partida) === meuEquipe;
      elFim.textContent = venceuEu ? "FIM DE PARTIDA — sua equipe venceu! 🏆" : "FIM DE PARTIDA — a equipe adversária venceu.";
      elFim.classList.remove("escondido");
    } else {
      elFim.classList.add("escondido");
    }
  }

  function conectarEventos() {
    const fonte = new EventSource("/events");
    fonte.onmessage = function (evento) {
      renderizar(JSON.parse(evento.data));
    };
  }

  el("btn-login").addEventListener("click", function () {
    const nickname = el("input-nickname").value.trim();
    if (nickname) post("/login", { nickname: nickname });
  });

  document.querySelectorAll(".botao-modo").forEach(function (btn) {
    btn.addEventListener("click", function () {
      post("/entrar_mesa", { modo: btn.dataset.modo });
    });
  });

  el("btn-atualizar-mesas").addEventListener("click", function () {
    post("/listar_mesas");
  });

  el("btn-completar-bots").addEventListener("click", function () {
    post("/completar_com_bots");
  });

  el("btn-corte-descer").addEventListener("click", function () {
    post("/cortar", { direcao: "DESCER" });
  });
  el("btn-corte-subir").addEventListener("click", function () {
    post("/cortar", { direcao: "SUBIR" });
  });
  el("btn-decidir-jogar").addEventListener("click", function () {
    post("/decidir_mao_10", { decisao: "JOGAR" });
  });
  el("btn-decidir-correr").addEventListener("click", function () {
    post("/decidir_mao_10", { decisao: "CORRER" });
  });

  el("btn-truco").addEventListener("click", function () {
    post("/truco");
  });
  el("btn-aceitar").addEventListener("click", function () {
    post("/aceitar");
  });
  el("btn-correr").addEventListener("click", function () {
    post("/correr");
  });
  el("btn-aumentar").addEventListener("click", function () {
    post("/aumentar");
  });
  // mesmo prefixo usado pelo servidor (common/constants.py:PREFIXO_NICKNAME_BOT)
  // pra reconhecer bots só pelo nickname — aqui é só pra escolher o texto
  // do aviso; a decisão de desfazer a mesa de verdade é sempre do servidor.
  const PREFIXO_NICKNAME_BOT = "Bot";

  el("btn-sair").addEventListener("click", function () {
    const jogadores = (estadoAtual && estadoAtual.mesa && estadoAtual.mesa.jogadores) || [];
    const outrosHumanos = jogadores.filter(function (nick) {
      return nick !== meuNickname && nick.indexOf(PREFIXO_NICKNAME_BOT) !== 0;
    });
    el("texto-confirmar-saida").textContent =
      outrosHumanos.length === 0
        ? "Só tem bots com você nessa mesa — ao sair, a mesa será desfeita. Quer mesmo sair?"
        : "A mesa vai continuar para os outros jogadores. Quer mesmo sair?";
    el("modal-confirmar-saida").classList.remove("escondido");
  });

  el("btn-cancelar-saida").addEventListener("click", function () {
    el("modal-confirmar-saida").classList.add("escondido");
  });

  el("btn-confirmar-saida").addEventListener("click", function () {
    el("btn-confirmar-saida").disabled = true;
    post("/sair").then(function () {
      // recarrega pra abrir uma sessão (e um EventSource) limpa — a sessão
      // antiga foi descartada no servidor, então a aba não veria mais
      // atualização nenhuma se só esperasse o próximo evento.
      window.location.reload();
    });
  });

  conectarEventos();
})();
