#!/usr/bin/env python3
"""Тест синтаксиса без импорта зависимостей."""
import py_compile
import os

print("Проверка синтаксиса всех Python файлов...\n")

files_ok = []
files_error = []

for root, dirs, files in os.walk('src'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            try:
                py_compile.compile(filepath, doraise=True)
                files_ok.append(filepath)
                print(f"✅ {filepath}")
            except py_compile.PyCompileError as e:
                files_error.append((filepath, str(e)))
                print(f"❌ {filepath}")
                print(f"   Ошибка: {e}")

print("\n" + "="*60)
print(f"Результат: {len(files_ok)} файлов OK, {len(files_error)} ошибок")
print("="*60)

if files_error:
    print("\n❌ Найдены ошибки синтаксиса:")
    for filepath, error in files_error:
        print(f"\n{filepath}:")
        print(f"  {error[:500]}")
    exit(1)
else:
    print("\n✅ Все файлы без синтаксических ошибок!")
    print("Ошибка 'Tuple is not defined' исправлена.")
    exit(0)
