# database.py
import sqlite3
import datetime
import logging
import json
import re
import hashlib
import urllib.parse
from datetime import datetime as dt, timedelta
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple, Any


@dataclass
class CachedProduct:
    url: str
    price: float
    title: str
    availability: bool
    data: Dict[str, Any]
    last_updated: float


logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_file="bot_database.db"):
        # allow usage from multiple threads/tasks
        self.connection = sqlite3.connect(db_file, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

        # Enable WAL mode for better concurrency (Problem #10)
        try:
            self.connection.execute("PRAGMA journal_mode=WAL;")
            self.connection.execute("PRAGMA synchronous=NORMAL;")
            self.connection.commit()  # Ensure PRAGMA takes effect
            logger.info("SQLite WAL mode enabled for better concurrency")
        except Exception as e:
            logger.warning(f"Could not enable WAL mode: {e}")

        self.create_tables()
        self._migrate_normalized_urls()


    def create_tables(self):
        with self.connection:
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY,
                    url TEXT UNIQUE,
                    image_hash TEXT,
                    date_added TIMESTAMP,
                    title TEXT DEFAULT ''
                )
            """
            )
            # Добавляем колонку title если её нет (для существующих БД)
            try:
                self.cursor.execute(
                    "ALTER TABLE history ADD COLUMN title TEXT DEFAULT ''"
                )
            except sqlite3.OperationalError:
                pass  # Колонка уже существует

            # PERFORMANCE FIX (Problem #2, #8): Add normalized_url column for O(1) lookups
            try:
                self.cursor.execute(
                    "ALTER TABLE history ADD COLUMN normalized_url TEXT"
                )
                logger.info("Added normalized_url column to history table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Price Drop Monitor: Add last_price column for price tracking
            try:
                self.cursor.execute("ALTER TABLE history ADD COLUMN last_price REAL")
                logger.info("Added last_price column to history table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Sold Out Cleaner: Add message_id and channel_id for post management
            try:
                self.cursor.execute("ALTER TABLE history ADD COLUMN message_id INTEGER")
                logger.info("Added message_id column to history table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                self.cursor.execute("ALTER TABLE history ADD COLUMN channel_id TEXT")
                logger.info("Added channel_id column to history table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # A/B Testing: Add columns for template type and views tracking
            try:
                self.cursor.execute("ALTER TABLE history ADD COLUMN template_type TEXT")
                logger.info("Added template_type column to history table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                self.cursor.execute(
                    "ALTER TABLE history ADD COLUMN views_24h INTEGER DEFAULT 0"
                )
                logger.info("Added views_24h column to history table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Cleanup service: Add deleted column for post deletion tracking
            try:
                self.cursor.execute(
                    "ALTER TABLE history ADD COLUMN deleted BOOLEAN DEFAULT 0"
                )
                logger.info("Added deleted column to history table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Index for faster queries by message_id
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_message_id ON history(message_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_channel_id ON history(channel_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_template_type ON history(template_type)"
            )

            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY,
                    url TEXT UNIQUE,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP,
                    priority INTEGER DEFAULT 0,
                    scheduled_time TIMESTAMP NULL
                )
            """
            )
            # Добавляем колонки если их нет
            try:
                self.cursor.execute(
                    "ALTER TABLE queue ADD COLUMN priority INTEGER DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass
            try:
                self.cursor.execute(
                    "ALTER TABLE queue ADD COLUMN scheduled_time TIMESTAMP NULL"
                )
            except sqlite3.OperationalError:
                pass

            # PERFORMANCE FIX (Problem #2, #8): Add normalized_url column for O(1) lookups
            try:
                self.cursor.execute("ALTER TABLE queue ADD COLUMN normalized_url TEXT")
                logger.info("Added normalized_url column to queue table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Создаем индексы для оптимизации
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_url ON history(url)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_image_hash ON history(image_hash)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_date ON history(date_added)"
            )

            # CRITICAL INDEX (Problem #2): Fast lookups by normalized_url
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_normalized_url ON history(normalized_url)"
            )

            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_created ON queue(created_at)"
            )

            # CRITICAL INDEX (Problem #2): Fast lookups by normalized_url
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_normalized_url ON queue(normalized_url)"
            )

            # Таблица для кэширования результатов парсинга
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    url TEXT PRIMARY KEY,
                    data TEXT,
                    cached_at TIMESTAMP
                )
            """
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_url ON cache(url)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_date ON cache(cached_at)"
            )

            # Таблица для кэширования продуктов (CachedProduct)
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS product_cache (
                    product_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    price REAL NOT NULL,
                    cc_link TEXT NOT NULL,
                    discount REAL,
                    category TEXT,
                    rating REAL,
                    created_at TIMESTAMP NOT NULL
                )
            """
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_cache_id ON product_cache(product_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_cache_cc_link ON product_cache(cc_link)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_cache_created ON product_cache(created_at)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_cache_category ON product_cache(category)"
            )

            # Таблица для черного списка товаров
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS blacklist (
                    id INTEGER PRIMARY KEY,
                    url TEXT UNIQUE,
                    reason TEXT,
                    added_at TIMESTAMP
                )
            """
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_blacklist_url ON blacklist(url)"
            )

            # Таблица для очереди ошибок (некорректные товары)
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS error_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    reason TEXT,
                    added_at TIMESTAMP,
                    resolved BOOLEAN DEFAULT 0
                )
            """
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_error_queue_url ON error_queue(url)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_error_queue_resolved ON error_queue(resolved)"
            )

            # Таблица для настроек бота
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP
                )
            """
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bot_settings_key ON bot_settings(key)"
            )

            # Таблица для состояния публикации (state machine)
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS publishing_state (
                    queue_id INTEGER PRIMARY KEY,
                    url TEXT NOT NULL,
                    state TEXT NOT NULL,
                    message_id INTEGER,
                    chat_id INTEGER,
                    text TEXT,
                    scheduled_time TIMESTAMP,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    error TEXT,
                    FOREIGN KEY (queue_id) REFERENCES queue(id)
                )
            """
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_publishing_state_state ON publishing_state(state)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_publishing_state_scheduled ON publishing_state(scheduled_time)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_publishing_state_message ON publishing_state(chat_id, message_id)"
            )

            # Таблица для пользователей
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
            )

            # De-duplication: Table for tracking posted products
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS posted_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_key TEXT NOT NULL,
                    posted_at TIMESTAMP NOT NULL
                )
            """
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_key ON posted_products (product_key)"
            )

    # ---- Новые методы для продвинутой дедупликации ----
    import re
    import hashlib
    import urllib.parse
    from datetime import datetime

    def _safe_lower(self, x):
        try:
            return x.lower()
        except Exception:
            return str(x)

    def _now_iso(self):
        return datetime.utcnow().isoformat(timespec="seconds")

    # Нормализация URL — FIXED: Use unified implementation
    def normalize_url(self, url: str) -> str:
        """
        FIXED: Now uses utils.product_key.normalize_url (single source of truth).
        This prevents deduplication failures from inconsistent normalization.
        """
        from utils.product_key import normalize_url as unified_normalize_url
        return unified_normalize_url(url)

    # Создание детерминированного ключа продукта
    def make_product_key(self, *, title: str = "", vendor: str = "", offerid: str = "", url: str = "", market_id: str = "") -> str:
        """
        FIXED: Now uses utils.product_key.generate_product_key (single source of truth).
        This prevents deduplication failures from inconsistent key generation.
        """
        from utils.product_key import generate_product_key as unified_generate_key
        return unified_generate_key(
            title=title,
            vendor=vendor,
            offerid=offerid,
            url=url,
            market_id=market_id
        )

    # Проверить есть ли такой ключ в очереди
    def queue_contains_product_key(self, product_key: str) -> bool:
        try:
            cur = self.cursor.execute("SELECT 1 FROM queue WHERE product_key = ? LIMIT 1", (product_key,))
            return cur.fetchone() is not None
        except Exception:
            return False

    # Проверить был ли опубликован похожий пост за N дней
    def has_recent_post(self, product_key: str, days: int = 7) -> bool:
        """
        Check if product was posted recently.
        FIXED: SQL injection risk - now using pure parameterized query.
        """
        try:
            # FIXED: f"-{days}" is string formatting - changed to pure param
            cur = self.cursor.execute(
                "SELECT 1 FROM posts WHERE product_key = ? AND published_at >= datetime('now', '-' || ? || ' days') LIMIT 1",
                (product_key, str(days))
            )
            return cur.fetchone() is not None
        except Exception as e:
            # если нет столбца published_at или таблицы — fallback по ключу
            logger.debug(f"has_recent_post fallback: {e}")
            try:
                cur = self.cursor.execute("SELECT 1 FROM posts WHERE product_key = ? LIMIT 1", (product_key,))
                return cur.fetchone() is not None
            except Exception as e2:
                logger.warning(f"has_recent_post failed: {e2}")
                return False

    # Вставка в очередь с ключом (без дублей на уровне SQL)
    def add_queue_item_with_key(self, url: str, title: str, product_key: str, extra: dict = None) -> bool:
        try:
            # гарантируем, что колонка added_at существует; используем datetime('now')
            self.cursor.execute(
                "INSERT OR IGNORE INTO queue (url, title, product_key, added_at) VALUES (?, ?, ?, datetime('now'))",
                (url, title, product_key)
            )
            self.conn.commit()
            # проверим, действительно ли запись создана
            cur = self.cursor.execute("SELECT 1 FROM queue WHERE product_key = ? LIMIT 1", (product_key,))
            return cur.fetchone() is not None
        except Exception:
            return False

    # Запись опубликованного поста
    def add_posted_product(self, product_key: str, url: str = None) -> None:
        try:
            # создаём таблицу posts если её нет — тихо
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY,
                    product_key TEXT,
                    url TEXT,
                    published_at TEXT
                )
            """)
            self.cursor.execute(
                "INSERT INTO posts (product_key, url, published_at) VALUES (?, ?, datetime('now'))",
                (product_key, url)
            )
            self.conn.commit()
        except Exception:
            pass
    # ---- конец новых методов ----

    def _migrate_normalized_urls(self):
        """
        Migration: Populate normalized_url for existing records (Problem #2, #8).
        This runs once on startup if normalized_url is NULL.
        """
        try:
            with self.connection:
                # Migrate history table
                rows = self.cursor.execute(
                    "SELECT id, url FROM history WHERE normalized_url IS NULL"
                ).fetchall()

                if rows:
                    logger.info(
                        f"Migrating {len(rows)} history records with normalized_url..."
                    )
                    for row in rows:
                        normalized = self.normalize_url(row["url"])
                        self.cursor.execute(
                            "UPDATE history SET normalized_url = ? WHERE id = ?",
                            (normalized, row["id"]),
                        )
                    logger.info("History migration complete")

                # Migrate queue table
                rows = self.cursor.execute(
                    "SELECT id, url FROM queue WHERE normalized_url IS NULL"
                ).fetchall()

                if rows:
                    logger.info(
                        f"Migrating {len(rows)} queue records with normalized_url..."
                    )
                    for row in rows:
                        normalized = self.normalize_url(row["url"])
                        self.cursor.execute(
                            "UPDATE queue SET normalized_url = ? WHERE id = ?",
                            (normalized, row["id"]),
                        )
                    logger.info("Queue migration complete")
        except Exception as e:
            logger.warning(f"Migration error (non-fatal): {e}")

    # PERFORMANCE FIX (Problem #2): O(1) SQL query instead of O(n) Python loop
    def exists_url(self, url: str, check_normalized: bool = True) -> bool:
        """
        Check if URL exists in history using fast SQL index lookup.

        Args:
            url: URL to check
            check_normalized: If True, checks by normalized URL (default, recommended)

        Returns:
            True if URL exists, False otherwise
        """
        with self.connection:
            if check_normalized:
                # Fast O(1) lookup using indexed normalized_url column
                normalized = self.normalize_url(url)
                res = self.cursor.execute(
                    "SELECT 1 FROM history WHERE normalized_url = ? LIMIT 1",
                    (normalized,),
                ).fetchone()
                return bool(res)
            else:
                # Exact URL match
                res = self.cursor.execute(
                    "SELECT 1 FROM history WHERE url = ? LIMIT 1", (url,)
                ).fetchone()
                return bool(res)

    # PERFORMANCE FIX (Problem #2): O(1) SQL query instead of O(n) Python loop
    def exists_url_in_queue(self, url: str, check_normalized: bool = True) -> bool:
        """
        Check if URL exists in pending queue using fast SQL index lookup.

        Args:
            url: URL to check
            check_normalized: If True, checks by normalized URL (default, recommended)

        Returns:
            True if URL exists in pending queue, False otherwise
        """
        with self.connection:
            if check_normalized:
                # Fast O(1) lookup using indexed normalized_url column
                normalized = self.normalize_url(url)
                res = self.cursor.execute(
                    "SELECT 1 FROM queue WHERE normalized_url = ? AND status = 'pending' LIMIT 1",
                    (normalized,),
                ).fetchone()
                return bool(res)
            else:
                # Exact URL match
                res = self.cursor.execute(
                    "SELECT 1 FROM queue WHERE url = ? AND status = 'pending' LIMIT 1",
                    (url,),
                ).fetchone()
                return bool(res)

    def exists_image(self, img_hash: str) -> bool:
        with self.connection:
            res = self.cursor.execute(
                "SELECT id FROM history WHERE image_hash = ?", (img_hash,)
            ).fetchone()
            return bool(res)

    def add_post_to_history(
        self,
        url: str,
        img_hash: str,
        title: str = "",
        message_id: Optional[int] = None,
        channel_id: Optional[str] = None,
        price: Optional[float] = None,
        template_type: Optional[str] = None,
    ) -> None:
        """
        Add post to history with auto-computed normalized_url and Telegram message info.

        Args:
            url: Product URL
            img_hash: Image hash
            title: Product title
            message_id: Telegram message ID (for sold out cleaner)
            channel_id: Telegram channel ID (for sold out cleaner)
            price: Product price (for price drop monitoring)
            template_type: A/B test template type ("emoji_heavy" or "professional")
        """
        try:
            normalized = self.normalize_url(url)
            # Extract price number if price is a string
            price_num = None
            if price:
                if isinstance(price, str):
                    # Try to extract number from price string
                    import re

                    price_clean = re.sub(
                        r"[^\d.,]", "", price.replace(",", ".").replace("\u00a0", " ")
                    )
                    try:
                        price_num = float(price_clean.replace(" ", ""))
                    except (ValueError, TypeError):
                        price_num = None
                elif isinstance(price, (int, float)):
                    price_num = float(price)

            with self.connection:
                self.cursor.execute(
                    """INSERT INTO history
                       (url, image_hash, date_added, title, normalized_url, message_id, channel_id, last_price, template_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        url,
                        img_hash,
                        datetime.datetime.utcnow(),
                        title,
                        normalized,
                        message_id,
                        channel_id,
                        price_num,
                        template_type,
                    ),
                )
        except sqlite3.IntegrityError:
            # If duplicate, update message_id, channel_id and template_type
            logger.debug(
                "Updating existing history entry with message_id for url=%s", url
            )
            with self.connection:
                self.cursor.execute(
                    """UPDATE history
                       SET message_id = ?, channel_id = ?, template_type = ?
                       WHERE url = ?""",
                    (message_id, channel_id, template_type, url),
                )

    def get_history(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Возвращает историю публикаций

        Args:
            limit: максимальное количество записей
            offset: смещение для пагинации
        """
        with self.connection:
            rows = self.cursor.execute(
                "SELECT url, title, date_added FROM history ORDER BY date_added DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            result = []
            for row in rows:
                title = row["title"] if "title" in row.keys() else ""
                result.append(
                    {"url": row["url"], "title": title, "date": row["date_added"]}
                )
            return result

    def get_recent_posts_with_messages(self, hours: int = 48) -> List[Dict[str, Any]]:
        """
        Получает посты за последние N часов с message_id и channel_id.
        Используется для проверки на "Sold Out".

        Args:
            hours: Количество часов назад для проверки

        Returns:
            Список словарей с полями: id, url, title, message_id, channel_id, date_added
        """
        with self.connection:
            cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
            rows = self.cursor.execute(
                """
                SELECT id, url, title, message_id, channel_id, date_added
                FROM history
                WHERE date_added >= ?
                AND message_id IS NOT NULL
                AND channel_id IS NOT NULL
                ORDER BY date_added DESC
            """,
                (cutoff_time,),
            ).fetchall()

            result = []
            for row in rows:
                result.append(
                    {
                        "id": row["id"],
                        "url": row["url"],
                        "title": row["title"] if "title" in row.keys() else "",
                        "message_id": row["message_id"],
                        "channel_id": row["channel_id"],
                        "date_added": row["date_added"],
                    }
                )
            return result

    def update_message_id(self, url: str, message_id: int, channel_id: str) -> bool:
        """
        Обновляет message_id и channel_id для существующей записи.

        Args:
            url: URL товара
            message_id: Telegram message ID
            channel_id: Telegram channel ID

        Returns:
            True если обновлено, False если запись не найдена
        """
        with self.connection:
            cursor = self.cursor.execute(
                "UPDATE history SET message_id = ?, channel_id = ? WHERE url = ?",
                (message_id, channel_id, url),
            )
            return cursor.rowcount > 0

    def get_history_count(self) -> int:
        """Возвращает общее количество записей в истории"""
        with self.connection:
            return self.cursor.execute("SELECT count(*) as c FROM history").fetchone()[
                "c"
            ]

    def mark_history_as_deleted(self, history_id: int) -> bool:
        """
        Помечает запись в истории как удаленную.

        Args:
            history_id: ID записи в истории

        Returns:
            True если запись обновлена, False если запись не найдена
        """
        try:
            # Добавляем колонку deleted если её нет
            try:
                self.cursor.execute(
                    "ALTER TABLE history ADD COLUMN deleted BOOLEAN DEFAULT 0"
                )
                logger.debug("Added deleted column to history table")
            except sqlite3.OperationalError:
                pass  # Колонка уже существует

            with self.connection:
                cursor = self.cursor.execute(
                    "UPDATE history SET deleted = 1 WHERE id = ?", (history_id,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error marking history entry {history_id} as deleted: {e}")
            return False

    def get_old_posts_for_cleanup(
        self, hours_threshold: int = 48
    ) -> List[Dict[str, Any]]:
        """
        Получает старые посты для проверки на мертвые ссылки.

        Args:
            hours_threshold: Минимальный возраст поста в часах

        Returns:
            Список словарей с полями: id, url, title, message_id, channel_id, date_added
        """
        with self.connection:
            cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(
                hours=hours_threshold
            )
            rows = self.cursor.execute(
                """
                SELECT id, url, title, message_id, channel_id, date_added
                FROM history
                WHERE date_added <= ?
                AND (deleted IS NULL OR deleted = 0)
                AND message_id IS NOT NULL
                AND channel_id IS NOT NULL
                ORDER BY date_added ASC
            """,
                (cutoff_time,),
            ).fetchall()

            result = []
            for row in rows:
                result.append(
                    {
                        "id": row["id"],
                        "url": row["url"],
                        "title": row["title"] if "title" in row.keys() else "",
                        "message_id": row["message_id"],
                        "channel_id": row["channel_id"],
                        "date_added": row["date_added"],
                    }
                )
            return result

    def get_ab_test_stats(self) -> Dict[str, Any]:
        """
        Получает статистику A/B тестирования.

        Returns:
            Словарь со статистикой по типам шаблонов
        """
        with self.connection:
            # Статистика по типам шаблонов
            template_stats = self.cursor.execute(
                """
                SELECT
                    template_type,
                    COUNT(*) as total_posts,
                    AVG(views_24h) as avg_views,
                    SUM(views_24h) as total_views,
                    MIN(views_24h) as min_views,
                    MAX(views_24h) as max_views
                FROM history
                WHERE template_type IS NOT NULL
                GROUP BY template_type
            """
            ).fetchall()

            # Статистика за последние 7 дней
            week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
            weekly_stats = self.cursor.execute(
                """
                SELECT
                    template_type,
                    COUNT(*) as posts_last_week,
                    AVG(views_24h) as avg_views_week,
                    SUM(views_24h) as total_views_week
                FROM history
                WHERE template_type IS NOT NULL
                AND date_added >= ?
                GROUP BY template_type
            """,
                (week_ago,),
            ).fetchall()

            # Общая статистика
            total_stats = self.cursor.execute(
                """
                SELECT
                    COUNT(*) as total_ab_posts,
                    AVG(views_24h) as overall_avg_views,
                    SUM(views_24h) as overall_total_views
                FROM history
                WHERE template_type IS NOT NULL
            """
            ).fetchone()

            return {
                "template_stats": [
                    {
                        "template_type": row["template_type"],
                        "total_posts": row["total_posts"],
                        "avg_views": row["avg_views"] or 0,
                        "total_views": row["total_views"] or 0,
                        "min_views": row["min_views"] or 0,
                        "max_views": row["max_views"] or 0,
                    }
                    for row in template_stats
                ],
                "weekly_stats": [
                    {
                        "template_type": row["template_type"],
                        "posts_last_week": row["posts_last_week"],
                        "avg_views_week": row["avg_views_week"] or 0,
                        "total_views_week": row["total_views_week"] or 0,
                    }
                    for row in weekly_stats
                ],
                "total_stats": {
                    "total_ab_posts": total_stats["total_ab_posts"],
                    "overall_avg_views": total_stats["overall_avg_views"] or 0,
                    "overall_total_views": total_stats["overall_total_views"] or 0,
                },
            }

    def update_post_views(self, message_id: int, views: int) -> bool:
        """
        Обновляет количество просмотров для поста.

        Args:
            message_id: Telegram message ID
            views: Количество просмотров

        Returns:
            True если обновлено, False если пост не найден
        """
        with self.connection:
            cursor = self.cursor.execute(
                "UPDATE history SET views_24h = ? WHERE message_id = ?",
                (views, message_id),
            )
            return cursor.rowcount > 0

    def get_posts_for_views_update(self, hours_old: int = 24) -> List[Dict[str, Any]]:
        """
        Получает посты для обновления просмотров.

        Args:
            hours_old: Возраст постов в часах

        Returns:
            Список с message_id, channel_id и текущими views_24h
        """
        with self.connection:
            cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(
                hours=hours_old
            )
            rows = self.cursor.execute(
                """
                SELECT message_id, channel_id, views_24h, date_added
                FROM history
                WHERE message_id IS NOT NULL
                AND channel_id IS NOT NULL
                AND template_type IS NOT NULL
                AND date_added <= ?
                ORDER BY date_added DESC
            """,
                (cutoff_time,),
            ).fetchall()

            return [
                {
                    "message_id": row["message_id"],
                    "channel_id": row["channel_id"],
                    "current_views": row["views_24h"] or 0,
                    "date_added": row["date_added"],
                }
                for row in rows
            ]

    # queue
    def add_to_queue(
        self, url: str, priority: int = 0, scheduled_time: dt = None
    ) -> Optional[int]:
        """
        Add URL to queue with auto-computed normalized_url (Problem #2, #8).

        Returns:
            Queue entry ID if successful, None otherwise
        """
        # Проверяем дубликаты перед добавлением (с нормализацией) - теперь быстро O(1)
        if self.exists_url_in_queue(url, check_normalized=True):
            logger.debug(f"URL already in queue (normalized check): {url[:100]}")
            return None

        try:
            normalized = self.normalize_url(url)
            with self.connection:
                self.cursor.execute(
                    "INSERT INTO queue (url, created_at, priority, scheduled_time, normalized_url) VALUES (?, ?, ?, ?, ?)",
                    (
                        url,
                        datetime.datetime.utcnow(),
                        priority,
                        scheduled_time,
                        normalized,
                    ),
                )
                queue_id = self.cursor.lastrowid

                # Create publishing entry with state 'queued'
                # Используем INSERT OR IGNORE для предотвращения UNIQUE constraint failed
                try:
                    from models.publishing_state import PublishingState

                    now = datetime.datetime.utcnow()
                    self.cursor.execute(
                        """
                        INSERT OR IGNORE INTO publishing_state 
                        (queue_id, url, state, scheduled_time, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            queue_id,
                            url,
                            PublishingState.QUEUED.value,
                            scheduled_time.isoformat() if scheduled_time else None,
                            now.isoformat(),
                            now.isoformat(),
                        ),
                    )
                    # Если запись уже существует, обновляем её (ON CONFLICT не поддерживается в старых версиях SQLite)
                    if self.cursor.rowcount == 0:
                        # Запись уже существует, обновляем состояние
                        self.cursor.execute(
                            """
                            UPDATE publishing_state
                            SET state = ?, updated_at = ?
                            WHERE queue_id = ?
                        """,
                            (PublishingState.QUEUED.value, now.isoformat(), queue_id),
                        )
                except Exception as e:
                    logger.warning(f"Failed to create/update publishing entry: {e}")
                    # Continue anyway, queue entry is created

                return queue_id
        except sqlite3.IntegrityError:
            return None
        except Exception as e:
            logger.error(f"Error in add_to_queue: {e}")
            return None

    def add_to_queue_batch(
        self, urls: List[Tuple[str, int, Optional[dt]]]
    ) -> int:
        """
        Batch добавление URL в очередь

        Args:
            urls: Список кортежей (url, priority, scheduled_time)

        Returns:
            Количество успешно добавленных URL
        """
        if not urls:
            return 0

        added_count = 0
        try:
            with self.connection:
                now = datetime.datetime.utcnow()
                for url, priority, scheduled_time in urls:
                    try:
                        self.cursor.execute(
                            "INSERT INTO queue (url, created_at, priority, scheduled_time) VALUES (?, ?, ?, ?)",
                            (url, now, priority, scheduled_time),
                        )
                        added_count += 1
                    except sqlite3.IntegrityError:
                        # URL уже существует, пропускаем
                        continue
                return added_count
        except Exception as e:
            logger.error(f"Error in batch add_to_queue: {e}")
            return added_count

    def get_next_from_queue(
        self, respect_schedule: bool = True, rotate: bool = True
    ) -> Optional[Tuple[int, str]]:
        """Получает следующий товар из очереди с учетом приоритета и расписания

        Args:
            respect_schedule: учитывать расписание
            rotate: ротация - если True, берет товары по кругу (старые первыми)
        """
        with self.connection:
            now = datetime.datetime.utcnow()
            if respect_schedule:
                # Берем товары с приоритетом, которые можно публиковать сейчас
                if rotate:
                    # Ротация: сначала старые товары с высоким приоритетом, потом новые
                    row = self.cursor.execute(
                        """SELECT id, url FROM queue 
                           WHERE status = 'pending' 
                           AND (scheduled_time IS NULL OR scheduled_time <= ?)
                           ORDER BY priority DESC, created_at ASC, id ASC 
                           LIMIT 1""",
                        (now,),
                    ).fetchone()
                else:
                    row = self.cursor.execute(
                        """SELECT id, url FROM queue 
                           WHERE status = 'pending' 
                           AND (scheduled_time IS NULL OR scheduled_time <= ?)
                           ORDER BY priority DESC, id ASC 
                           LIMIT 1""",
                        (now,),
                    ).fetchone()
            else:
                # Без учета расписания
                if rotate:
                    row = self.cursor.execute(
                        "SELECT id, url FROM queue WHERE status = 'pending' ORDER BY priority DESC, created_at ASC, id ASC LIMIT 1"
                    ).fetchone()
                else:
                    row = self.cursor.execute(
                        "SELECT id, url FROM queue WHERE status = 'pending' ORDER BY priority DESC, id ASC LIMIT 1"
                    ).fetchone()

            if row:
                return (row["id"], row["url"])
            return None

    def mark_as_done(self, task_id: int) -> None:
        with self.connection:
            self.cursor.execute(
                "UPDATE queue SET status = 'done' WHERE id = ?", (task_id,)
            )

    def mark_as_error(self, task_id: int) -> None:
        with self.connection:
            self.cursor.execute(
                "UPDATE queue SET status = 'error' WHERE id = ?", (task_id,)
            )

    def get_queue_count(self) -> int:
        with self.connection:
            return self.cursor.execute(
                "SELECT count(*) as c FROM queue WHERE status = 'pending'"
            ).fetchone()["c"]

    def get_queue_size(self) -> int:
        """Алиас для get_queue_count для совместимости"""
        return self.get_queue_count()

    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику бота"""
        with self.connection:
            stats = {}
            # Опубликовано всего
            stats["published"] = self.cursor.execute(
                "SELECT count(*) as c FROM history"
            ).fetchone()["c"]
            # В очереди
            stats["pending"] = self.cursor.execute(
                "SELECT count(*) as c FROM queue WHERE status = 'pending'"
            ).fetchone()["c"]
            # Ошибок
            stats["errors"] = self.cursor.execute(
                "SELECT count(*) as c FROM queue WHERE status = 'error'"
            ).fetchone()["c"]
            # В истории
            stats["history"] = stats["published"]
            # Успешных сегодня
            today = datetime.datetime.utcnow().date()
            stats["today"] = self.cursor.execute(
                "SELECT count(*) as c FROM history WHERE date(date_added) = date(?)",
                (today.isoformat(),),
            ).fetchone()["c"]
            return stats

    def clear_queue(self) -> int:
        """Очищает очередь от всех pending задач"""
        with self.connection:
            count = self.cursor.execute(
                "SELECT count(*) as c FROM queue WHERE status = 'pending'"
            ).fetchone()["c"]
            self.cursor.execute("DELETE FROM queue WHERE status = 'pending'")
            return count

    def remove_from_queue(self, url: str = None, task_id: int = None) -> bool:
        """Удаляет URL из очереди по URL или task_id"""
        with self.connection:
            if task_id:
                cursor = self.cursor.execute(
                    "DELETE FROM queue WHERE id = ? AND status = 'pending'", (task_id,)
                )
            elif url:
                cursor = self.cursor.execute(
                    "DELETE FROM queue WHERE url = ? AND status = 'pending'", (url,)
                )
            else:
                return False
            return cursor.rowcount > 0

    def get_queue_urls(self, limit: int = 20) -> List[Tuple[int, str]]:
        """Возвращает список URL из очереди (id, url)"""
        with self.connection:
            rows = self.cursor.execute(
                "SELECT id, url FROM queue WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [(row["id"], row["url"]) for row in rows]

    # Кэширование
    def get_cached_data(
        self, url: str, max_age_hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """Получает закэшированные данные парсинга, если они не старше max_age_hours"""
        with self.connection:
            row = self.cursor.execute(
                "SELECT data, cached_at FROM cache WHERE url = ?", (url,)
            ).fetchone()
            if row:
                cached_at = datetime.datetime.fromisoformat(row["cached_at"])
                age = datetime.datetime.utcnow() - cached_at
                if age.total_seconds() < max_age_hours * 3600:
                    try:
                        return json.loads(row["data"])
                    except Exception:
                        return None
            return None

    def set_cached_data(self, url: str, data: Dict[str, Any]) -> None:
        """Сохраняет данные парсинга в кэш"""
        try:
            # Убираем image_bytes из данных перед сериализацией (bytes не сериализуется в JSON)
            cache_data = {k: v for k, v in data.items() if k != "image_bytes"}
            with self.connection:
                self.cursor.execute(
                    "INSERT OR REPLACE INTO cache (url, data, cached_at) VALUES (?, ?, ?)",
                    (url, json.dumps(cache_data), datetime.datetime.utcnow()),
                )
        except Exception as e:
            logger.warning("set_cached_data error: %s", e)

    def clear_old_cache(self, max_age_hours: int = 48) -> None:
        """Удаляет устаревшие записи из кэша"""
        try:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(
                hours=max_age_hours
            )
            with self.connection:
                self.cursor.execute("DELETE FROM cache WHERE cached_at < ?", (cutoff,))
        except Exception as e:
            logger.warning("clear_old_cache error: %s", e)

    # Product Cache (CachedProduct)
    def cache_product(self, product: "CachedProduct") -> bool:
        """
        Cache product data after successful CC generation.

        Args:
            product: CachedProduct instance

        Returns:
            True if cached successfully, False otherwise
        """
        try:
            from models.cached_product import CachedProduct

            if not isinstance(product, CachedProduct):
                logger.warning("cache_product: invalid product type")
                return False

            # Validate before caching
            if not product.title or not product.title.strip():
                logger.warning("cache_product: empty title, skipping cache")
                return False

            if product.price <= 0:
                logger.warning(
                    f"cache_product: invalid price {product.price}, skipping cache"
                )
                return False

            with self.connection:
                self.cursor.execute(
                    """
                    INSERT OR REPLACE INTO product_cache 
                    (product_id, title, price, cc_link, discount, category, rating, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        product.product_id,
                        product.title,
                        product.price,
                        product.cc_link,
                        product.discount,
                        product.category,
                        product.rating,
                        (
                            product.created_at.isoformat()
                            if isinstance(product.created_at, datetime.datetime)
                            else product.created_at
                        ),
                    ),
                )
            logger.debug(f"Cached product: {product.product_id} - {product.title[:50]}")
            return True
        except Exception as e:
            logger.warning(f"cache_product error: {e}")
            return False

    def get_cached_product(
        self, product_id: str, ttl_days: int = 7
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached product if fresh (within TTL).

        Args:
            product_id: Product ID
            ttl_days: Time-to-live in days (default: 7)

        Returns:
            Product data dict or None if not found or expired
        """
        try:
            with self.connection:
                row = self.cursor.execute(
                    "SELECT * FROM product_cache WHERE product_id = ?", (product_id,)
                ).fetchone()

                if row:
                    # Check TTL
                    created_at = datetime.datetime.fromisoformat(row["created_at"])
                    age = datetime.datetime.utcnow() - created_at
                    if age.days >= ttl_days:
                        logger.debug(
                            f"Product {product_id} cache expired (age: {age.days} days)"
                        )
                        return None

                    return {
                        "product_id": row["product_id"],
                        "title": row["title"],
                        "price": row["price"],
                        "cc_link": row["cc_link"],
                        "discount": row["discount"],
                        "category": row["category"],
                        "rating": row["rating"],
                        "created_at": row["created_at"],
                    }
            return None
        except Exception as e:
            logger.warning(f"get_cached_product error: {e}")
            return None

    def get_cached_product_by_cc_link(
        self, cc_link: str, ttl_days: int = 7
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached product by CC link.

        Args:
            cc_link: CC link
            ttl_days: Time-to-live in days (default: 7)

        Returns:
            Product data dict or None if not found or expired
        """
        try:
            with self.connection:
                row = self.cursor.execute(
                    "SELECT * FROM product_cache WHERE cc_link = ?", (cc_link,)
                ).fetchone()

                if row:
                    # Check TTL
                    created_at = datetime.datetime.fromisoformat(row["created_at"])
                    age = datetime.datetime.utcnow() - created_at
                    if age.days >= ttl_days:
                        logger.debug(
                            f"Product {row['product_id']} cache expired (age: {age.days} days)"
                        )
                        return None

                    return {
                        "product_id": row["product_id"],
                        "title": row["title"],
                        "price": row["price"],
                        "cc_link": row["cc_link"],
                        "discount": row["discount"],
                        "category": row["category"],
                        "rating": row["rating"],
                        "created_at": row["created_at"],
                    }
            return None
        except Exception as e:
            logger.warning(f"get_cached_product_by_cc_link error: {e}")
            return None

    def clear_old_product_cache(self, ttl_days: int = 7) -> int:
        """
        Remove expired product cache entries.

        Args:
            ttl_days: Time-to-live in days (default: 7)

        Returns:
            Number of deleted entries
        """
        try:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=ttl_days)
            with self.connection:
                cursor = self.cursor.execute(
                    "DELETE FROM product_cache WHERE created_at < ?",
                    (cutoff.isoformat(),),
                )
                count = cursor.rowcount
                logger.info(f"Cleared {count} expired product cache entries")
                return count
        except Exception as e:
            logger.warning(f"clear_old_product_cache error: {e}")
            return 0

    # Черный список
    def is_blacklisted(self, url: str) -> bool:
        """Проверяет, находится ли URL в черном списке"""
        with self.connection:
            res = self.cursor.execute(
                "SELECT id FROM blacklist WHERE url = ?", (url,)
            ).fetchone()
            return bool(res)

    def add_to_blacklist(self, url: str, reason: str = "") -> bool:
        """Добавляет URL в черный список"""
        try:
            with self.connection:
                self.cursor.execute(
                    "INSERT INTO blacklist (url, reason, added_at) VALUES (?, ?, ?)",
                    (url, reason, datetime.datetime.utcnow()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_from_blacklist(self, url: str) -> bool:
        """Удаляет URL из черного списка"""
        with self.connection:
            cursor = self.cursor.execute("DELETE FROM blacklist WHERE url = ?", (url,))
            return cursor.rowcount > 0

    def get_blacklist(self) -> List[Dict[str, str]]:
        """Возвращает список черного списка"""
        with self.connection:
            rows = self.cursor.execute(
                "SELECT url, reason FROM blacklist ORDER BY added_at DESC"
            ).fetchall()
            result = []
            for row in rows:
                reason = row["reason"] if "reason" in row.keys() else ""
                result.append({"url": row["url"], "reason": reason})
            return result

    def get_last_post(self) -> Optional[Dict[str, str]]:
        """Возвращает последний опубликованный пост"""
        with self.connection:
            row = self.cursor.execute(
                "SELECT url, title, date_added FROM history ORDER BY date_added DESC LIMIT 1"
            ).fetchone()
            if row:
                return {
                    "url": row["url"],
                    "title": row["title"] if "title" in row.keys() else "",
                    "date": row["date_added"],
                }
            return None

    def get_last_post_time(self) -> Optional[dt]:
        """Возвращает время последнего опубликованного поста"""
        try:
            with self.connection:
                row = self.cursor.execute(
                    "SELECT date_added FROM history ORDER BY date_added DESC LIMIT 1"
                ).fetchone()
                if row:
                    # Преобразуем строку в datetime
                    date_str = row["date_added"]
                    if isinstance(date_str, str):
                        # Пробуем разные форматы
                        try:
                            return datetime.datetime.fromisoformat(
                                date_str.replace("Z", "+00:00")
                            )
                        except ValueError:
                            try:
                                return datetime.datetime.strptime(
                                    date_str, "%Y-%m-%d %H:%M:%S"
                                )
                            except ValueError:
                                return datetime.datetime.strptime(
                                    date_str, "%Y-%m-%d %H:%M:%S.%f"
                                )
                    elif isinstance(date_str, datetime.datetime):
                        return date_str
            return None
        except Exception as e:
            logger.warning(f"get_last_post_time error: {e}")
            return None

    def add_to_error_queue(self, url: str, reason: str) -> None:
        """Добавляет товар в очередь ошибок для отладки"""
        try:
            with self.connection:
                self.cursor.execute(
                    "INSERT INTO error_queue (url, reason, added_at) VALUES (?, ?, ?)",
                    (url, reason, datetime.datetime.utcnow()),
                )
        except Exception as e:
            logger.warning("add_to_error_queue error: %s", e)

    def get_error_queue(self, limit: int = 50) -> List[Dict[str, str]]:
        """Возвращает список товаров из очереди ошибок"""
        with self.connection:
            rows = self.cursor.execute(
                "SELECT url, reason, added_at FROM error_queue WHERE resolved = 0 ORDER BY added_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "url": row["url"],
                    "reason": row["reason"] if "reason" in row.keys() else "",
                    "date": row["added_at"],
                }
                for row in rows
            ]

    # Publishing State Machine
    def get_publishing_entry(self, queue_id: int) -> Optional[Dict[str, Any]]:
        """
        Get publishing entry by queue_id.

        Returns:
            Publishing entry dict or None if not found
        """
        try:
            with self.connection:
                row = self.cursor.execute(
                    "SELECT * FROM publishing_state WHERE queue_id = ?", (queue_id,)
                ).fetchone()

                if row:
                    return {
                        "queue_id": row["queue_id"],
                        "url": row["url"],
                        "state": row["state"],
                        "message_id": row["message_id"],
                        "chat_id": row["chat_id"],
                        "text": row["text"],
                        "scheduled_time": row["scheduled_time"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "error": row["error"],
                    }
            return None
        except Exception as e:
            logger.warning(f"get_publishing_entry error: {e}")
            return None

    def update_publishing_state(
        self,
        queue_id: int,
        state: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        text: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update publishing state.

        Args:
            queue_id: Queue entry ID
            state: New state (queued, processing, ready, posted, failed)
            message_id: Telegram message ID (if posted)
            chat_id: Telegram chat ID
            text: Message text/caption
            error: Error message (if failed)

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            now = datetime.datetime.utcnow()
            with self.connection:
                self.cursor.execute(
                    """
                    UPDATE publishing_state
                    SET state = ?, message_id = ?, chat_id = ?, text = ?, 
                        updated_at = ?, error = ?
                    WHERE queue_id = ?
                """,
                    (
                        state,
                        message_id,
                        chat_id,
                        text,
                        now.isoformat(),
                        error,
                        queue_id,
                    ),
                )
            return True
        except Exception as e:
            logger.warning(f"update_publishing_state error: {e}")
            return False

    def get_ready_posts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get posts in 'ready' state that are ready to be published.

        Returns:
            List of publishing entries
        """
        try:
            with self.connection:
                rows = self.cursor.execute(
                    """
                    SELECT * FROM publishing_state
                    WHERE state = 'ready'
                    AND (scheduled_time IS NULL OR scheduled_time <= ?)
                    ORDER BY created_at ASC
                    LIMIT ?
                """,
                    (datetime.datetime.utcnow().isoformat(), limit),
                ).fetchall()

                return [
                    {
                        "queue_id": row["queue_id"],
                        "url": row["url"],
                        "state": row["state"],
                        "message_id": row["message_id"],
                        "chat_id": row["chat_id"],
                        "text": row["text"],
                        "scheduled_time": row["scheduled_time"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "error": row["error"],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.warning(f"get_ready_posts error: {e}")
            return []

    def get_processing_posts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get posts stuck in 'processing' state (for recovery).

        Returns:
            List of publishing entries
        """
        try:
            # Get posts in processing state older than 10 minutes
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
            with self.connection:
                rows = self.cursor.execute(
                    """
                    SELECT * FROM publishing_state
                    WHERE state = 'processing'
                    AND updated_at < ?
                    ORDER BY updated_at ASC
                    LIMIT ?
                """,
                    (cutoff.isoformat(), limit),
                ).fetchall()

                return [
                    {
                        "queue_id": row["queue_id"],
                        "url": row["url"],
                        "state": row["state"],
                        "message_id": row["message_id"],
                        "chat_id": row["chat_id"],
                        "text": row["text"],
                        "scheduled_time": row["scheduled_time"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "error": row["error"],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.warning(f"get_processing_posts error: {e}")
            return []

    # Настройки бота
    def get_setting(self, key: str, default: str = "False") -> str:
        """Получить настройку из bot_settings"""
        try:
            with self.connection:
                row = self.cursor.execute(
                    "SELECT value FROM bot_settings WHERE key = ?", (key,)
                ).fetchone()
                if row:
                    return row["value"]
                return default
        except Exception as e:
            logger.warning(f"get_setting error: {e}")
            return default

    def set_setting(self, key: str, value: str) -> None:
        """Установить настройку в bot_settings"""
        try:
            with self.connection:
                self.cursor.execute(
                    """
                    INSERT OR REPLACE INTO bot_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                """,
                    (key, value, datetime.datetime.utcnow()),
                )
        except Exception as e:
            logger.warning(f"set_setting error: {e}")

    def get_queue_stats(self) -> Dict[str, int]:
        """Получить статистику очереди"""
        try:
            with self.connection:
                stats = {}
                # Опубликовано
                stats["published"] = self.cursor.execute(
                    "SELECT count(*) as c FROM queue WHERE status = 'done'"
                ).fetchone()["c"]
                # Ошибок
                stats["errors"] = self.cursor.execute(
                    "SELECT count(*) as c FROM queue WHERE status = 'error'"
                ).fetchone()["c"]
                # Сегодня
                today = datetime.datetime.utcnow().date()
                stats["today"] = self.cursor.execute(
                    "SELECT count(*) as c FROM queue WHERE status = 'done' AND date(created_at) = date(?)",
                    (today.isoformat(),),
                ).fetchone()["c"]
                return stats
        except Exception as e:
            logger.warning(f"get_queue_stats error: {e}")
            return {"published": 0, "errors": 0, "today": 0}

    # Пользователи
    def add_user(
        self,
        user_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
    ) -> None:
        """Добавить или обновить пользователя"""
        try:
            with self.connection:
                self.cursor.execute(
                    """
                    INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, last_activity)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        user_id,
                        username,
                        first_name,
                        last_name,
                        datetime.datetime.utcnow(),
                    ),
                )
        except Exception as e:
            logger.warning(f"add_user error: {e}")

    def get_user_stats(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить статистику пользователя"""
        try:
            with self.connection:
                row = self.cursor.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row:
                    return {
                        "user_id": row["user_id"],
                        "username": row["username"],
                        "first_name": row["first_name"],
                        "last_name": row["last_name"],
                        "joined_at": row["joined_at"],
                        "last_activity": row["last_activity"],
                        "downloads_count": 0,  # Заглушка, можно добавить реальную статистику
                    }
            return None
        except Exception as e:
            logger.warning(f"get_user_stats error: {e}")
            return None

    # Методы для работы с ключами — вставьте в класс Database (адаптируйте имена курсора/conn)
    def queue_contains_product_key(self, product_key: str) -> bool:
        cur = self.cursor.execute("SELECT 1 FROM queue WHERE product_key = ? LIMIT 1", (product_key,))
        return cur.fetchone() is not None

    # NOTE: This is a DUPLICATE method - should be removed (see line 422)
    # Kept for backward compatibility but marked as deprecated
    def has_recent_post_duplicate(self, product_key: str, days: int = 7) -> bool:
        """
        DEPRECATED: Duplicate of has_recent_post (line 422). Use that instead.
        FIXED: SQL injection risk - now using pure parameterized query.
        """
        # используем таблицу posted_products с полем posted_at
        try:
            # FIXED: f"-{days}" is string formatting - changed to pure param
            cur = self.cursor.execute(
                "SELECT 1 FROM posted_products WHERE product_key = ? AND posted_at >= datetime('now', '-' || ? || ' days') LIMIT 1",
                (product_key, str(days))
            )
            return cur.fetchone() is not None
        except Exception as e:
            # fallback: если нет posted_at, просто ищем по ключу
            logger.debug(f"has_recent_post_duplicate fallback: {e}")
            cur = self.cursor.execute("SELECT 1 FROM posted_products WHERE product_key = ? LIMIT 1", (product_key,))
            return cur.fetchone() is not None

    def add_queue_item_with_key(self, url: str, title: str, product_key: str, extra_fields: dict = None) -> None:
        now = datetime.utcnow().isoformat()
        # добавим basic columns, подставьте дополнительные поля по своей схеме
        try:
            self.cursor.execute(
                "INSERT OR IGNORE INTO queue (url, title, product_key, added_at) VALUES (?, ?, ?, ?)",
                (url, title, product_key, now)
            )
            self.connection.commit()
        except Exception:
            # в случае, если в схеме нет колонок — упадёт, но главное: не вставит дубликат
            pass

    def add_posted_product(self, product_key: str, url: str = None) -> None:
        now = datetime.utcnow().isoformat()
        try:
            self.cursor.execute(
                "INSERT INTO posted_products (product_key, posted_at) VALUES (?, ?)",
                (product_key, now)
            )
            self.connection.commit()
        except Exception:
            # если нет таблицы posted_products или другие колонки — аккуратно игнорируем
            pass

    # De-duplication methods
    def has_been_posted_recently(
        self, product_key: str, days_to_check: int = 7
    ) -> bool:
        """
        Check if a product with the same key has been posted within the last N days.

        Args:
            product_key: Normalized product key
            days_to_check: Number of days to check for duplicates (default: 7)

        Returns:
            True if product was posted recently, False otherwise
        """
        try:
            with self.connection:
                cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days_to_check)
                row = self.cursor.execute(
                    """
                    SELECT 1 FROM posted_products
                    WHERE product_key = ? AND posted_at >= ?
                    LIMIT 1
                """,
                    (product_key, cutoff_date.isoformat()),
                ).fetchone()
                return bool(row)
        except Exception as e:
            logger.warning(f"Error checking for duplicate product '{product_key}': {e}")
            # Return False on error to avoid blocking posts due to DB issues
            return False

    def add_posted_product(self, product_key: str) -> bool:
        """
        Record that a product has been posted.

        Args:
            product_key: Normalized product key

        Returns:
            True if successfully recorded, False otherwise
        """
        try:
            with self.connection:
                self.cursor.execute(
                    "INSERT INTO posted_products (product_key, posted_at) VALUES (?, ?)",
                    (product_key, datetime.datetime.utcnow().isoformat()),
                )
                return True
        except Exception as e:
            logger.warning(f"Error recording posted product '{product_key}': {e}")
            return False

    def get_recent_posted_products(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recently posted products for debugging/monitoring.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of posted products with keys and timestamps
        """
        try:
            with self.connection:
                rows = self.cursor.execute(
                    """
                    SELECT product_key, posted_at
                    FROM posted_products
                    ORDER BY posted_at DESC
                    LIMIT ?
                """,
                    (limit,),
                ).fetchall()
                return [
                    {"product_key": row["product_key"], "posted_at": row["posted_at"]}
                    for row in rows
                ]
        except Exception as e:
            logger.warning(f"Error getting recent posted products: {e}")
            return []

    def cleanup_old_posted_products(self, days_to_keep: int = 30) -> int:
        """
        Remove old posted product records to keep the table size manageable.

        Args:
            days_to_keep: Number of days of history to keep

        Returns:
            Number of records deleted
        """
        try:
            with self.connection:
                cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days_to_keep)
                cursor = self.cursor.execute(
                    "DELETE FROM posted_products WHERE posted_at < ?",
                    (cutoff_date.isoformat(),),
                )
                count = cursor.rowcount
                logger.info(f"Cleaned up {count} old posted product records")
                return count
        except Exception as e:
            logger.warning(f"Error cleaning up old posted products: {e}")
            return 0


# Глобальный экземпляр базы данных для асинхронных функций
_db_instance: Optional[Database] = None


def get_db_instance() -> Database:
    """Получить или создать глобальный экземпляр базы данных"""
    global _db_instance
    if _db_instance is None:
        import config

        _db_instance = Database(
            config.DB_FILE if hasattr(config, "DB_FILE") else "bot_database.db"
        )
    return _db_instance


# ==========================================
# DEPRECATED: Fake async wrappers
# ==========================================
# THESE WRAPPERS ARE DEPRECATED AND DANGEROUS!
# They call blocking sync methods from async context → event loop blocks!
# 
# MIGRATION: Use database_async.py instead:
#   from database_async import get_async_db
#   db = await get_async_db()
#   await db.add_user(...)
# ==========================================

async def add_user(
    user_id: int, username: str = None, first_name: str = None, last_name: str = None
) -> None:
    """
    DEPRECATED: Fake async wrapper - calls blocking sync method!
    Use database_async.py instead for true async operations.
    """
    import warnings
    warnings.warn(
        "add_user() is a fake async wrapper (blocks event loop). "
        "Migrate to database_async.py for true async.",
        DeprecationWarning,
        stacklevel=2
    )
    db = get_db_instance()
    db.add_user(user_id, username, first_name, last_name)


async def get_user_stats(user_id: int) -> Optional[Dict[str, Any]]:
    """
    DEPRECATED: Fake async wrapper - calls blocking sync method!
    Use database_async.py instead for true async operations.
    """
    import warnings
    warnings.warn(
        "get_user_stats() is a fake async wrapper (blocks event loop). "
        "Migrate to database_async.py for true async.",
        DeprecationWarning,
        stacklevel=2
    )
    db = get_db_instance()
    return db.get_user_stats(user_id)


async def has_been_posted_recently(
    product_key: str, days_to_check: int = 7
) -> bool:
    """
    DEPRECATED: Fake async wrapper - calls blocking sync method!
    Use database_async.py instead for true async operations.
    """
    import warnings
    warnings.warn(
        "has_been_posted_recently() is a fake async wrapper (blocks event loop). "
        "Migrate to database_async.py for true async.",
        DeprecationWarning,
        stacklevel=2
    )
    db = get_db_instance()
    return db.has_been_posted_recently(product_key, days_to_check)


async def add_posted_product(product_key: str) -> bool:
    """
    DEPRECATED: Fake async wrapper - calls blocking sync method!
    Use database_async.py instead for true async operations.
    """
    import warnings
    warnings.warn(
        "add_posted_product() is a fake async wrapper (blocks event loop). "
        "Migrate to database_async.py for true async.",
        DeprecationWarning,
        stacklevel=2
    )
    db = get_db_instance()
    return db.add_posted_product(product_key)


async def init_db():
    """
    DEPRECATED: Fake async wrapper - calls blocking sync method!
    Use database_async.get_async_db() instead.
    """
    import warnings
    warnings.warn(
        "init_db() is a fake async wrapper (blocks event loop). "
        "Use: db = await get_async_db() from database_async.py",
        DeprecationWarning,
        stacklevel=2
    )
    db = get_db_instance()
    logger.info("База данных инициализирована (WARNING: using deprecated sync wrapper)")
