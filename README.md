

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
backend/
├── app/                         # Код backend-сервиса
│   ├── main.py                  # Точка входа FastAPI, middleware, маршруты
│   ├── config.py                # Конфигурация приложения
│   ├── db.py                    # Инициализация базы данных и сессий
│   ├── models.py                # ORM-модели
│   ├── schemas.py               # Pydantic-схемы запросов и ответов
│   ├── security.py              # JWT, хеширование паролей, безопасность
│   ├── deps.py                  # Зависимости FastAPI 
│   ├── scales_client.py         # Работа с весами и кэшем товаров
│   ├── logging_config.py        # Конфигурация логирования
│   └── scheduler.py             # Планировщик фоновых задач
│
├── requirements.txt             # Зависимости Python
├── .env.example                 # Пример файла переменных окружения
├── .gitignore                   # Исключения для Git
└── README.md                    # Документация backend-сервиса
```

---

## Установка

## Клонирование репозитория

```bash
git clone https://github.com/Zazikni/web_scales_api
```

```bash
cd backend
```

## Создание виртуального окружения

```bash
python -m venv .venv
```

## Активация виртуального окружения

### Windows (PowerShell)

```powershell
.\.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

## Установка зависимостей

```bash
pip install -r requirements.txt
```

## Настройка переменных окружения

```bash
cp .env.example .env
```

Заполнить необходимые параметры в файле `.env`.

## Запуск backend-сервиса

```bash
uvicorn app.main:app --port 8000
```

Backend-сервис будет доступен по адресу:

```
http://127.0.0.1:8000
```

Swagger-документация (при `DEBUG=true`):

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
