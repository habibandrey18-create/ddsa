"""
Prompt Generator - генерация промптов для авто-дебага и авто-рефакторинга
"""

from typing import Optional, Literal
from enum import Enum


class PromptMode(Enum):
    """Режимы генерации промптов"""

    DEBUG = "auto-debug"
    REFACTOR = "auto-refactor"


class PromptGenerator:
    """
    Генератор промптов для LLM для авто-дебага и авто-рефакторинга
    """

    DEBUG_PROMPT_TEMPLATE = """Ты — эксперт по Python и асинхронному программированию, специализирующийся на отладке кода.

РЕЖИМ: АВТО-ДЕБАГ

ЗАДАЧА:
Проанализируй предоставленный код и найди все ошибки, потенциальные баги и проблемы.

ИНСТРУКЦИИ:
1. Найди все ошибки:
   - Синтаксические ошибки
   - Логические ошибки
   - Ошибки с неинициализированными переменными
   - Ошибки с None (AttributeError, TypeError)
   - Ошибки обработки исключений
   - Проблемы с асинхронностью (неправильное использование await, asyncio)
   - Race conditions
   - Утечки ресурсов

2. Для каждой найденной ошибки:
   - Укажи точное место (строка, функция)
   - Объясни причину ошибки
   - Опиши, что произойдёт при выполнении
   - Предложи конкретный фикс с кодом

3. Проверь:
   - Все ли переменные инициализированы перед использованием
   - Есть ли проверки на None перед обращением к атрибутам/методам
   - Корректно ли обрабатываются исключения
   - Правильно ли используются async/await
   - Нет ли утечек ресурсов (незакрытые файлы, соединения)

ФОРМАТ ОТВЕТА:
```markdown
## Найденные ошибки

### Ошибка 1: [Название]
**Местоположение:** [файл:строка, функция]
**Тип:** [тип ошибки]
**Описание:** [подробное описание]
**Что произойдёт:** [последствия]
**Исправление:**
```python
# Исправленный код
```

### Ошибка 2: [Название]
...

## Исправленная версия функции

```python
# Полный исправленный код
```

## Список изменений
1. [Описание изменения 1]
2. [Описание изменения 2]
...
```

КОД ДЛЯ АНАЛИЗА:
```python
{code}
```
"""

    REFACTOR_PROMPT_TEMPLATE = """Ты — эксперт по Python и рефакторингу кода, специализирующийся на улучшении качества кода без изменения бизнес-логики.

РЕЖИМ: АВТО-РЕФАКТОРИНГ

ЗАДАЧА:
Улучши предоставленный код, сохранив всю бизнес-логику без изменений.

ИНСТРУКЦИИ:
1. Улучшения кода (без изменения логики):
   - Добавь docstring для функций/классов (если отсутствуют)
   - Добавь type hints (если отсутствуют)
   - Улучши читаемость: переименуй переменные, разбей длинные функции
   - Добавь проверки на None перед обращением к атрибутам
   - Добавь try/except блоки с правильной обработкой ошибок
   - Улучши обработку исключений: логируй оригинальные ошибки
   - Оптимизируй структуру: вынеси повторяющийся код
   - Улучши именование: используй понятные имена переменных/функций

2. НЕ МЕНЯЙ:
   - Бизнес-логику
   - Алгоритмы
   - Возвращаемые значения
   - Поведение функций
   - API интерфейсы

3. Обязательно добавь:
   - Docstring в формате Google style для всех функций
   - Type hints для параметров и возвращаемых значений
   - Проверки на None перед обращением к атрибутам
   - Try/except блоки с логированием ошибок
   - Комментарии для сложных участков кода

4. Следуй принципам:
   - DRY (Don't Repeat Yourself)
   - SOLID
   - PEP 8
   - Читаемость важнее краткости

ФОРМАТ ОТВЕТА:
```markdown
## Улучшенная версия функции

```python
# Полный улучшенный код
```

## Список изменений
1. [Описание улучшения 1]
2. [Описание улучшения 2]
...

## Добавленные docstring
- [Функция 1]: [краткое описание]
- [Функция 2]: [краткое описание]
...

## Добавленные проверки
- [Описание проверки 1]
- [Описание проверки 2]
...

## Добавленные try/except блоки
- [Описание обработки ошибок 1]
- [Описание обработки ошибок 2]
...
```

КОД ДЛЯ АНАЛИЗА:
```python
{code}
```
"""

    @staticmethod
    def generate(
        code: str,
        mode: Literal["auto-debug", "auto-refactor"] = "auto-debug",
        context: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> str:
        """
        Генерирует промпт для LLM

        Args:
            code: Код для анализа (тело функции или diff)
            mode: Режим работы ("auto-debug" или "auto-refactor")
            context: Дополнительный контекст (описание проблемы, требования)
            file_path: Путь к файлу (для контекста)

        Returns:
            Сгенерированный промпт
        """
        if mode == "auto-debug":
            template = PromptGenerator.DEBUG_PROMPT_TEMPLATE
        elif mode == "auto-refactor":
            template = PromptGenerator.REFACTOR_PROMPT_TEMPLATE
        else:
            raise ValueError(
                f"Unknown mode: {mode}. Use 'auto-debug' or 'auto-refactor'"
            )

        # Форматируем промпт
        prompt = template.format(code=code)

        # Добавляем контекст если есть
        if context:
            context_section = f"\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:\n{context}\n"
            prompt = prompt.replace(
                "КОД ДЛЯ АНАЛИЗА:", context_section + "КОД ДЛЯ АНАЛИЗА:"
            )

        # Добавляем путь к файлу если есть
        if file_path:
            file_section = f"\n\nФАЙЛ: {file_path}\n"
            prompt = prompt.replace(
                "КОД ДЛЯ АНАЛИЗА:", file_section + "КОД ДЛЯ АНАЛИЗА:"
            )

        return prompt

    @staticmethod
    def generate_from_diff(
        diff: str,
        mode: Literal["auto-debug", "auto-refactor"] = "auto-debug",
        context: Optional[str] = None,
    ) -> str:
        """
        Генерирует промпт из git diff

        Args:
            diff: Git diff строка
            mode: Режим работы
            context: Дополнительный контекст

        Returns:
            Сгенерированный промпт
        """
        diff_section = f"""
АНАЛИЗИРУЕМЫЕ ИЗМЕНЕНИЯ (git diff):
```
{diff}
```

ПРОБЛЕМА:
Проанализируй изменения в diff и найди потенциальные ошибки, которые могли быть внесены этими изменениями.
"""

        if mode == "auto-debug":
            template = PromptGenerator.DEBUG_PROMPT_TEMPLATE.replace(
                "КОД ДЛЯ АНАЛИЗА:", diff_section + "\nКОД ДЛЯ АНАЛИЗА:"
            )
        else:
            template = PromptGenerator.REFACTOR_PROMPT_TEMPLATE.replace(
                "КОД ДЛЯ АНАЛИЗА:", diff_section + "\nКОД ДЛЯ АНАЛИЗА:"
            )

        if context:
            context_section = f"\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:\n{context}\n"
            template = template.replace(
                "КОД ДЛЯ АНАЛИЗА:", context_section + "КОД ДЛЯ АНАЛИЗА:"
            )

        return template


def generate_prompt(
    code: str,
    mode: Literal["auto-debug", "auto-refactor"] = "auto-debug",
    context: Optional[str] = None,
    file_path: Optional[str] = None,
) -> str:
    """
    Удобная функция для генерации промпта

    Args:
        code: Код для анализа
        mode: Режим работы
        context: Дополнительный контекст
        file_path: Путь к файлу

    Returns:
        Сгенерированный промпт
    """
    return PromptGenerator.generate(code, mode, context, file_path)


def generate_prompt_from_diff(
    diff: str,
    mode: Literal["auto-debug", "auto-refactor"] = "auto-debug",
    context: Optional[str] = None,
) -> str:
    """
    Удобная функция для генерации промпта из diff

    Args:
        diff: Git diff
        mode: Режим работы
        context: Дополнительный контекст

    Returns:
        Сгенерированный промпт
    """
    return PromptGenerator.generate_from_diff(diff, mode, context)
