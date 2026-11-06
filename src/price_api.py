"""
Módulo de API / Preço
----------------------
Toda a comunicação com a API pública da Binance fica isolada aqui.
Usamos apenas endpoints públicos (somente leitura) — nenhuma chave de API
é necessária.
"""
import requests
import config

TIMEOUT = 10  # segundos

# Adicionado na v0.2.1: Sessão para reaproveitamento de conexões TCP
session = requests.Session()


class ErroAPIExchange(Exception):
    """Erro genérico ao falar com a exchange — nunca deve derrubar o loop principal."""
    pass


def obter_preco_atual(symbol=None):
    symbol = symbol or config.SYMBOL
    url = f"{config.EXCHANGE_BASE_URL}/api/v3/ticker/price"
    try:
        resp = session.get(url, params={"symbol": symbol}, timeout=TIMEOUT)
        resp.raise_for_status()
        dados = resp.json()
        return float(dados["price"])
    except (requests.exceptions.RequestException, KeyError, ValueError, TypeError) as e:
        raise ErroAPIExchange(f"Falha ao obter preço atual: {e}") from e


def obter_abertura_diaria_utc(symbol=None):
    """
    Retorna o preço de abertura do candle DIÁRIO atual (00:00 UTC).

    Usar o candle 1d da própria exchange é a forma mais robusta de obter essa
    referência: não depende de o bot estar rodando desde a meia-noite, nem de
    guardarmos manualmente o "primeiro preço do dia".
    """
    symbol = symbol or config.SYMBOL
    url = f"{config.EXCHANGE_BASE_URL}/api/v3/klines"
    try:
        resp = session.get(
            url,
            params={"symbol": symbol, "interval": "1d", "limit": 1},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        dados = resp.json()
        # kline: [openTime, open, high, low, close, volume, closeTime, ...]
        return float(dados[0][1])
    except (requests.exceptions.RequestException, KeyError, IndexError, ValueError, TypeError) as e:
        raise ErroAPIExchange(f"Falha ao obter abertura diária: {e}") from e
