from main_functions import *


class PlaceImageStampOnA4(QDialog):
    def __init__(self, page_image_path, real_page_size, stamp_image_path):
        super().__init__()
        self.page_image_path = page_image_path
        self.stamp_image_path = stamp_image_path
        self.real_page_size = real_page_size
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Переместите штамп на нужное место и закройте окно')
        # Размеры для A4
        portrait_size = QSize(595, 842)
        landscape_size = QSize(842, 595)

        # Определяем ориентацию страницы
        page_image = QPixmap(self.page_image_path)
        if page_image.width() > page_image.height():
            self.page_size = landscape_size  # Альбомная ориентация
        else:
            self.page_size = portrait_size  # Портретная ориентация

        # Устанавливаем фиксированный размер окна
        self.setFixedSize(self.page_size)

        layout = QVBoxLayout()

        self.square_draggable = ImageStampOnDraggable(self.page_image_path, self.stamp_image_path, self.page_size)
        layout.addWidget(self.square_draggable)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(10)
        self.slider.setMaximum(100)
        self.slider.setValue(25)  # По умолчанию 50% от оригинального размера
        self.slider.valueChanged.connect(self.square_draggable.update_image_size)
        layout.addWidget(self.slider)

        self.confirm_button = QPushButton('Подтвердить', self)
        layout.addWidget(self.confirm_button)
        self.confirm_button.clicked.connect(self.accept)

        self.setLayout(layout)

    def get_stamp_coordinates_and_scale(self):
        image_rect = self.square_draggable.image_rect

        # Масштаб перевода координат из размеров окна в реальные размеры страницы
        scale_x = self.real_page_size[0] / self.page_size.width()
        scale_y = self.real_page_size[1] / self.page_size.height()

        real_coordinates = (image_rect.left() * scale_x,
                            image_rect.top() * scale_y,
                            image_rect.right() * scale_x,
                            image_rect.bottom() * scale_y)
        return real_coordinates


class ImageStampOnDraggable(QWidget):
    def __init__(self, page_image_path, stamp_image_path, page_size):
        super().__init__()
        self.page_image = QPixmap(page_image_path)
        self.stamp_image_original = QPixmap(stamp_image_path)  # Оригинальное изображение штампа
        self.page_size = page_size

        # Устанавливаем фиксированный размер виджета для A4
        self.setFixedSize(self.page_size)

        # Вычисляем масштаб для вписывания страницы в A4
        self.page_image = self.page_image.scaled(self.page_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Изначальный размер штампа: 25% от оригинального
        self.current_scale = 0.25
        self.stamp_image = self.stamp_image_original.scaled(
            int(self.stamp_image_original.width() * self.current_scale),
            int(self.stamp_image_original.height() * self.current_scale),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        # Вычисление начального положения штампа
        stamp_width = self.stamp_image.width()
        stamp_height = self.stamp_image.height()

        # Центр по горизонтали
        center_x = (self.page_size.width() - stamp_width) // 2
        # Отступ 10% от нижнего края
        bottom_margin = int(self.page_size.height() * 0.05)
        top_y = self.page_size.height() - stamp_height - bottom_margin

        # Прямоугольник штампа
        self.image_rect = QRect(center_x, top_y, stamp_width, stamp_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        # Отображаем изображение страницы на фоне
        painter.drawPixmap(self.rect(), self.page_image)
        # Отображаем границу и штамп
        painter.drawRect(self.image_rect)
        painter.drawPixmap(self.image_rect, self.stamp_image)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.image_rect.contains(event.pos()):
            self.drag_start_position = event.pos()

    def mouseMoveEvent(self, event):
        if hasattr(self, 'drag_start_position'):
            new_rect = self.image_rect.translated(event.pos() - self.drag_start_position)
            if self.rect().contains(new_rect):
                self.image_rect = new_rect
                self.drag_start_position = event.pos()
                self.update()

    def update_image_size(self, value):
        # Преобразуем значение из ползунка в масштаб
        self.current_scale = value / 100

        # Пересчитываем размеры штампа на основе оригинального изображения
        new_width = int(self.stamp_image_original.width() * self.current_scale)
        new_height = int(self.stamp_image_original.height() * self.current_scale)

        # Обновляем размеры штампа и прямоугольника
        self.stamp_image = self.stamp_image_original.scaled(
            new_width,
            new_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image_rect.setSize(QSize(new_width, new_height))
        self.update()
