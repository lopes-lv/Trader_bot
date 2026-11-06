"""
Módulo de Lógica / Indicadores
--------------------------------
Implementações leves (sem numpy/pandas) de RSI e Média Móvel, usadas para
identificar exaustão de venda (possível fundo) e reversão de tendência de
curtíssimo prazo.
"""


def calcular_rsi(precos, period=14):
    """
    RSI de Wilder (o método clássico, com suavização exponencial simples).
    `precos` deve estar em ordem cronológica (mais antigo -> mais recente).
    Retorna None se não houver pontos suficientes.
    """
    if len(precos) < period + 1:
        return None

    ganhos = []
    perdas = []
    for i in range(1, len(precos)):
        delta = precos[i] - precos[i - 1]
        ganhos.append(max(delta, 0.0))
        perdas.append(max(-delta, 0.0))

    media_ganho = sum(ganhos[:period]) / period
    media_perda = sum(perdas[:period]) / period

    for i in range(period, len(ganhos)):
        media_ganho = (media_ganho * (period - 1) + ganhos[i]) / period
        media_perda = (media_perda * (period - 1) + perdas[i]) / period

    if media_perda == 0:
        return 100.0
    rs = media_ganho / media_perda
    return 100.0 - (100.0 / (1.0 + rs))


def media_movel(precos, janela):
    if len(precos) < janela:
        return None
    return sum(precos[-janela:]) / janela


def detectar_virada_alta(precos, janela=3):
    """
    Compara a média móvel rápida atual (últimos `janela` pontos) com a média
    móvel do período imediatamente anterior. Retorna True se a média virou
    para cima — sinal de que a queda cessou e o preço reagiu — e False caso
    contrário ou se faltarem dados.

    Com checagens a cada 5 min e janela=3, isso equivale aos "últimos 15 min".
    """
    if len(precos) < janela * 2:
        return False
    ma_atual = media_movel(precos, janela)
    ma_anterior = media_movel(precos[:-janela], janela)
    if ma_atual is None or ma_anterior is None:
        return False
    return ma_atual > ma_anterior
