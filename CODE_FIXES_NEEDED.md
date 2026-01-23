# Рекомендуемые исправления кода

Список потенциальных проблем в коде и рекомендации по их исправлению.

---

## 🔴 КРИТИЧНЫЕ ИСПРАВЛЕНИЯ

### 1. Исправить обработку сигналов в main.py

**Файл**: `src/main.py:402-407`

**Проблема**:
```python
def signal_handler(sig, frame):
    logger.info("Received shutdown signal")
    asyncio.create_task(system.stop())  # ❌ Не работает вне event loop
```

**Решение**:
```python
# Замените функцию main() на:
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Offline Face Access Control System')
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Path to configuration file (YAML)'
    )
    parser.add_argument(
        '--export-logs',
        type=str,
        help='Export audit logs to JSON file'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('face_access.log')
        ]
    )

    # Load config
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Handle export logs command
    if args.export_logs:
        export_logs(config.database.path, args.export_logs)
        return

    # Create system
    system = FaceAccessSystem(config)

    # ✅ ИСПРАВЛЕННЫЙ КОД: Правильная обработка сигналов
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        system.running = False
        # Планируем остановку в event loop
        if loop.is_running():
            loop.create_task(system.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run async main loop
    try:
        loop.run_until_complete(system.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        loop.run_until_complete(system.stop())
    except Exception as e:
        logger.error(f"System error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        loop.close()
```

---

### 2. Улучшить обработку импортов

**Файл**: `src/main.py:16-28`

**Проблема**: Относительные импорты могут не работать при разных способах запуска.

**Решение 1** (минимальное изменение): Добавить try-except:
```python
import sys
from pathlib import Path

# Добавить src в путь если запускается напрямую
if __name__ == '__main__':
    src_path = Path(__file__).parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

try:
    from config import load_config, SystemConfig
    from db import Database
    # ... остальные импорты
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("Make sure to run from project root or install package with 'pip install -e .'")
    sys.exit(1)
```

**Решение 2** (правильное): Использовать явные относительные импорты:
```python
# В начале src/main.py
from .config import load_config, SystemConfig
from .db import Database
from .camera.usb_camera import USBCamera
from .camera.rtsp_camera import RTSPCamera
from .camera.base import CameraBase
from .face.detector import FaceDetector
from .face.align import FaceAligner
from .face.embedder_onnx import FaceEmbedder
from .face.matcher import FaceMatcher
from .face.quality import FaceQualityChecker
from .access_control import AccessController
from .lock import LockController
from .ble_server import BLEProtocol, BLEServer
```

И запускать как модуль:
```bash
python -m src.main --config config/usb_config.yaml
```

---

## 🟡 РЕКОМЕНДУЕМЫЕ УЛУЧШЕНИЯ

### 3. Добавить проверку Python версии

**Файл**: `src/main.py` (в начале функции main)

**Добавить**:
```python
def main():
    """Main entry point."""
    # Проверка Python версии
    import sys
    if sys.version_info < (3, 10):
        print(f"ERROR: Python 3.10+ required, but {sys.version_info.major}.{sys.version_info.minor} found")
        print("Please upgrade Python or use a newer Raspberry Pi OS version")
        sys.exit(1)

    # Остальной код main()...
```

---

### 4. Улучшить обработку ошибок при инициализации

**Файл**: `src/main.py:36-88`

**Добавить**:
```python
def __init__(self, config: SystemConfig):
    """
    Initialize system.

    Args:
        config: System configuration
    """
    self.config = config
    self.running = False

    # Initialize components
    logger.info("Initializing Face Access Control System...")

    try:
        self.db = Database(config.database.path)
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    try:
        self.camera = self._init_camera()
    except Exception as e:
        logger.error(f"Failed to initialize camera: {e}")
        raise

    try:
        self.detector = FaceDetector(
            detector_type=config.face.detector_type,
            scale_factor=config.face.detector_scale_factor,
            min_neighbors=config.face.detector_min_neighbors,
            min_face_size=config.face.detector_min_face_size
        )
    except Exception as e:
        logger.error(f"Failed to initialize face detector: {e}")
        raise

    # ... аналогично для остальных компонентов

    # Явная проверка ONNX модели
    try:
        from pathlib import Path
        model_path = Path(config.face.onnx_model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"ONNX model not found: {model_path}\n"
                f"Please download InsightFace model and place it in models/ directory.\n"
                f"See TODO_USER.md for instructions."
            )

        self.embedder = FaceEmbedder(
            model_path=config.face.onnx_model_path,
            embedding_dim=config.face.embedding_dim
        )
    except Exception as e:
        logger.error(f"Failed to initialize face embedder: {e}")
        raise

    logger.info("System initialized successfully")
```

---

### 5. Добавить валидацию конфигурации

**Файл**: `src/config.py:91-193`

**Добавить в конец load_config()**:
```python
def load_config(config_path: str) -> SystemConfig:
    """Load configuration from YAML file."""
    # ... существующий код загрузки ...

    # Создаем конфиг
    config = SystemConfig(
        camera=camera,
        face=face,
        ble=ble,
        access=access,
        lock=lock,
        database=database,
        log_level=data.get('log_level', 'INFO')
    )

    # ✅ НОВЫЙ КОД: Валидация конфигурации
    _validate_config(config)

    return config


def _validate_config(config: SystemConfig):
    """
    Validate configuration for common errors.

    Raises:
        ValueError: If configuration is invalid
    """
    from pathlib import Path

    # Проверка модели
    model_path = Path(config.face.onnx_model_path)
    if not model_path.exists():
        raise ValueError(
            f"ONNX model not found: {model_path}\n"
            f"Download InsightFace model from: https://github.com/deepinsight/insightface\n"
            f"Place the .onnx file in models/ directory and update config"
        )

    # Проверка секрета
    if config.ble.hmac_enabled:
        if not config.ble.shared_secret:
            raise ValueError("BLE shared_secret is required when hmac_enabled=true")

        if config.ble.shared_secret == "change_this_secret_key_in_production":
            logger.warning("⚠️  WARNING: Using default shared_secret! Change it in production!")
            logger.warning("   Generate new secret: python3 -c \"import os; print(os.urandom(32).hex())\"")

    # Проверка типа камеры
    if config.camera.type not in ['usb', 'rtsp']:
        raise ValueError(f"Invalid camera type: {config.camera.type}. Must be 'usb' or 'rtsp'")

    if config.camera.type == 'rtsp' and not config.camera.rtsp_url:
        raise ValueError("rtsp_url is required when camera.type='rtsp'")

    # Проверка директорий
    db_dir = Path(config.database.path).parent
    if not db_dir.exists():
        logger.info(f"Creating database directory: {db_dir}")
        db_dir.mkdir(parents=True, exist_ok=True)

    logger.info("✅ Configuration validated successfully")
```

---

### 6. Добавить graceful shutdown

**Файл**: `src/main.py:305-330`

**Улучшить метод run()**:
```python
async def run(self):
    """Run the system."""
    self.running = True

    # Register BLE callbacks
    # Note: In full implementation, these would be wired to BLE characteristics

    # Start tasks
    tasks = [
        asyncio.create_task(self.recognition_loop(), name="recognition"),
        asyncio.create_task(self.ble_server.start(), name="ble_server")
    ]

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        logger.info("System shutting down")
    except Exception as e:
        logger.error(f"System error in main loop: {e}", exc_info=True)
    finally:
        # ✅ НОВЫЙ КОД: Корректная остановка
        logger.info("Cleaning up...")

        # Отменить все задачи
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Закрыть ресурсы
        if hasattr(self, 'camera') and self.camera:
            self.camera.release()

        if hasattr(self, 'lock') and self.lock:
            self.lock.cleanup()

        if hasattr(self, 'db') and self.db:
            self.db.close()

        logger.info("Cleanup complete")
```

---

## 🟢 ДОПОЛНИТЕЛЬНЫЕ УЛУЧШЕНИЯ

### 7. Добавить health check endpoint (опционально)

**Файл**: Новый файл `src/health.py`

```python
"""Health check endpoint for monitoring."""
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


class HealthChecker:
    """System health checker."""

    def __init__(self, system):
        self.system = system
        self.start_time = datetime.now()

    def get_status(self) -> Dict[str, Any]:
        """Get system health status."""
        return {
            'status': 'healthy' if self.system.running else 'stopped',
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'camera_active': self.system.camera is not None,
            'db_connected': self.system.db is not None,
            'timestamp': datetime.now().isoformat()
        }
```

---

### 8. Добавить rate limiting для логов

**Файл**: `src/main.py:240-296`

**Проблема**: При постоянном отказе в доступе логи могут быстро расти.

**Решение**: Добавить подавление повторяющихся сообщений:
```python
# В начале класса FaceAccessSystem
class FaceAccessSystem:
    def __init__(self, config: SystemConfig):
        # ... существующий код ...

        # ✅ НОВЫЙ КОД: Кэш для подавления повторяющихся логов
        self._last_log_message = None
        self._log_repeat_count = 0
        self._max_log_repeats = 5

# В recognition_loop:
if granted:
    logger.info(f"Access GRANTED: {employee_id} ({display_name}) - score: {score:.3f}")
    self.lock.unlock()
    self._last_log_message = None
    self._log_repeat_count = 0
else:
    # ✅ НОВЫЙ КОД: Подавление повторяющихся отказов
    message = f"Access DENIED: {reason} - score: {score:.3f}"
    if message == self._last_log_message:
        self._log_repeat_count += 1
        if self._log_repeat_count == self._max_log_repeats:
            logger.info(f"[Suppressing repeated denials...]")
    else:
        logger.info(message)
        self._last_log_message = message
        self._log_repeat_count = 0
```

---

## 📝 ПРИОРИТЕТЫ ИСПРАВЛЕНИЙ

### Критичные (сделать перед production):
1. ✅ Исправить обработку сигналов (Исправление #1)
2. ✅ Добавить валидацию конфигурации (Исправление #5)
3. ✅ Улучшить обработку ошибок при инициализации (Исправление #4)

### Рекомендуемые (для стабильности):
4. ✅ Улучшить обработку импортов (Исправление #2)
5. ✅ Добавить проверку Python версии (Исправление #3)
6. ✅ Добавить graceful shutdown (Исправление #6)

### Опциональные (для удобства):
7. Rate limiting для логов (Исправление #8)
8. Health check endpoint (Исправление #7)

---

## 🔧 КАК ПРИМЕНИТЬ ИСПРАВЛЕНИЯ

### Вариант 1: Автоматический патч (рекомендуется)

Создайте файл `patches/critical_fixes.patch` и примените:
```bash
cd /home/pi/rp3_face_access
patch -p1 < patches/critical_fixes.patch
```

### Вариант 2: Ручное редактирование

Откройте каждый файл и внесите изменения согласно инструкциям выше:
```bash
nano src/main.py
nano src/config.py
# и т.д.
```

### Вариант 3: Создать новую ветку (для Git)

```bash
git checkout -b deployment-fixes
# Внести изменения
git commit -am "Apply deployment fixes"
git checkout main
git merge deployment-fixes
```

---

## ✅ ПРОВЕРКА ПОСЛЕ ИСПРАВЛЕНИЙ

```bash
# Запустите тесты
python -m pytest tests/ -v

# Запустите систему в DEBUG режиме
python src/main.py --config config/my_config.yaml --log-level DEBUG

# Проверьте логи на ошибки
tail -100 face_access.log | grep ERROR
```

---

**Версия**: 1.0
**Дата**: 2026-01-24
**Статус**: Рекомендации к внедрению
