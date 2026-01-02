#!/usr/bin/env python3
"""
Скрипт для запуска Redis локально для тестирования продакшена
"""

import subprocess
import sys
import time
import redis
import os

def check_redis_available():
    """Проверяет доступность Redis"""
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        return True
    except redis.ConnectionError:
        return False

def start_redis_docker():
    """Запускает Redis через Docker"""
    print("Starting Redis via Docker...")

    try:
        # Проверяем, есть ли уже контейнер
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=redis_test", "--format", "{{.Names}}"],
            capture_output=True, text=True
        )

        if "redis_test" in result.stdout:
            print("Redis container already exists, starting it...")
            subprocess.run(["docker", "start", "redis_test"])
        else:
            print("Creating new Redis container...")
            subprocess.run([
                "docker", "run", "-d",
                "--name", "redis_test",
                "-p", "6379:6379",
                "redis:7-alpine",
                "redis-server", "--appendonly", "yes"
            ])

        # Ждем запуска
        print("Waiting for Redis to start...")
        time.sleep(3)

        return True

    except FileNotFoundError:
        print("Docker not found. Please install Docker or run Redis manually.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Failed to start Redis: {e}")
        return False

def start_redis_local():
    """Пытается запустить Redis локально"""
    print("Trying to start Redis locally...")

    try:
        # Проверяем, установлен ли Redis
        result = subprocess.run(["redis-server", "--version"],
                              capture_output=True, text=True)

        if result.returncode != 0:
            print("Redis not installed locally. Trying Docker...")
            return start_redis_docker()

        # Запускаем Redis сервер
        print("Starting Redis server...")
        process = subprocess.Popen([
            "redis-server",
            "--port", "6379",
            "--daemonize", "yes",
            "--appendonly", "yes",
            "--dir", "./redis_data"
        ])

        time.sleep(2)

        if process.poll() is None:  # Процесс еще работает
            print("Redis started successfully")
            return True
        else:
            print("Failed to start Redis locally, trying Docker...")
            return start_redis_docker()

    except FileNotFoundError:
        print("Redis not found locally, trying Docker...")
        return start_redis_docker()
    except Exception as e:
        print(f"Error starting Redis locally: {e}")
        return start_redis_docker()

def test_redis_connection():
    """Тестирует подключение к Redis"""
    print("Testing Redis connection...")

    try:
        r = redis.Redis(host='localhost', port=6379, db=0)

        # Тест ping
        if r.ping():
            print("[OK] Redis ping successful")

            # Тест записи/чтения
            r.set('test_key', 'test_value')
            value = r.get('test_key')
            if value == b'test_value':
                print("[OK] Redis read/write test successful")
                r.delete('test_key')
                return True
            else:
                print("[FAIL] Redis read/write test failed")
                return False
        else:
            print("[FAIL] Redis ping failed")
            return False

    except Exception as e:
        print(f"[FAIL] Redis connection test failed: {e}")
        return False

def stop_redis():
    """Останавливает Redis"""
    print("Stopping Redis...")

    try:
        # Останавливаем Docker контейнер
        subprocess.run(["docker", "stop", "redis_test"],
                      capture_output=True)

        # Также пытаемся остановить локальный Redis
        subprocess.run(["pkill", "redis-server"],
                      capture_output=True)

        print("Redis stopped")
    except Exception as e:
        print(f"Error stopping Redis: {e}")

def main():
    """Основная функция"""
    print("Redis Setup for Production Testing")
    print("=" * 40)

    # Проверяем, не запущен ли уже Redis
    if check_redis_available():
        print("[OK] Redis is already running")
        if test_redis_connection():
            print("[OK] Redis is ready for production testing")
            return True
        else:
            print("[FAIL] Redis connection test failed")
            return False

    # Пытаемся запустить Redis
    print("Redis not running, attempting to start...")

    if start_redis_local():
        if test_redis_connection():
            print("\n[SUCCESS] Redis is ready for production testing!")
            print("\nTo use in production mode:")
            print("1. Set ENVIRONMENT=prod in your .env file")
            print("2. Set USE_REDIS=true")
            print("3. Run your bot with Redis support")
            print("\nTo stop Redis: python start_redis_local.py --stop")
            return True
        else:
            print("[FAIL] Failed to verify Redis functionality")
            return False
    else:
        print("[FAIL] Failed to start Redis")
        print("\nPlease install Redis or Docker and try again.")
        print("Alternative: run Redis manually with 'redis-server'")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stop":
        stop_redis()
    else:
        success = main()
        sys.exit(0 if success else 1)
