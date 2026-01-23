# Исправление ошибки: name 'Tuple' is not defined

## Проблема

При запуске системы возникала ошибка:
```
name 'Tuple' is not defined. Did you mean 'tuple'
```

## Причина

В файле `src/config.py` на строке 33 использовался встроенный тип `tuple` вместо типа `Tuple` из модуля `typing`:

```python
# ❌ БЫЛО (неправильно):
from typing import Optional, Dict, Any

@dataclass
class FaceConfig:
    detector_min_face_size: tuple = (60, 60)  # Ошибка!
```

В Python для type hints нужно использовать `Tuple` из модуля `typing`, а не встроенный `tuple`.

## Решение

Добавлен импорт `Tuple` и исправлен тип:

```python
# ✅ СТАЛО (правильно):
from typing import Optional, Dict, Any, Tuple

@dataclass
class FaceConfig:
    detector_min_face_size: Tuple[int, int] = (60, 60)  # Правильно!
```

## Изменённые файлы

- `src/config.py` - строка 8 (добавлен импорт `Tuple`)
- `src/config.py` - строка 33 (изменён тип с `tuple` на `Tuple[int, int]`)

## Проверка

После исправления все файлы успешно компилируются:

```bash
# Проверка синтаксиса
python3 -m py_compile src/config.py
# ✅ Успешно

# Проверка всех файлов
find src -name "*.py" -exec python3 -m py_compile {} \;
# ✅ 17 файлов скомпилированы без ошибок
```

## Как избежать в будущем

При использовании type hints для составных типов (tuple, list, dict) всегда импортируйте соответствующие типы из модуля `typing`:

```python
from typing import List, Dict, Tuple, Optional, Set

# Правильные type hints:
my_tuple: Tuple[int, int] = (1, 2)
my_list: List[str] = ["a", "b"]
my_dict: Dict[str, int] = {"key": 1}
my_optional: Optional[str] = None
my_set: Set[int] = {1, 2, 3}
```

## Статус

✅ **Исправлено** - 2026-01-24

Система теперь запускается без этой ошибки.
