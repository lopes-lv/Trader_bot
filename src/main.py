"""
Módulo Principal
-----------------
Loop de segundo plano que:
  1. Busca o preço atual do BTC a cada N segundos (padrão: 5 minutos).
  2. Persiste o histórico de preços no SQLite.
  3. Calcula indicadores (RSI + reversão de média móvel) e verifica o
     gatilho de compra (fundo após queda em relação às 00:00 UTC).
  4. Verifica posições abertas e dispara alertas de venda (lucro ou stop loss).
  5. Nunca deixa uma falha de rede/API derrubar o loop.
"""
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import config
import database
import indicators
import price_api
import sistema
import telegram_bot
import utils

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def _data_utc_hoje():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _obter_abertura_do_dia():
    """Abertura das 00:00 UTC de hoje — busca na API apenas 1x por dia (cache no SQLite)."""
    hoje = _data_utc_hoje()
    abertura = database.obter_abertura_dia(config.DB_PATH, hoje)
    if abertura is not None:
        return abertura
    abertura = price_api.obter_abertura_diaria_utc()
    database.definir_abertura_dia(config.DB_PATH, hoje, abertura)
    logger.info("Abertura diária (00:00 UTC) registrada: $%.2f", abertura)
    return abertura


def _cooldown_expirado(chave, minutos):
    valor = database.obter_estado(config.DB_PATH, chave)
    if valor is None:
        return True
    ultimo = datetime.fromisoformat(valor)
    agora = datetime.now(timezone.utc)
    return (agora - ultimo).total_seconds() >= minutos * 60


def _marcar_alerta(chave):
    database.definir_estado(config.DB_PATH, chave, datetime.now(timezone.utc).isoformat())


def _verificar_orcamento_diario():
    """
    (v0.2) No primeiro ciclo de cada dia — no fuso horário LOCAL, não UTC —
    pergunta "Com quanto vamos operar hoje?". Usa uma chave por data local
    em estado_alertas só para saber se já perguntou hoje; a resposta em si
    é guardada em estado_diario via database.definir_orcamento_diario().

    Importante: isso NÃO altera a abertura das 00:00 UTC usada no gatilho
    de compra (RSI/queda) — são dois conceitos de "início de dia" distintos
    e independentes, conforme a regra de ouro da v0.2.
    """
    hoje_local = utils.data_local_hoje()
    chave = f"pergunta_orcamento_{hoje_local}"
    if database.obter_estado(config.DB_PATH, chave) is not None:
        return  # já perguntamos hoje

    if telegram_bot.enviar_mensagem("☀️ Bom dia! Com quanto vamos operar hoje?"):
        database.definir_estado(config.DB_PATH, chave, "1")
        logger.info("Pergunta de orçamento diário enviada (data local: %s).", hoje_local)


def verificar_gatilho_compra(preco_atual, abertura):
    queda_pct = (preco_atual - abertura) / abertura * 100

    limite = max(config.RSI_PERIOD + 1, config.MA_FAST_JANELA_PONTOS * 2) + 5
    precos = database.obter_precos_recentes(config.DB_PATH, limite=limite)

    rsi = indicators.calcular_rsi(precos, period=config.RSI_PERIOD)
    if rsi is None:
        logger.info("Dados insuficientes para calcular RSI ainda (%d pontos).", len(precos))
        return

    virada = indicators.detectar_virada_alta(precos, janela=config.MA_FAST_JANELA_PONTOS)

    condicao = (
        queda_pct <= -config.QUEDA_MINIMA_PERCENTUAL
        and rsi < config.RSI_OVERSOLD_THRESHOLD
        and virada
    )

    if condicao and _cooldown_expirado("ultimo_alerta_compra", config.ALERTA_COOLDOWN_MINUTOS):
        texto = (
            f"⚠️ O Bitcoin atingiu {utils.formatar_moeda(preco_atual)}. "
            f"Identificada oportunidade de compra no fundo!\n"
            f"Comparado às 00:00 UTC, o recuo é de {queda_pct:.2f}%.\n"
            f"RSI atual em {rsi:.1f}."
        )
        if telegram_bot.enviar_mensagem(texto):
            _marcar_alerta("ultimo_alerta_compra")
            logger.info("Alerta de compra enviado (RSI=%.1f, queda=%.2f%%).", rsi, queda_pct)


def verificar_gatilho_venda(preco_atual):
    posicoes = database.get_posicoes_abertas(config.DB_PATH)
    if not posicoes:
        return

    preco_medio = database.calcular_preco_medio(config.DB_PATH)
    if preco_medio is None:
        return

    ganho_pct = (preco_atual - preco_medio) / preco_medio * 100

    if ganho_pct >= config.META_LUCRO_PERCENTUAL and _cooldown_expirado(
        "ultimo_alerta_lucro", config.ALERTA_COOLDOWN_MINUTOS
    ):
        texto = (
            f"🚀 Alerta de Lucro! O Bitcoin valorizou.\n"
            f"Seu preço médio: {utils.formatar_moeda(preco_medio)}\n"
            f"Preço atual: {utils.formatar_moeda(preco_atual)}\n"
            f"Ganho atual: {ganho_pct:.2f}%.\n"
            f"Recomendado realizar venda!"
        )
        if telegram_bot.enviar_mensagem(texto):
            _marcar_alerta("ultimo_alerta_lucro")
            logger.info("Alerta de lucro enviado (ganho=%.2f%%).", ganho_pct)

    elif ganho_pct <= -config.STOP_LOSS_PERCENTUAL and _cooldown_expirado(
        "ultimo_alerta_stoploss", config.ALERTA_COOLDOWN_MINUTOS
    ):
        texto = (
            f"🛑 Alerta de Stop Loss! O mercado derreteu.\n"
            f"Seu preço médio: {utils.formatar_moeda(preco_medio)}\n"
            f"Preço atual: {utils.formatar_moeda(preco_atual)}\n"
            f"Perda atual: {ganho_pct:.2f}%.\n"
            f"Considere realizar a venda para proteger o capital."
        )
        if telegram_bot.enviar_mensagem(texto):
            _marcar_alerta("ultimo_alerta_stoploss")
            logger.warning("Alerta de stop loss enviado (perda=%.2f%%).", ganho_pct)


def ciclo_de_verificacao():
    preco_atual = price_api.obter_preco_atual()
    agora_iso = datetime.now(timezone.utc).isoformat()
    database.inserir_preco(config.DB_PATH, agora_iso, preco_atual)
    database.limpar_precos_antigos(config.DB_PATH, config.RETENCAO_HISTORICO_HORAS)

    # abertura em UTC (padrão de mercado) — inalterada desde a v0.1
    abertura = _obter_abertura_do_dia()

    # pergunta de orçamento em fuso horário LOCAL — novo na v0.2
    _verificar_orcamento_diario()

    logger.info(
        "Preço atual: %s | Abertura 00:00 UTC: %s",
        utils.formatar_moeda(preco_atual), utils.formatar_moeda(abertura),
    )

    verificar_gatilho_compra(preco_atual, abertura)
    verificar_gatilho_venda(preco_atual)
    sistema.registrar_ciclo_ok()


def loop_principal():
    while True:
        inicio = time.monotonic()
        try:
            ciclo_de_verificacao()
        except price_api.ErroAPIExchange as e:
            # Falha de rede/API — não deve quebrar o loop, apenas logar e tentar de novo.
            logger.warning("Falha temporária na API da exchange: %s", e)
        except Exception as e:
            # Rede protetora final: nenhum erro inesperado derruba o processo.
            logger.exception("Erro inesperado no ciclo de verificação: %s", e)

        decorrido = time.monotonic() - inicio
        time.sleep(max(0, config.CHECK_INTERVAL_SECONDS - decorrido))


def _avisar_online():
    """Avisa no Telegram que o bot subiu; falha de envio nunca derruba o bot."""
    try:
        telegram_bot.enviar_mensagem(sistema.texto_online())
    except Exception as e:
        logger.warning("Não foi possível enviar o aviso de bot online: %s", e)


def _ao_desligar(signum, frame):
    """Handler de SIGTERM: tenta avisar no Telegram e encerra o processo."""
    try:
        telegram_bot.enviar_mensagem(sistema.texto_desligando())
    except Exception as e:
        logger.warning("Não foi possível enviar o aviso de desligamento: %s", e)
    sys.exit(0)


def main():
    config.validar()
    database.init_db(config.DB_PATH)

    listener = threading.Thread(target=telegram_bot.escutar_mensagens_loop, daemon=True)
    listener.start()

    signal.signal(signal.SIGTERM, _ao_desligar)
    _avisar_online()

    logger.info("Bot de monitoramento de BTC iniciado. Símbolo: %s", config.SYMBOL)
    loop_principal()


if __name__ == "__main__":
    main()
