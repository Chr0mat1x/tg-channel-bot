# Деплой бота на сервер

Боту нужен постоянный доступ к `api.telegram.org` и работа 24/7 — локальный компьютер для этого подходит плохо.

## Вариант 1. VPS + Docker (рекомендуется)

Подойдёт любой VPS с Ubuntu 22.04/24.04, 1 ГБ RAM, 10 ГБ диска.

```bash
# на сервере
apt update && apt install -y docker.io docker-compose-plugin
mkdir -p /opt/tg-bot && cd /opt/tg-bot
# скопировать сюда папку bot/, requirements.txt, Dockerfile, docker-compose.yml, .env
docker compose up -d --build
docker compose logs -f
```

База хранится в `./data/bot.db` (том из compose), настройки канала и слоты сохраняются между перезапусками.

Обновление после правок:

```bash
docker compose up -d --build
```

## Вариант 2. VPS + systemd (без Docker)

```bash
apt update && apt install -y python3.12 python3.12-venv
mkdir -p /opt/tg-bot && cd /opt/tg-bot
# скопировать проект
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`/etc/systemd/system/tg-bot.service`:

```ini
[Unit]
Description=Telegram channel bot
After=network-online.target

[Service]
WorkingDirectory=/opt/tg-bot
ExecStart=/opt/tg-bot/.venv/bin/python -m bot
Restart=always
RestartSec=15
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now tg-bot
journalctl -u tg-bot -f
```

## Вариант 3. Локальный компьютер (уже настроено)

Задача Планировщика Windows «TG Channel Bot» поднимает бота при входе в систему и проверяет его каждые 5 минут. Минусы: работает только при включённом компьютере и требует стабильного доступа к Telegram с домашней сети.

Проверить статус:

```powershell
Get-ScheduledTask -TaskName "TG Channel Bot" | Select-Object State
Get-Content C:\Users\Пользователь\Documents\tg-channel-bot\bot.log -Tail 20
```

## Что переносить

- `bot/` — код
- `requirements.txt`
- `Dockerfile`, `docker-compose.yml`
- `.env` — токен и ID (не коммитить)
- `bot.db` — база с привязанным каналом, слотами и историей постов (по желанию)
