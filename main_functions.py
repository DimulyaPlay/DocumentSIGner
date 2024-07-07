import json
import os
import shutil
import traceback
import msvcrt
from glob import glob
import subprocess
import re
import sys
from PIL import Image, ImageDraw, ImageFont
import requests
import tempfile
import fitz
import sys
from PySide2.QtWidgets import QApplication, QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QHBoxLayout, QLabel, QRadioButton, QLineEdit, QPushButton, QFileDialog, QWidget, QComboBox, QCheckBox, QMessageBox
from PySide2.QtCore import Qt


config_folder = os.path.dirname(sys.argv[0])
if not os.path.exists(config_folder):
    os.mkdir(config_folder)
config_file = os.path.join(config_folder, 'config.json')

serial_names = ('Серийный номер', 'Serial')
date_make = ('Выдан', 'Not valid before')
date_exp = ('Истекает', 'Not valid after')


def read_create_config(config_path):
    default_configuration = {
        'soed': True,
        'port': '4999',
        "stamp_on_original": True,
        "csp_path": r"C:\Program Files\Crypto Pro\CSP",
        'last_cert': '',
        'widget_visible': True
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as configfile:
                configuration = json.load(configfile)
        except Exception as e:
            print(e)
            os.remove(config_path)
            configuration = default_configuration
            with open(config_path, 'w') as configfile:
                json.dump(configuration, configfile, indent=4)
    else:
        configuration = default_configuration
        with open(config_path, 'w') as configfile:
            json.dump(configuration, configfile, indent=4)
    return configuration


def save_config():
    with open(config_file, 'w') as configfile:
        json.dump(config, configfile, indent=4)


config = read_create_config(config_file)


def get_cert_data():
    cert_mgr_path = os.path.join(config['csp_path'], 'certmgr.exe')
    if os.path.exists(cert_mgr_path):
        certs_data = {}
        try:
            result = subprocess.run([cert_mgr_path, '-list'],
                                    capture_output=True,
                                    text=True, check=True,
                                    encoding='cp866',
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout
            for i in output.split('-------')[1:]:
                rows = i.split('\n')
                cert = {}
                for row in rows:
                    cleaned_row = ' '.join(row.split()).split(" : ")
                    if len(cleaned_row) == 2:
                        cert[cleaned_row[0]] = cleaned_row[1]
                        if 'CN=' in cleaned_row[1]:
                            cert_name = re.search(r'CN=([^\n]+)', cleaned_row[1]).group(1)
                certs_data[cert_name] = cert
        except subprocess.CalledProcessError as e:
            print(f"Ошибка выполнения команды: {e}")
        return certs_data
    else:
        return {}


def sign_document(s_source_file, cert_data):
    if s_source_file:
        if os.path.exists(s_source_file):
            command = [
                config['csp_path']+'\\csptest.exe',
                "-sfsign",
                "-sign",
                "-in",
                s_source_file,
                "-out",
                f"{s_source_file}.sig",
                "-my",
                cert_data.get('SHA1 отпечаток', cert_data.get('SHA1 Hash','')),
                "-add",
                "-detached",
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding='cp866', creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.returncode
            if output == 2148081675:
                print('Не удалось найти закрытый ключ')
                return 1
            elif os.path.isfile(f"{s_source_file}.sig"):
                return f"{s_source_file}.sig"
            else:
                return 2
        else:
            print(f"Не удается найти исходный файл [{s_source_file}].")


def check_chosen_pages(chosen_pages_string):
    if not chosen_pages_string:
        return []
    if chosen_pages_string == 'all':
        return 'all'
    outList = []
    chosen_pages_string = chosen_pages_string.replace(' ', '')
    if chosen_pages_string:
        stringLst = chosen_pages_string.split(',')
        for i in stringLst:
            try:
                if int(i) not in outList:
                    outList.append(int(i))
            except:
                iRange = i.split('-')
                for j in range(int(iRange[0]), int(iRange[1]) + 1):
                    if j not in outList:
                        outList.append(j)
        outList = sorted(outList)
        return outList
    else:
        return []


def add_stamp(doc_path, cert_name, cert_info, pagelist):
    """
    :param doc_path: путь к документу
    :param cert_name: Имя пользователя сертификата
    :param cert_info: Данные сертификата
    :param pagelist: список страниц для простановки штампа
    :return:
    """
    template_png_path = os.path.join(os.path.dirname(sys.argv[0]), 'dcs.png')
    fingerprint = cert_info.get('Серийный номер', cert_info.get('Serial', ' '))
    create_date = cert_info.get('Выдан', cert_info.get('Not valid before', ' '))[:10].replace('/','.')
    exp_date = cert_info.get('Истекает', cert_info.get('Not valid after', ' '))[:10].replace('/','.')
    stamp_path = add_text_to_stamp(template_png_path, cert_name, fingerprint, create_date, exp_date)
    stamped_doc = add_stamp_to_pages(doc_path, stamp_path, pagelist)
    return stamped_doc


def add_text_to_stamp(template_path, cert_name, fingerprint, create_date, exp_date):
    template_image = Image.open(template_path)
    draw = ImageDraw.Draw(template_image)
    font_path = 'times.ttf'
    font = ImageFont.truetype(font_path, 24)
    text_positions = {
        'cert_name': (20, 145),
        'fingerprint': (20, 185),
        'create_date': (20, 225),
    }
    draw.text(text_positions['cert_name'], "Владелец:", fill='blue', font=font)
    draw.text(text_positions['cert_name'], "                          " + cert_name, fill='blue', font=font)
    draw.text(text_positions['fingerprint'], "Сертификат:", fill='blue', font=font)
    draw.text(text_positions['fingerprint'], "                          " + fingerprint[2:], fill='blue', font=font)
    draw.text(text_positions['create_date'], "Действителен:", fill='blue', font=font)
    draw.text(text_positions['create_date'], "                          " + f"c {create_date} по {exp_date}", fill='blue', font=font)
    modified_image_path = "modified_stamp.png"
    template_image.save(modified_image_path)
    return modified_image_path


def add_stamp_to_pages(pdf_path, modified_stamp_path, pagelist):
    doc = fitz.open(pdf_path)
    img_stamp = fitz.Pixmap(modified_stamp_path)  # Загружаем изображение
    metadata = doc.metadata
    # Проверка, был ли документ создан с помощью "Microsoft: Print To PDF"
    is_microsoft_pdf = 'Microsoft: Print To PDF' in (metadata.get('producer', '') + metadata.get('creator', ''))
    if pagelist == 'all':
        for page in doc:
            if is_microsoft_pdf:
                page.clean_contents()
            img_width, img_height = img_stamp.width / 4.5, img_stamp.height / 4.5
            page_width = page.rect.width
            page_height = page.rect.height
            x0 = (page_width / 2) - (img_width / 2)
            y0 = page_height - img_height - 25
            x1 = x0 + img_width
            y1 = y0 + img_height
            img_rect = fitz.Rect(x0, y0, x1, y1)
            page.insert_image(img_rect, pixmap=img_stamp)
    else:
        for page in pagelist:
            page = int(page)
            page_index = page-1
            if is_microsoft_pdf:
                doc[page_index].clean_contents()
            if page == -1:
                page_index = -1
            img_width, img_height = img_stamp.width / 4.5, img_stamp.height / 4.5
            page_width = doc[page_index].rect.width
            page_height = doc[page_index].rect.height
            x0 = (page_width / 2) - (img_width / 2)
            y0 = page_height-img_height-25
            x1 = x0 + img_width
            y1 = y0 + img_height
            img_rect = fitz.Rect(x0, y0, x1, y1)
            doc[page_index].insert_image(img_rect, pixmap=img_stamp)
    doc.saveIncr()
    return pdf_path

def resource_path(relative_path):
    """ Возвращает корректный путь для доступа к ресурсам для PyInstaller """
    try:
        # PyInstaller создает временную папку и устанавливает переменную _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def handle_dropped_files(file_paths):
    file_paths = [fp for fp in file_paths if not fp.endswith('.sig')]
    dialog = FileDialog(file_paths)
    dialog.show()
    dialog.activateWindow()
    return dialog


class CustomListWidgetItem(QWidget):
    def __init__(self, file_path):
        super().__init__()

        layout = QHBoxLayout()
        self.file_path = file_path

        # Название файла
        self.file_label = QLabel(os.path.basename(file_path))
        self.file_label.mouseDoubleClickEvent = self.open_file
        self.file_label.setMinimumWidth(440)
        self.file_label.setToolTip(os.path.basename(file_path))
        layout.addWidget(self.file_label)
        layout.addStretch()

        # Радиокнопки
        self.radio_none = QRadioButton("Нет")
        self.radio_first = QRadioButton("Первая")
        self.radio_last = QRadioButton("Последняя")
        self.radio_last.setChecked(True)
        self.radio_all = QRadioButton("Все")
        self.radio_custom = QRadioButton("Своё")
        layout.addWidget(self.radio_none)
        layout.addWidget(self.radio_first)
        layout.addWidget(self.radio_last)
        layout.addWidget(self.radio_all)
        layout.addWidget(self.radio_custom)

        # Поле для ввода своих страниц
        self.custom_pages = QLineEdit()
        self.custom_pages.setPlaceholderText("Введите страницы")
        self.custom_pages.textEdited.connect(lambda: self.radio_custom.setChecked(True))
        self.custom_pages.setFixedWidth(140)  # Фиксированная ширина
        layout.addWidget(self.custom_pages)

        self.setLayout(layout)

    def open_file(self, event):
        # Открытие файла по двойному клику
        os.startfile(self.file_path)


class FileDialog(QDialog):
    def __init__(self, file_paths):
        super().__init__()
        self.certs_data = get_cert_data()
        self.certs_list = list(self.certs_data.keys())
        self.setWindowTitle("Подписание файлов")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        self.resize(600, 400)
        self.setMaximumWidth(1900)
        self.file_list = QListWidget()
        for file_path in file_paths:
            item = QListWidgetItem(self.file_list)
            widget = CustomListWidgetItem(file_path)
            item.setSizeHint(widget.sizeHint())
            if self.width() < widget.sizeHint().width()+70:
                self.setFixedWidth(widget.sizeHint().width()+70)
            self.file_list.setItemWidget(item, widget)
        self.layout.addWidget(self.file_list)

        self.certificate_label = QLabel("Сертификат для подписи:")
        font = self.certificate_label.font()
        font.setPointSize(10)
        self.certificate_label.setFont(font)
        self.layout.addWidget(self.certificate_label)

        self.certificate_comboBox = QComboBox()
        self.certificate_comboBox.setFont(font)
        if self.certs_list:
            self.certificate_comboBox.addItems(self.certs_list)  # Добавьте свои сертификаты здесь
        else:
            self.certificate_comboBox.addItem('Не удалось найти сертификаты')
        if config['last_cert'] and config['last_cert'] in self.certs_list:
            self.certificate_comboBox.setCurrentText(config['last_cert'])
        self.layout.addWidget(self.certificate_comboBox)

        self.sign_original = QCheckBox('Ставить штамп на исходном файле.')
        self.sign_original.setChecked(config['stamp_on_original'])
        self.sign_original.setToolTip("""
        Если включено, штамп наносится на оригинал, и создается подпись.
        Если выключено, создается подпись для оригинала, а штамп наносится на копию.
        """)
        self.layout.addWidget(self.sign_original)

        self.sign_button = QPushButton("Подписать")
        self.sign_button.setFont(font)
        self.sign_button.clicked.connect(self.sign_files)
        self.layout.addWidget(self.sign_button)

        self.setLayout(self.layout)

    def sign_files(self):
        for index in range(self.file_list.count()):
            try:
                item = self.file_list.item(index)
                widget = self.file_list.itemWidget(item)
                file_path = widget.file_path
                if widget.radio_first.isChecked():
                    pages = [1]
                elif widget.radio_last.isChecked():
                    pages = [-1]
                elif widget.radio_all.isChecked():
                    pages = "all"
                elif widget.radio_custom.isChecked():
                    pages = widget.custom_pages.text()
                    pages = check_chosen_pages(pages)
                else:
                    pages = None
                print(f"Файл: {file_path}, Страницы: {pages}")
                if file_path.endswith('.pdf') and pages:
                    if not self.sign_original.isChecked():
                        filepath_to_stamp = os.path.join(os.path.dirname(file_path),
                                                         f'gf_{os.path.basename(file_path)}')
                        shutil.copy(file_path, filepath_to_stamp)
                        pages = check_chosen_pages(pages)
                        if pages:
                            _ = add_stamp(filepath_to_stamp, self.certificate_comboBox.currentText(), self.certs_data[self.certificate_comboBox.currentText()], pages)
                    else:
                        add_stamp(file_path, self.certificate_comboBox.currentText(), self.certs_data[self.certificate_comboBox.currentText()], pages)

                sign_document(file_path, self.certs_data[self.certificate_comboBox.currentText()])
            except Exception as e:
                print(f'Не удалось подписать {file_path}: {e}')
                traceback.print_exc()
        QMessageBox.information(self, 'Успех', 'Создание подписи завершено.')

