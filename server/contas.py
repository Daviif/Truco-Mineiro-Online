"""Persistência de contas de usuário (autenticação — bônus do TP01).

Continua "Python puro": só `sqlite3`/`hashlib`/`secrets` da stdlib, sem
dependência externa, igual o resto do projeto. As contas são opcionais e
aditivas — o login avulso por nickname (`LOGIN;nickname`, sem senha) não
muda em nada; isto aqui só serve quem quiser uma identidade de verdade
(pré-requisito pro ranking, que vem numa etapa futura).

Verificação de email institucional é só por domínio (sem confirmação real
por e-mail/SMTP) — suficiente pro escopo de bônus, mas não prova posse do
email.
"""

import hashlib
import re
import secrets
import sqlite3
import threading
from pathlib import Path

CAMINHO_BANCO_PADRAO = Path(__file__).resolve().parent / "dados" / "contas.db"

# domínios institucionais da UFOP — ajustar/completar se houver outros.
DOMINIOS_INSTITUCIONAIS = ("ufop.edu.br", "aluno.ufop.edu.br")

TAMANHO_MINIMO_SENHA = 6
_ITERACOES_PBKDF2 = 200_000
_REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErroConta(Exception):
    """Erro de cadastro/login de conta; `motivo` é um ERRO_* do protocolo."""

    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


class Conta:
    def __init__(self, id_, email, nickname, institucional, curso):
        self.id = id_
        self.email = email
        self.nickname = nickname
        self.institucional = bool(institucional)
        self.curso = curso


def _email_normalizado(email):
    return (email or "").strip().lower()


def _eh_institucional(email):
    dominio = email.rsplit("@", 1)[-1]
    return any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_INSTITUCIONAIS)


def _gerar_hash(senha, salt):
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, _ITERACOES_PBKDF2).hex()


class ContasRepositorio:
    """Uma instância por servidor; `sqlite3` com `check_same_thread=False`
    porque cada `ClientSession` roda na sua própria thread, mas todo acesso
    passa por aqui serializado (`_lock`) — volume de cadastro/login é baixo,
    não precisa de nada mais sofisticado."""

    def __init__(self, caminho=CAMINHO_BANCO_PADRAO):
        self._lock = threading.Lock()
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self._conexao = sqlite3.connect(str(caminho), check_same_thread=False)
        self._conexao.execute("PRAGMA foreign_keys = ON")
        self._criar_tabela()

    def _criar_tabela(self):
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS contas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                senha_hash TEXT NOT NULL,
                senha_salt TEXT NOT NULL,
                nickname TEXT NOT NULL UNIQUE,
                institucional INTEGER NOT NULL,
                curso TEXT,
                criado_em TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._conexao.commit()

    def criar_conta(self, email, senha, nickname, curso):
        email = _email_normalizado(email)
        nickname = (nickname or "").strip()
        if not _REGEX_EMAIL.match(email):
            raise ErroConta("EMAIL_INVALIDO")
        if not senha or len(senha) < TAMANHO_MINIMO_SENHA:
            raise ErroConta("SENHA_FRACA")
        if not nickname:
            raise ErroConta("MENSAGEM_INVALIDA")

        institucional = _eh_institucional(email)
        curso = (curso or "").strip() if institucional else None
        salt = secrets.token_bytes(16)
        senha_hash = _gerar_hash(senha, salt)

        with self._lock:
            try:
                cursor = self._conexao.execute(
                    "INSERT INTO contas (email, senha_hash, senha_salt, nickname, institucional, curso) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (email, senha_hash, salt.hex(), nickname, int(institucional), curso),
                )
                self._conexao.commit()
            except sqlite3.IntegrityError as erro:
                # a mensagem do sqlite diz qual UNIQUE constraint falhou
                if "contas.email" in str(erro):
                    raise ErroConta("EMAIL_EM_USO") from erro
                raise ErroConta("NICKNAME_EM_USO") from erro

        return Conta(cursor.lastrowid, email, nickname, institucional, curso)

    def autenticar(self, email, senha):
        email = _email_normalizado(email)
        with self._lock:
            linha = self._conexao.execute(
                "SELECT id, email, senha_hash, senha_salt, nickname, institucional, curso "
                "FROM contas WHERE email = ?",
                (email,),
            ).fetchone()
        if linha is None:
            raise ErroConta("CREDENCIAIS_INVALIDAS")
        id_, email, senha_hash, salt_hex, nickname, institucional, curso = linha
        salt = bytes.fromhex(salt_hex)
        if not secrets.compare_digest(_gerar_hash(senha, salt), senha_hash):
            raise ErroConta("CREDENCIAIS_INVALIDAS")
        return Conta(id_, email, nickname, institucional, curso)
