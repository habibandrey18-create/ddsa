"""Analytics service for bot activity visualization"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import io

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, db):
        self.db = db

    def get_daily_stats(self, days: int = 7) -> Dict[str, int]:
        """
        Get post count per day for the last N days.

        Returns:
            Dict with dates as keys and post counts as values
        """
        try:
            stats = {}
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=days - 1)

            # Get all posts within date range
            with self.db.connection:
                rows = self.db.cursor.execute(
                    """
                    SELECT DATE(date_added) as post_date, COUNT(*) as count
                    FROM history
                    WHERE DATE(date_added) >= DATE(?)
                    GROUP BY DATE(date_added)
                    ORDER BY post_date ASC
                """,
                    (start_date.isoformat(),),
                ).fetchall()

                # Fill all dates (including zeros)
                current_date = start_date
                while current_date <= end_date:
                    date_str = current_date.strftime("%Y-%m-%d")
                    stats[date_str] = 0
                    current_date += timedelta(days=1)

                # Update with actual counts
                for row in rows:
                    date_str = row["post_date"]
                    stats[date_str] = row["count"]

                return stats
        except Exception as e:
            logger.exception(f"Error getting daily stats: {e}")
            return {}

    def generate_activity_graph(self, days: int = 7) -> Optional[io.BytesIO]:
        """
        Generate visual activity graph as image.

        Args:
            days: Number of days to include

        Returns:
            BytesIO buffer with PNG image, or None if failed
        """
        try:
            # Try using matplotlib for beautiful graphs
            try:
                import matplotlib

                matplotlib.use("Agg")  # Non-interactive backend
                import matplotlib.pyplot as plt
                import matplotlib.dates as mdates
                from datetime import datetime

                stats = self.get_daily_stats(days)
                if not stats:
                    return None

                # Prepare data
                dates = [datetime.strptime(d, "%Y-%m-%d") for d in sorted(stats.keys())]
                counts = [stats[d] for d in sorted(stats.keys())]

                # Create figure
                fig, ax = plt.subplots(figsize=(10, 6), facecolor="white")

                # Plot bar chart
                bars = ax.bar(
                    dates,
                    counts,
                    color="#2196F3",
                    alpha=0.8,
                    edgecolor="#1976D2",
                    linewidth=1.5,
                )

                # Customize
                ax.set_xlabel("Дата", fontsize=12, fontweight="bold")
                ax.set_ylabel("Количество публикаций", fontsize=12, fontweight="bold")
                ax.set_title(
                    f"Активность бота за последние {days} дней",
                    fontsize=14,
                    fontweight="bold",
                    pad=20,
                )
                ax.grid(axis="y", alpha=0.3, linestyle="--")

                # Format x-axis
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
                plt.xticks(rotation=45, ha="right")

                # Add value labels on bars
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2.0,
                            height,
                            f"{int(height)}",
                            ha="center",
                            va="bottom",
                            fontweight="bold",
                            fontsize=10,
                        )

                # Tight layout
                plt.tight_layout()

                # Save to buffer
                buffer = io.BytesIO()
                plt.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
                buffer.seek(0)
                plt.close(fig)

                logger.info(f"Generated activity graph for {days} days")
                return buffer

            except ImportError:
                # Fallback: ASCII chart
                logger.info("matplotlib not available, using ASCII chart")
                return self._generate_ascii_chart(days)

        except Exception as e:
            logger.exception(f"Error generating activity graph: {e}")
            return None

    def _generate_ascii_chart(self, days: int = 7) -> Optional[io.BytesIO]:
        """
        Generate ASCII-based chart as image using PIL.
        Fallback when matplotlib is not available.
        """
        try:
            from PIL import Image, ImageDraw, ImageFont

            stats = self.get_daily_stats(days)
            if not stats:
                return None

            # Prepare data
            dates = sorted(stats.keys())
            counts = [stats[d] for d in dates]
            max_count = max(counts) if counts else 1

            # Image dimensions
            width = 800
            height = 400
            margin = 60

            # Create image
            img = Image.new("RGB", (width, height), color="white")
            draw = ImageDraw.Draw(img)

            # Try to load font
            try:
                font = ImageFont.truetype("arial.ttf", 14)
                font_small = ImageFont.truetype("arial.ttf", 12)
            except:
                font = ImageFont.load_default()
                font_small = ImageFont.load_default()

            # Chart area
            chart_width = width - 2 * margin
            chart_height = height - 2 * margin
            bar_width = chart_width / len(dates) - 10

            # Draw bars
            for i, (date, count) in enumerate(zip(dates, counts)):
                if max_count > 0:
                    bar_height = (count / max_count) * chart_height
                else:
                    bar_height = 0

                x = margin + i * (bar_width + 10)
                y = height - margin - bar_height

                # Draw bar
                draw.rectangle(
                    [x, y, x + bar_width, height - margin],
                    fill="#2196F3",
                    outline="#1976D2",
                )

                # Draw value
                if count > 0:
                    draw.text(
                        (x + bar_width / 2, y - 15),
                        str(count),
                        fill="black",
                        font=font,
                        anchor="mm",
                    )

                # Draw date
                date_label = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m")
                draw.text(
                    (x + bar_width / 2, height - margin + 15),
                    date_label,
                    fill="black",
                    font=font_small,
                    anchor="mm",
                )

            # Draw axes
            draw.line(
                [margin, height - margin, width - margin, height - margin],
                fill="black",
                width=2,
            )
            draw.line([margin, margin, margin, height - margin], fill="black", width=2)

            # Title
            title = f"Активность за последние {days} дней"
            draw.text((width / 2, 20), title, fill="black", font=font, anchor="mm")

            # Save to buffer
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            logger.info(f"Generated ASCII chart for {days} days")
            return buffer

        except ImportError:
            logger.warning("PIL not available, cannot generate ASCII chart")
            return None
        except Exception as e:
            logger.exception(f"Error generating ASCII chart: {e}")
            return None

    def get_summary_text(self) -> str:
        """
        Generate text summary of bot statistics.

        Returns:
            Formatted text with statistics
        """
        try:
            stats = self.db.get_stats()

            # Get daily stats
            daily = self.get_daily_stats(7)
            last_7_days = sum(daily.values())

            # Get hourly stats (last 24h)
            with self.db.connection:
                last_24h = self.db.cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM history
                    WHERE datetime(date_added) >= datetime('now', '-24 hours')
                """
                ).fetchone()["count"]

            text = f"""📊 <b>Статистика бота</b>

📈 <b>Всего опубликовано:</b> {stats.get('published', 0)}
📅 <b>За сегодня:</b> {stats.get('today', 0)}
⏰ <b>За последние 24 часа:</b> {last_24h}
📆 <b>За последние 7 дней:</b> {last_7_days}

📋 <b>Очередь:</b> {stats.get('pending', 0)} товаров
❌ <b>Ошибок:</b> {stats.get('errors', 0)}

<b>Динамика по дням:</b>"""

            # Add daily breakdown
            for date_str in sorted(daily.keys(), reverse=True)[:7]:
                count = daily[date_str]
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m")
                bar = "█" * count if count > 0 else "▪️"
                text += f"\n{formatted_date}: {bar} ({count})"

            return text

        except Exception as e:
            logger.exception(f"Error generating summary: {e}")
            return "❌ Ошибка получения статистики"

    def get_category_stats(self) -> Dict[str, int]:
        """
        Returns stats by category (e.g. from history table).
        Since we don't have a category column, we group by template_type from A/B testing.
        """
        try:
            with self.db.connection:
                # Group by template_type (A/B testing templates)
                cursor = self.db.cursor.execute(
                    """
                    SELECT
                        COALESCE(template_type, 'Без шаблона') as category,
                        COUNT(*) as count
                    FROM history
                    WHERE deleted IS NULL OR deleted = 0
                    GROUP BY template_type
                    ORDER BY count DESC
                """
                )
                rows = cursor.fetchall()

                # Convert to dict
                result = {row[0]: row[1] for row in rows}

                # Add total if no categories
                if not result:
                    total_count = self.db.cursor.execute(
                        "SELECT COUNT(*) FROM history WHERE deleted IS NULL OR deleted = 0"
                    ).fetchone()[0]
                    result = {"Всего": total_count}

                return result

        except Exception as e:
            logger.error(f"Error getting category stats: {e}")
            # Fallback: return basic stats
            try:
                with self.db.connection:
                    total = self.db.cursor.execute(
                        "SELECT COUNT(*) FROM history WHERE deleted IS NULL OR deleted = 0"
                    ).fetchone()[0]
                    return {"Всего": total}
            except Exception:
                return {"Ошибка": 0}

    def get_price_range_stats(self) -> Dict[str, int]:
        """
        Get statistics of products by price ranges.

        Returns:
            Dict with price ranges as keys and counts as values
        """
        try:
            with self.db.connection:
                # Group products by price ranges - use last_price field
                cursor = self.db.cursor.execute(
                    """
                    SELECT
                        CASE
                            WHEN last_price < 1000 THEN 'До 1000 ₽'
                            WHEN last_price >= 1000 AND last_price < 5000 THEN '1000-4999 ₽'
                            WHEN last_price >= 5000 AND last_price < 10000 THEN '5000-9999 ₽'
                            WHEN last_price >= 10000 AND last_price < 20000 THEN '10000-19999 ₽'
                            WHEN last_price >= 20000 THEN '20000+ ₽'
                            ELSE 'Цена не указана'
                        END as price_range,
                        COUNT(*) as count
                    FROM history
                    WHERE last_price IS NOT NULL
                    GROUP BY price_range
                    ORDER BY
                        CASE price_range
                            WHEN 'До 1000 ₽' THEN 1
                            WHEN '1000-4999 ₽' THEN 2
                            WHEN '5000-9999 ₽' THEN 3
                            WHEN '10000-19999 ₽' THEN 4
                            WHEN '20000+ ₽' THEN 5
                            ELSE 6
                        END
                """
                )
                rows = cursor.fetchall()

                # Convert to dict
                result = {row[0]: row[1] for row in rows}

                return result

        except Exception as e:
            logger.error(f"Error getting price range stats: {e}")
            return {"Ошибка": 0}

    def get_error_stats(self) -> Dict[str, int]:
        """
        Get error statistics.

        Returns:
            Dict with error types and counts
        """
        try:
            with self.db.connection:
                # Get total errors
                total_errors = self.db.cursor.execute(
                    "SELECT COUNT(*) FROM error_queue"
                ).fetchone()[0]

                # Get recent errors (last 7 days) - use date_added
                recent_errors = self.db.cursor.execute(
                    """
                    SELECT COUNT(*) FROM error_queue
                    WHERE datetime(date_added) >= datetime('now', '-7 days')
                """
                ).fetchone()[0]

                return {
                    "total_errors": total_errors,
                    "recent_errors": recent_errors,
                }

        except Exception as e:
            logger.error(f"Error getting error stats: {e}")
            return {"total_errors": 0, "recent_errors": 0}

    def get_time_distribution(self, days: int = 7) -> Dict[str, int]:
        """
        Get posting distribution by hour of day.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with hours (0-23) as keys and post counts as values
        """
        try:
            with self.db.connection:
                # Get hourly distribution - remove deleted filter if column doesn't exist
                try:
                    cursor = self.db.cursor.execute(
                        f"""
                        SELECT
                            strftime('%H', date_added) as hour,
                            COUNT(*) as count
                        FROM history
                        WHERE deleted IS NULL OR deleted = 0
                        AND date_added >= datetime('now', '-{days} days')
                        GROUP BY hour
                        ORDER BY hour
                    """
                    )
                except Exception:
                    # Fallback if deleted column doesn't exist
                    cursor = self.db.cursor.execute(
                        f"""
                        SELECT
                            strftime('%H', date_added) as hour,
                            COUNT(*) as count
                        FROM history
                        WHERE date_added >= datetime('now', '-{days} days')
                        GROUP BY hour
                        ORDER BY hour
                    """
                    )

                rows = cursor.fetchall()

                # Initialize all hours with 0
                result = {f"{h:02d}": 0 for h in range(24)}

                # Update with actual counts
                for row in rows:
                    hour_str = row[0]
                    result[hour_str] = row[1]

                return result

        except Exception as e:
            logger.error(f"Error getting time distribution: {e}")
            return {f"{h:02d}": 0 for h in range(24)}

    def get_top_products(self, limit: int = 5) -> List[Dict]:
        """
        Get top products by some metric (views, engagement, etc.).

        Args:
            limit: Maximum number of products to return

        Returns:
            List of product dictionaries with basic info
        """
        try:
            with self.db.connection:
                # Get products with highest view counts (if available)
                try:
                    cursor = self.db.cursor.execute(
                        """
                        SELECT
                            id,
                            url,
                            title,
                            last_price,
                            views_24h,
                            date_added
                        FROM history
                        WHERE (deleted IS NULL OR deleted = 0)
                        AND views_24h IS NOT NULL
                        ORDER BY views_24h DESC
                        LIMIT ?
                    """,
                        (limit,),
                    )
                    rows = cursor.fetchall()

                    # Convert to list of dicts
                    result = []
                    for row in rows:
                        result.append({
                            "id": row[0],
                            "url": row[1],
                            "title": row[2] or "Без названия",
                            "price": f"{row[3]} ₽" if row[3] else "Цена не указана",
                            "views": row[4] or 0,
                            "date_added": row[5],
                        })

                except Exception:
                    # Fallback if views_24h column doesn't exist
                    result = []

                # If no products with views, return recent products
                if not result:
                    try:
                        cursor = self.db.cursor.execute(
                            """
                            SELECT
                                id,
                                url,
                                title,
                                last_price,
                                date_added
                            FROM history
                            WHERE deleted IS NULL OR deleted = 0
                            ORDER BY date_added DESC
                            LIMIT ?
                        """,
                            (limit,),
                        )
                    except Exception:
                        # Fallback if deleted column doesn't exist
                        cursor = self.db.cursor.execute(
                            """
                            SELECT
                                id,
                                url,
                                title,
                                last_price,
                                date_added
                            FROM history
                            ORDER BY date_added DESC
                            LIMIT ?
                        """,
                            (limit,),
                        )

                    rows = cursor.fetchall()

                    for row in rows:
                        result.append({
                            "id": row[0],
                            "url": row[1],
                            "title": row[2] or "Без названия",
                            "price": f"{row[3]} ₽" if row[3] else "Цена не указана",
                            "views": 0,
                            "date_added": row[4],
                        })

                return result

        except Exception as e:
            logger.error(f"Error getting top products: {e}")
            return []
