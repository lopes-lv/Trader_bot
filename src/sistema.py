"""
Módulo de Sistema (TV box)
---------------------------
Leitura de temperatura, memória, uptime, carga e disco, e os textos de
status/aviso enviados pelo Telegram. Só usa biblioteca padrão e cada
leitura falha de forma isolada ("indisponível"), então também roda em
sistemas sem /proc e /sys (ex.: Windows durante o desenvolvimento).
"""
import glob
import os
import shutil
import time

import utils

INDISPONIVEL = "indisponível"
LIMITE_REINICIO_SISTEMA_S = 600  # uptime menor que isso => TV box acabou de ligar

INICIO_BOT = time.time()
_ultimo_ciclo_ok = None


def registrar_ciclo_ok():
    """Marca que o último ciclo de verificação de preço terminou sem erro."""
    global _ultimo_ciclo_ok
    _ultimo_ciclo_ok = time.time()


def ler_temperatura_c(base="/sys/class/thermal"):
    """Maior temperatura entre as zonas térmicas, em °C (o kernel informa em milésimos)."""
    leituras = []
    for caminho in glob.glob(os.path.join(base, "thermal_zone*", "temp")):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                leituras.append(int(f.read().strip()) / 1000.0)
        except (OSError, ValueError):
            continue
    return max(leituras) if leituras else None


def ler_memoria_kb(caminho="/proc/meminfo"):
    """(usada, total) em kB, onde usada = MemTotal - MemAvailable; None se incompleto."""
    try:
        valores = {}
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                chave, _, resto = linha.partition(":")
                if chave in ("MemTotal", "MemAvailable"):
                    valores[chave] = int(resto.split()[0])
        return valores["MemTotal"] - valores["MemAvailable"], valores["MemTotal"]
    except (OSError, ValueError, KeyError, IndexError):
        return None


def ler_uptime_s(caminho="/proc/uptime"):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def formatar_duracao(segundos):
    if segundos is None:
        return INDISPONIVEL
    if segundos < 60:
        return "menos de 1min"
    minutos = int(segundos // 60)
    dias, resto = divmod(minutos, 1440)
    horas, minutos = divmod(resto, 60)
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if dias or horas:
        partes.append(f"{horas}h")
    partes.append(f"{minutos}min")
    return " ".join(partes)


def _texto_temperatura():
    temp = ler_temperatura_c()
    return INDISPONIVEL if temp is None else f"{temp:.1f} °C"


def _texto_memoria():
    mem = ler_memoria_kb()
    if mem is None:
        return INDISPONIVEL
    usada, total = mem
    return f"{usada // 1024} MB / {total // 1024} MB ({usada * 100 / total:.0f}%)"


def _texto_carga():
    try:
        c1, c5, c15 = os.getloadavg()
        return f"{c1:.2f} / {c5:.2f} / {c15:.2f}"
    except (AttributeError, OSError):
        return INDISPONIVEL


def _texto_disco():
    try:
        uso = shutil.disk_usage(os.path.abspath(os.sep))
        return f"{uso.used // 2**30} GB / {uso.total // 2**30} GB ({uso.used * 100 / uso.total:.0f}%)"
    except OSError:
        return INDISPONIVEL


def texto_saude():
    if _ultimo_ciclo_ok is None:
        ultimo = "ainda não houve"
    else:
        ultimo = f"há {formatar_duracao(time.time() - _ultimo_ciclo_ok)}"
    return (
        "🟢 Bot online\n"
        f"Último ciclo de preço: {ultimo}\n"
        f"Bot ligado há: {formatar_duracao(time.time() - INICIO_BOT)}\n"
        f"TV box ligada há: {formatar_duracao(ler_uptime_s())}\n"
        f"🌡 Temperatura: {_texto_temperatura()}\n"
        f"🧠 RAM: {_texto_memoria()}\n"
        f"⚙️ Carga CPU (1/5/15 min): {_texto_carga()}\n"
        f"💾 Disco: {_texto_disco()}"
    )


def texto_online():
    uptime = ler_uptime_s()
    if uptime is not None and uptime < LIMITE_REINICIO_SISTEMA_S:
        motivo = "Reinício da TV box detectado."
    else:
        motivo = "Reinício só do bot."
    return (
        "🟢 Bot online\n"
        f"{motivo}\n"
        f"Hora local: {utils.agora_local().strftime('%d/%m/%Y %H:%M')}\n"
        f"TV box ligada há: {formatar_duracao(uptime)}"
    )


def texto_desligando():
    return "🔴 Bot desligando (parada ou reinício do sistema)"
