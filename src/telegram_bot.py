"""
Módulo do Telegram
-------------------
Envio de alertas e escuta (long polling) de mensagens do usuário.

Comandos aceitos a partir da v0.2:
    "comprei [quantidade] a [preço]"   ex.: "comprei 0,005 a 350.000,00"
    "vendi [valor em R$] a [cotação]"  ex.: "vendi 1750 a 350000"
    "status"      -> preço atual do BTC em tempo real
    "carteira"    -> posições abertas e preço médio (era o antigo "status")
    "saude"       -> bot online + temperatura, RAM e uptime da TV box
    "/comandos"   -> lista de comandos
    "[valor],00"  -> resposta à pergunta diária de orçamento (ex.: "10,00")
"""
import re
import time
import logging
import requests

import config
import database
import price_api
import sistema
import utils

logger = logging.getLogger("telegram_bot")

API_BASE = "https://api.telegram.org/bot{token}"

# v0.2: regex de compra/venda atualizadas para aceitar quantidade e preço
REGEX_COMPRA = re.compile(r"^\s*comprei\s+([\d.,]+)\s+a\s+([\d.,]+)\s*$", re.IGNORECASE)
REGEX_VENDA = re.compile(r"^\s*vendi\s+([\d.,]+)\s+a\s+([\d.,]+)\s*$", re.IGNORECASE)
# Resposta ao orçamento diário: sempre no formato "valor,00" (ex.: "10,00", "1.500,00")
REGEX_ORCAMENTO = re.compile(r"^\s*(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})\s*$")

# Adicionado na v0.2.1: Sessão para reaproveitamento de conexões TCP
session = requests.Session()


def _parse_numero_brl(texto_valor):
    """
    Converte um número em texto para float, aceitando o formato brasileiro
    (350.000,00), o formato simples com ponto decimal (0.005, 65000.5) ou
    nenhum separador (350000).

    Regra: se houver ponto E vírgula, o separador que aparece por último no
    texto é tratado como decimal. Se houver só vírgula, ela é decimal
    (padrão brasileiro). Se houver só ponto, assumimos decimal — exceto no
    caso clássico de milhar sem casas decimais (ex.: "350.000" -> 350000).
    """
    limpo = texto_valor.strip()
    tem_ponto = "." in limpo
    tem_virgula = "," in limpo

    if tem_ponto and tem_virgula:
        if limpo.rfind(",") > limpo.rfind("."):
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            limpo = limpo.replace(",", "")
    elif tem_virgula:
        limpo = limpo.replace(",", ".")
    elif tem_ponto:
        partes = limpo.split(".")
        if len(partes) > 2:
            # múltiplos pontos -> todos são separadores de milhar
            limpo = limpo.replace(".", "")
        elif len(partes) == 2:
            antes, depois = partes
            if len(depois) == 3 and antes and len(antes) <= 3 and not antes.startswith("0"):
                # ex.: "350.000" -> separador de milhar -> 350000
                limpo = antes + depois
            # senão, já é um ponto decimal válido (ex.: "0.005", "65000.5")

    return float(limpo)


def enviar_mensagem(texto, chat_id=None):
    chat_id = chat_id or config.TELEGRAM_CHAT_ID
    url = API_BASE.format(token=config.TELEGRAM_BOT_TOKEN) + "/sendMessage"
    try:
        resp = session.post(url, data={"chat_id": chat_id, "text": texto}, timeout=10)
        resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error("Falha ao enviar mensagem ao Telegram: %s", e)
        return False


def _obter_atualizacoes(offset, timeout=30):
    url = API_BASE.format(token=config.TELEGRAM_BOT_TOKEN) + "/getUpdates"
    resp = session.get(
        url, params={"offset": offset, "timeout": timeout}, timeout=timeout + 10
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def _processar_texto(texto):
    """
    Retorna uma tupla (tipo, conteudo) — tipo é sempre 'texto' — se o
    texto corresponder a um comando conhecido, ou None caso contrário.
    """
    texto_normalizado = texto.strip().lower()

    if texto_normalizado in ("/comandos", "comandos", "/help", "/start"):
        return ("texto", (
            "🤖 Comandos disponíveis:\n\n"
            "status — preço atual do BTC em tempo real\n"
            "carteira — ativos abertos e preços de compra\n"
            "comprei [quantidade] a [preço] — registra uma compra\n"
            "   ex.: comprei 0,005 a 350.000,00\n"
            "vendi [valor em R$] a [cotação] — registra uma venda\n"
            "   ex.: vendi 1750 a 350000\n"
            "saude — confere se o bot está online e mostra temperatura, RAM e uptime da TV box\n"
            "/comandos — mostra esta lista"
        ))

    m_compra = REGEX_COMPRA.match(texto)
    if m_compra:
        quantidade = _parse_numero_brl(m_compra.group(1))
        preco = _parse_numero_brl(m_compra.group(2))
        if quantidade <= 0 or preco <= 0:
            return ("texto", "⚠️ Quantidade e preço devem ser maiores que zero.")
        database.registrar_compra(config.DB_PATH, preco, quantidade)
        preco_medio = database.calcular_preco_medio(config.DB_PATH)
        saldo_total = sum(p[2] for p in database.get_posicoes_abertas(config.DB_PATH))
        return ("texto", (
            f"✅ Compra registrada: {quantidade:.8f} BTC a {utils.formatar_moeda(preco)}\n"
            f"Preço médio da carteira: {utils.formatar_moeda(preco_medio)}\n"
            f"Saldo total: {saldo_total:.8f} BTC"
        ))

    m_venda = REGEX_VENDA.match(texto)
    if m_venda:
        valor_reais = _parse_numero_brl(m_venda.group(1))
        preco_cotacao = _parse_numero_brl(m_venda.group(2))
        if valor_reais <= 0 or preco_cotacao <= 0:
            return ("texto", "⚠️ Valor e cotação devem ser maiores que zero.")
        quantidade_alvo = valor_reais / preco_cotacao
        resumo = database.vender_quantidade(config.DB_PATH, quantidade_alvo, preco_cotacao)
        if resumo is None:
            return ("texto", "⚠️ Nenhuma posição em aberto para fechar.")
        emoji = "🟢" if resumo["pnl_reais"] >= 0 else "🔴"
        resposta = (
            f"✅ Venda registrada: {resumo['quantidade_vendida']:.8f} BTC "
            f"({utils.formatar_moeda(valor_reais)}) a {utils.formatar_moeda(preco_cotacao)}\n"
            f"{emoji} PnL realizado: {utils.formatar_moeda(resumo['pnl_reais'])} "
            f"({resumo['pnl_pct']:.2f}%)"
        )
        if resumo["restante_nao_atendido"] > 1e-8:
            resposta += (
                f"\n⚠️ Saldo insuficiente: {resumo['restante_nao_atendido']:.8f} BTC "
                f"não puderam ser vendidos (excedia a carteira)."
            )
        return ("texto", resposta)

    if texto_normalizado in ("carteira", "/carteira"):
        posicoes = database.get_posicoes_abertas(config.DB_PATH)
        if not posicoes:
            return ("texto", "Nenhum ativo em carteira no momento.")
        linhas = ["📊 Carteira em aberto:"]
        saldo_total = 0.0
        for _pid, valor_compra, quantidade, data_compra in posicoes:
            linhas.append(
                f"• {quantidade:.8f} BTC a {utils.formatar_moeda(valor_compra)} ({data_compra})"
            )
            saldo_total += quantidade
        preco_medio = database.calcular_preco_medio(config.DB_PATH)
        linhas.append("")
        linhas.append(f"Saldo total: {saldo_total:.8f} BTC")
        linhas.append(f"Preço médio: {utils.formatar_moeda(preco_medio)}")
        return ("texto", "\n".join(linhas))

    if texto_normalizado in ("saude", "saúde", "/saude", "ping"):
        return ("texto", sistema.texto_saude())

    if texto_normalizado in ("status", "/status"):
        try:
            preco_atual = price_api.obter_preco_atual()
        except price_api.ErroAPIExchange:
            return ("texto", "⚠️ Não foi possível obter o preço atual agora. Tente novamente em instantes.")
        return ("texto", f"💰 Bitcoin agora: {utils.formatar_moeda(preco_atual)}")

    m_orcamento = REGEX_ORCAMENTO.match(texto)
    if m_orcamento:
        valor = _parse_numero_brl(texto.strip())
        hoje = utils.data_local_hoje()
        database.definir_orcamento_diario(config.DB_PATH, hoje, valor)
        return ("texto", f"✅ Orçamento de hoje definido: {utils.formatar_moeda(valor)}")

    return None


def escutar_mensagens_loop():
    """
    Loop de long-polling do Telegram — deve rodar em uma thread separada (daemon).
    Fica bloqueado aguardando novas mensagens, com uso de CPU praticamente nulo.
    Qualquer falha de rede é absorvida e o loop tenta novamente.
    """
    offset = 0
    logger.info("Listener do Telegram iniciado.")
    while True:
        try:
            atualizacoes = _obter_atualizacoes(offset)
            for att in atualizacoes:
                offset = att["update_id"] + 1
                mensagem = att.get("message") or att.get("edited_message")
                if not mensagem or "text" not in mensagem:
                    continue
                chat_id = str(mensagem["chat"]["id"])
                if chat_id != str(config.TELEGRAM_CHAT_ID):
                    continue  # ignora mensagens de qualquer outro chat
                resultado = _processar_texto(mensagem["text"])
                if resultado:
                    _tipo, conteudo = resultado
                    enviar_mensagem(conteudo, chat_id=chat_id)
        except requests.exceptions.RequestException as e:
            logger.warning("Falha de rede no listener do Telegram: %s", e)
            time.sleep(5)
        except Exception as e:
            logger.exception("Erro inesperado no listener do Telegram: %s", e)
            time.sleep(5)
