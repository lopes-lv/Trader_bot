"""
Módulo de Persistência (SQLite)
--------------------------------
Centraliza todas as operações de leitura/escrita no banco de dados.
SQLite foi escolhido por ser um único arquivo, sem processo de servidor,
ideal para hardware limitado.
"""
import sqlite3
from contextlib import contextmanager


@contextmanager
def _conectar(db_path):
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path):
    with _conectar(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS historico_precos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                preco REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS carteira (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_compra TEXT NOT NULL,
                valor_compra REAL NOT NULL,
                quantidade REAL NOT NULL DEFAULT 1.0,
                status TEXT NOT NULL DEFAULT 'aberto',
                valor_venda REAL,
                data_venda TEXT
            );

            -- v0.2: preco_abertura ficou opcional (NULL permitido) porque
            -- agora a linha também pode ser criada/atualizada só com
            -- orcamento_diario (pergunta do orçamento, em fuso local),
            -- independentemente da abertura em UTC.
            CREATE TABLE IF NOT EXISTS estado_diario (
                data TEXT PRIMARY KEY,
                preco_abertura REAL,
                orcamento_diario REAL
            );

            CREATE TABLE IF NOT EXISTS estado_alertas (
                chave TEXT PRIMARY KEY,
                valor TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_historico_timestamp
                ON historico_precos(timestamp);
            """
        )
        conn.commit()
        _migrar_schema(conn)
        conn.commit()


def _migrar_schema(conn):
    """
    Migração idempotente de bancos criados na v0.1, sem perder nenhum dado:

    1. A v0.1 criou `preco_abertura` como NOT NULL. Na v0.2 ela precisa
       aceitar NULL (uma linha pode existir só com orcamento_diario
       preenchido). SQLite não suporta remover NOT NULL via ALTER TABLE,
       então recriamos a tabela e copiamos os dados.
    2. Garante a existência da coluna orcamento_diario.
    """
    info = list(conn.execute("PRAGMA table_info(estado_diario)"))
    colunas = {linha[1] for linha in info}
    preco_abertura_not_null = any(
        linha[1] == "preco_abertura" and linha[3] == 1 for linha in info
    )
    tem_orcamento = "orcamento_diario" in colunas

    if preco_abertura_not_null:
        conn.execute("ALTER TABLE estado_diario RENAME TO estado_diario_old")
        conn.execute(
            """CREATE TABLE estado_diario (
                data TEXT PRIMARY KEY,
                preco_abertura REAL,
                orcamento_diario REAL
            )"""
        )
        if tem_orcamento:
            conn.execute(
                """INSERT INTO estado_diario (data, preco_abertura, orcamento_diario)
                   SELECT data, preco_abertura, orcamento_diario FROM estado_diario_old"""
            )
        else:
            conn.execute(
                """INSERT INTO estado_diario (data, preco_abertura)
                   SELECT data, preco_abertura FROM estado_diario_old"""
            )
        conn.execute("DROP TABLE estado_diario_old")
    elif not tem_orcamento:
        conn.execute("ALTER TABLE estado_diario ADD COLUMN orcamento_diario REAL")


# ---------- historico_precos ----------

def inserir_preco(db_path, timestamp_iso, preco):
    with _conectar(db_path) as conn:
        conn.execute(
            "INSERT INTO historico_precos (timestamp, preco) VALUES (?, ?)",
            (timestamp_iso, preco),
        )
        conn.commit()


def obter_precos_recentes(db_path, limite):
    """Retorna os últimos `limite` preços em ordem cronológica (mais antigo -> mais recente)."""
    with _conectar(db_path) as conn:
        cur = conn.execute(
            "SELECT preco FROM historico_precos ORDER BY id DESC LIMIT ?",
            (limite,),
        )
        linhas = cur.fetchall()
    return [linha[0] for linha in reversed(linhas)]


def limpar_precos_antigos(db_path, horas):
    """Remove registros antigos para manter o arquivo .db pequeno."""
    with _conectar(db_path) as conn:
        conn.execute(
            "DELETE FROM historico_precos WHERE timestamp < datetime('now', ?)",
            (f"-{horas} hours",),
        )
        conn.commit()


# ---------- estado_diario (cache da abertura das 00:00 UTC) ----------

def obter_abertura_dia(db_path, data_str):
    with _conectar(db_path) as conn:
        cur = conn.execute(
            "SELECT preco_abertura FROM estado_diario WHERE data = ?", (data_str,)
        )
        linha = cur.fetchone()
    return linha[0] if linha else None


def definir_abertura_dia(db_path, data_str, preco):
    # v0.2: trocado de "INSERT OR REPLACE" para upsert parcial. Com a nova
    # coluna orcamento_diario, um REPLACE apagaria (setaria NULL) qualquer
    # orçamento já registrado para o mesmo dia, pois REPLACE recria a linha
    # inteira. O upsert abaixo só toca a coluna preco_abertura.
    with _conectar(db_path) as conn:
        conn.execute(
            """INSERT INTO estado_diario (data, preco_abertura) VALUES (?, ?)
               ON CONFLICT(data) DO UPDATE SET preco_abertura = excluded.preco_abertura""",
            (data_str, preco),
        )
        conn.commit()


# ---------- orçamento diário (v0.2) ----------

def definir_orcamento_diario(db_path, data_str, valor):
    with _conectar(db_path) as conn:
        conn.execute(
            """INSERT INTO estado_diario (data, orcamento_diario) VALUES (?, ?)
               ON CONFLICT(data) DO UPDATE SET orcamento_diario = excluded.orcamento_diario""",
            (data_str, valor),
        )
        conn.commit()


def obter_orcamento_diario(db_path, data_str):
    with _conectar(db_path) as conn:
        cur = conn.execute(
            "SELECT orcamento_diario FROM estado_diario WHERE data = ?", (data_str,)
        )
        linha = cur.fetchone()
    return linha[0] if linha and linha[0] is not None else None


# ---------- estado_alertas (cooldown de alertas) ----------

def obter_estado(db_path, chave):
    with _conectar(db_path) as conn:
        cur = conn.execute("SELECT valor FROM estado_alertas WHERE chave = ?", (chave,))
        linha = cur.fetchone()
    return linha[0] if linha else None


def definir_estado(db_path, chave, valor):
    with _conectar(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO estado_alertas (chave, valor) VALUES (?, ?)",
            (chave, valor),
        )
        conn.commit()


# ---------- carteira ----------

def registrar_compra(db_path, valor_compra, quantidade=1.0):
    with _conectar(db_path) as conn:
        conn.execute(
            """INSERT INTO carteira (data_compra, valor_compra, quantidade, status)
               VALUES (datetime('now'), ?, ?, 'aberto')""",
            (valor_compra, quantidade),
        )
        conn.commit()


def get_posicoes_abertas(db_path):
    # v0.2: passou a incluir data_compra (índice 3) para exibição no comando
    # "carteira" e no dashboard. Código antigo que usa apenas p[1]/p[2]
    # continua funcionando normalmente.
    with _conectar(db_path) as conn:
        cur = conn.execute(
            """SELECT id, valor_compra, quantidade, data_compra
               FROM carteira WHERE status = 'aberto' ORDER BY id ASC"""
        )
        return cur.fetchall()


def calcular_preco_medio(db_path):
    """
    Preço médio ponderado das posições abertas.
    Assume quantidade=1.0 por compra quando não informada (ou seja, vira uma
    média aritmética simples — adequado para quem investe o mesmo valor a
    cada aporte). Se quiser ponderar por quantidade real de BTC comprada,
    basta popular a coluna `quantidade` ao registrar a compra.
    """
    posicoes = get_posicoes_abertas(db_path)
    if not posicoes:
        return None
    custo_total = sum(p[1] * p[2] for p in posicoes)
    qtd_total = sum(p[2] for p in posicoes)
    if qtd_total == 0:
        return None
    return custo_total / qtd_total


def fechar_posicoes(db_path, valor_venda):
    """Fecha TODAS as posições abertas ao preço informado (venda da carteira consolidada).
    Mantido por compatibilidade — a partir da v0.2 o comando "vendi" do
    Telegram usa vender_quantidade() abaixo, que permite venda parcial."""
    with _conectar(db_path) as conn:
        cur = conn.execute(
            """UPDATE carteira
               SET status = 'fechado', valor_venda = ?, data_venda = datetime('now')
               WHERE status = 'aberto'""",
            (valor_venda,),
        )
        conn.commit()
        return cur.rowcount


def vender_quantidade(db_path, quantidade_alvo, preco_venda):
    """
    (v0.2) Abate `quantidade_alvo` de BTC das posições abertas, em ordem
    FIFO (compras mais antigas primeiro — id ASC). Se uma posição for
    vendida apenas parcialmente, ela é dividida em duas linhas: o restante
    continua 'aberto' com a quantidade reduzida, e a fração vendida vira um
    novo registro 'fechado' preservando a data_compra original (histórico
    correto de custo).

    Retorna um dicionário-resumo, ou None se não havia nenhuma posição aberta.
    """
    EPS = 1e-12
    with _conectar(db_path) as conn:
        posicoes = conn.execute(
            """SELECT id, data_compra, valor_compra, quantidade
               FROM carteira WHERE status = 'aberto' ORDER BY id ASC"""
        ).fetchall()

        if not posicoes:
            return None

        restante = quantidade_alvo
        custo_total_vendido = 0.0
        quantidade_total_vendida = 0.0

        for pid, data_compra, valor_compra, quantidade in posicoes:
            if restante <= EPS:
                break

            if quantidade <= restante + EPS:
                # vende a posição inteira
                conn.execute(
                    """UPDATE carteira
                       SET status = 'fechado', valor_venda = ?, data_venda = datetime('now')
                       WHERE id = ?""",
                    (preco_venda, pid),
                )
                custo_total_vendido += quantidade * valor_compra
                quantidade_total_vendida += quantidade
                restante -= quantidade
            else:
                # vende só uma fração: reduz a posição aberta e cria um
                # registro fechado só com a fração vendida
                nova_quantidade_aberta = quantidade - restante
                conn.execute(
                    "UPDATE carteira SET quantidade = ? WHERE id = ?",
                    (nova_quantidade_aberta, pid),
                )
                conn.execute(
                    """INSERT INTO carteira
                       (data_compra, valor_compra, quantidade, status, valor_venda, data_venda)
                       VALUES (?, ?, ?, 'fechado', ?, datetime('now'))""",
                    (data_compra, valor_compra, restante, preco_venda),
                )
                custo_total_vendido += restante * valor_compra
                quantidade_total_vendida += restante
                restante = 0.0

        conn.commit()

    if quantidade_total_vendida <= EPS:
        return None

    custo_medio_vendido = custo_total_vendido / quantidade_total_vendida
    pnl_reais = (preco_venda - custo_medio_vendido) * quantidade_total_vendida
    pnl_pct = (preco_venda - custo_medio_vendido) / custo_medio_vendido * 100

    return {
        "quantidade_vendida": quantidade_total_vendida,
        "quantidade_solicitada": quantidade_alvo,
        "restante_nao_atendido": max(restante, 0.0),
        "custo_medio": custo_medio_vendido,
        "pnl_reais": pnl_reais,
        "pnl_pct": pnl_pct,
    }
