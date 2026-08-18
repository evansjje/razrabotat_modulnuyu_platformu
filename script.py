# app/services/promo_service.py
import random
import string
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import PromoCode, Order
from app.schemas import PromoApplyRequest

class PromoService:
    @staticmethod
    async def validate_promo(db: AsyncSession, code: str, user_id: int) -> dict:
        try:
            result = await db.execute(
                select(PromoCode).where(PromoCode.code == code.upper())
            )
            promo = result.scalar_one_or_none()
            
            if not promo:
                return {"valid": False, "error": "Промокод не найден"}
            
            if not promo.is_active:
                return {"valid": False, "error": "Промокод неактивен"}
            
            if promo.expires_at and promo.expires_at < datetime.utcnow():
                return {"valid": False, "error": "Промокод истёк"}
            
            if promo.max_uses and promo.used_count >= promo.max_uses:
                return {"valid": False, "error": "Лимит использований исчерпан"}
            
            # Проверка на персональный промокод
            if promo.user_id and promo.user_id != user_id:
                return {"valid": False, "error": "Промокод не для вас"}
            
            return {
                "valid": True,
                "promo": promo,
                "discount_type": promo.discount_type,
                "discount_value": promo.discount_value
            }
        except Exception as e:
            print(f"Error validating promo: {e}")
            return {"valid": False, "error": "Ошибка валидации"}

    @staticmethod
    async def calculate_discount(promo: PromoCode, total: float) -> float:
        if promo.discount_type == "percent":
            return total * (promo.discount_value / 100)
        elif promo.discount_type == "fixed":
            return min(promo.discount_value, total)
        return 0

    @staticmethod
    async def generate_personal_code(user_id: int, order_id: int) -> str:
        """Генерация персонального промокода после покупки"""
        prefix = "AMUR"
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return f"{prefix}-{user_id}-{random_part}"

    @staticmethod
    async def create_personal_promo(db: AsyncSession, user_id: int, order_id: int):
        code = await PromoService.generate_personal_code(user_id, order_id)
        promo = PromoCode(
            code=code,
            discount_type="percent",
            discount_value=10,
            user_id=user_id,
            max_uses=1,
            expires_at=datetime.utcnow() + timedelta(days=30),
            description=f"Персональный промокод за заказ #{order_id}"
        )
        db.add(promo)
        await db.commit()
        return code

# app/services/sheets_service.py
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Product, Category, Order
from app.config import settings

class SheetsService:
    def __init__(self):
        self.client = None
        self.sheet = None
        
    async def connect(self):
        try:
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_file(
                settings.GOOGLE_CREDENTIALS_FILE, scopes=scopes
            )
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(settings.GOOGLE_SHEET_ID)
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")
            raise

    async def import_products(self, db: AsyncSession):
        try:
            if not self.sheet:
                await self.connect()
            
            # Импорт категорий
            categories_sheet = self.sheet.worksheet("Категории")
            categories_data = categories_sheet.get_all_records()
            
            for row in categories_data:
                category = Category(
                    name=row["name"],
                    description=row.get("description", ""),
                    is_active=row.get("is_active", True)
                )
                db.add(category)
            
            await db.flush()
            
            # Импорт товаров
            products_sheet = self.sheet.worksheet("Товары")
            products_data = products_sheet.get_all_records()
            
            for row in products_data:
                # Найти категорию
                result = await db.execute(
                    select(Category).where(Category.name == row["category"])
                )
                category = result.scalar_one_or_none()
                
                if category:
                    product = Product(
                        name=row["name"],
                        description=row.get("description", ""),
                        price=float(row["price"]),
                        category_id=category.id,
                        is_active=row.get("is_active", True),
                        payload_url=row.get("payload_url", ""),
                        image_url=row.get("image_url", "")
                    )
                    db.add(product)
            
            await db.commit()
            print("Products imported from Google Sheets")
            return {"status": "success", "message": "Товары импортированы"}
        except Exception as e:
            print(f"Error importing products: {e}")
            await db.rollback()
            return {"status": "error", "message": str(e)}

    async def export_orders(self, db: AsyncSession):
        try:
            if not self.sheet:
                await self.connect()
            
            result = await db.execute(select(Order))
            orders = result.scalars().all()
            
            orders_sheet = self.sheet.worksheet("Заказы")
            
            # Очистка и запись заголовков
            orders_sheet.clear()
            headers = ["ID", "User ID", "Items", "Total", "Promo Code", "Status", "Created At"]
            orders_sheet.append_row(headers)
            
            for order in orders:
                row = [
                    order.id,
                    order.user_id,
                    order.items,
                    order.total,
                    order.promo_code or "",
                    order.status,
                    str(order.created_at)
                ]
                orders_sheet.append_row(row)
            
            print("Orders exported to Google Sheets")
            return {"status": "success", "message": "Заказы экспортированы"}
        except Exception as e:
            print(f"Error exporting orders: {e}")
            return {"status": "error", "message": str(e)}

# app/services/billing.py
import json
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Order, Product
from app.config import settings

class BillingService:
    @staticmethod
    async def create_order(db: AsyncSession, user_id: int, items: list, total: float, promo_code: Optional[str] = None) -> Order:
        try:
            order = Order(
                user_id=user_id,
                items=json.dumps(items),
                total=total,
                promo_code=promo_code,
                status="pending"
            )
            db.add(order)
            await db.commit()
            await db.refresh(order)
            return order
        except Exception as e:
            print(f"Error creating order: {e}")
            await db.rollback()
            raise

    @staticmethod
    async def process_stars_payment(order_id: int, amount: int) -> bool:
        """Обработка платежа через Telegram Stars"""
        try:
            # Здесь должна быть интеграция с Telegram Stars API
            # Для примера просто возвращаем True
            print(f"Processing Stars payment for order {order_id}, amount: {amount}")
            return True
        except Exception as e:
            print(f"Error processing Stars payment: {e}")
            return False

    @staticmethod
    async def process_card_payment(order_id: int, amount: int, payment_token: str) -> bool:
        """Обработка платежа через Telegram Payments (ЮKassa/СБП)"""
        try:
            # Здесь должна быть интеграция с Telegram Payments API
            # Для примера просто возвращаем True
            print(f"Processing card payment for order {order_id}, amount: {amount}")
            return True
        except Exception as e:
            print(f"Error processing card payment: {e}")
            return False

# app/main.py
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import json

from app.database import get_db
from app.models import Product, Category, Order, PromoCode
from app.schemas import ProductOut, CategoryOut, OrderCreate, PromoApplyRequest, PromoApplyResponse
from app.services.promo_service import PromoService
from app.services.sheets_service import SheetsService
from app.services.billing import BillingService
from app.config import settings

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
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return {"message": "Amuriy Studio Enterprise Shop API"}

@app.get("/api/categories", response_model=List[CategoryOut])
async def get_categories(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(Category).where(Category.is_active == True)
        )
        categories = result.scalars().all()
        return categories
    except Exception as e:
        print(f"Error getting categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products", response_model=List[ProductOut])
async def get_products(
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Product).where(Product.is_active == True)
        
        if category_id:
            query = query.where(Product.category_id == category_id)
        
        if search:
            query = query.where(Product.name.ilike(f"%{search}%"))
        
        result = await db.execute(query)
        products = result.scalars().all()
        return products
    except Exception as e:
        print(f"Error getting products: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/order")
async def create_order(order_data: OrderCreate, db: AsyncSession = Depends(get_db)):
    try:
        # Расчет итоговой суммы
        total = 0
        items = []
        
        for item in order_data.items:
            result = await db.execute(
                select(Product).where(Product.id == item.product_id)
            )
            product = result.scalar_one_or_none()
            
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
            
            subtotal = product.price * item.quantity
            total += subtotal
            items.append({
                "product_id": product.id,
                "name": product.name,
                "price": product.price,
                "quantity": item.quantity,
                "subtotal": subtotal
            })
        
        # Применение промокода
        promo_code = None
        if order_data.promo_code:
            promo_result = await PromoService.validate_promo(db, order_data.promo_code, order_data.user_id)
            if promo_result["valid"]:
                promo = promo_result["promo"]
                discount = await PromoService.calculate_discount(promo, total)
                total -= discount
                promo_code = promo.code
                
                # Обновление счетчика использований
                promo.used_count += 1
                await db.commit()
            else:
                raise HTTPException(status_code=400, detail=promo_result["error"])
        
        # Создание заказа
        order = await BillingService.create_order(
            db,
            user_id=order_data.user_id,
            items=items,
            total=total,
            promo_code=promo_code
        )
        
        # Генерация персонального промокода
        personal_promo = await PromoService.create_personal_promo(db, order_data.user_id, order.id)
        
        return {
            "order_id": order.id,
            "total": total,
            "status": "created",
            "personal_promo": personal_promo
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/promo/apply", response_model=PromoApplyResponse)
async def apply_promo(promo_data: PromoApplyRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await PromoService.validate_promo(db, promo_data.code, promo_data.user_id)
        
        if not result["valid"]:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return PromoApplyResponse(
            valid=True,
            discount_type=result["discount_type"],
            discount_value=result["discount_value"]
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error applying promo: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync_sheets")
async def sync_sheets(db: AsyncSession = Depends(get_db)):
    try:
        sheets_service = SheetsService()
        result = await sheets_service.import_products(db)
        return result
    except Exception as e:
        print(f"Error syncing sheets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# app/bot.py
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User, Order, Product, Category
from app.services.sheets_service import SheetsService

logging.basicConfig(level=logging.INFO)

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

# Хранение сессий БД
db_sessions = {}

async def get_db_session() -> AsyncSession:
    """Получение сессии БД для текущего контекста"""
    return await get_db()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    try:
        # Регистрация пользователя
        db = await get_db_session()
        try:
            result = await db.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name
                )
                db.add(user)
                await db.commit()
        finally:
            await db.close()
        
        # Кнопка WebApp
        webapp_button = InlineKeyboardButton(
            text="🛍️ Открыть магазин",
            web_app=WebAppInfo(url=settings.WEBAPP_URL)
        )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[webapp_button]]
        )
        
        await message.answer(
            "👋 Добро пожаловать в Amuriy Studio Enterprise Shop!\n\n"
            "🛒 Нажмите кнопку ниже, чтобы открыть магазин",
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Error in start command: {e}")
        await message.answer("Произошла ошибка. Попробуйте позже.")

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    try:
        if message.from_user.id != settings.ADMIN_CHAT_ID:
            await message.answer("⛔ У вас нет доступа к админ-панели")
            return
        
        db = await get_db_session()
        try:
            # Статистика
            users_count = await db.scalar(select(func.count(User.id)))
            orders_count = await db.scalar(select(func.count(Order.id)))
            products_count = await db.scalar(select(func.count(Product.id)))
            
            # Сумма заказов
            total_revenue = await db.scalar(select(func.sum(Order.total)))
            
            stats_text = (
                f"📊 Статистика магазина:\n\n"
                f"👥 Пользователей: {users_count}\n"
                f"📦 Заказов: {orders_count}\n"
                f"🛍️ Товаров: {products_count}\n"
                f"💰 Выручка: {total_revenue or 0:.2f} ⭐\n"
            )
            
            # Кнопки админ-панели
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔄 Синхронизировать с Google Sheets",
                            callback_data="sync_sheets"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📢 Рассылка",
                            callback_data="broadcast"
                        )
                    ]
                ]
            )
            
            await message.answer(stats_text, reply_markup=keyboard)
        finally:
            await db.close()
    except Exception as e:
        logging.error(f"Error in admin command: {e}")
        await message.answer("Произошла ошибка")

@dp.callback_query(F.data == "sync_sheets")
async def sync_sheets_callback(callback: CallbackQuery):
    try:
        if callback.from_user.id != settings.ADMIN_CHAT_ID:
            await callback.answer("Нет доступа", show_alert=True)
            return
        
        await callback.message.edit_text("🔄 Синхронизация с Google Sheets...")
        
        db = await get_db_session()
        try:
            sheets_service = SheetsService()
            result = await sheets_service.import_products(db)
            
            if result["status"] == "success":
                await callback.message.edit_text("✅ Синхронизация завершена успешно!")
            else:
                await callback.message.edit_text(f"❌ Ошибка синхронизации: {result['message']}")
        finally:
            await db.close()
    except Exception as e:
        logging.error(f"Error in sync sheets callback: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при синхронизации")

@dp.callback_query(F.data == "broadcast")
async def broadcast_callback(callback: CallbackQuery):
    try:
        if callback.from_user.id != settings.ADMIN_CHAT_ID:
            await callback.answer("Нет доступа", show_alert=True)
            return
        
        await callback.message.edit_text(
            "📢 Введите текст для рассылки:\n"
            "(Отправьте сообщение с текстом рассылки)"
        )
        
        # Здесь должна быть логика ожидания текста
        # Для простоты просто уведомляем
        await callback.answer("Функция рассылки в разработке", show_alert=True)
    except Exception as e:
        logging.error(f"Error in broadcast callback: {e}")

@dp.message()
async def handle_orders_notification(message: Message):
    """Обработка уведомлений о заказах"""
    try:
        # Проверка на уведомление от WebApp
        if message.web_app_data:
            data = message.web_app_data.data
            # Здесь можно обработать данные из WebApp
            logging.info(f"WebApp data received: {data}")
    except Exception as e:
        logging.error(f"Error handling message: {e}")

async def notify_admin_about_order(order_data: dict):
    """Отправка уведомления админу о новом заказе"""
    try:
        admin_id = settings.ADMIN_CHAT_ID
        
        text = (
            f"🛒 Новый заказ!\n\n"
            f"📦 Заказ #{order_data['order_id']}\n"
            f"💰 Сумма: {order_data['total']} ⭐\n"
            f"👤 Пользователь: {order_data['user_id']}\n"
        )
        
        if order_data.get('promo_code'):
            text += f"🏷️ Промокод: {order_data['promo_code']}\n"
        
        await bot.send_message(admin_id, text)
    except Exception as e:
        logging.error(f"Error notifying admin: {e}")

async def main():
    logging.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

# static/index.html
"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amuriy Studio Enterprise Shop</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body class="bg-black text-white">
    <div id="app" class="max-w-md mx-auto p-4">
        <!-- Hero Banner -->
        <div class="hero-banner mb-6 p-6 rounded-2xl">
            <h1 class="text-3xl font-bold neon-text">AMURIY STUDIO</h1>
            <p class="text-sm mt-2 opacity-80">Enterprise Shop</p>
        </div>
        
        <!-- Search -->
        <div class="mb-4">
            <input 
                type="text" 
                id="searchInput" 
                placeholder="🔍 Поиск товаров..."
                class="w-full p-3 rounded-xl bg-gray-800 border border-purple-500/30 focus:outline-none focus:border-purple-500"
            >
        </div>
        
        <!-- Categories -->
        <div id="categories" class="flex gap-2 overflow-x-auto mb-6 pb-2">
            <button class="category-btn active px-4 py-2 rounded-full bg-purple-600" data-category="all">
                Все
            </button>
        </div>
        
        <!-- Products Grid -->
        <div id="products" class="grid grid-cols-2 gap-4 mb-20">
            <!-- Products will be rendered here -->
        </div>
        
        <!-- Bottom Sheet for Product Details -->
        <div id="productSheet" class="fixed inset-0 z-50 hidden">
            <div class="absolute inset-0 bg-black/70" onclick="closeProductSheet()"></div>
            <div class="absolute bottom-0 w-full bg-gray-900 rounded-t-3xl p-6 max-h-[80vh] overflow-y-auto">
                <div id="productDetails"></div>
            </div>
        </div>
        
        <!-- Cart Button -->
        <button id="cartButton" class="fixed bottom-4 right-4 bg-purple-600 text-white p-4 rounded-full shadow-lg hover:bg-purple-700 transition-all">
            🛒 <span id="cartCount">0</span>
        </button>
        
        <!-- Cart Modal -->
        <div id="cartModal" class="fixed inset-0 z-50 hidden">
            <div class="absolute inset-0 bg-black/70" onclick="closeCart()"></div>
            <div class="absolute bottom-0 w-full bg-gray-900 rounded-t-3xl p-6 max-h-[80vh] overflow-y-auto">
                <h2 class="text-2xl font-bold mb-4">🛒 Корзина</h2>
                <div id="cartItems"></div>
                
                <!-- Promo Code -->
                <div class="mt-4">
                    <input 
                        type="text" 
                        id="promoInput" 
                        placeholder="Введите промокод"
                        class="w-full p-3 rounded-xl bg-gray-800 border border-purple-500/30 focus:outline-none focus:border-purple-500"
                    >
                    <button onclick="applyPromo()" class="mt-2 w-full bg-blue-600 text-white p-3 rounded-xl hover:bg-blue-700">
                        Применить промокод
                    </button>
                    <div id="promoMessage" class="mt-2 text-sm"></div>
                </div>
                
                <!-- Total -->
                <div class="mt-4 border-t border-gray-700 pt-4">
                    <div class="flex justify-between text-lg">
                        <span>Итого:</span>
                        <span id="totalAmount">0 ⭐</span>
                    </div>
                    <div id="discountInfo" class="text-green-500 text-sm mt-1 hidden"></div>
                </div>
                
                <button onclick="checkout()" class="mt-4 w-full bg-green-600 text-white p-4 rounded-xl font-bold hover:bg-green-700">
                    Оформить заказ
                </button>
            </div>
        </div>
        
        <!-- My Purchases -->
        <div id="purchasesSection" class="mt-8">
            <h2 class="text-xl font-bold mb-4">📦 Мои покупки</h2>
            <div id="purchasesList"></div>
        </div>
        
        <!-- About -->
        <div id="aboutSection" class="mt-8 p-6 bg-gray-900 rounded-2xl">
            <h2 class="text-xl font-bold mb-4">О студии</h2>
            <p class="text-sm opacity-80">
                Amuriy Studio — это творческая студия, создающая уникальные цифровые продукты.
                Мы объединяем искусство и технологии для создания незабываемых впечатлений.
            </p>
        </div>
    </div>
    
    <script src="/static/app.js"></script>
</body>
</html>
"""

# static/app.js
"""
// Telegram WebApp initialization
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// State
let products = [];
let categories = [];
let cart = [];
let currentCategory = 'all';
let appliedPromo = null;
let totalAmount = 0;

// Initialize
async function init() {
    try {
        // Load categories
        const catResponse = await fetch('/api/categories');
        categories = await catResponse.json();
        renderCategories();
        
        // Load products
        await loadProducts();
        
        // Load purchases
        await loadPurchases();
        
        // Setup Telegram MainButton
        setupMainButton();
        
        // Haptic feedback
        tg.HapticFeedback.impactOccurred('light');
    } catch (error) {
        console.error('Init error:', error);
        showError('Ошибка загрузки данных');
    }
}

async function loadProducts() {
    try {
        let url = '/api/products';
        if (currentCategory !== 'all') {
            url += `?category_id=${currentCategory}`;
        }
        
        const searchTerm = document.getElementById('searchInput').value;
        if (searchTerm) {
            url += `${url.includes('?') ? '&' : '?'}search=${encodeURIComponent(searchTerm)}`;
        }
        
        const response = await fetch(url);
        products = await response.json();
        renderProducts();
    } catch (error) {
        console.error('Load products error:', error);
        showError('Ошибка загрузки товаров');
    }
}

function renderCategories() {
    const container = document.getElementById('categories');
    container.innerHTML = `
        <button class="category-btn active px-4 py-2 rounded-full bg-purple-600" data-category="all">
            Все
        </button>
    `;
    
    categories.forEach(category => {
        const btn = document.createElement('button');
        btn.className = 'category-btn px-4 py-2 rounded-full bg-gray-800 hover:bg-purple-600 transition-all';
        btn.dataset.category = category.id;
        btn.textContent = category.name;
        btn.onclick = () => selectCategory(category.id);
        container.appendChild(btn);
    });
}

function selectCategory(categoryId) {
    currentCategory = categoryId;
    
    // Update active state
    document.querySelectorAll('.category-btn').forEach(btn => {
        btn.classList.remove('active', 'bg-purple-600');
        btn.classList.add('bg-gray-800');
    });
    
    const activeBtn = document.querySelector(`[data-category="${categoryId}"]`);
    if (activeBtn) {
        activeBtn.classList.add('active', 'bg-purple-600');
        activeBtn.classList.remove('bg-gray-800');
    }
    
    loadProducts();
    tg.HapticFeedback.selectionChanged();
}

function renderProducts() {
    const container = document.getElementById('products');
    
    if (products.length === 0) {
        container.innerHTML = '<div class="col-span-2 text-center py-8 text-gray-500">Товары не найдены</div>';
        return;
    }
    
    container.innerHTML = products.map(product => `
        <div class="product-card bg-gray-900 rounded-2xl overflow-hidden cursor-pointer hover:scale-105 transition-transform"
             onclick="showProductDetails(${product.id})">
            <div class="aspect-square bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center">
                <span class="text-4xl">🛍️</span>
            </div>
            <div class="p-3">
                <h3 class="font-semibold text-sm">${product.name}</h3>
                <p class="text-purple-400 font-bold mt-1">${product.price} ⭐</p>
                <button onclick="addToCart(${product.id})" 
                        class="mt-2 w-full bg-purple-600 text-white py-2 rounded-lg text-sm hover:bg-purple-700">
                    В корзину
                </button>
            </div>
        </div>
    `).join('');
}

function showProductDetails(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) return;
    
    const sheet = document.getElementById('productSheet');
    const details = document.getElementById('productDetails');
    
    details.innerHTML = `
        <div class="flex justify-between items-start mb-4">
            <h3 class="text-2xl font-bold">${product.name}</h3>
            <button onclick="closeProductSheet()" class="text-gray-500 hover:text-white">✕</button>
        </div>
        <div class="aspect-video bg-gradient-to-br from-purple-600 to-blue-600 rounded-xl flex items-center justify-center mb-4">
            <span class="text-6xl">🛍️</span>
        </div>
        <p class="text-gray-300 mb-4">${product.description || 'Описание отсутствует'}</p>
        <div class="flex justify-between items-center mb-4">
            <span class="text-2xl font-bold text-purple-400">${product.price} ⭐</span>
        </div>
        <button onclick="addToCart(${product.id})" 
                class="w-full bg-purple-600 text-white py-3 rounded-xl font-bold hover:bg-purple-700">
            Добавить в корзину
        </button>
    `;
    
    sheet.classList.remove('hidden');
    tg.HapticFeedback.impactOccurred('medium');
}

function closeProductSheet() {
    document.getElementById('productSheet').classList.add('hidden');
}

function addToCart(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) return;
    
    const existingItem = cart.find(item => item.product_id === productId);
    
    if (existingItem) {
        existingItem.quantity++;
    } else {
        cart.push({
            product_id: product.id,
            name: product.name,
            price: product.price,
            quantity: 1
        });
    }
    
    updateCartCount();
    tg.HapticFeedback.notificationOccurred('success');
    
    // Show mini notification
    showToast(`${product.name} добавлен в корзину`);
}

function updateCartCount() {
    const count = cart.reduce((sum, item) => sum + item.quantity, 0);
    document.getElementById('cartCount').textContent = count;
}

function openCart() {
    renderCart();
    document.getElementById('cartModal').classList.remove('hidden');
    tg.HapticFeedback.impactOccurred('light');
}

function closeCart() {
    document.getElementById('cartModal').classList.add('hidden');
}

function renderCart() {
    const container = document.getElementById('cartItems');
    
    if (cart.length === 0) {
        container.innerHTML = '<div class="text-center py-8 text-gray-500">Корзина пуста</div>';
        document.getElementById('totalAmount').textContent = '0 ⭐';
        return;
    }
    
    container.innerHTML = cart.map((item, index) => `
        <div class="flex justify-between items-center py-3 border-b border-gray-800">
            <div>
                <div class="font-semibold">${item.name}</div>
                <div class="text-sm text-gray-500">${item.price} ⭐ × ${item.quantity}</div>
            </div>
            <div class="flex items-center gap-2">
                <button onclick="changeQuantity(${index}, -1)" class="w-8 h-8 bg-gray-800 rounded-lg">−</button>
                <span class="w-8 text-center">${item.quantity}</span>
                <button onclick="changeQuantity(${index}, 1)" class="w-8 h-8 bg-gray-800 rounded-lg">+</button>
                <button onclick="removeFromCart(${index})" class="ml-2 text-red-500">🗑️</button>
            </div>
        </div>
    `).join('');
    
    calculateTotal();
}

function changeQuantity(index, delta) {
    cart[index].quantity += delta;
    
    if (cart[index].quantity <= 0) {
        cart.splice(index, 1);
    }
    
    renderCart();
    updateCartCount();
    tg.HapticFeedback.impactOccurred('light');
}

function removeFromCart(index) {
    cart.splice(index, 1);
    renderCart();
    updateCartCount();
    tg.HapticFeedback.notificationOccurred('error');
}

function calculateTotal() {
    totalAmount = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    
    if (appliedPromo) {
        const discount = calculateDiscount(totalAmount);
        totalAmount -= discount;
        document.getElementById('discountInfo').classList.remove('hidden');
        document.getElementById('discountInfo').textContent = `Скидка: ${discount} ⭐`;
    } else {
        document.getElementById('discountInfo').classList.add('hidden');
    }
    
    document.getElementById('totalAmount').textContent = `${totalAmount} ⭐`;
}

function calculateDiscount(total) {
    if (!appliedPromo) return 0;
    
    if (appliedPromo.discount_type === 'percent') {
        return total * (appliedPromo.discount_value / 100);
    } else {
        return Math.min(appliedPromo.discount_value, total);
    }
}

async function applyPromo() {
    const code = document.getElementById('promoInput').value.trim();
    if (!code) return;
    
    try {
        const response = await fetch('/api/promo/apply', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                code: code,
                user_id: tg.initDataUnsafe.user?.id
            })
        });
        
        const data = await response.json();
        
        if (data.valid) {
            appliedPromo = data;
            document.getElementById('promoMessage').innerHTML = 
                '<span class="text-green-500">✅ Промокод применен!</span>';
            calculateTotal();
            tg.HapticFeedback.notificationOccurred('success');
        } else {
            document