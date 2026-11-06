# Instalação nativa na TV box (via pendrive)

## 1. Gerar o pacote (no Windows)
Na raiz do projeto:

```powershell
powershell -File deploy\gerar_pacote.ps1
```

Copie a pasta `pacote_tvbox` (ou o `pacote_tvbox.zip`) para o pendrive.

## 2. Instalar na TV box
Espete o pendrive, copie a pasta para a TV box (ex.: `~/pacote_tvbox`) e rode:

```bash
cd ~/pacote_tvbox
sudo bash deploy/instalar.sh
```

O script:
- instala `python3` e o ambiente virtual;
- migra o `.env` e o `btc_bot.db` do Podman (backup em `/root/backup_btc_bot_*`); se não achar, pergunta o caminho;
- ativa o serviço `btc_alert_bot` (liga sozinho no boot e reinicia se cair);
- para o container do Podman, **sem apagá-lo**.

**Sobre o `.env`:** se o container Podman ainda existir, o script o encontra e migra sozinho. Se não, copie o seu `.env` para dentro da pasta `pacote_tvbox` (ao lado da pasta `src`) antes de rodar; ele é usado na instalação. Sem banco encontrado, o bot começa com banco novo.

Pode rodar de novo para atualizar: o `.env` e o banco já instalados não são sobrescritos.

## 3. Conferir
```bash
systemctl status btc_alert_bot
journalctl -u btc_alert_bot -f
```
No Telegram, você deve receber "🟢 Bot online". Envie `saude` para ver temperatura, RAM e uptime.

## 4. Teste de reinício
```bash
sudo reboot
```
Depois que a TV box voltar, o aviso "🟢 Bot online — Reinício da TV box detectado" deve chegar sozinho.

## Observações
- TV boxes costumam não ter relógio com bateria: após uma queda de energia a hora pode ficar errada até a rede sincronizar. O serviço espera `time-sync.target`, mas a hora no aviso pode divergir por alguns instantes.
- Numa queda de energia súbita o aviso "desligando" não é enviado; só o "online" na volta.

## Rollback (voltar ao Podman)
```bash
sudo systemctl disable --now btc_alert_bot
podman start btc_alert_bot
podman update --restart=unless-stopped btc_alert_bot
```
