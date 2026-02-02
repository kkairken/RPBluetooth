#!/usr/bin/env python3
"""
GUI приложение для управления базой данных сотрудников.
Позволяет добавлять, редактировать и удалять сотрудников,
а также загружать фотографии для распознавания лиц.
"""
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageTk
import cv2
import numpy as np
import hashlib
import json

from db import Database
from face.detector import FaceDetector
from face.align import FaceAligner
try:
    from face.embedder_onnx import FaceEmbedder
except ImportError:
    from face.embedder_opencv import FaceEmbedderOpenCV as FaceEmbedder
from face.quality import FaceQualityChecker


# Значения по умолчанию
DEFAULT_DB_PATH = "data/access_control.db"
DEFAULT_MODEL_PATH = "models/insightface_medium.onnx"
SETTINGS_FILE = "data/gui_settings.json"


class EmployeeManagerGUI:
    """Главное окно приложения для управления сотрудниками."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Управление сотрудниками - Face Access Control")
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)

        self.base_dir = Path(__file__).parent.parent

        # Загрузка настроек
        self._load_settings()

        # Инициализация компонентов
        self.db = None
        self.detector = None
        self.aligner = None
        self.embedder = None
        self.quality_checker = None

        # Список фотографий для добавления
        self.selected_photos = []
        self.all_employees = []

        # Создание интерфейса
        self._create_ui()

        # Подключение к БД
        self._connect_db()

    def _load_settings(self):
        """Загрузка сохранённых настроек."""
        settings_path = self.base_dir / SETTINGS_FILE
        self.settings = {
            'db_path': str(self.base_dir / DEFAULT_DB_PATH),
            'model_path': str(self.base_dir / DEFAULT_MODEL_PATH)
        }

        if settings_path.exists():
            try:
                with open(settings_path, 'r') as f:
                    saved = json.load(f)
                    self.settings.update(saved)
            except Exception:
                pass

    def _save_settings(self):
        """Сохранение настроек."""
        settings_path = self.base_dir / SETTINGS_FILE
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(settings_path, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def _connect_db(self):
        """Подключение к базе данных."""
        db_path = Path(self.settings['db_path'])
        db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.db = Database(str(db_path))
            self._refresh_employees()
            self._update_status(f"БД: {db_path.name}")
        except Exception as e:
            messagebox.showerror("Ошибка БД", f"Не удалось подключиться к БД:\n{e}")

    def _init_face_components(self):
        """Инициализация компонентов распознавания лиц."""
        if self.embedder:
            return True  # Уже инициализированы

        model_path = Path(self.settings['model_path'])

        if not model_path.exists():
            result = messagebox.askyesno(
                "Модель не найдена",
                f"ONNX модель не найдена:\n{model_path}\n\n"
                "Выбрать файл модели?"
            )
            if result:
                self._select_model()
                model_path = Path(self.settings['model_path'])
            if not model_path.exists():
                return False

        try:
            self.detector = FaceDetector(
                detector_type='opencv_haar',
                scale_factor=1.1,
                min_neighbors=5,
                min_face_size=(60, 60)
            )
            self.aligner = FaceAligner(output_size=(112, 112))
            self.embedder = FaceEmbedder(
                model_path=str(model_path),
                embedding_dim=512
            )
            self.quality_checker = FaceQualityChecker(
                min_face_size=80,
                blur_threshold=100.0
            )
            return True
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка инициализации компонентов:\n{e}")
            return False

    def _create_ui(self):
        """Создание пользовательского интерфейса."""
        # Меню
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Выбрать базу данных...", command=self._select_db)
        file_menu.add_command(label="Выбрать ONNX модель...", command=self._select_model)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit)

        # Основной контейнер
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Левая панель - список сотрудников
        left_frame = ttk.LabelFrame(main_frame, text="Сотрудники", padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # Поиск
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self._filter_employees())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Таблица сотрудников
        columns = ('id', 'name', 'status', 'access_start', 'access_end', 'embeddings')
        self.tree = ttk.Treeview(left_frame, columns=columns, show='headings', height=20)

        self.tree.heading('id', text='ID')
        self.tree.heading('name', text='Имя')
        self.tree.heading('status', text='Статус')
        self.tree.heading('access_start', text='Начало доступа')
        self.tree.heading('access_end', text='Конец доступа')
        self.tree.heading('embeddings', text='Фото')

        self.tree.column('id', width=100)
        self.tree.column('name', width=150)
        self.tree.column('status', width=80)
        self.tree.column('access_start', width=120)
        self.tree.column('access_end', width=120)
        self.tree.column('embeddings', width=50)

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<<TreeviewSelect>>', self._on_employee_select)

        # Правая панель - форма редактирования
        right_frame = ttk.Frame(main_frame, width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_frame.pack_propagate(False)

        # Форма добавления/редактирования
        form_frame = ttk.LabelFrame(right_frame, text="Данные сотрудника", padding="10")
        form_frame.pack(fill=tk.X, pady=(0, 10))

        # ID сотрудника
        ttk.Label(form_frame, text="ID сотрудника:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.id_var = tk.StringVar()
        self.id_entry = ttk.Entry(form_frame, textvariable=self.id_var, width=30)
        self.id_entry.grid(row=0, column=1, sticky=tk.EW, pady=2)

        # Имя
        ttk.Label(form_frame, text="Имя:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.name_var, width=30).grid(row=1, column=1, sticky=tk.EW, pady=2)

        # Начало доступа
        ttk.Label(form_frame, text="Начало доступа:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.start_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(form_frame, textvariable=self.start_var, width=30).grid(row=2, column=1, sticky=tk.EW, pady=2)

        # Конец доступа
        ttk.Label(form_frame, text="Конец доступа:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.end_var = tk.StringVar(value=datetime(datetime.now().year + 1, 12, 31).strftime("%Y-%m-%d"))
        ttk.Entry(form_frame, textvariable=self.end_var, width=30).grid(row=3, column=1, sticky=tk.EW, pady=2)

        # Статус
        ttk.Label(form_frame, text="Активен:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form_frame, variable=self.active_var).grid(row=4, column=1, sticky=tk.W, pady=2)

        form_frame.columnconfigure(1, weight=1)

        # Фотографии
        photo_frame = ttk.LabelFrame(right_frame, text="Фотографии", padding="10")
        photo_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Список фото
        self.photo_listbox = tk.Listbox(photo_frame, height=6)
        self.photo_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.photo_listbox.bind('<<ListboxSelect>>', self._on_photo_select)

        # Превью фото
        self.preview_label = ttk.Label(photo_frame, text="Выберите фото для превью")
        self.preview_label.pack(pady=5)

        # Кнопки для фото
        photo_btn_frame = ttk.Frame(photo_frame)
        photo_btn_frame.pack(fill=tk.X)

        ttk.Button(photo_btn_frame, text="Добавить фото", command=self._add_photos).pack(side=tk.LEFT, padx=2)
        ttk.Button(photo_btn_frame, text="Удалить фото", command=self._remove_photo).pack(side=tk.LEFT, padx=2)
        ttk.Button(photo_btn_frame, text="Очистить все", command=self._clear_photos).pack(side=tk.LEFT, padx=2)

        # Кнопки действий
        action_frame = ttk.Frame(right_frame)
        action_frame.pack(fill=tk.X)

        ttk.Button(action_frame, text="Новый", command=self._new_employee).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Сохранить", command=self._save_employee).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Удалить", command=self._delete_employee).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Деактивировать", command=self._deactivate_employee).pack(side=tk.LEFT, padx=2)

        # Нижняя панель - статус и логи
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)

        # Статистика
        self.status_label = ttk.Label(bottom_frame, text="")
        self.status_label.pack(side=tk.LEFT)

        # Кнопки
        ttk.Button(bottom_frame, text="Обновить", command=self._refresh_employees).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bottom_frame, text="Журнал событий", command=self._show_audit_log).pack(side=tk.RIGHT, padx=2)

    def _select_db(self):
        """Выбор файла базы данных."""
        filetypes = [("SQLite Database", "*.db"), ("Все файлы", "*.*")]
        path = filedialog.askopenfilename(
            title="Выберите базу данных",
            filetypes=filetypes,
            initialdir=self.base_dir / "data"
        )
        if path:
            self.settings['db_path'] = path
            self._save_settings()
            self._connect_db()

    def _select_model(self):
        """Выбор ONNX модели."""
        filetypes = [("ONNX Model", "*.onnx"), ("Все файлы", "*.*")]
        path = filedialog.askopenfilename(
            title="Выберите ONNX модель",
            filetypes=filetypes,
            initialdir=self.base_dir / "models"
        )
        if path:
            self.settings['model_path'] = path
            self._save_settings()
            # Сбрасываем компоненты для переинициализации
            self.embedder = None
            self.detector = None

    def _update_status(self, extra: str = ""):
        """Обновление строки статуса."""
        if not self.db:
            self.status_label.config(text="БД не подключена")
            return

        stats = self.db.get_system_status()
        text = (
            f"Всего: {stats['total_employees']} | "
            f"Активных: {stats['active_employees']} | "
            f"Эмбеддингов: {stats['total_embeddings']} | "
            f"Событий за час: {stats['recent_attempts_1h']}"
        )
        if extra:
            text = f"{extra} | {text}"
        self.status_label.config(text=text)

    def _refresh_employees(self):
        """Обновление списка сотрудников."""
        if not self.db:
            return

        # Очистка таблицы
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Загрузка сотрудников
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT e.employee_id, e.display_name, e.is_active, e.access_start, e.access_end,
                   (SELECT COUNT(*) FROM embeddings WHERE employee_id = e.employee_id) as emb_count
            FROM employees e
            ORDER BY e.display_name
        """)

        self.all_employees = []
        for row in cursor.fetchall():
            emp = {
                'id': row[0],
                'name': row[1] or row[0],
                'active': row[2],
                'start': row[3][:10] if row[3] else '',
                'end': row[4][:10] if row[4] else '',
                'embeddings': row[5]
            }
            self.all_employees.append(emp)

            status = "Активен" if row[2] else "Неактивен"
            self.tree.insert('', tk.END, values=(
                emp['id'], emp['name'], status, emp['start'], emp['end'], emp['embeddings']
            ))

        self._update_status()

    def _filter_employees(self):
        """Фильтрация списка сотрудников."""
        search_text = self.search_var.get().lower()

        for item in self.tree.get_children():
            self.tree.delete(item)

        for emp in self.all_employees:
            if search_text in emp['id'].lower() or search_text in emp['name'].lower():
                status = "Активен" if emp['active'] else "Неактивен"
                self.tree.insert('', tk.END, values=(
                    emp['id'], emp['name'], status, emp['start'], emp['end'], emp['embeddings']
                ))

    def _on_employee_select(self, event):
        """Обработка выбора сотрудника в списке."""
        if not self.db:
            return

        selection = self.tree.selection()
        if not selection:
            return

        item = self.tree.item(selection[0])
        values = item['values']

        employee_id = values[0]
        employee = self.db.get_employee(employee_id)

        if employee:
            self.id_var.set(employee['employee_id'])
            self.name_var.set(employee['display_name'] or '')
            self.start_var.set(employee['access_start'][:10] if employee['access_start'] else '')
            self.end_var.set(employee['access_end'][:10] if employee['access_end'] else '')
            self.active_var.set(bool(employee['is_active']))

            # Блокируем редактирование ID для существующего сотрудника
            self.id_entry.config(state='disabled')

            # Очищаем выбранные фото
            self._clear_photos()

    def _on_photo_select(self, event):
        """Обработка выбора фото в списке."""
        selection = self.photo_listbox.curselection()
        if not selection:
            return

        photo_path = self.selected_photos[selection[0]]
        self._show_preview(photo_path)

    def _show_preview(self, photo_path: str):
        """Показ превью фотографии."""
        try:
            image = Image.open(photo_path)
            image.thumbnail((200, 200))
            photo = ImageTk.PhotoImage(image)
            self.preview_label.config(image=photo, text="")
            self.preview_label.image = photo
        except Exception as e:
            self.preview_label.config(image='', text=f"Ошибка: {e}")

    def _add_photos(self):
        """Добавление фотографий."""
        filetypes = [
            ("Изображения", "*.jpg *.jpeg *.png *.bmp"),
            ("JPEG", "*.jpg *.jpeg"),
            ("PNG", "*.png"),
            ("Все файлы", "*.*")
        ]

        files = filedialog.askopenfilenames(
            title="Выберите фотографии",
            filetypes=filetypes
        )

        for f in files:
            if f not in self.selected_photos:
                self.selected_photos.append(f)
                self.photo_listbox.insert(tk.END, Path(f).name)

    def _remove_photo(self):
        """Удаление выбранной фотографии из списка."""
        selection = self.photo_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        self.photo_listbox.delete(idx)
        del self.selected_photos[idx]

        self.preview_label.config(image='', text="Выберите фото для превью")

    def _clear_photos(self):
        """Очистка всех фотографий."""
        self.selected_photos = []
        self.photo_listbox.delete(0, tk.END)
        self.preview_label.config(image='', text="Выберите фото для превью")

    def _new_employee(self):
        """Подготовка формы для нового сотрудника."""
        self.id_var.set("")
        self.name_var.set("")
        self.start_var.set(datetime.now().strftime("%Y-%m-%d"))
        self.end_var.set(datetime(datetime.now().year + 1, 12, 31).strftime("%Y-%m-%d"))
        self.active_var.set(True)

        self.id_entry.config(state='normal')
        self._clear_photos()
        self.tree.selection_remove(*self.tree.selection())

    def _save_employee(self):
        """Сохранение сотрудника."""
        if not self.db:
            messagebox.showerror("Ошибка", "База данных не подключена")
            return

        employee_id = self.id_var.get().strip()
        name = self.name_var.get().strip()
        start_str = self.start_var.get().strip()
        end_str = self.end_var.get().strip()

        # Валидация
        if not employee_id:
            messagebox.showerror("Ошибка", "Введите ID сотрудника")
            return

        if not name:
            messagebox.showerror("Ошибка", "Введите имя сотрудника")
            return

        # Парсинг дат
        try:
            access_start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат даты начала (YYYY-MM-DD)")
            return

        try:
            access_end = datetime.strptime(end_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат даты окончания (YYYY-MM-DD)")
            return

        if access_end <= access_start:
            messagebox.showerror("Ошибка", "Дата окончания должна быть позже даты начала")
            return

        # Обработка фотографий
        embeddings = []
        if self.selected_photos:
            if not self._init_face_components():
                messagebox.showerror(
                    "Ошибка",
                    "Не удалось инициализировать компоненты распознавания.\n"
                    "Выберите ONNX модель через меню Файл."
                )
                return

            progress_window = tk.Toplevel(self.root)
            progress_window.title("Обработка фотографий")
            progress_window.geometry("400x150")
            progress_window.transient(self.root)
            progress_window.grab_set()

            progress_label = ttk.Label(progress_window, text="Обработка фотографий...")
            progress_label.pack(pady=20)

            progress_bar = ttk.Progressbar(progress_window, length=300, mode='determinate')
            progress_bar.pack(pady=10)

            status_label = ttk.Label(progress_window, text="")
            status_label.pack(pady=10)

            self.root.update()

            for i, photo_path in enumerate(self.selected_photos):
                progress_bar['value'] = (i / len(self.selected_photos)) * 100
                status_label.config(text=f"Обработка: {Path(photo_path).name}")
                self.root.update()

                try:
                    frame = cv2.imread(photo_path)
                    if frame is None:
                        continue

                    faces = self.detector.detect(frame)
                    if not faces:
                        continue

                    largest_face = max(faces, key=lambda f: f[2] * f[3])
                    aligned = self.aligner.align(frame, largest_face)
                    if aligned is None:
                        continue

                    embedding = self.embedder.compute_embedding(aligned)
                    if embedding is not None:
                        with open(photo_path, 'rb') as f:
                            photo_hash = hashlib.sha256(f.read()).hexdigest()
                        embeddings.append((embedding, photo_hash))

                except Exception as e:
                    print(f"Ошибка обработки {photo_path}: {e}")

            progress_window.destroy()

            if not embeddings and self.selected_photos:
                messagebox.showwarning(
                    "Предупреждение",
                    "Не удалось извлечь эмбеддинги из фотографий.\n"
                    "Убедитесь, что на фото есть чёткое изображение лица."
                )

        # Сохранение в БД
        try:
            existing = self.db.get_employee(employee_id)

            self.db.upsert_employee(
                employee_id=employee_id,
                access_start=access_start,
                access_end=access_end,
                display_name=name,
                is_active=self.active_var.get()
            )

            if embeddings:
                self.db.delete_embeddings(employee_id)
                for emb, photo_hash in embeddings:
                    self.db.add_embedding(employee_id, emb, photo_hash)

            action = "обновлён" if existing else "добавлен"
            photo_info = f" с {len(embeddings)} фото" if embeddings else ""
            messagebox.showinfo("Успех", f"Сотрудник {name} ({employee_id}) {action}{photo_info}")

            self._refresh_employees()
            self._clear_photos()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка сохранения:\n{e}")

    def _delete_employee(self):
        """Удаление сотрудника."""
        if not self.db:
            return

        employee_id = self.id_var.get().strip()
        if not employee_id:
            messagebox.showerror("Ошибка", "Выберите сотрудника для удаления")
            return

        if not messagebox.askyesno(
            "Подтверждение",
            f"Удалить сотрудника {employee_id}?\nЭто действие необратимо!"
        ):
            return

        if self.db.delete_employee(employee_id):
            messagebox.showinfo("Успех", f"Сотрудник {employee_id} удалён")
            self._new_employee()
            self._refresh_employees()
        else:
            messagebox.showerror("Ошибка", "Не удалось удалить сотрудника")

    def _deactivate_employee(self):
        """Деактивация сотрудника."""
        if not self.db:
            return

        employee_id = self.id_var.get().strip()
        if not employee_id:
            messagebox.showerror("Ошибка", "Выберите сотрудника для деактивации")
            return

        if not messagebox.askyesno(
            "Подтверждение",
            f"Деактивировать сотрудника {employee_id}?\n"
            "Он не сможет получить доступ, но останется в базе."
        ):
            return

        if self.db.deactivate_employee(employee_id):
            messagebox.showinfo("Успех", f"Сотрудник {employee_id} деактивирован")
            self._refresh_employees()
        else:
            messagebox.showerror("Ошибка", "Не удалось деактивировать сотрудника")

    def _show_audit_log(self):
        """Показ журнала событий."""
        if not self.db:
            messagebox.showerror("Ошибка", "База данных не подключена")
            return

        log_window = tk.Toplevel(self.root)
        log_window.title("Журнал событий")
        log_window.geometry("900x500")
        log_window.transient(self.root)

        # Фильтры
        filter_frame = ttk.Frame(log_window, padding="10")
        filter_frame.pack(fill=tk.X)

        ttk.Label(filter_frame, text="Записей:").pack(side=tk.LEFT)
        limit_var = tk.StringVar(value="100")
        limit_combo = ttk.Combobox(filter_frame, textvariable=limit_var, values=["50", "100", "200", "500"], width=10)
        limit_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="Сотрудник:").pack(side=tk.LEFT, padx=(20, 0))
        emp_var = tk.StringVar()
        emp_entry = ttk.Entry(filter_frame, textvariable=emp_var, width=15)
        emp_entry.pack(side=tk.LEFT, padx=5)

        def refresh_logs():
            for item in log_tree.get_children():
                log_tree.delete(item)

            limit = int(limit_var.get())
            emp_id = emp_var.get().strip() or None

            logs = self.db.get_audit_logs(employee_id=emp_id, limit=limit)
            for log in logs:
                log_tree.insert('', tk.END, values=(
                    log['timestamp'][:19] if log['timestamp'] else '',
                    log['event_type'],
                    log['matched_employee_id'] or '',
                    f"{log['similarity_score']:.2f}" if log['similarity_score'] else '',
                    log['result'],
                    log['reason'] or ''
                ))

        ttk.Button(filter_frame, text="Обновить", command=refresh_logs).pack(side=tk.LEFT, padx=20)

        # Таблица логов
        columns = ('timestamp', 'event', 'employee', 'score', 'result', 'reason')
        log_tree = ttk.Treeview(log_window, columns=columns, show='headings', height=20)

        log_tree.heading('timestamp', text='Время')
        log_tree.heading('event', text='Событие')
        log_tree.heading('employee', text='Сотрудник')
        log_tree.heading('score', text='Сходство')
        log_tree.heading('result', text='Результат')
        log_tree.heading('reason', text='Причина')

        log_tree.column('timestamp', width=150)
        log_tree.column('event', width=120)
        log_tree.column('employee', width=100)
        log_tree.column('score', width=80)
        log_tree.column('result', width=80)
        log_tree.column('reason', width=300)

        scrollbar = ttk.Scrollbar(log_window, orient=tk.VERTICAL, command=log_tree.yview)
        log_tree.configure(yscrollcommand=scrollbar.set)

        log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        refresh_logs()


def main():
    """Точка входа."""
    root = tk.Tk()

    style = ttk.Style()
    if 'clam' in style.theme_names():
        style.theme_use('clam')

    app = EmployeeManagerGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
