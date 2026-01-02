# utils/link_gen/link_extraction.py
"""
Link extraction utilities for Yandex Market Link Generator.
Handles CC link extraction from various text sources.
"""
import re
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class LinkExtractionMixin:
    """Mixin class for link extraction utilities."""

    @staticmethod
    def _extract_cc_link(text: str) -> Optional[str]:
        """
        МАКСИМАЛЬНО УЛУЧШЕННОЕ извлечение cc/ ссылки из текста.
        Использует множество паттернов и валидацию для максимальной надежности.
        """
        if not text:
            return None

        # #region agent edit - МАКСИМАЛЬНО УЛУЧШЕННЫЙ ПОИСК: множество паттернов
        # Паттерны для поиска CC ссылок (от более специфичных к более общим)
        patterns = [
            # Полная ссылка с протоколом
            r'https?://market\.yandex\.ru/cc/([A-Za-z0-9_-]+)',
            # Без протокола
            r'market\.yandex\.ru/cc/([A-Za-z0-9_-]+)',
            # Только /cc/ код
            r'/cc/([A-Za-z0-9_-]+)',
            # В JSON строках
            r'"shortUrl"\s*:\s*"([^"]*market\.yandex\.ru/cc/[^"]+)"',
            r'"url"\s*:\s*"([^"]*market\.yandex\.ru/cc/[^"]+)"',
            r'"link"\s*:\s*"([^"]*market\.yandex\.ru/cc/[^"]+)"',
            # В HTML атрибутах
            r'href=["\']([^"\']*market\.yandex\.ru/cc/[^"\']+)["\']',
            r'data-url=["\']([^"\']*market\.yandex\.ru/cc/[^"\']+)["\']',
            r'data-href=["\']([^"\']*market\.yandex\.ru/cc/[^"\']+)["\']',
            # Короткий код (5-20 символов, не число, не _0x)
            r'\b([A-Za-z][A-Za-z0-9_-]{4,19})\b(?=.*market\.yandex\.ru)',
        ]

        found_links = []

        for pattern_str in patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            matches = pattern.findall(text)

            for match in matches:
                # Если match - это уже полная ссылка
                if isinstance(match, str) and 'market.yandex.ru/cc/' in match:
                    cc_code_match = re.search(r'/cc/([A-Za-z0-9_-]+)', match)
                    if cc_code_match:
                        cc_code = cc_code_match.group(1)
                    else:
                        continue
                else:
                    cc_code = match

                # Очистка кода от лишних символов
                cc_code = str(cc_code).split('?')[0].split(',')[0].split('&')[0].split('#')[0].strip()

                # Валидация кода
                if not cc_code:
                    continue

                # Исключаем обфусцированный JavaScript код
                if cc_code.startswith('_0x') or '_0x' in cc_code:
                    continue

                # Исключаем слишком короткие или длинные коды
                if len(cc_code) < 5 or len(cc_code) > 30:
                    continue

                # Исключаем чисто числовые коды (обычно это не CC коды)
                if cc_code.isdigit():
                    continue

                # Исключаем коды, которые выглядят как хеши (слишком длинные и случайные)
                if len(cc_code) > 20 and all(c in '0123456789abcdefABCDEF' for c in cc_code):
                    continue

                # #region agent edit - ИСКЛЮЧАЕМ ЗАРЕЗЕРВИРОВАННЫЕ СЛОВА И ПРОТОКОЛЫ
                # Исключаем зарезервированные слова и протоколы
                invalid_codes = [
                    'https', 'http', 'www', 'market', 'yandex', 'ru', 'com', 'org', 'net',
                    'special', 'originals', 'card', 'product', 'catalog', 'search', 'shop',
                    'seller', 'offer', 'price', 'review', 'rating', 'image', 'photo', 'video',
                    'javascript', 'void', 'null', 'undefined', 'true', 'false', 'function',
                    'object', 'array', 'string', 'number', 'boolean', 'date', 'time',
                    'partner', 'passport', 'auth', 'login', 'register', 'account', 'profile',
                    'settings', 'help', 'support', 'about', 'contact', 'terms', 'privacy',
                    'cookie', 'policy', 'legal', 'faq', 'blog', 'news', 'press', 'careers'
                ]
                if cc_code.lower() in invalid_codes:
                    continue

                # Исключаем коды, которые начинаются с протоколов или доменов
                if cc_code.lower().startswith(('http', 'www', 'ftp', 'file')):
                    continue

                # Исключаем коды, которые содержат точки (обычно это домены)
                if '.' in cc_code:
                    continue

                # Исключаем коды, которые содержат слеши (обычно это пути)
                if '/' in cc_code or '\\' in cc_code:
                    continue

                # Исключаем коды, которые слишком похожи на URL (содержат ://)
                if '://' in text and cc_code in text.split('://')[1] if '://' in text else False:
                    # Проверяем, не является ли это частью URL
                    context_start = max(0, text.find(cc_code) - 50)
                    context_end = min(len(text), text.find(cc_code) + len(cc_code) + 50)
                    context = text[context_start:context_end]
                    if '://' in context or 'http' in context.lower() or 'www' in context.lower():
                        # Это часть URL, пропускаем
                        continue

                # #region agent edit - ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: исключаем коды из других доменов
                # Проверяем контекст вокруг кода - если это часть другого домена, пропускаем
                code_index = text.find(cc_code)
                if code_index >= 0:
                    # Проверяем, что перед кодом нет других доменов
                    before_context = text[max(0, code_index - 30):code_index].lower()
                    if any(domain in before_context for domain in ['partner.', 'passport.', 'auth.', 'login.', 'register.', 'account.', 'profile.']):
                        # Это часть другого домена, пропускаем
                        continue

                    # Проверяем, что после кода нет продолжения URL
                    after_context = text[code_index + len(cc_code):min(len(text), code_index + len(cc_code) + 30)].lower()
                    if any(marker in after_context for marker in ['.market', '.yandex', '.ru', '://', '/auth', '/login']):
                        # Это часть другого URL, пропускаем
                        continue
                # #endregion
                # #endregion

                # Формируем полную ссылку
                full_link = f"https://market.yandex.ru/cc/{cc_code}"

                # Проверяем, что ссылка еще не была найдена
                if full_link not in found_links:
                    found_links.append(full_link)

        # Возвращаем первую найденную ссылку (или самую короткую, если их несколько)
        if found_links:
            # Предпочитаем более короткие коды (обычно это правильные CC коды)
            found_links.sort(key=lambda x: len(x.split('/cc/')[1]) if '/cc/' in x else 999)
            return found_links[0]

        return None
        # #endregion

    def _search_cc_link_recursive(self, data: Any, max_depth: int = 25, current_depth: int = 0, visited: Optional[set] = None) -> Optional[str]:
        """
        Рекурсивный поиск CC ссылки в JSON-подобных структурах.
        """
        if current_depth > max_depth:
            return None

        if visited is None:
            visited = set()

        # Избегаем бесконечной рекурсии для циклических структур
        data_id = id(data)
        if data_id in visited:
            return None
        visited.add(data_id)

        try:
            if isinstance(data, dict):
                # Проверяем ключи, которые могут содержать ссылки
                for key in ['shortUrl', 'url', 'link', 'href', 'data-url', 'data-href']:
                    if key in data and isinstance(data[key], str):
                        link = self._extract_cc_link(data[key])
                        if link:
                            return link

                # Рекурсивно проверяем вложенные объекты
                for value in data.values():
                    link = self._search_cc_link_recursive(value, max_depth, current_depth + 1, visited)
                    if link:
                        return link

            elif isinstance(data, list):
                # Рекурсивно проверяем элементы массива
                for item in data:
                    link = self._search_cc_link_recursive(item, max_depth, current_depth + 1, visited)
                    if link:
                        return link

            elif isinstance(data, str):
                # Проверяем строку напрямую
                return self._extract_cc_link(data)

        except Exception as e:
            logger.debug(f"Error during recursive search at depth {current_depth}: {e}")

        return None
