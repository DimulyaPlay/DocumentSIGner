from main_functions import *


class PlaceImageStampOnA4(QDialog):
    def __init__(self, file_path, pages, stamp_image_path):
        super().__init__()
        self.file_path = file_path
        self.stamp_image_path = stamp_image_path
        self.doc = fitz.open(file_path)

        self.pages = self.parse_pages(pages)
        # Определяем режим: одна страница или несколько
        self.mode = 'single' if len(self.pages) == 1 else 'multi'

        # В одностраничном режиме будем по умолчанию показывать именно ту страницу,
        # которую попросил пользователь (self.pages[0]).
        # Однако теперь даём возможность листать ВСЕ страницы документа:
        # current_doc_page отвечает за то, какая страница открыта сейчас.
        if self.mode == 'single':
            self.current_doc_page = self.pages[0]
        else:
            self.current_doc_page = None

        # Индекс для последовательной обработки (только в многостраничном режиме)
        self.current_process_idx = 0 if self.mode == 'multi' else None

        self.results = {}
        self.temp_files = []

        self.initUI()
        self.setWindowModality(Qt.ApplicationModal)

    def parse_pages(self, pages):
        """Обработка входного параметра pages: может быть 'all', список, кортеж или число."""
        if pages == 'all':
            return list(range(len(self.doc)))
        elif isinstance(pages, (list, tuple)):
            parsed_pages = []
            for page in pages:
                if page == -1:
                    parsed_pages.append(len(self.doc) - 1)
                else:
                    parsed_pages.append(page)
            return parsed_pages
        else:
            # Если pages – одиночное число
            if pages == -1:
                return [len(self.doc) - 1]
            else:
                return [pages]

    def initUI(self):
        self.setWindowTitle('Переместите штамп на нужное место')
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Виджет для размещения штампа
        self.stamp_widget = ImageStampWidget(self.stamp_image_path)
        self.layout.addWidget(self.stamp_widget)

        # Панель управления (нижняя полоса с кнопками и слайдером)
        control_panel = QHBoxLayout()
        control_panel.setContentsMargins(5, 0, 5, 5)

        # Кнопки навигации (актуальны только в режиме single)
        self.prev_btn = QPushButton("← Предыдущая")
        self.prev_btn.setVisible(self.mode == 'single')
        self.prev_btn.clicked.connect(self.prev_page)
        control_panel.addWidget(self.prev_btn)

        # Слайдер масштаба
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(10, 100)
        self.scale_slider.setValue(25)
        self.scale_slider.valueChanged.connect(self.stamp_widget.set_scale)
        control_panel.addWidget(self.scale_slider)

        self.next_btn = QPushButton("Следующая →")
        self.next_btn.setVisible(self.mode == 'single')
        self.next_btn.clicked.connect(self.next_page)
        control_panel.addWidget(self.next_btn)

        self.layout.addLayout(control_panel)

        # Кнопки подтверждения и пропуска
        btn_box = QHBoxLayout()
        btn_box.setContentsMargins(5, 0, 5, 5)

        # Для многостраничного режима кнопка может называться «Далее»/«Применить»
        # Для одностраничного – всегда «Применить»
        apply_text = "Применить" if self.mode == 'single' else "Далее"
        self.apply_btn = QPushButton(apply_text)
        self.apply_btn.clicked.connect(self.apply_changes)
        btn_box.addWidget(self.apply_btn)

        self.skip_btn = QPushButton("Пропустить")
        self.skip_btn.clicked.connect(self.skip_page)
        btn_box.addWidget(self.skip_btn)

        self.layout.addLayout(btn_box)
        self.setLayout(self.layout)

        # Загрузка начальной страницы
        if self.mode == 'single':
            # Просто открываем текущую (по умолчанию – pages[0])
            self.load_page(self.current_doc_page)
        else:
            # Многостраничный режим – начнём с первой из списка pages
            self.load_page(self.pages[self.current_process_idx])

    def load_page(self, page_idx):
        """Загружает в виджет указанную страницу документа (в уменьшенном/увеличенном виде)."""
        page = self.doc.load_page(page_idx)
        pix = page.get_pixmap(dpi=150)
        temp_path = f"temp_page_{page_idx}.png"
        pix.save(temp_path)
        self.temp_files.append(temp_path)

        # Определяем «стандартный» размер страницы A4-ish с учётом ориентации
        if page.rect.width > page.rect.height:
            page_size = QSize(842, 595)  # Альбомная
        else:
            page_size = QSize(595, 842)  # Портретная

        # Если мы уже что-то сохранили для этой страницы, подставим:
        saved_state = self.results.get(page_idx, None)

        # Передаём полученную картинку и размер в ImageStampWidget
        self.stamp_widget.set_page(QPixmap(temp_path), page_size, saved_state)

        # Устанавливаем фиксированный размер диалога
        self.setFixedSize(page_size)

    # ---------------------- МНОГОСТРАНИЧНЫЙ РЕЖИМ ----------------------
    def apply_changes(self):
        """Обработка кнопки «Применить» (single) или «Далее»/«Применить» (multi)."""
        if self.mode == 'multi':
            # Сохраняем текущее положение штампа для текущей страницы
            self.save_current_state()

            # Если ещё есть страницы, переходим к следующей
            if self.current_process_idx < len(self.pages) - 1:
                self.current_process_idx += 1
                self.load_page(self.pages[self.current_process_idx])

                # Если мы на последней странице, меняем текст кнопки
                if self.current_process_idx == len(self.pages) - 1:
                    self.apply_btn.setText("Применить")
            else:
                # Больше страниц нет, завершаем
                self.accept()

        else:
            # В одностраничном режиме сохраняем ТОЛЬКО страницу, которая сейчас отображается
            # (возможно, пользователь полистал document и остановился на нужной)
            state = self.stamp_widget.get_state()
            self.results.clear()  # на всякий случай сбросим то, что могло было сохраниться ранее
            self.results[self.current_doc_page] = state

            self.accept()

    def skip_page(self):
        """Обработка кнопки «Пропустить»."""
        if self.mode == 'single':
            # Для одной страницы «Пропустить» = отмена всей операции
            self.reject()
        else:
            # Многостраничный режим: исключаем текущую страницу из результатов
            current_page = self.pages[self.current_process_idx]
            if current_page in self.results:
                del self.results[current_page]

            # Переходим к следующей, если есть
            if self.current_process_idx < len(self.pages) - 1:
                self.current_process_idx += 1
                self.load_page(self.pages[self.current_process_idx])

                # Если это уже последняя страница, то текст кнопки меняется
                if self.current_process_idx == len(self.pages) - 1:
                    self.apply_btn.setText("Применить")
            else:
                # Если это была последняя страница, завершаем диалог
                self.accept()

    def save_current_state(self):
        """Сохраняет положение штампа (get_state) в self.results для текущей страницы (multi)."""
        if self.mode == 'multi':
            page_idx = self.pages[self.current_process_idx]
            state = self.stamp_widget.get_state()
            if state:
                self.results[page_idx] = state

    # ---------------------- ОДНОСТРАНИЧНЫЙ РЕЖИМ (листание) ----------------------
    def prev_page(self):
        """Переключение на предыдущую страницу (только в режиме single). Ничего не сохраняем."""
        if self.mode == 'single':
            new_page = max(0, self.current_doc_page - 1)
            if new_page != self.current_doc_page:
                self.current_doc_page = new_page
                self.load_page(new_page)

    def next_page(self):
        """Переключение на следующую страницу (только в режиме single). Ничего не сохраняем."""
        if self.mode == 'single':
            new_page = min(len(self.doc) - 1, self.current_doc_page + 1)
            if new_page != self.current_doc_page:
                self.current_doc_page = new_page
                self.load_page(new_page)

    # ---------------------- ЗАВЕРШЕНИЕ ----------------------
    def get_results(self):
        # Возвращаем словарь { self.file_path: {page_idx: {...}, ...} }
        return {self.file_path: self.results}

    def closeEvent(self, event):
        """Обработка нажатия на крестик окна."""
        reply = QMessageBox.question(
            self, 'Подтверждение',
            'Все несохраненные изменения будут потеряны. Продолжить?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.reject()
        else:
            event.ignore()

    def cleanup(self):
        for f in self.temp_files:
            if os.path.exists(f):
                os.remove(f)
        self.doc.close()

    def accept(self):
        self.cleanup()
        super().accept()

    def reject(self):
        self.cleanup()
        super().reject()



class ImageStampWidget(QWidget):
    """Виджет для отображения страницы и перетаскивания штампа."""
    def __init__(self, stamp_path):
        super().__init__()
        self.stamp_original = QPixmap(stamp_path)
        self.current_scale = 0.25
        self.stamp = self.stamp_original.scaledToWidth(
            int(self.stamp_original.width() * self.current_scale),
            Qt.SmoothTransformation
        )
        self.drag_pos = None
        self.page_image = QPixmap()
        self.stamp_pos = QPoint(0, 0)
        self.setMouseTracking(True)

    def set_page(self, pixmap, page_size, saved_state=None):
        """Задаёт текущую страницу (pixmap) и восстанавливает штамп, если он уже был сохранён."""
        # Масштабируем картинку страницы в указанный размер (с сохранением пропорций)
        self.page_image = pixmap.scaled(page_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setFixedSize(page_size)

        if saved_state:
            self.stamp_pos = QPoint(*saved_state['position'])
            self.current_scale = saved_state['scale']
        else:
            # Позиция по умолчанию (центр ближе к низу)
            self.stamp_pos = QPoint(
                (page_size.width() - self.stamp.width()) // 2,
                page_size.height() - int(self.stamp.height() * 1.1)
            )
        self.update_stamp()

    def update_stamp(self):
        """Пересчитывает текущий pixmap штампа при изменении self.current_scale."""
        self.stamp = self.stamp_original.scaledToWidth(
            int(self.stamp_original.width() * self.current_scale),
            Qt.SmoothTransformation
        )
        self.update()

    def set_scale(self, value):
        """Вызывается при перемещении слайдера масштаба (0..100)."""
        self.current_scale = value / 100.0
        self.update_stamp()
    def get_state(self):
        return {
            'position': (self.stamp_pos.x(), self.stamp_pos.y()),
            'scale': self.current_scale
        }

    def get_state(self):
        """Возвращает текущие позицию штампа и масштаб, чтобы потом пересчитать координаты."""
        return {
            'position': (self.stamp_pos.x(), self.stamp_pos.y()),
            'scale': self.current_scale
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.page_image)
        painter.drawPixmap(self.stamp_pos, self.stamp)
        # Рисуем рамку вокруг штампа для наглядности
        painter.drawRect(QRect(self.stamp_pos, self.stamp.size()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Запоминаем, с каким смещением от левого-верхнего угла штампа кликнули
            self.drag_pos = event.pos() - self.stamp_pos

    def mouseMoveEvent(self, event):
        if self.drag_pos is not None:
            # Смещаем позицию штампа
            new_pos = event.pos() - self.drag_pos
            # Ограничиваем в пределах виджета
            new_pos.setX(max(0, min(new_pos.x(), self.width() - self.stamp.width())))
            new_pos.setY(max(0, min(new_pos.y(), self.height() - self.stamp.height())))
            self.stamp_pos = new_pos
            self.update()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None