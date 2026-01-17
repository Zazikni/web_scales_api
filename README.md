

# Backend-сервис управления торговыми весами

Backend-сервис предоставляет REST API для управления пользователями, торговыми весами и товарными данными.  
Все защищённые эндпоинты требуют аутентификации с использованием JWT-токена.

---

## Технологический стек проекта

- **Язык программирования**
  - Python 3.10+

- **Фреймворки и библиотеки**
  - FastAPI — REST API, OpenAPI/Swagger
  - Uvicorn — ASGI-сервер
  - SQLAlchemy — ORM
  - Pydantic + pydantic-settings — конфигурация и валидация данных
  - python-jose — JWT-аутентификация
  - passlib — хеширование паролей пользователей
  - cryptography (Fernet) — шифрование чувствительных данных устройств
  - APScheduler — планировщик фоновых задач
  - scales_mer725_driver — взаимодействие с торговыми весами

- **База данных**
  - SQLite

- **Инструменты**
  - Git
  - venv

---

## Структура репозитория

```
web_scales_api/
├── app/
│ ├── main.py # создание FastAPI, CORS, include_router, startup/shutdown
│ ├── config.py # Settings (.env) через pydantic-settings
│ ├── logging_config.py # настройка логирования
│ ├── deps.py # зависимости FastAPI (DB, auth и т.п.)
│ │
│ ├── api/
│ │ ├── router.py # корневой APIRouter, include subrouters
│ │ └── v1/
│ │ ├── auth.py # /auth/*
│ │ ├── devices.py # /devices/*
│ │ ├── products.py # /devices/{id}/products*, /devices/{id}/upload
│ │ └── auto_update.py # /devices/{id}/auto-update
│ │
│ ├── db/
│ │ ├── base.py # Base для моделей SQLAlchemy
│ │ └── session.py # engine + SessionLocal
│ │
│ ├── models/
│ │ ├── user.py # ORM User
│ │ ├── device.py # ORM Device
│ │ └── schedule.py # ORM AutoUpdateSchedule
│ │
│ ├── schemas/
│ │ ├── auth.py # Pydantic-схемы auth
│ │ ├── device.py # схемы устройств
│ │ ├── products.py # схемы кэша/патча товаров
│ │ └── auto_update.py # схемы автообновления
│ │
│ ├── security/
│ │ ├── jwt.py # encode/decode JWT
│ │ ├── password.py # hash/verify паролей пользователей
│ │ └── fernet.py # encrypt/decrypt пароля устройства
│ │
│ ├── services/
│ │ ├── scales_service.py # fetch/push: взаимодействие с весами
│ │ ├── products_cache_service.py # работа с кэшем: load/save/patch/validate
│ │ ├── auto_update_service.py # логика auto-update (обновление дат и пр.)
│ │ └── scheduler_service.py # управление APScheduler (start/shutdown/rebuild)
│ │
│ └── integrations/
│ └── mertech/
│ └── client.py # get_scales(): фабрика клиента весов
│
├── app.db
├── requirements.txt
├── .env.example
├── .env
└── README.md
```

---

## Установка

## Клонирование репозитория

```bash
git clone https://github.com/Zazikni/web_scales_api
```

```bash
cd web_scales_api
```

## Создание виртуального окружения

```bash
python -m venv .venv
```

## Активация виртуального окружения

### Windows

```powershell
.\.venv\Scripts\activate
```

## Установка зависимостей

```bash
pip install -r requirements.txt
```
## Настройка переменных окружения

Windows
```bash
copy .env.example .env
```
Заполнить необходимые параметры в файле `.env`.

## Запуск backend-сервиса

```bash
uvicorn app.main:app
```

Backend-сервис будет доступен по адресу:

```
http://127.0.0.1:8000
```

Swagger-документация (при `.env DEBUG=true`):

```
http://127.0.0.1:8000/docs
```

---

## Использование

Backend-сервис предоставляет REST API для управления пользователями, торговыми весами и товарными данными.  
Все защищённые эндпоинты требуют аутентификации с использованием JWT-токена.

## Сценарии использования

### 1. Регистрация пользователя

```http
POST /auth/register
```

### 2. Аутентификация пользователя

```http
POST /auth/login
```

Возвращает JWT-токен для выполнения авторизованных запросов.

### 3. Управление устройствами

```http
POST   /devices
GET    /devices
PUT    /devices/{device_id}
DELETE /devices/{device_id}
```

### 4. Работа с товарами

```http
GET   /devices/{device_id}/products
PATCH /devices/{device_id}/products/{plu}
POST  /devices/{device_id}/upload
```

### 5. Автоматическое обновление

```http
GET /devices/{device_id}/auto-update
PUT /devices/{device_id}/auto-update
```

---

## Логирование

В проекте используется централизованная настройка логирования:

- уровень логирования задаётся через `LOG_LEVEL`;
- конфигурация инициализируется при старте приложения.

---

## Безопасность

- пароли пользователей хранятся в виде необратимого хеша;
- пароли устройств хранятся в зашифрованном виде (Fernet);
- JWT-секреты и ключи шифрования хранятся вне исходного кода;
- доступ к API осуществляется по JWT-токенам.
