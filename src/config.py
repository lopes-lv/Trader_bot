"""
Módulo de Configuração
-----------------------
Carrega variáveis de ambiente (de um arquivo .env local, se existir, ou do
ambiente do sistema/systemd) e expõe como constantes tipadas para o resto
da aplicação.

Não depende de python-dotenv para manter o projeto o mais leve possível —
o parser abaixo é suficiente para o formato CHAVE=VALOR.
"""
import os


def _carregar_dotenv(caminho=".env"):
    if not os.path.exists(caminho):
        return
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            os.environ.setdefault(chave, valor)


_carregar_dotenv()


def _env_float(nome, padrao):
    return float(os.environ.get(nome, padrao))


def _env_int(nome, padrao):
    return int(os.environ.get(nome, padrao))


# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- Exchange / Mercado (Binance pública — não requer chave de API) ---
EXCHANGE_BASE_URL = os.environ.get("EXCHANGE_BASE_URL", "https://api.binance.com")
# v0.2: paridade padrão trocada de BTCUSDT para BTCBRL (par existente na Binance)
SYMBOL = os.environ.get("SYMBOL", "BTCBRL")

# --- Banco de dados ---
DB_PATH = os.environ.get("DB_PATH", "btc_bot.db")

# --- Fuso horário local (v0.2) ---
# Usado apenas para decidir QUANDO perguntar o orçamento diário (pela manhã,
# no horário do usuário). O marco das 00:00 UTC usado no gatilho de compra
# (RSI + queda vs. abertura do dia) permanece intacto, pois é o padrão de
# mercado e não deve ser alterado (ver golden rule da v0.2).
FUSO_HORARIO_LOCAL = os.environ.get("FUSO_HORARIO_LOCAL", "America/Boa_Vista")

# --- Timing ---
CHECK_INTERVAL_SECONDS = _env_int("CHECK_INTERVAL_SECONDS", 300)  # 5 minutos
RETENCAO_HISTORICO_HORAS = _env_int("RETENCAO_HISTORICO_HORAS", 24)

# --- Indicadores técnicos ---
RSI_PERIOD = _env_int("RSI_PERIOD", 14)
RSI_OVERSOLD_THRESHOLD = _env_float("RSI_OVERSOLD_THRESHOLD", 30.0)
# 3 pontos x 5 min = 15 min de "média móvel rápida"
MA_FAST_JANELA_PONTOS = _env_int("MA_FAST_JANELA_PONTOS", 3)

# --- Regras de negócio ---
QUEDA_MINIMA_PERCENTUAL = _env_float("QUEDA_MINIMA_PERCENTUAL", 1.0)
META_LUCRO_PERCENTUAL = _env_float("META_LUCRO_PERCENTUAL", 5.0)
STOP_LOSS_PERCENTUAL = _env_float("STOP_LOSS_PERCENTUAL", 8.0)
ALERTA_COOLDOWN_MINUTOS = _env_int("ALERTA_COOLDOWN_MINUTOS", 60)


def validar():
    faltando = []
    if not TELEGRAM_BOT_TOKEN:
        faltando.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        faltando.append("TELEGRAM_CHAT_ID")
    if faltando:
        raise RuntimeError(
            f"Variáveis de ambiente obrigatórias ausentes: {', '.join(faltando)}"
        )
