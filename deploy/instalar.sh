#!/usr/bin/env bash
# Instala/atualiza o BTC Alert Bot de forma nativa (systemd) na TV box.
# Uso: sudo bash deploy/instalar.sh   (a partir da pasta copiada do pendrive)
# Pode ser executado várias vezes: nunca sobrescreve .env nem data/ já instalados.
set -euo pipefail

DESTINO=/opt/btc_alert_bot
USUARIO=btcbot
SERVICO=btc_alert_bot
CONTAINER=btc_alert_bot
ORIGEM="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Execute como root: sudo bash deploy/instalar.sh" >&2
    exit 1
fi

instalar_pacotes() {
    echo "==> Instalando python3 e venv"
    apt-get update -y
    apt-get install -y python3 python3-venv
}

criar_usuario() {
    if ! id "$USUARIO" >/dev/null 2>&1; then
        echo "==> Criando usuário $USUARIO"
        useradd --system --home "$DESTINO" --shell /usr/sbin/nologin "$USUARIO"
    fi
}

copiar_codigo() {
    echo "==> Copiando código para $DESTINO"
    mkdir -p "$DESTINO/data" "$DESTINO/src"
    rm -f "$DESTINO"/*.py   # restos de instalações anteriores, quando o código ficava na raiz
    cp -f "$ORIGEM"/src/*.py "$DESTINO/src/"
    cp -f "$ORIGEM/requirements.txt" "$DESTINO/"
    cp -f "$ORIGEM/deploy/btc_alert_bot.service" "$DESTINO/btc_alert_bot.service"
}

migrar_dados_podman() {
    if [[ -f "$DESTINO/.env" && -f "$DESTINO/data/btc_bot.db" ]]; then
        echo "==> .env e banco já instalados; migração ignorada"
        return
    fi

    local pasta_dados="" pasta_env=""
    if command -v podman >/dev/null 2>&1; then
        local montagens
        montagens="$(podman inspect "$CONTAINER" --format '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}' 2>/dev/null || true)"
        while IFS= read -r origem; do
            if [[ -n "$origem" && -f "$origem/btc_bot.db" ]]; then
                pasta_dados="$origem"
                pasta_env="$(dirname "$origem")"
                break
            fi
        done <<< "$montagens"
    fi

    # Um .env colocado ao lado do pacote (no pendrive) vale para instalar do zero.
    if [[ -f "$ORIGEM/.env" && ! -f "$DESTINO/.env" ]]; then
        cp -a "$ORIGEM/.env" "$DESTINO/.env"
        echo "==> .env copiado do pacote"
    fi

    # Sem banco encontrado, mas com .env já disponível: começa com banco novo, sem perguntar.
    if [[ -z "$pasta_dados" && -f "$DESTINO/.env" ]]; then
        echo "==> Nenhum banco encontrado; o bot começa com banco novo."
    elif [[ -z "$pasta_dados" ]]; then
        echo "Não encontrei os dados do Podman automaticamente."
        read -rp "Pasta que contém btc_bot.db (Enter para pular): " pasta_dados
        if [[ -n "$pasta_dados" ]]; then
            read -rp "Pasta que contém o .env [$(dirname "$pasta_dados")]: " pasta_env
            pasta_env="${pasta_env:-$(dirname "$pasta_dados")}"
        fi
    fi

    local backup="/root/backup_btc_bot_$(date +%Y%m%d_%H%M%S)"
    if [[ -n "$pasta_dados" && -f "$pasta_dados/btc_bot.db" && ! -f "$DESTINO/data/btc_bot.db" ]]; then
        mkdir -p "$backup"
        cp -a "$pasta_dados/btc_bot.db" "$backup/"
        cp -a "$pasta_dados/btc_bot.db" "$DESTINO/data/btc_bot.db"
        echo "==> Banco migrado (backup em $backup)"
    fi
    if [[ -n "$pasta_env" && -f "$pasta_env/.env" && ! -f "$DESTINO/.env" ]]; then
        mkdir -p "$backup"
        cp -a "$pasta_env/.env" "$backup/"
        cp -a "$pasta_env/.env" "$DESTINO/.env"
        echo "==> .env migrado (backup em $backup)"
    fi
    if [[ ! -f "$DESTINO/.env" ]]; then
        echo "ATENÇÃO: nenhum .env encontrado. Crie $DESTINO/.env com TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID e rode o script de novo." >&2
        exit 1
    fi
}

ajustar_db_path() {
    # O .env do container aponta para /app/data; o serviço nativo usa o caminho abaixo.
    sed -i '/^DB_PATH=/d' "$DESTINO/.env"
    printf '\nDB_PATH=%s/data/btc_bot.db\n' "$DESTINO" >> "$DESTINO/.env"
}

preparar_venv() {
    echo "==> Preparando ambiente virtual"
    [[ -d "$DESTINO/venv" ]] || python3 -m venv "$DESTINO/venv"
    "$DESTINO/venv/bin/pip" install --quiet -r "$DESTINO/requirements.txt"
}

ajustar_permissoes() {
    chown -R "$USUARIO:$USUARIO" "$DESTINO"
    chmod 600 "$DESTINO/.env"
}

ativar_servico() {
    echo "==> Ativando serviço systemd"
    cp -f "$DESTINO/btc_alert_bot.service" "/etc/systemd/system/$SERVICO.service"
    systemctl daemon-reload
    systemctl enable "$SERVICO"
    systemctl restart "$SERVICO"
}

desativar_podman() {
    if command -v podman >/dev/null 2>&1 && podman container exists "$CONTAINER" 2>/dev/null; then
        echo "==> Parando o container Podman (não será apagado)"
        podman stop "$CONTAINER" || echo "Aviso: não consegui parar o container."
        podman update --restart=no "$CONTAINER" || echo "Aviso: não consegui desativar o restart do container."
    fi
}

instalar_pacotes
criar_usuario
copiar_codigo
desativar_podman   # antes de migrar: evita copiar o banco com o container gravando
migrar_dados_podman
ajustar_db_path
preparar_venv
ajustar_permissoes
ativar_servico

echo
systemctl --no-pager --lines=5 status "$SERVICO" || true
echo
echo "Pronto. Logs: journalctl -u $SERVICO -f"
