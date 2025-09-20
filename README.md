# Nightscout Telegram WebApp Bridge

Минимальный проект, который принимает записи из Nightscout и позволяет пользователю редактировать их через Telegram Mini App.

## Возможности
- FastAPI-бэкенд (Python 3.10+) с тремя API-эндпоинтами:
  - `GET /api/treatment` — возвращает данные записи по `clientId`.
  - `PUT /api/treatment` — обновляет запись (только изменённые поля) и синхронизирует JSON-метаданные.
  - `POST /api/upload` — принимает фото (jpg/png до 5 МБ), сохраняет на диске и отдаёт публичный URL.
- Проверка `initData` Telegram WebApp по HMAC-SHA256 и фильтрация `ALLOWED_USER_IDS`.
- Работа с Nightscout через REST API c поддержкой `token` и/или `api-secret`.
- Telegram Mini App (`/webapp/`) на чистом HTML/CSS/JS с предзаполнением формы, загрузкой фото и отправкой изменений.
- Утилита `send_tg_with_webapp(summary_text, cid)` для отправки сообщения в Telegram с кнопкой «Редактировать».

## Подготовка окружения
1. Скопируйте `.env.example` в `.env` и заполните значения (в репозитории уже создан шаблон под `toolsmegusto.duckdns.org`).
   - `NS_URL` → `http://megusto.duckdns.org:1337`, `NS_API_SECRET` → `megusto2025nightscout`.
   - `TG_TOKEN` уже указан; пропишите `TG_CHAT_ID` (идентификатор вашего чата) и `ALLOWED_USER_IDS` — **числовые** Telegram user.id (например, узнайте через @userinfobot). Псевдоним `@gstm0` нужно заменить на его ID, иначе доступ будет запрещён.
   - `MEDIA_ROOT` → `/var/www/ns-media`, `MEDIA_BASE_URL` → `https://toolsmegusto.duckdns.org/media`.
   - `APP_BASE_URL` → `https://toolsmegusto.duckdns.org`.
   - `HOST`, `PORT` оставьте `0.0.0.0` и `8080`.
2. Установите зависимости: `pip install -r requirements.txt`.
3. Запустите приложение: `uvicorn app.main:app --host $HOST --port $PORT`.
4. Настройте Nginx на раздачу `MEDIA_ROOT` по `MEDIA_BASE_URL`.

### Развёртывание на toolsmegusto.duckdns.org (VDS)

0. **VDS**: создайте пользователя на сервере, обновите пакеты (`sudo apt update && sudo apt upgrade -y`) и установите зависимости `nginx python3-venv python3-pip git ufw`. Разрешите 22/80/443 в `ufw` и включите `ufw enable`.
1. **DNS**: в панели DuckDNS создайте запись `toolsmegusto.duckdns.org`, укажите публичный IP VDS.
2. **TLS-сертификат**: установите certbot (`sudo apt install certbot python3-certbot-nginx`) и получите сертификат `sudo certbot certonly --nginx -d toolsmegusto.duckdns.org`.
3. **Nginx**: скопируйте `deploy/nginx.conf` в `/etc/nginx/sites-available/ns-webapp.conf`, проверьте пути (сертификаты, alias медиа) и включите сайт (`sudo ln -s .../ns-webapp.conf /etc/nginx/sites-enabled/`). Перезапустите Nginx (`sudo nginx -t && sudo systemctl reload nginx`).
4. **Виртуальное окружение**: в директории проекта выполните `python -m venv .venv && source .venv/bin/activate`, затем `pip install -r requirements.txt`.
5. **Сервис**: скопируйте `deploy/systemd/ns-webapp.service` в `/etc/systemd/system/`, при необходимости поменяйте `User=`/`WorkingDirectory`. Затем `sudo systemctl daemon-reload && sudo systemctl enable --now ns-webapp.service`.
6. **Каталог медиа**: создайте `sudo mkdir -p /var/www/ns-media && sudo chown www-data:www-data /var/www/ns-media` (или владельца сервиса).
7. **Проверка**: откройте `https://toolsmegusto.duckdns.org/webapp/?cid=test` в Telegram WebView (с валидным `cid` и initData), убедитесь, что API отвечает (`curl https://toolsmegusto.duckdns.org/healthz`).
8. **Telegram**: используя `scripts/send_telegram.py`, укажите реальный `cid` и текст, чтобы отправить сообщение с кнопкой «Редактировать».

## Интеграция с Яндекс-навыком
После создания записи в Nightscout (с заполнением `treatment.clientId`), вызовите утилиту `scripts/send_telegram.py`:

```bash
python scripts/send_telegram.py <CID> "Краткое описание записи"
```

или подключите функцию непосредственно:

```python
from scripts.send_telegram import send_tg_with_webapp

send_tg_with_webapp("Инсулин 3 ед, углеводы 25 г", cid)
```

Кнопка «✏️ Редактировать» откроет Telegram Mini App по адресу `APP_BASE_URL/webapp/?cid=<cid>`.

## Примечания по безопасности
- Логи не содержат `initData` или секреты.
- Пользователи вне списка `ALLOWED_USER_IDS` получают HTTP 403.
- Фото сохраняются в подкаталогах `YYYY/MM` и доступны только через настроенный Nginx.

## Структура проекта
```
app/
  main.py              # основной FastAPI-приложение и эндпоинты
  config.py            # загрузка настроек из окружения
  services/nightscout.py
  utils/telegram.py   # проверка initData
  utils/treatments.py # работа с метаданными notes
  webapp/             # статический Telegram Mini App
scripts/send_telegram.py
requirements.txt
.env.example
README.md
```

## Проверка
- `GET /healthz` возвращает `{ "status": "ok" }`.
- Используйте `curl` или Postman для ручной проверки API (не передавайте реальные секреты в логи).
