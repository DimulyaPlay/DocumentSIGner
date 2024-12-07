import json
import os
import socket
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
import base64
import winreg as reg
from PySide2.QtWidgets import (QApplication, QAbstractItemView, QAction, QDialog,
                               QMenu, QVBoxLayout, QListWidget, QTableWidget,
                               QTableWidgetItem, QListWidgetItem, QHBoxLayout,
                               QLabel, QRadioButton, QLineEdit, QPushButton,
                               QFileDialog, QWidget, QComboBox, QCheckBox, QMessageBox,
                               QSlider)
from PySide2.QtCore import Qt, QThread, Signal, QRect, QSize
from PySide2.QtGui import QIcon, QMovie, QPixmap, QPainter
from queue import Queue
import fnmatch
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import urllib3
import zipfile
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


config_folder = config_file = os.path.join(os.path.expanduser('~/Documents'), 'DocumentSIGner')
if not os.path.exists(config_folder):
    os.mkdir(config_folder)
config_file = os.path.join(os.path.expanduser('~/Documents'), 'DocumentSIGner', 'config.json')
file_paths_queue = Queue()

ALLOWED_EXTENTIONS = ('.blp', '.bmp', '.dib', '.bufr', '.cur', '.pcx', '.dcx', '.dds', '.ps', '.eps', '.fit',
               '.fits', '.fli', '.flc', '.fpx', '.ftc', '.ftu', '.gbr', '.gif', '.grib', '.h5', '.hdf',
               '.png', '.apng', '.jp2', '.j2k', '.jpc', '.jpf', '.jpx', '.j2c', '.icns', '.ico', '.im',
               '.iim', '.tif', '.tiff', '.jfif', '.jpe', '.jpg', '.jpeg', '.mic', '.mpg', '.mpeg', '.mpo',
               '.msp', '.palm', '.pcd', '.pxr', '.pbm', '.pgm', '.ppm', '.pnm', '.psd', '.bw',
               '.rgb', '.rgba', '.sgi', '.ras', '.tga', '.icb', '.vda', '.vst', '.webp', '.wmf', '.emf',
               '.xbm', '.xpm', '.doc', '.docx', '.pdf', '.docm', '.xlsm',
               '.rtf', '.ods', '.odt', '.xlsx', '.xls', '.blp', '.bmp', '.dib', '.bufr', '.cur', '.pcx', '.dcx', '.dds', '.ps', '.eps', '.fit',
                   '.fits', '.fli', '.flc', '.fpx', '.ftc', '.ftu', '.gbr', '.gif', '.grib', '.h5', '.hdf',
                   '.png', '.apng', '.jp2', '.j2k', '.jpc', '.jpf', '.jpx', '.j2c', '.icns', '.ico', '.im',
                   '.iim', '.tif', '.tiff', '.jfif', '.jpe', '.jpg', '.jpeg', '.mic', '.mpg', '.mpeg', '.mpo',
                   '.msp', '.palm', '.pcd', '.pxr', '.pbm', '.pgm', '.ppm', '.pnm', '.psd', '.bw', '.rgb',
                   '.rgba', '.sgi', '.ras', '.tga', '.icb', '.vda', '.vst', '.webp', '.wmf', '.emf', '.xbm',
                   '.xpm')
serial_names = ('Серийный номер', 'Serial')
sha1 = ('SHA1 отпечаток', 'SHA1 Hash')
date_make = ('Выдан', 'Not valid before')
date_exp = ('Истекает', 'Not valid after')


def read_create_config(config_path):
    default_configuration = {
        'soed': True,
        'port': '4999',
        "stamp_on_original": True,
        "csp_path": r"C:\Program Files\Crypto Pro\CSP",
        'last_cert': '',
        'widget_visible': False,
        "context_menu": False,
        'autorun': False,
        'default_page': 2,
        'stamp_place': 0,
        'notify': False
    }

    def update_configuration(configuration, default_configuration):
        for key, value in default_configuration.items():
            if key not in configuration:
                configuration[key] = value
        return configuration

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as configfile:
                configuration = json.load(configfile)
                configuration = update_configuration(configuration, default_configuration)
        except Exception as e:
            print(e)
            os.remove(config_path)
            configuration = default_configuration
    else:
        configuration = default_configuration
    with open(config_path, 'w') as configfile:
        json.dump(configuration, configfile, indent=4)
    return configuration


def save_config():
    with open(config_file, 'w') as configfile:
        json.dump(config, configfile, indent=4)


config = read_create_config(config_file)

def get_console_encoding():
    result = subprocess.run(['chcp'], capture_output=True, text=True, shell=True)
    match = re.search(r'(\d+)', result.stdout)
    if match:
        codepage = int(match.group(1))
        if codepage == 866:
            return 'cp866'
        elif codepage == 1251:
            return 'cp1251'
        else:
            return 'utf-8'
    return 'cp866'


def get_cert_data():
    encoding =get_console_encoding()
    cert_mgr_path = os.path.join(config['csp_path'], 'certmgr.exe')
    if os.path.exists(cert_mgr_path):
        certs_data = {}
        try:
            result = subprocess.run([cert_mgr_path, '-list'],
                                    capture_output=True,
                                    text=True, check=True,
                                    encoding=encoding,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout
            for i in output.split('-------')[1:]:
                rows = i.split('\n')
                cert = {}
                for row in rows:
                    cleaned_row = ' '.join(row.split()).split(" : ")
                    if len(cleaned_row) == 2:
                        cert[cleaned_row[0]] = cleaned_row[1]
                        if 'CN=' in cleaned_row[1] and 'CN=Казначейство России' not in cleaned_row[1]:
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
                print(result)
                return 0
            elif os.path.isfile(f"{s_source_file}.sig"):
                return f"{s_source_file}.sig"
            else:
                print(result)
                return 0
        else:
            print(f"Не удается найти исходный файл [{s_source_file}].")
            return 0


def check_chosen_pages(chosen_pages_string):
    if not chosen_pages_string:
        return []
    if chosen_pages_string.strip().lower() == 'all':
        return 'all'
    chosen_pages_string = chosen_pages_string.replace(' ', '')
    pages = set()
    try:
        for part in chosen_pages_string.split(','):
            if '-' in part:
                start, end = map(int, part.split('-'))
                if start > end:
                    start, end = end, start  # Переставляем местами, если диапазон введен в обратном порядке
                pages.update(range(start - 1, end))  # Индексация с нуля
            else:
                pages.add(int(part) - 1)  # Добавляем одиночные страницы, с учетом индексации с нуля
    except ValueError:
        raise ValueError("Invalid input format. Use numbers or ranges like '1-3, 5'.")
    return sorted(pages)


def get_stamp_coords_for_filepath(file_path, pages, stamp_image):
    from stamp_editor import PlaceImageStampOnA4
    results = {}
    doc = fitz.open(file_path)
    pages = range(len(doc)) if pages == 'all' else pages
    for page_index in pages:
        if page_index == -1:
            page_index = len(doc) - 1
        page = doc[page_index]
        page_size = page.rect
        pix = page.get_pixmap(dpi=150)
        page_image_path = f"temp_page_{page_index}.png"
        pix.save(page_image_path)
        dialog = PlaceImageStampOnA4(page_image_path, (page_size.width, page_size.height), stamp_image)
        dialog.exec_()
        coords_and_scale = dialog.get_stamp_coordinates_and_scale()
        results[page_index] = coords_and_scale
        os.remove(page_image_path)
    doc.close()
    return {file_path: results}


def create_stamp_image(cert_name, cert_info):
    template_png_path = os.path.join(os.path.dirname(sys.argv[0]), 'dcs.png')
    fingerprint = cert_info.get('Серийный номер', cert_info.get('Serial', ' '))
    create_date = cert_info.get('Выдан', cert_info.get('Not valid before', ' '))[:10].replace('/','.')
    exp_date = cert_info.get('Истекает', cert_info.get('Not valid after', ' '))[:10].replace('/','.')
    stamp_path = add_text_to_stamp(template_png_path, cert_name, fingerprint, create_date, exp_date)
    return stamp_path


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
    modified_image_path = os.path.join(os.path.dirname(sys.argv[0]), 'modified_stamp.png')
    template_image.save(modified_image_path)
    return modified_image_path


def add_to_context_menu():
    key = reg.HKEY_CLASSES_ROOT
    key_path = r'*\shell\DocumentSIGner'
    command_key_path = r'*\shell\DocumentSIGner\command'
    multi_select_key_path = r'*\shell\DocumentSIGner\DropTarget\Command'
    exe_path_one = f'\"{os.path.abspath(sys.argv[0])}\" \"%1\"'
    exe_path_many = f'\"{os.path.abspath(sys.argv[0])}\" \"%*\"'
    try:
        reg.CreateKey(key, key_path)
        reg.CreateKey(key, command_key_path)
        reg.CreateKey(key, multi_select_key_path)  # Create the DropTarget\Command key
        reg.SetValue(key, key_path, reg.REG_SZ, "Подписать с помощью DocumentSIGner")
        reg.SetValue(key, command_key_path, reg.REG_SZ, exe_path_one)
        reg.SetValue(key, multi_select_key_path, reg.REG_SZ, exe_path_many)  # Set the command for multiple files
    except Exception as e:
        print(f"Failed to add context menu: {e}")


def remove_from_context_menu():
    key = reg.HKEY_CLASSES_ROOT
    key_path = r'*\shell\DocumentSIGner'

    try:
        delete_registry_key(key, key_path)
    except Exception as e:
        print(f"Failed to remove context menu: {e}")


def delete_registry_key(key, key_path):
    try:
        open_key = reg.OpenKey(key, key_path, 0, reg.KEY_ALL_ACCESS)
        num_subkeys, num_values, last_modified = reg.QueryInfoKey(open_key)

        for i in range(num_subkeys):
            subkey = reg.EnumKey(open_key, 0)
            delete_registry_key(open_key, subkey)

        reg.CloseKey(open_key)
        reg.DeleteKey(key, key_path)
    except FileNotFoundError:
        pass  # Ключ не найден, ничего не делаем
    except PermissionError as e:
        print(f"Permission error: {e}")
    except Exception as e:
        print(f"Failed to delete registry key: {e}")


def add_stamp(pdf_path, stamp_path, pagelist, custom_coords=None):
    try:
        doc = fitz.open(pdf_path)
        img_stamp = fitz.Pixmap(stamp_path)  # Загружаем изображение
        print('Добавление штампа на страницы', pagelist)
        if pagelist == 'all':
            pagelist = range(len(doc))
        for page_index in pagelist:
            if page_index == -1:
                page_index = len(doc)-1
            img_width, img_height = img_stamp.width / 4.5, img_stamp.height / 4.5
            page_width = doc[page_index].rect.width
            page_height = doc[page_index].rect.height
            x0 = (page_width / 2) - (img_width / 2)
            y0 = page_height-img_height-25
            x1 = x0 + img_width
            y1 = y0 + img_height
            img_rect = fitz.Rect(x0, y0, x1, y1)
            if custom_coords:
                custom_coord = custom_coords.get(page_index, None)
                img_rect = custom_coord if custom_coord else img_rect
            doc[page_index].insert_image(img_rect, pixmap=img_stamp)
            print('штамп создан', page_index, img_rect)
        doc.saveIncr()
    except:
        print('Не удалось добавить штамп на', pdf_path)
        traceback.print_exc()
    return pdf_path


def check_api_key(api_key):
    try:
        decoded_data = base64.b64decode(api_key).decode()
        key_data = json.loads(decoded_data)
        required_fields = ['url', 'port', 'username', 'api_key']
        if not all(field in key_data for field in required_fields):
            return False, None, None
        url = key_data['url']
        port = key_data['port']
        try:
            port = int(port)
            if not (0 < port < 65536):
                return False, None, None
        except ValueError:
            traceback.print_exc()
            return False, None, None
        return True, url, port
    except (json.JSONDecodeError, base64.binascii.Error, KeyError):
        traceback.print_exc()
        return False, None, None


def resource_path(relative_path):
    """ Возвращает корректный путь для доступа к ресурсам для PyInstaller """
    try:
        # PyInstaller создает временную папку и устанавливает переменную _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def handle_dropped_files(file_paths, dialog=None):
    filtered_filepaths = []
    for fp in file_paths:
        fn = os.path.basename(fp)
        if fp.lower().endswith(ALLOWED_EXTENTIONS) and not fn.startswith(('~', "gf_")):
            filtered_filepaths.append(fp)
    dialog = FileDialog(filtered_filepaths)
    dialog.show()
    dialog.activateWindow()
    return dialog


class CustomListWidgetItem(QWidget):
    def __init__(self, file_path, file_id=None, name=None, sig_pages=None):
        super().__init__()
        layout = QHBoxLayout()
        self.file_path = file_path.lower()
        self.gf_file_path = None
        if self.file_path.endswith('.pdf'):
            # Получаем директорию и имя файла
            directory, filename = os.path.split(self.file_path)
            self.gf_file_path = os.path.join(directory, f"gf_{filename}")
        self.file_id = file_id
        self.name = name
        self.sig_pages = sig_pages
        self.page_fragment = ""  # Переменная для хранения найденного фрагмента
        self.chb = QCheckBox()
        layout.addWidget(self.chb)
        # Название файла
        self.file_label = QLabel(os.path.basename(file_path) if name is None else name)
        self.file_label.mouseDoubleClickEvent = self.open_file
        self.file_label.setMinimumWidth(440)
        self.file_label.setToolTip(os.path.basename(file_path) if name is None else name)
        layout.addWidget(self.file_label)
        layout.addStretch()
        # Радиокнопки
        self.radio_none = QRadioButton("Нет")
        self.radio_none.setChecked(config.get('default_page', 2) == 0)
        self.radio_none.setChecked(not self.file_path.endswith('.pdf'))
        self.radio_first = QRadioButton("Первая")
        self.radio_first.setEnabled(self.file_path.endswith('.pdf'))
        self.radio_first.setChecked(config.get('default_page', 2) == 1)
        self.radio_last = QRadioButton("Последняя")
        self.radio_last.setEnabled(self.file_path.endswith('.pdf'))
        self.radio_last.setChecked(config.get('default_page', 2) == 2)
        self.radio_all = QRadioButton("Все")
        self.radio_all.setEnabled(self.file_path.endswith('.pdf'))
        self.radio_all.setChecked(config.get('default_page', 2) == 3)
        self.radio_custom = QRadioButton("Своё")
        self.radio_custom.setEnabled(self.file_path.endswith('.pdf'))
        layout.addWidget(self.radio_none)
        layout.addWidget(self.radio_first)
        layout.addWidget(self.radio_last)
        layout.addWidget(self.radio_all)
        layout.addWidget(self.radio_custom)
        # Поле для ввода своих страниц
        self.custom_pages = QLineEdit()
        self.custom_pages.setPlaceholderText("Введите страницы")
        self.custom_pages.setEnabled(self.file_path.endswith('.pdf'))
        self.custom_pages.textEdited.connect(lambda: self.radio_custom.setChecked(True))
        self.custom_pages.setFixedWidth(110)  # Фиксированная ширина
        layout.addWidget(self.custom_pages)
        self.setLayout(layout)
        self.parse_file_name_for_pages()
        if self.sig_pages:
            pagelist = check_chosen_pages(self.sig_pages)
            if pagelist:
                self.custom_pages.setText(', '.join(pagelist))
                self.radio_custom.setChecked(True)  # Явно включаем радиокнопку
        elif self.sig_pages is not None:
            self.radio_none.setChecked(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setLayout(layout)

    def show_context_menu(self, pos):
        # Создаем контекстное меню
        menu = QMenu(self)
        open_in_folder_action = QAction("Показать в папке", self)
        open_in_folder_action.triggered.connect(lambda: self.open_in_explorer(self.file_path))
        menu.addAction(open_in_folder_action)
        menu.exec_(self.mapToGlobal(pos))

    def open_file(self, event):
        if self.gf_file_path and os.path.exists(self.gf_file_path):
            os.startfile(self.gf_file_path)
        else:
            os.startfile(self.file_path)

    def parse_file_name_for_pages(self):
        # Регулярное выражение для извлечения страниц из имени файла
        pattern = r'\{(.*?)\}'
        match = re.search(pattern, os.path.basename(self.file_path))
        if match:
            self.page_fragment = match.group(0)
            pages = match.group(1)
            self.custom_pages.setText(pages)
            self.radio_custom.setChecked(True)

    def get_clean_file_path(self):
        if self.page_fragment:
            return os.path.basename(self.file_path).replace(self.page_fragment, '')
        else:
            return self.file_path

    def set_file_label_background(self, color):
        self.file_label.setStyleSheet(f'background-color: {color}; border-radius: 4px; padding-left: 3px; padding-right: 3px; margin-right: 3px')

    def open_in_explorer(self, filepath: str):
        """
        Показать файл/папку в проводнике
        @param filepath: путь к файлу
        """
        filepath = filepath.replace('/', '\\')
        subprocess.Popen(fr'explorer /select,"{filepath}')


class FileDialog(QDialog):
    def __init__(self, file_paths, downloaded_server_files=dict()):
        super().__init__()
        self.current_session_stamps = None
        self.certs_data = get_cert_data()
        self.setWindowIcon(QIcon(resource_path('icons8-legal-document-64.ico')))
        self.certs_list = list(self.certs_data.keys())
        self.setWindowTitle("Подписание файлов")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        self.resize(600, 500)
        self.setMaximumWidth(1900)
        self.downloaded_server_files = downloaded_server_files
        self.rules_file = os.path.join(config_folder, 'rules.txt')
        # Загрузка и проверка файла по правилам из rules.txt
        if os.path.exists(self.rules_file):
            with open(self.rules_file, 'r') as file:
                self.rules = file.readlines()
        else:
            self.rules = []
        # Добавляем QLabel с инструкцией
        self.instruction_label = QLabel("Укажите страницы для размещения штампа на документе (только для PDF), выберите сертификат из списка и нажмите 'Подписать'")
        font = self.instruction_label.font()
        font.setPointSize(10)
        self.instruction_label.setFont(font)
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.instruction_label)

        self.file_list = QListWidget()
        self.file_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        vertical_scroll_bar = self.file_list.verticalScrollBar()
        vertical_scroll_bar.setSingleStep(10)  # Значение в пикселях
        for file_path in file_paths:
            self.append_new_file_to_list(file_path)
        self.layout.addWidget(self.file_list)

        self.certificate_label = QLabel("Сертификат для подписи:")
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

        self.sign_original = QCheckBox('Ставить штамп на оригинале документа (Если нет, будет создана копия с нанесенным штампом).')
        self.sign_original.setChecked(config['stamp_on_original'])
        self.sign_original.setToolTip("""
        Если включено, штамп наносится на оригинал, и создается подпись.
        Если выключено, для оригинала создается подпись, а затем создается копия с нанесенным штампом.
        Таким образом оригинал останется чистым и в то же время появится версия для печати.
        """)
        self.sign_original.setFont(font)
        self.layout.addWidget(self.sign_original)

        layout_buttons = QHBoxLayout()
        layout_buttons.setContentsMargins(0, 0, 0, 0)
        layout_buttons.setSpacing(4)

        self.sign_button_all = QPushButton("Подписать все")
        self.sign_button_all.setFixedHeight(28)
        self.sign_button_all.setFont(font)
        self.sign_button_all.clicked.connect(self.sign_all)
        layout_buttons.addWidget(self.sign_button_all)

        self.loading_label = QLabel()
        self.loading_label.setFixedSize(32, 32)  # Устанавливаем фиксированный размер для QLabel
        self.loading_label.setStyleSheet("background-color: transparent;")  # Удаляем фон
        layout_buttons.addWidget(self.loading_label)

        self.movie = QMovie(os.path.join(os.path.dirname(sys.argv[0]), '35.gif'))
        self.movie.setScaledSize(self.loading_label.size())  # Масштабируем анимацию до размера QLabel

        self.sign_button_chosen = QPushButton("Подписать отмеченные")
        self.sign_button_chosen.setFixedHeight(28)
        self.sign_button_chosen.setFont(font)
        self.sign_button_chosen.clicked.connect(self.sign_chosen)
        layout_buttons.addWidget(self.sign_button_chosen)

        self.layout.addLayout(layout_buttons)

        self.setLayout(self.layout)

    def request_stamp_positions_from_user(self, files_to_sign):
        stamp_image = create_stamp_image(self.certificate_comboBox.currentText(), self.certs_data[self.certificate_comboBox.currentText()])
        for idx in files_to_sign:
            file_path, pages, _ = self.get_filepath_and_pages_for_sign(idx)
            if file_path and pages:
                file_path_coords = get_stamp_coords_for_filepath(file_path, pages, stamp_image)
                self.current_session_stamps.update(file_path_coords)

    def get_file_indexes_for_sign(self, all=False):
        if all:
            return range(self.file_list.count())
        files_to_sign = []
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            widget = self.file_list.itemWidget(item)
            if widget.chb.isChecked():  # Проверяем установлен ли чекбокс
                files_to_sign.append(index)
                widget.chb.setChecked(False)
        return files_to_sign

    def sign_all(self):
        self.current_session_stamps = {}
        self.block_buttons(True)
        self.loading_label.setMovie(self.movie)
        self.movie.start()
        if config.get('stamp_place', 0) == 1:
            files_to_sign = self.get_file_indexes_for_sign(all=True)
            self.request_stamp_positions_from_user(files_to_sign)
        self.thread = SignAllFilesThread(self)
        self.thread.result.connect(self.on_sign_all_result)
        self.thread.start()

    def sign_chosen(self):
        self.current_session_stamps = {}
        files_to_sign = self.get_file_indexes_for_sign()
        if config.get('stamp_place', 0) == 1:
            self.request_stamp_positions_from_user(files_to_sign)
        if files_to_sign:
            self.block_buttons(True)
            self.loading_label.setMovie(self.movie)
            self.movie.start()
            self.thread = SignAllFilesThread(self, files_to_sign)
            self.thread.result.connect(self.on_sign_all_result)
            self.thread.start()
        else:
            QMessageBox.information(self, 'Ничего не выбрано', 'Выберите документы для подписи.')

    def on_sign_all_result(self, fuckuped_files, index_list_red, index_list_green):
        self.movie.stop()
        self.loading_label.clear()
        self.block_buttons(False)
        for idx in index_list_green:
            item = self.file_list.item(idx)
            widget = self.file_list.itemWidget(item)
            widget.set_file_label_background("rgba(0, 128, 0, 128)")
        if fuckuped_files:
            for idx in index_list_red:
                item = self.file_list.item(idx)
                widget = self.file_list.itemWidget(item)
                widget.set_file_label_background("rgba(255, 0, 0, 128)")
            msg_lst = [f'{os.path.basename(fp)}-{err}' for fp, err in fuckuped_files.items()]
            msg_str = '\n'.join(msg_lst)
            QMessageBox.warning(self, 'Ошибка', f'Возникли ошибки со следующими документами:\n{msg_str}')
        else:
            QMessageBox.information(self, 'Успех', 'Создание подписи завершено.')

    def block_buttons(self, block):
        self.sign_button_all.setEnabled(not block)
        self.sign_button_chosen.setEnabled(not block)

    def get_filepath_and_pages_for_sign(self, index):
        item = self.file_list.item(index)
        widget = self.file_list.itemWidget(item)
        file_path = widget.file_path
        file_path_clean = widget.get_clean_file_path()
        soed_file_id = widget.file_id
        if file_path != file_path_clean:
            shutil.move(file_path, file_path_clean)
            file_path = file_path_clean
        if widget.radio_first.isChecked():
            pages = [0]
        elif widget.radio_last.isChecked():
            pages = [-1]
        elif widget.radio_all.isChecked():
            pages = "all"
        elif widget.radio_custom.isChecked():
            pages = widget.custom_pages.text()
            pages = check_chosen_pages(pages)
        else:
            pages = None
        return file_path, pages, soed_file_id

    def sign_file(self, index):
        try:
            filepath_to_stamp = ''
            file_path, pages, soed_file_id = self.get_filepath_and_pages_for_sign(index)
            print(f"Файл: {file_path}, Страницы: {pages}")
            custom_coords = self.current_session_stamps.get(file_path)
            if file_path.lower().endswith('.pdf') and pages:
                stamp_image_path = create_stamp_image(self.certificate_comboBox.currentText(), self.certs_data[self.certificate_comboBox.currentText()])
                if not self.sign_original.isChecked():
                    filepath_to_stamp = os.path.join(os.path.dirname(file_path),
                                                     f'gf_{os.path.basename(file_path)}')
                    shutil.copy(file_path, filepath_to_stamp)
                    _ = add_stamp(filepath_to_stamp, stamp_image_path, pages, custom_coords)
                else:
                    add_stamp(file_path, stamp_image_path, pages, custom_coords)
            sign_path = sign_document(file_path, self.certs_data[self.certificate_comboBox.currentText()])
            if soed_file_id:
                if os.path.isfile(sign_path):
                    fd, zip_to_send = tempfile.mkstemp(f'.zip')
                    os.close(fd)
                    with zipfile.ZipFile(zip_to_send, 'w') as zipf:
                        zipf.write(file_path, os.path.basename(file_path))
                        zipf.write(sign_path, os.path.basename(sign_path))
                        if filepath_to_stamp:
                            zipf.write(filepath_to_stamp, os.path.basename(filepath_to_stamp))
                        else:
                            zipf.write(file_path, f'gf_{os.path.basename(file_path)}')
                    result = self.send_zip_to_soed(zip_to_send, soed_file_id)
                    for fp in [zip_to_send, file_path, sign_path, filepath_to_stamp]:
                        try:
                            os.remove(fp)
                        except:
                            pass
                    if not result:
                        del self.downloaded_server_files[soed_file_id]
                        return 0, '', file_path
                    else:
                        return 1, result, file_path
                else:
                    return 1, 'Не удалось найти sig фал при проверке', file_path

            if sign_path:
                # Блок проверки пользовательских правил перемещения
                for rule in self.rules:
                    source_dir, patterns, dest_dir, _ = rule.strip().split('|')
                    if file_path.startswith(source_dir):
                        patterns_list = patterns.split(';')
                        # Проверяем, соответствует ли файл всем паттернам
                        all_patterns_match = True
                        for pattern in patterns_list:
                            if not fnmatch.fnmatch(os.path.basename(file_path), pattern):
                                all_patterns_match = False
                                break
                        if all_patterns_match:
                            if os.path.dirname(file_path) != os.path.abspath(dest_dir):
                                # Перемещаем файл в целевую директорию
                                new_file_path = os.path.join(dest_dir, os.path.basename(file_path))
                                shutil.move(file_path, dest_dir)
                                shutil.move(sign_path, dest_dir)
                                widget.file_path = new_file_path
                                if filepath_to_stamp:
                                    shutil.move(filepath_to_stamp, dest_dir)
            else:
                print(f'Не удалось подписать {file_path}')
                return 1, '', file_path
        except Exception as e:
            print(f'Не удалось подписать: {e}')
            traceback.print_exc()
            return 1, e, file_path
        config['last_cert'] = self.certificate_comboBox.currentText()
        save_config()
        return 0, '', file_path

    def append_new_file_to_list(self, file_path):
        fn = os.path.basename(file_path)
        if file_path.lower().endswith(ALLOWED_EXTENTIONS) and not fn.startswith(('~', "gf_")):
            item = QListWidgetItem(self.file_list)
            widget = CustomListWidgetItem(file_path)
            item.setSizeHint(widget.sizeHint())
            if self.width() < widget.sizeHint().width() + 35:
                self.setFixedWidth(widget.sizeHint().width() + 35)
            self.file_list.setItemWidget(item, widget)
            print(file_path, "добавлен в список")

    def append_new_online_file_to_list(self, file_id, file_attr):
        fn = file_attr['fileName']
        file_path = file_attr['filePath']
        sig_pages = file_attr['sigPages']
        item = QListWidgetItem(self.file_list)
        widget = CustomListWidgetItem(file_path, file_id=file_id, name=fn, sig_pages=sig_pages)
        item.setSizeHint(widget.sizeHint())
        if self.width() < widget.sizeHint().width() + 35:
            self.setFixedWidth(widget.sizeHint().width() + 35)
        self.file_list.setItemWidget(item, widget)
        print(file_path, "добавлен в список")

    def send_zip_to_soed(self, zip_to_send, soed_file_id):
        ip_server = config.get('soed_url')
        port_server = config.get('soed_port')
        api_key = config.get('api_key')
        # Проверка наличия URL и порта
        if not ip_server or not port_server:
            raise ValueError("URL или порт не указаны в конфигурации")
        url = f"https://{ip_server}:{port_server}/ext/upload-signed-file"
        headers = {'X-API-KEY': api_key}
        # Параметры запроса
        params = {'fileId': soed_file_id}
        # Открываем файл ZIP для отправки
        with open(zip_to_send, 'rb') as file:
            files = {'file': file}
            # Отправка POST-запроса
            response = requests.post(url, headers=headers, data=params, files=files, verify=False, proxies={'http': False, 'https': False})
        # Проверка ответа
        if response.status_code == 200:
            result = response.json()
            if not result.get('error'):
                return 0
            else:
                return f"Ошибка при отправке: {result.get('error_message')}"
        else:
            return f"Ошибка подключения: статус {response.status_code}"

    def closeEvent(self, event):
        self.file_list.clear()
        self.hide()


class RulesDialog(QDialog):
    def __init__(self, rules_file):
        super().__init__()
        self.rules_file = rules_file
        self.initUI()

    def initUI(self):
        self.setWindowIcon(QIcon(resource_path('icons8-legal-document-64.ico')))
        self.setWindowTitle('Правила после подписания')

        layout = QVBoxLayout()
        self.instruction_label = QLabel('Исходное расположение: место, файлы в котором будут проверяться\n'
                                        'Паттерны: * - все файлы, текст* - файл начинается с "текст", *текст.pdf - файл заканчивается на "текст.pdf", *текст* - файл содержит в названии "текст"\n'
                                        'Паттерны можно расположить друг за другом через ;, они будет вычисляться со знаком И. Для ИЛИ нужно добавить паттерны в новую строку как еще одно правило.\n'
                                        'Целевое расположение: место, куда перемещать подписанные файл и подпись. \n'
                                        'На подпись: да или нет. Отображать файлы из этой директории в списке при нажатии ЛКМ на значке в трее.')
        font = self.instruction_label.font()
        font.setPointSize(10)
        self.instruction_label.setFont(font)
        layout.addWidget(self.instruction_label)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Исходное расположение', 'Паттерны', 'Целевое расположение', 'На подпись'])
        layout.addWidget(self.table)

        button_layout = QHBoxLayout()

        self.save_to_file_button = QPushButton('Сохранить правила в .txt')
        self.save_to_file_button.clicked.connect(lambda: self.save_rules(to_file=True))
        button_layout.addWidget(self.save_to_file_button)

        self.load_button = QPushButton('Загрузить правила из .txt')
        self.load_button.clicked.connect(lambda: self.load_rules(from_file=True))
        button_layout.addWidget(self.load_button)

        self.save_button = QPushButton('Сохранить правила')
        self.save_button.clicked.connect(self.save_rules)
        button_layout.addWidget(self.save_button)

        self.add_row_button = QPushButton('Добавить правило')
        self.add_row_button.clicked.connect(self.add_row)
        button_layout.addWidget(self.add_row_button)

        self.del_row_button = QPushButton('Удалить правило')
        self.del_row_button.clicked.connect(self.del_row)
        button_layout.addWidget(self.del_row_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)
        # Resize columns after setting the layout
        self.table.resizeColumnsToContents()

        self.load_rules(from_file=False)

        self.resize_columns_to_max_width()

    def resize_columns_to_max_width(self):
        max_width = 700
        for column in range(self.table.columnCount()):
            width = self.table.columnWidth(column)
            if width > max_width:
                self.table.setColumnWidth(column, max_width)

    def load_rules(self, from_file=True):
        if from_file:
            options = QFileDialog.Options()
            fileName, _ = QFileDialog.getOpenFileName(self, "Открыть правила", "", "Text Files (*.txt);;All Files (*)",
                                                      options=options)
            if fileName:
                rules_file = fileName
            else:
                return
        else:
            rules_file = self.rules_file
        if not os.path.exists(self.rules_file) and not from_file:
            return
        with open(rules_file, 'r') as file:
            lines = file.readlines()
            self.table.setRowCount(0)
            for line in lines:
                parts = line.strip().split('|')
                if len(parts) == 4:
                    self.add_row(parts[0], parts[1], parts[2], parts[3])
            self.resize_columns_to_max_width()

    def save_rules(self, to_file=False):
        file_for_save = self.rules_file
        if to_file:
            file_for_save, _ = QFileDialog.getSaveFileName(None, "Сохранить правила как",
                                                         f"Правила DocumentSINer",
                                                         "*.txt")
            if not file_for_save:
                return

        with open(file_for_save, 'w') as file:
            for row in range(self.table.rowCount()):
                source_dir = self.table.item(row, 0).text()
                patterns = self.table.item(row, 1).text()
                dest_dir = self.table.item(row, 2).text()
                for_sign = self.table.item(row, 3).text()
                file.write(f'{source_dir}|{patterns}|{dest_dir}|{for_sign}\n')

    def add_row(self, source_dir='', patterns='', dest_dir='', for_sign=''):
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)
        self.table.setItem(row_position, 0, QTableWidgetItem(source_dir))
        self.table.setItem(row_position, 1, QTableWidgetItem(patterns))
        self.table.setItem(row_position, 2, QTableWidgetItem(dest_dir))
        self.table.setItem(row_position, 3, QTableWidgetItem(for_sign))

    def del_row(self):
        row_position = self.table.currentRow()
        self.table.removeRow(row_position)


def send_file_path_to_existing_instance(file_paths):
    attempts = 5
    for attempt in range(attempts):
        try:
            print(f'Attempt {attempt + 1} to send file paths to existing instance...')  # Лог для отладки
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect(('localhost', 65432))
            print('Connected to the socket server')  # Лог для отладки
            data = file_paths[0]
            client_socket.sendall(data.encode())
            client_socket.close()
            print('File paths sent successfully and connection closed')  # Лог для отладки
            return 1
        except ConnectionRefusedError:
            print('Connection to the socket server failed')  # Лог для отладки
            if attempt < attempts - 1:
                print('Retrying in 1 second...')  # Лог для отладки
                time.sleep(1)
    return 0


class QueueMonitorThread(QThread):
    file_path_signal = Signal(str)
    def run(self):
        while True:
            file_path = file_paths_queue.get()
            if file_path is None:
                break
            self.file_path_signal.emit(file_path)
            file_paths_queue.task_done()


class SignAllFilesThread(QThread):
    result = Signal(dict, object, object)

    def __init__(self, parent=None, indexes=None):
        super().__init__(parent)
        self.indexes = indexes

    def run(self):
        res_total = 0
        fuckuped_files = {}
        redlist = []
        greenlist = []
        file_index_list = self.indexes if self.indexes else range(self.parent().file_list.count())
        for index in file_index_list:
            res, err, fp = self.sign_file(index)
            if res:
                res_total += res
                fuckuped_files[fp] = str(err)
                redlist.append(index)
            else:
                greenlist.append(index)
        self.result.emit(fuckuped_files, redlist, greenlist)

    def sign_file(self, index):
        return self.parent().sign_file(index)


class SignFileThread(QThread):
    result = Signal(bool, str, int)

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index

    def run(self):
        res, err, fp = self.sign_file(self.index)
        self.result.emit(res, err, self.index)

    def sign_file(self, index):
        return self.parent().sign_file(index)


class FileWatchHandler(FileSystemEventHandler):
    def __init__(self, notify_callback):
        super().__init__()
        self.notify_callback = notify_callback

    def on_created(self, event):
        if not event.is_directory:
            fn = os.path.basename(event.src_path)
            time.sleep(2)
            if event.src_path.lower().endswith(ALLOWED_EXTENTIONS) and not fn.startswith(('~', "gf_")) and not os.path.exists(event.src_path.lower()+'.sig'):
                self.notify_callback(event.src_path)


class FileWatcher:
    def __init__(self, directory_to_watch, notify_callback):
        self.observer = Observer()
        self.directory_to_watch = fr'{directory_to_watch}'
        print(directory_to_watch)
        self.notify_callback = notify_callback

    def run(self):
        event_handler = FileWatchHandler(self.notify_callback)
        self.observer.schedule(event_handler, self.directory_to_watch, recursive=False)
        self.observer.start()
