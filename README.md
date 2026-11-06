# BTC Alert Bot

Bot de Telegram que monitora o preço do Bitcoin, avisa quando surge uma possível oportunidade de compra, acompanha uma carteira informada manualmente e alerta quando a meta de lucro ou o stop loss é atingido.

> ⚠️ **Aviso:** Este projeto é apenas uma ferramenta de monitoramento/alertas. Não é consultoria financeira, e decisões de investimento são de responsabilidade exclusiva de quem usar o bot.

## Objetivo e motivação

Acompanhar o mercado o dia todo é cansativo, e decidir comprar ou vender no impulso costuma dar prejuízo. O bot existe para:

* **Observar o preço no seu lugar**, 24/7, sem você precisar ficar olhando o gráfico.
* **Dar sinais objetivos de compra**, baseados em regras claras (queda no dia, RSI e média móvel) em vez de emoção.
* **Proteger a carteira**, avisando quando o lucro-alvo ou o limite de perda é alcançado.
* **Rodar em hardware modesto** (TV box, Raspberry Pi, VPS barata): sem servidor de banco de dados, sem `numpy`/`pandas`, sem chave de API da exchange.

O bot **não opera nem executa ordens**: ele só lê preços públicos e envia mensagens. As compras e vendas são feitas por você, que as registra no bot por mensagem.

## O que ele faz

* **Monitora o preço** na Binance (endpoints públicos, somente leitura) a cada 5 minutos.
* **Alerta de compra**, quando as três condições ocorrem juntas:
  1. o preço caiu pelo menos `QUEDA_MINIMA_PERCENTUAL` em relação à abertura do dia (00:00 UTC);
  2. o RSI (Wilder) está abaixo do limite de sobrevenda;
  3. a média móvel rápida virou para cima.

  Um cooldown evita alertas repetidos.
* **Alerta de venda**: compara o preço atual com o preço médio da carteira e avisa ao atingir a meta de lucro ou o stop loss.
* **Carteira manual com FIFO**: você informa o que comprou e vendeu; as vendas consomem primeiro as posições mais antigas, e vendas parciais preservam a data de compra original.
* **Orçamento diário**: de manhã (no seu fuso horário) o bot pergunta com quanto você vai operar no dia.
* **Monitoramento do equipamento**: o comando `saude` mostra se o bot está online, temperatura, RAM, CPU, disco e uptime. Ao iniciar, o bot avisa "🟢 Bot online".
* **Resiliente**: falhas de rede ou da API da exchange não derrubam o processo.

### Comandos no Telegram

| Mensagem | O que faz |
|---|---|
| `comprei 0,005 a 350.000,00` | Registra uma compra (quantidade de BTC e preço) |
| `vendi 1750 a 350000` | Registra uma venda (valor em R$ e cotação) |
| `status` | Preço atual do BTC |
| `carteira` | Posições abertas e preço médio |
| `saude` (ou `ping`) | Estado do bot e da máquina |
| `/comandos` | Lista de comandos |
| `10,00` | Resposta à pergunta diária de orçamento |

Os números aceitam o formato brasileiro (`1.500,00`) e o decimal simples (`1500.00`).

## Como o código está organizado

| Arquivo | Responsabilidade |
|---|---|
| `src/main.py` | Loop principal: a cada ciclo busca o preço, grava, avalia os gatilhos de compra e venda e dispara a pergunta diária. Só orquestra. |
| `config.py` | Lê variáveis de ambiente / `.env` (parser próprio, sem `python-dotenv`) e valida as obrigatórias. |
| `database.py` | Todo o acesso ao SQLite: esquema, migrações, histórico de preços, carteira e estado diário. |
| `price_api.py` | Chamadas à API pública da Binance (preço atual e abertura diária UTC). |
| `indicators.py` | RSI de Wilder e detecção de virada de alta na média móvel, em funções puras. |
| `telegram_bot.py` | Envio de alertas e tratamento dos comandos recebidos (escuta em uma thread separada). |
| `sistema.py` | Temperatura, memória, carga, disco e uptime, usados pelo comando `saude`. |
| `utils.py` | Formatação de moeda (R$) e funções de fuso horário local. |

### Fluxo de cada ciclo

1. Busca o preço atual e grava no SQLite, descartando histórico mais antigo que `RETENCAO_HISTORICO_HORAS`.
2. Obtém (e guarda em cache) o preço de abertura do dia às 00:00 UTC.
3. Pergunta o orçamento diário, uma vez por dia local.
4. Avalia o gatilho de compra e o de venda.

### Decisão de projeto importante

Existem **dois "inícios de dia" independentes**:

* o gatilho de compra usa sempre a abertura das **00:00 UTC** (padrão de mercado);
* a pergunta de orçamento usa o **fuso local** (`FUSO_HORARIO_LOCAL`), só para falar com você de manhã.

Eles nunca devem ser misturados.

## Configuração

Copie `.env.example` para `.env` e preencha. O projeto lê o `.env` da raiz ou variáveis de ambiente.

```bash
cp .env.example .env
```

**Obrigatórias**

* `TELEGRAM_BOT_TOKEN`: token do bot (obtido com o @BotFather).
* `TELEGRAM_CHAT_ID`: ID do chat autorizado a receber alertas e enviar comandos.

**Opcionais (valor padrão)**

| Variável | Padrão | Descrição |
|---|---|---|
| `SYMBOL` | `BTCBRL` | Par na Binance |
| `FUSO_HORARIO_LOCAL` | `America/Boa_Vista` | Fuso da pergunta de orçamento |
| `DB_PATH` | `btc_bot.db` | Caminho do banco SQLite |
| `CHECK_INTERVAL_SECONDS` | `300` | Intervalo entre checagens |
| `RETENCAO_HISTORICO_HORAS` | `24` | Quanto histórico de preço manter |
| `RSI_PERIOD` | `14` | Período do RSI |
| `RSI_OVERSOLD_THRESHOLD` | `30.0` | RSI abaixo disso = sobrevenda |
| `MA_FAST_JANELA_PONTOS` | `3` | Janela da média móvel rápida |
| `QUEDA_MINIMA_PERCENTUAL` | `1.0` | Queda mínima no dia para alertar compra |
| `META_LUCRO_PERCENTUAL` | `5.0` | Alvo de lucro |
| `STOP_LOSS_PERCENTUAL` | `8.0` | Limite de perda |
| `ALERTA_COOLDOWN_MINUTOS` | `60` | Intervalo mínimo entre alertas |

## Executando

Requer Python 3.11+ (dependências: `requests` e `tzdata`).

### Direto

```bash
pip install -r requirements.txt
python src/main.py
```

### Docker Compose

```bash
docker compose up -d --build
```

O banco fica em `./data/btc_bot.db`, fora do container, para não perder o histórico se ele for recriado.

### Systemd (Linux)

Copie o projeto para `/opt/btc_alert_bot`, crie o usuário `btcbot` e instale o serviço:

```bash
sudo cp src/btc_alert_bot.service /etc/systemd/system/btc_bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now btc_bot
```

O serviço limita a memória a `128M` e a CPU a `20%`, pensando em hardware modesto.

## Aviso

Este projeto é uma ferramenta pessoal de apoio e não constitui recomendação de investimento. Criptoativos são voláteis; use por sua conta e risco.
