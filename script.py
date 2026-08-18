#!/usr/bin/env python3
"""
Amuriy Studio Enterprise Shop - Project Initializer
Creates the complete project structure with configuration files.
"""

import os
import sys
import shutil
from pathlib import Path
from typing import Optional
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path("/tmp/agent_projects/amuriy_studio_enterprise")


def create_directory_structure() -> None:
    """Create the required directory structure."""
    directories = [
        PROJECT_ROOT / "app" / "services",
        PROJECT_ROOT / "static",
    ]
    
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {directory}")
        except OSError as e:
            logger.error(f"Failed to create directory {directory}: {e}")
            raise


def write_config_py() -> None:
    """Write app/config.py with settings management."""
    content = '''"""
Configuration management for Amuriy Studio Enterprise Shop.
Loads environment variables with fallback to SQLite for development.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""
    
    # Bot configuration
    BOT_TOKEN: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    ADMIN_CHAT_ID: str = field(default_factory=lambda: os.getenv("ADMIN_CHAT_ID", ""))
    
    # Database configuration
    DB_URL: str = field(default_factory=lambda: os.getenv(
        "DB_URL",
        "sqlite+aiosqlite:///./amuriy_shop.db"
    ))
    
    # Web app URL for Telegram Mini App
    WEBAPP_URL: str = field(default_factory=lambda: os.getenv(
        "WEBAPP_URL",
        "https://localhost:8000"
    ))
    
    # Google Sheets integration
    GOOGLE_SHEET_ID: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_ID", ""))
    
    # Payment provider token (Telegram Stars / ЮKassa)
    PAYMENT_PROVIDER_TOKEN: str = field(default_factory=lambda: os.getenv(
        "PAYMENT_PROVIDER_TOKEN",
        ""
    ))
    
    # Database type detection
    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL."""
        return "postgres" in self.DB_URL.lower()
    
    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return "sqlite" in self.DB_URL.lower()


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Return the global settings instance."""
    return settings
'''


def write_database_py() -> None:
    """Write app/database.py with async SQLAlchemy setup."""
    content = '''"""
Async SQLAlchemy database setup with PostgreSQL/SQLite fallback.
"""

from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import logging

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def create_engine() -> AsyncEngine:
    """
    Create async engine based on configuration.
    Falls back to SQLite if PostgreSQL is not available.
    """
    try:
        engine = create_async_engine(
            settings.DB_URL,
            echo=False,
            pool_pre_ping=True if settings.is_postgres else False,
            pool_size=5 if settings.is_postgres else None,
            max_overflow=10 if settings.is_postgres else None,
        )
        logger.info(f"Database engine created: {settings.DB_URL.split('@')[-1]}")
        return engine
    except Exception as e:
        logger.error(f"Failed to create engine with {settings.DB_URL}: {e}")
        logger.warning("Falling back to SQLite")
        fallback_url = "sqlite+aiosqlite:///./amuriy_shop.db"
        return create_async_engine(fallback_url, echo=False)


# Create engine and session factory
engine = create_engine()
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables and create indexes.
    """
    from . import models  # noqa: F401
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise


async def check_connection() -> bool:
    """
    Test database connection.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
'''


def write_models_py() -> None:
    """Write app/models.py with SQLAlchemy models."""
    content = '''"""
SQLAlchemy models for Amuriy Studio Enterprise Shop.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Float,
    JSON,
    Table,
    Column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .database import Base


class TimestampMixin:
    """Mixin for created/updated timestamps."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base, TimestampMixin):
    """Telegram user model."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[Optional[str]] = mapped_column(String(255))
    first_name: Mapped[Optional[str]] = mapped_column(String(255))
    last_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    orders: Mapped[List["Order"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    promo_codes: Mapped[List["PromoCode"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Category(Base, TimestampMixin):
    """Product category model."""
    
    __tablename__ = "categories"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    products: Mapped[List["Product"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class Product(Base, TimestampMixin):
    """Product model with auto-delivery support."""
    
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    old_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    payload_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_digital: Mapped[bool] = mapped_column(Boolean, default=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Relationships
    category: Mapped["Category"] = relationship(back_populates="products")
    order_items: Mapped[List["OrderItem"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class Order(Base, TimestampMixin):
    """Order model."""
    
    __tablename__ = "orders"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    order_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        index=True,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
    )
    promo_code: Mapped[Optional[str]] = mapped_column(String(50))
    payment_method: Mapped[str] = mapped_column(String(50), default="stars")
    payment_id: Mapped[Optional[str]] = mapped_column(String(255))
    delivery_info: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    """Order item model."""
    
    __tablename__ = "order_items"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"),
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    
    # Relationships
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="order_items")


class PromoCode(Base, TimestampMixin):
    """Promo code model."""
    
    __tablename__ = "promo_codes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    discount_type: Mapped[str] = mapped_column(
        String(20),
        default="percent",
    )  # percent or fixed
    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0"),
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="promo_codes")


class Broadcast(Base, TimestampMixin):
    """Broadcast message model."""
    
    __tablename__ = "broadcasts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
'''


def write_schemas_py() -> None:
    """Write app/schemas.py with Pydantic schemas."""
    content = '''"""
Pydantic schemas for API validation.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


# Category schemas
class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CategoryResponse(CategoryBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Product schemas
class ProductBase(BaseModel):
    category_id: int
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    price: Decimal = Field(..., gt=0)
    old_price: Optional[Decimal] = None
    currency: str = "RUB"
    image_url: Optional[str] = None
    payload_url: Optional[str] = None
    is_active: bool = True
    is_digital: bool = False
    stock_quantity: int = 0
    attributes: Optional[Dict[str, Any]] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    category_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    old_price: Optional[Decimal] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None
    payload_url: Optional[str] = None
    is_active: Optional[bool] = None
    is_digital: Optional[bool] = None
    stock_quantity: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None


class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Order schemas
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)


class OrderCreate(BaseModel):
    user_id: int
    items: List[OrderItemCreate]
    promo_code: Optional[str] = None
    payment_method: str = "stars"
    delivery_info: Optional[Dict[str, Any]] = None


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    price: Decimal
    total: Decimal
    
    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: int
    user_id: int
    order_number: str
    status: str
    total_amount: Decimal
    discount_amount: Decimal
    promo_code: Optional[str]
    payment_method: str
    payment_id: Optional[str]
    created_at: datetime
    items: List[OrderItemResponse]
    
    model_config = ConfigDict(from_attributes=True)


# Promo code schemas
class PromoCodeApply(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    order_amount: Decimal = Field(..., gt=0)


class PromoCodeResponse(BaseModel):
    code: str
    discount_type: str
    discount_value: Decimal
    is_valid: bool
    discount_amount: Decimal
    final_amount: Decimal
    
    model_config = ConfigDict(from_attributes=True)


# User schemas
class UserCreate(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Broadcast schemas
class BroadcastCreate(BaseModel):
    message_text: str = Field(..., min_length=1)
    photo_url: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class BroadcastResponse(BaseModel):
    id: int
    message_text: str
    photo_url: Optional[str]
    status: str
    sent_count: int
    total_count: int
    scheduled_at: Optional[datetime]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# API Response wrapper
class APIResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[Any] = None
    error: Optional[str] = None
'''


def write_init_files() -> None:
    """Write __init__.py files for packages."""
    init_files = [
        PROJECT_ROOT / "app" / "__init__.py",
        PROJECT_ROOT / "app" / "services" / "__init__.py",
    ]
    
    for init_file in init_files:
        try:
            init_file.write_text('"""Amuriy Studio Enterprise Shop package."""\n')
            logger.info(f"Created init file: {init_file}")
        except OSError as e:
            logger.error(f"Failed to create init file {init_file}: {e}")
            raise


def main() -> None:
    """Main execution function."""
    logger.info("Starting Amuriy Studio Enterprise Shop initialization...")
    
    try:
        # Clean existing directory if it exists
        if PROJECT_ROOT.exists():
            logger.info(f"Removing existing directory: {PROJECT_ROOT}")
            shutil.rmtree(PROJECT_ROOT)
        
        # Create directory structure
        create_directory_structure()
        
        # Write configuration files
        write_config_py()
        write_database_py()
        write_models_py()
        write_schemas_py()
        write_init_files()
        
        logger.info("=" * 60)
        logger.info("Project structure created successfully!")
        logger.info(f"Project root: {PROJECT_ROOT}")
        logger.info("=" * 60)
        
        # Display structure
        for root, dirs, files in os.walk(PROJECT_ROOT):
            level = root.replace(str(PROJECT_ROOT), '').count(os.sep)
            indent = ' ' * 2 * level
            logger.info(f"{indent}{os.path.basename(root)}/")
            sub_indent = ' ' * 2 * (level + 1)
            for file in files:
                logger.info(f"{sub_indent}{file}")
        
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()