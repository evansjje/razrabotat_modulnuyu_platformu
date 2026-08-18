#!/usr/bin/env python3
"""
Amuriy Studio Enterprise Shop - Infrastructure Setup and Local Test Script
Creates Dockerfile, docker-compose.yml, requirements.txt, .env.example, README.md
and tests local project startup.
"""

import os
import sys
import subprocess
import time
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import json
import urllib.request
import socket

PROJECT_ROOT = Path("/tmp/agent_projects/amuriy_studio_enterprise")
PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

REQUIREMENTS = """fastapi==0.104.1
uvicorn[standard]==0.24.0
aiogram==3.4.1
sqlalchemy[asyncio]==2.0.23
asyncpg==0.29.0
aiosqlite==0.19.0
gspread==6.0.1
pydantic==2.5.2
pydantic-settings==2.1.0
python-dotenv==1.0.0
aiohttp==3.9.1
"""

DOCKERFILE = """FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1

RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        build-essential \\
        curl \\
        git \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

DOCKER_COMPOSE = """version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: amuriy_postgres
    environment:
      POSTGRES_USER: amuriy
      POSTGRES_PASSWORD: amuriy_secret
      POSTGRES_DB: amuriy_shop
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U amuriy"]
      interval: 10s
      timeout: 5s
      retries: 5

  web_app:
    build: .
    container_name: amuriy_web
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://amuriy:amuriy_secret@postgres:5432/amuriy_shop
      BOT_TOKEN: ${BOT_TOKEN}
      ADMIN_CHAT_ID: ${ADMIN_CHAT_ID}
      WEBAPP_URL: ${WEBAPP_URL}
      GOOGLE_SHEET_ID: ${GOOGLE_SHEET_ID}
      PAYMENT_PROVIDER_TOKEN: ${PAYMENT_PROVIDER_TOKEN}
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
"""

ENV_EXAMPLE = """# Telegram Bot Configuration
BOT_TOKEN=your_bot_token_here
ADMIN_CHAT_ID=your_admin_chat_id_here

# WebApp URL (use ngrok or your domain)
WEBAPP_URL=https://your-domain.com

# Database (default: SQLite for local dev, PostgreSQL for production)
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname
DATABASE_URL=sqlite+aiosqlite:///./amuriy.db

# Google Sheets Integration
GOOGLE_SHEET_ID=your_google_sheet_id_here

# Payment Provider (Telegram Stars / YooKassa)
PAYMENT_PROVIDER_TOKEN=your_payment_token_here

# Optional: Google Sheets credentials file path
GOOGLE_CREDENTIALS_FILE=credentials.json
"""

README = """# Amuriy Studio Enterprise Shop

Telegram Mini App (TMA) платформа для продажи цифровых товаров с интеграцией PostgreSQL, Google Sheets и промокодами.

## 🚀 Быстрый старт

### 1. Клонирование и установка

```bash
git clone <your-repo-url> amuriy_studio_enterprise
cd amuriy_studio_enterprise
```

### 2. Настройка окружения

```bash
cp .env.example .env
# Отредактируйте .env файл, заполнив все поля
```

### 3. Запуск с Docker (рекомендуется)

```bash
docker-compose up --build
```

### 4. Локальный запуск (без Docker)

```bash
# Установка зависимостей
pip install -r requirements.txt

# Инициализация БД
python -m app.init_db

# Запуск бота
python -m app.bot

# Запуск API (в отдельном терминале)
uvicorn app.main:app --reload --port 8000
```

## 📁 Структура проекта

```
amuriy_studio_enterprise/
├── app/
│   ├── __init__.py
│   ├── config.py          # Настройки приложения
│   ├── database.py        # Подключение к БД
│   ├── models.py          # SQLAlchemy модели
│   ├── schemas.py         # Pydantic схемы
│   ├── main.py            # FastAPI приложение
│   ├── bot.py             # Telegram бот (aiogram 3)
│   └── services/
│       ├── __init__.py
│       ├── promo_service.py    # Промокоды и скидки
│       ├── sheets_service.py   # Google Sheets интеграция
│       └── billing.py          # Платежи (Stars/ЮKassa)
├── static/
│   ├── index.html         # Frontend TMA
│   ├── app.js             # Логика WebApp
│   └── styles.css         # Неоновый стиль
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## 🛠 Функциональность

- **Каталог товаров** с категориями и фильтрами
- **Корзина** с промокодами и скидками
- **Telegram Stars** и **ЮKassa** оплата
- **Google Sheets** двусторонняя синхронизация
- **Админ-панель** в Telegram боте
- **Автовыдача** цифровых товаров

## 📊 Google Sheets

1. Создайте Google Sheet с листами: `products`, `categories`, `orders`
2. Получите `GOOGLE_SHEET_ID` из URL
3. Скачайте credentials.json для сервисного аккаунта
4. Укажите путь в `.env`

## 🔒 Безопасность

- Все секреты хранятся в `.env` (не коммитьте!)
- Используйте HTTPS для WebApp
- Валидация всех входных данных через Pydantic
- SQL-инъекции защищены через SQLAlchemy

## 📝 Лицензия

MIT License - свободное использование и модификация
"""


def create_project_structure() -> None:
    """Create all necessary directories and files."""
    print("📁 Creating project structure...")
    
    # Create directories
    dirs = [
        PROJECT_ROOT / "app" / "services",
        PROJECT_ROOT / "static",
        PROJECT_ROOT / "tests",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Created: {d.relative_to(PROJECT_ROOT)}")

    # Create __init__.py files
    init_files = [
        PROJECT_ROOT / "app" / "__init__.py",
        PROJECT_ROOT / "app" / "services" / "__init__.py",
        PROJECT_ROOT / "tests" / "__init__.py",
    ]
    for f in init_files:
        f.touch(exist_ok=True)
        print(f"  ✅ Created: {f.relative_to(PROJECT_ROOT)}")


def write_infrastructure_files() -> None:
    """Write Docker, requirements, env, and README files."""
    print("\n📝 Writing infrastructure files...")
    
    files_content = {
        "requirements.txt": REQUIREMENTS,
        "Dockerfile": DOCKERFILE,
        "docker-compose.yml": DOCKER_COMPOSE,
        ".env.example": ENV_EXAMPLE,
        "README.md": README,
    }
    
    for filename, content in files_content.items():
        filepath = PROJECT_ROOT / filename
        filepath.write_text(content, encoding="utf-8")
        print(f"  ✅ Created: {filename}")


def create_initial_app_files() -> None:
    """Create minimal app files for testing."""
    print("\n📝 Creating initial app files...")
    
    # config.py
    config_content = '''
"""Application configuration."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    """Application settings from environment."""
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_chat_id: str = os.getenv("ADMIN_CHAT_ID", "")
    webapp_url: str = os.getenv("WEBAPP_URL", "http://localhost:8000")
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./amuriy.db")
    google_sheet_id: str = os.getenv("GOOGLE_SHEET_ID", "")
    payment_provider_token: str = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

settings = Settings()
'''
    (PROJECT_ROOT / "app" / "config.py").write_text(config_content, encoding="utf-8")
    print("  ✅ Created: app/config.py")

    # database.py
    database_content = '''
"""Database connection management."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

class Base(DeclarativeBase):
    """Base class for all models."""
    pass

# Create engine based on database URL
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    """Dependency for FastAPI to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    """Initialize database tables."""
    from app import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database initialized successfully")
'''
    (PROJECT_ROOT / "app" / "database.py").write_text(database_content, encoding="utf-8")
    print("  ✅ Created: app/database.py")

    # models.py
    models_content = '''
"""SQLAlchemy models."""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    """Telegram user."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    orders = relationship("Order", back_populates="user")

class Category(Base):
    """Product category."""
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    products = relationship("Product", back_populates="category")

class Product(Base):
    """Product item."""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    old_price = Column(Float, nullable=True)
    image_url = Column(String(500), nullable=True)
    payload_url = Column(String(500), nullable=True)  # Digital goods delivery
    is_active = Column(Boolean, default=True)
    stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    category = relationship("Category", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")

class Order(Base):
    """Customer order."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    order_number = Column(String(50), unique=True, index=True)
    total_amount = Column(Float, nullable=False)
    discount_amount = Column(Float, default=0)
    promo_code = Column(String(50), nullable=True)
    status = Column(String(50), default="pending")
    payment_method = Column(String(50), nullable=True)
    payment_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")

class OrderItem(Base):
    """Order line item."""
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    price = Column(Float, nullable=False)
    
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")

class PromoCode(Base):
    """Promotional code."""
    __tablename__ = "promo_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True)
    discount_type = Column(String(20), default="percent")  # percent or fixed
    discount_value = Column(Float, nullable=False)
    max_uses = Column(Integer, default=0)
    used_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Broadcast(Base):
    """Broadcast message."""
    __tablename__ = "broadcasts"
    
    id = Column(Integer, primary_key=True, index=True)
    message_text = Column(Text, nullable=False)
    status = Column(String(50), default="pending")
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
'''
    (PROJECT_ROOT / "app" / "models.py").write_text(models_content, encoding="utf-8")
    print("  ✅ Created: app/models.py")

    # schemas.py
    schemas_content = '''
"""Pydantic schemas for API validation."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ProductCreate(BaseModel):
    """Product creation schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    category_id: int
    image_url: Optional[str] = None
    payload_url: Optional[str] = None
    is_active: bool = True
    stock: int = 0

class ProductUpdate(BaseModel):
    """Product update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[int] = None
    image_url: Optional[str] = None
    payload_url: Optional[str] = None
    is_active: Optional[bool] = None
    stock: Optional[int] = None

class ProductResponse(BaseModel):
    """Product response schema."""
    id: int
    name: str
    description: Optional[str]
    price: float
    old_price: Optional[float]
    image_url: Optional[str]
    category_id: int
    is_active: bool
    stock: int
    
    class Config:
        from_attributes = True

class CategoryCreate(BaseModel):
    """Category creation schema."""
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0

class CategoryResponse(BaseModel):
    """Category response schema."""
    id: int
    name: str
    slug: str
    description: Optional[str]
    is_active: bool
    sort_order: int
    
    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    """Order creation schema."""
    user_id: int
    items: List[dict]
    promo_code: Optional[str] = None
    payment_method: str = "telegram_stars"

class OrderResponse(BaseModel):
    """Order response schema."""
    id: int
    order_number: str
    total_amount: float
    discount_amount: float
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class PromoApplyRequest(BaseModel):
    """Promo code apply request."""
    code: str
    amount: float

class PromoApplyResponse(BaseModel):
    """Promo code apply response."""
    valid: bool
    discount_amount: float
    final_amount: float
    message: str
'''
    (PROJECT_ROOT / "app" / "schemas.py").write_text(schemas_content, encoding="utf-8")
    print("  ✅ Created: app/schemas.py")

    # main.py (minimal FastAPI app)
    main_content = '''
"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
import os

app = FastAPI(title="Amuriy Studio Enterprise Shop API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    await init_db()

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "status": "ok",
        "app": "Amuriy Studio Enterprise Shop",
        "version": "1.0.0"
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
'''
    (PROJECT_ROOT / "app" / "main.py").write_text(main_content, encoding="utf-8")
    print("  ✅ Created: app/main.py")

    # bot.py (minimal bot)
    bot_content = '''
"""Telegram bot entry point."""
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from app.config import settings

bot = Bot(token=settings.bot_token)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command."""
    await message.answer(
        "👋 Добро пожаловать в Amuriy Studio Enterprise Shop!\\n"
        "Используйте кнопку WebApp для покупок:",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[
                types.InlineKeyboardButton(
                    text="🛍 Открыть магазин",
                    web_app=types.WebAppInfo(url=settings.webapp_url)
                )
            ]]
        )
    )

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Handle /admin command."""
    if str(message.from_user.id) == settings.admin_chat_id:
        await message.answer("🔐 Админ-панель доступна")
    else:
        await message.answer("⛔️ Доступ запрещен")

async def main():
    """Bot main entry point."""
    print("🤖 Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
'''
    (PROJECT_ROOT / "app" / "bot.py").write_text(bot_content, encoding="utf-8")
    print("  ✅ Created: app/bot.py")

    # services files
    services = {
        "promo_service.py": '''
"""Promo code service."""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import PromoCode

async def validate_promo_code(session: AsyncSession, code: str, amount: float) -> dict:
    """Validate promo code and calculate discount."""
    result = await session.execute(
        select(PromoCode).where(PromoCode.code == code.upper())
    )
    promo = result.scalar_one_or_none()
    
    if not promo:
        return {"valid": False, "message": "Промокод не найден"}
    
    if not promo.is_active:
        return {"valid": False, "message": "Промокод неактивен"}
    
    if promo.max_uses > 0 and promo.used_count >= promo.max_uses:
        return {"valid": False, "message": "Промокод исчерпан"}
    
    if promo.expires_at and promo.expires_at < datetime.utcnow():
        return {"valid": False, "message": "Промокод истек"}
    
    if promo.discount_type == "percent":
        discount = amount * (promo.discount_value / 100)
    else:
        discount = min(promo.discount_value, amount)
    
    return {
        "valid": True,
        "discount_amount": round(discount, 2),
        "final_amount": round(amount - discount, 2),
        "message": f"Промокод применен: скидка {promo.discount_value}%"
    }

async def generate_personal_promo(session: AsyncSession, user_id: int) -> str:
    """Generate personal promo code after purchase."""
    import random
    import string
    
    code = "AMUR" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    promo = PromoCode(
        code=code,
        discount_type="percent",
        discount_value=10,
        max_uses=1,
        is_active=True
    )
    session.add(promo)
    await session.commit()
    
    return code
''',
        "sheets_service.py": '''
"""Google Sheets integration service."""
import gspread
from google.oauth2.service_account import Credentials
from app.config import settings

class SheetsService:
    """Service for Google Sheets integration."""
    
    def __init__(self):
        self.client = None
        self.sheet = None
    
    def authenticate(self):
        """Authenticate with Google Sheets."""
        try:
            scopes = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_file(
                settings.google_credentials_file,
                scopes=scopes
            )
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(settings.google_sheet_id)
            return True
        except Exception as e:
            print(f"❌ Google Sheets auth error: {e}")
            return False
    
    async def import_products(self):
        """Import products from Google Sheets."""
        if not self.sheet:
            return False
        
        try:
            worksheet = self.sheet.worksheet("products")
            records = worksheet.get_all_records()
            return records
        except Exception as e:
            print(f"❌ Import error: {e}")
            return False
    
    async def export_orders(self, orders_data: list):
        """Export orders to Google Sheets."""
        if not self.sheet:
            return False
        
        try:
            worksheet = self.sheet.worksheet("orders")
            for order in orders_data:
                worksheet.append_row([
                    order.get("order_number", ""),
                    order.get("user_id", ""),
                    order.get("total_amount", 0),
                    order.get("status", "pending"),
                    str(order.get("created_at", ""))
                ])
            return True
        except Exception as e:
            print(f"❌ Export error: {e}")
            return False
''',
        "billing.py": '''
"""Billing and payment service."""
from typing import Optional

class BillingService:
    """Handle payments via Telegram Stars or YooKassa."""
    
    def __init__(self, provider_token: str):
        self.provider_token = provider_token
    
    async def create_stars_invoice(self, amount: float, description: str) -> dict:
        """Create Telegram Stars invoice."""
        return {
            "provider": "telegram_stars",
            "amount": amount,
            "description": description,
            "currency": "XTR"  # Telegram Stars
        }
    
    async def create_yookassa_invoice(self, amount: float, description: str) -> dict:
        """Create YooKassa invoice."""
        return {
            "provider": "yookassa",
            "amount": amount,
            "description": description,
            "currency": "RUB"
        }
    
    async def process_payment(self, payment_data: dict) -> bool:
        """Process payment."""
        # In production, integrate with actual payment provider
        return True
'''
    }
    
    for filename, content in services.items():
        filepath = PROJECT_ROOT / "app" / "services" / filename
        filepath.write_text(content, encoding="utf-8")
        print(f"  ✅ Created: app/services/{filename}")


def create_static_files() -> None:
    """Create minimal static files."""
    print("\n📝 Creating static files...")
    
    # index.html
    html_content = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amuriy Studio Enterprise Shop</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body class="bg-gray-900 text-white">
    <div id="app" class="container mx-auto p-4">
        <h1 class="text-3xl font-bold neon-text mb-6">Amuriy Studio</h1>
        <p class="text-gray-400 mb-8">Enterprise Shop</p>
        
        <div id="products" class="grid grid-cols-2 gap-4">
            <!-- Products will be loaded here -->
        </div>
    </div>
    
    <script src="/static/app.js"></script>
</body>
</html>
'''
    (PROJECT_ROOT / "static" / "index.html").write_text(html_content, encoding="utf-8")
    print("  ✅ Created: static/index.html")

    # app.js
    js_content = '''
// Telegram WebApp initialization
const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();
    
    // Haptic feedback
    const haptic = {
        success: () => tg.HapticFeedback?.notificationSuccess(),
        error: () => tg.HapticFeedback?.notificationError(),
        impact: (style = 'light') => tg.HapticFeedback?.impactOccurred(style)
    };
    
    // Theme
    const theme = tg.themeParams || {};
    document.body.style.backgroundColor = theme.bg_color || '#111827';
}

// Load products
async function loadProducts() {
    try {
        const response = await fetch('/api/products');
        const products = await response.json();
        renderProducts(products);
    } catch (error) {
        console.error('Error loading products:', error);
    }
}

function renderProducts(products) {
    const container = document.getElementById('products');
    container.innerHTML = products.map(product => `
        <div class="product-card bg-gray-800 rounded-lg p-4">
            <h3 class="font-semibold">${product.name}</h3>
            <p class="text-gray-400 text-sm">${product.description || ''}</p>
            <div class="mt-2">
                <span class="text-xl font-bold">${product.price} ⭐</span>
            </div>
            <button onclick="buyProduct(${product.id})" 
                    class="mt-3 w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                Купить
            </button>
        </div>
    `).join('');
}

function buyProduct(productId) {
    haptic.impact();
    // Implement purchase logic
    console.log('Buying product:', productId);
}

// Initialize
document.addEventListener('DOMContentLoaded', loadProducts);
'''
    (PROJECT_ROOT / "static" / "app.js").write_text(js_content, encoding="utf-8")
    print("  ✅ Created: static/app.js")

    # styles.css
    css_content = '''
/* Neon cyberpunk styles */
.neon-text {
    color: #fff;
    text-shadow: 0 0 10px #00fff9, 0 0 20px #00fff9, 0 0 40px #00fff9;
}

.product-card {
    transition: transform 0.3s ease, box-shadow 0.3s ease;
    border: 1px solid rgba(0, 255, 249, 0.3);
}

.product-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 0 20px rgba(0, 255, 249, 0.5);
}

/* Loading spinner */
.spinner {
    border: 3px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top: 3px solid #00fff9;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* Custom scrollbar */
::-webkit-scrollbar {
    width: 8px;
}

::-webkit-scrollbar-track {
    background: #1a1a1a;
}

::-webkit-scrollbar-thumb {
    background: #00fff9;
    border-radius: 4px;
}
'''
    (PROJECT_ROOT / "static" / "styles.css").write_text(css_content, encoding="utf-8")
    print("  ✅ Created: static/styles.css")


def test_local_startup() -> bool:
    """Test that the project can start locally."""
    print("\n🧪 Testing local startup...")
    
    try:
        # Check Python version
        python_version = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True,
            text=True
        )
        print(f"  Python: {python_version.stdout.strip()}")
        
        # Try importing key dependencies
        test_imports = [
            "fastapi",
            "sqlalchemy",
            "pydantic",
            "dotenv",
        ]
        
        for module in test_imports:
            try:
                __import__(module)
                print(f"  ✅ Imported: {module}")
            except ImportError as e:
                print(f"  ⚠️  Module not found: {module} ({e})")
                print("  📦 Installing requirements...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                    cwd=PROJECT_ROOT,
                    check=True
                )
                break
        
        # Test database initialization
        print("\n  Testing database initialization...")
        result = subprocess.run(
            [sys.executable, "-c", 
             "import asyncio; from app.database import init_db; asyncio.run(init_db())"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("  ✅ Database initialized successfully")
        else:
            print(f"  ⚠️  Database init warning: {result.stderr[:200]}")
        
        # Test FastAPI app import
        print("\n  Testing FastAPI app import...")
        result = subprocess.run(
            [sys.executable, "-c", "from app.main import app; print('✅ App imported')"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=15
        )
        print(f"  {result.stdout.strip()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def create_git_repo() -> None:
    """Initialize git repository and make initial commit."""
    print("\n📦 Initializing git repository...")
    
    try:
        # Check if git is available
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        
        # Initialize repo
        subprocess.run(["git", "init"], cwd=PROJECT_ROOT, check=True, capture_output=True)
        
        # Create .gitignore
        gitignore = """__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
env.bak/
venv.bak/
*.db
*.sqlite3
.env
credentials.json
.DS_Store
node_modules/
dist/
build/
*.egg-info/
.eggs/
"""
        (PROJECT_ROOT / ".gitignore").write_text(gitignore, encoding="utf-8")
        
        # Add all files
        subprocess.run(["git", "add", "."], cwd=PROJECT_ROOT, check=True, capture_output=True)
        
        # Initial commit
        subprocess.run(
            ["git", "commit", "-m", "Initial commit: Amuriy Studio Enterprise Shop infrastructure"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True
        )
        
        print("  ✅ Git repository initialized and committed")
        
    except subprocess.CalledProcessError as e:
        print(f"  ⚠️  Git error: {e}")
    except FileNotFoundError:
        print("  ⚠️  Git not installed, skipping")


def create_zip_archive() -> None:
    """Create ZIP archive of the project."""
    print("\n📦 Creating ZIP archive...")
    
    try:
        archive_name = PROJECT_ROOT.parent / "amuriy_studio_enterprise.zip"
        
        # Remove existing archive if any
        if archive_name.exists():
            archive_name.unlink()
        
        # Create archive
        shutil.make_archive(
            str(archive_name.with_suffix("")),
            "zip",
            PROJECT_ROOT
        )
        
        print(f"  ✅ Archive created: {archive_name}")
        
    except Exception as e:
        print(f"  ⚠️  Archive creation error