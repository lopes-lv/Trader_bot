"""
Módulo de Utilidades (novo na v0.2)
-------------------------------------
Funções pequenas e compartilhadas entre os demais módulos — evita duplicar
lógica de formatação monetária e de fuso horário em vários lugares.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import config


def formatar_moeda(valor):
    """
    Formata um número no padrão monetário brasileiro: R$ 65.000,00
    (não usamos o módulo `locale` pois ele depende de locales instalados no
    SO, o que nem sempre está disponível em servidores mínimos).
    """
    if valor is None:
        return "—"
    texto = f"{valor:,.2f}"  # formato US: "65,000.00"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def data_local_hoje():
    """Data de hoje (YYYY-MM-DD) no fuso horário local configurado."""
    return datetime.now(ZoneInfo(config.FUSO_HORARIO_LOCAL)).strftime("%Y-%m-%d")


def agora_local():
    return datetime.now(ZoneInfo(config.FUSO_HORARIO_LOCAL))
