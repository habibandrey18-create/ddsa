# run_tests.py
"""Запуск всех тестов с генерацией отчетов"""
import unittest
import sys
import os
import json
from datetime import datetime
from io import StringIO

# Получаем корневую директорию проекта
root_dir = os.path.dirname(os.path.abspath(__file__))
# Папка с тестами: tests\ (в корне проекта)
tests_dir = os.path.join(root_dir, "tests")

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, root_dir)

# Папка для отчетов
reports_dir = os.path.join(root_dir, "test_reports")
if not os.path.exists(reports_dir):
    os.makedirs(reports_dir)


class TestReportGenerator:
    """Генератор отчетов о тестах"""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.test_results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "test_details": [],
            "failures": [],
            "errors_list": [],
        }

    def generate_report(self, result):
        """Генерирует отчет о тестах"""
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()

        self.test_results["total_tests"] = result.testsRun
        skipped_count = len(getattr(result, "skipped", []))
        self.test_results["passed"] = (
            result.testsRun - len(result.failures) - len(result.errors) - skipped_count
        )
        self.test_results["failed"] = len(result.failures)
        self.test_results["errors"] = len(result.errors)
        self.test_results["skipped"] = skipped_count
        self.test_results["duration"] = f"{duration:.2f} секунд"
        self.test_results["timestamp"] = self.start_time.strftime("%Y-%m-%d %H:%M:%S")
        self.test_results["was_successful"] = result.wasSuccessful()

        # Детали ошибок
        for test, traceback in result.failures:
            self.test_results["failures"].append(
                {"test": str(test), "traceback": traceback}
            )

        for test, traceback in result.errors:
            self.test_results["errors_list"].append(
                {"test": str(test), "traceback": traceback}
            )

        # Сохраняем отчеты
        self._save_json_report()
        self._save_text_report()
        self._save_html_report()

        return self.test_results

    def _save_json_report(self):
        """Сохраняет JSON отчет"""
        json_file = os.path.join(
            reports_dir, f"test_report_{self.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False)
        print(f"\n✓ JSON отчет сохранен: {json_file}")

    def _save_text_report(self):
        """Сохраняет текстовый отчет"""
        txt_file = os.path.join(
            reports_dir, f"test_report_{self.start_time.strftime('%Y%m%d_%H%M%S')}.txt"
        )
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("ОТЧЕТ О ТЕСТИРОВАНИИ\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Дата и время: {self.test_results['timestamp']}\n")
            f.write(f"Длительность: {self.test_results['duration']}\n")
            f.write(f"Всего тестов: {self.test_results['total_tests']}\n")
            f.write(f"Успешно: {self.test_results['passed']}\n")
            f.write(f"Провалено: {self.test_results['failed']}\n")
            f.write(f"Ошибки: {self.test_results['errors']}\n")
            f.write(f"Пропущено: {self.test_results['skipped']}\n")
            f.write(
                f"Статус: {'✓ УСПЕШНО' if self.test_results['was_successful'] else '✗ ЕСТЬ ОШИБКИ'}\n"
            )
            f.write("\n" + "=" * 80 + "\n\n")

            if self.test_results["failures"]:
                f.write("ПРОВАЛЕННЫЕ ТЕСТЫ:\n")
                f.write("-" * 80 + "\n")
                for i, failure in enumerate(self.test_results["failures"], 1):
                    f.write(f"\n{i}. {failure['test']}\n")
                    f.write(f"{failure['traceback']}\n")
                    f.write("-" * 80 + "\n")

            if self.test_results["errors_list"]:
                f.write("\nОШИБКИ:\n")
                f.write("-" * 80 + "\n")
                for i, error in enumerate(self.test_results["errors_list"], 1):
                    f.write(f"\n{i}. {error['test']}\n")
                    f.write(f"{error['traceback']}\n")
                    f.write("-" * 80 + "\n")

        print(f"✓ Текстовый отчет сохранен: {txt_file}")

    def _save_html_report(self):
        """Сохраняет HTML отчет"""
        html_file = os.path.join(
            reports_dir, f"test_report_{self.start_time.strftime('%Y%m%d_%H%M%S')}.html"
        )
        status_color = "#28a745" if self.test_results["was_successful"] else "#dc3545"
        status_text = (
            "УСПЕШНО" if self.test_results["was_successful"] else "ЕСТЬ ОШИБКИ"
        )

        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчет о тестировании</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid {status_color}; padding-bottom: 10px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }}
        .stat-card.passed {{ border-left-color: #28a745; }}
        .stat-card.failed {{ border-left-color: #dc3545; }}
        .stat-card.errors {{ border-left-color: #ffc107; }}
        .stat-card h3 {{ margin: 0 0 10px 0; color: #333; }}
        .stat-value {{ font-size: 32px; font-weight: bold; color: #007bff; }}
        .stat-card.passed .stat-value {{ color: #28a745; }}
        .stat-card.failed .stat-value {{ color: #dc3545; }}
        .stat-card.errors .stat-value {{ color: #ffc107; }}
        .status {{ text-align: center; padding: 20px; background: {status_color}; color: white; border-radius: 5px; font-size: 24px; font-weight: bold; margin: 20px 0; }}
        .failure, .error {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .failure h3, .error h3 {{ margin-top: 0; color: #856404; }}
        pre {{ background: #f8f9fa; padding: 10px; border-radius: 5px; overflow-x: auto; font-size: 12px; }}
        .timestamp {{ color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Отчет о тестировании</h1>
        <div class="timestamp">Дата и время: {self.test_results['timestamp']} | Длительность: {self.test_results['duration']}</div>
        
        <div class="status">{status_text}</div>
        
        <div class="summary">
            <div class="stat-card">
                <h3>Всего тестов</h3>
                <div class="stat-value">{self.test_results['total_tests']}</div>
            </div>
            <div class="stat-card passed">
                <h3>Успешно</h3>
                <div class="stat-value">{self.test_results['passed']}</div>
            </div>
            <div class="stat-card failed">
                <h3>Провалено</h3>
                <div class="stat-value">{self.test_results['failed']}</div>
            </div>
            <div class="stat-card errors">
                <h3>Ошибки</h3>
                <div class="stat-value">{self.test_results['errors']}</div>
            </div>
        </div>
"""

        if self.test_results["failures"]:
            html += "<h2>Проваленные тесты</h2>\n"
            for failure in self.test_results["failures"]:
                html += f"""
        <div class="failure">
            <h3>{failure['test']}</h3>
            <pre>{failure['traceback']}</pre>
        </div>
"""

        if self.test_results["errors_list"]:
            html += "<h2>Ошибки</h2>\n"
            for error in self.test_results["errors_list"]:
                html += f"""
        <div class="error">
            <h3>{error['test']}</h3>
            <pre>{error['traceback']}</pre>
        </div>
"""

        html += """
    </div>
</body>
</html>
"""

        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✓ HTML отчет сохранен: {html_file}")


def run_all_tests():
    """Запускает все тесты с генерацией отчетов"""
    report_gen = TestReportGenerator()
    report_gen.start_time = datetime.now()

    print("=" * 80)
    print("ЗАПУСК ТЕСТОВ")
    print("=" * 80)
    print(f"Папка с тестами: {tests_dir}")
    print(f"Папка для отчетов: {reports_dir}")
    print(f"Время начала: {report_gen.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")

    # Находим все тестовые файлы в папке tests
    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir, pattern="test_*.py", top_level_dir=root_dir)

    # Запускаем тесты с выводом в консоль и в буфер
    stream = StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(suite)

    # Выводим результаты
    output = stream.getvalue()
    print(output)

    # Генерируем отчеты
    print("\n" + "=" * 80)
    print("ГЕНЕРАЦИЯ ОТЧЕТОВ")
    print("=" * 80)
    report = report_gen.generate_report(result)

    # Выводим сводку
    print("\n" + "=" * 80)
    print("СВОДКА")
    print("=" * 80)
    print(f"Всего тестов: {report['total_tests']}")
    print(f"Успешно: {report['passed']}")
    print(f"Провалено: {report['failed']}")
    print(f"Ошибки: {report['errors']}")
    print(f"Пропущено: {report['skipped']}")
    print(f"Длительность: {report['duration']}")
    print(f"Статус: {'✓ УСПЕШНО' if report['was_successful'] else '✗ ЕСТЬ ОШИБКИ'}")
    print("=" * 80)

    # Возвращаем код выхода
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)