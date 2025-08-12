import json
import os
import socket
import shutil
import traceback
import subprocess
import re
import sys
import pypdfium2 as pdfium
import tempfile
from PyPDF2 import PdfReader, PdfWriter, PageObject, Transformation
from reportlab.lib.pagesizes import A4, landscape
from threading import Lock, Timer, Thread
from reportlab.pdfgen import canvas
import winreg as reg
import winshell
from win32com.client import Dispatch
from PySide2.QtWidgets import (QApplication, QAbstractItemView, QAction, QDialog,
                               QMenu, QVBoxLayout, QListWidget, QTableWidget,
                               QTableWidgetItem, QListWidgetItem, QHBoxLayout,
                               QLabel, QRadioButton, QLineEdit, QPushButton,
                               QFileDialog, QWidget, QComboBox, QCheckBox, QMessageBox,
                               QSlider, QButtonGroup, QFrame)
from PySide2.QtCore import Qt, QThread, Signal, QRect, QSize, QLineF, QPoint, QTranslator, QLocale, QLibraryInfo, Slot
from PySide2.QtGui import QIcon, QMovie, QPixmap, QPainter
from PIL import Image, ImageDraw, ImageFont
from queue import Queue
import fnmatch
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import zipfile

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
                   '.xpm', ".txt")
serial_names = ('Серийный номер', 'Serial')
sha1 = ('SHA1 отпечаток', 'SHA1 Hash')
date_make = ('Выдан', 'Not valid before')
date_exp = ('Истекает', 'Not valid after')


def read_create_config(config_path):
    default_configuration = {
        "stamp_on_original": True,
        "csp_path": r"C:\Program Files\Crypto Pro\CSP",
        'last_cert': '',
        'widget_visible': False,
        "context_menu": False,
        'autorun': False,
        'default_page': 2,
        'stamp_place': 0,
        'notify': False,
        'normalize_to_a4': False
    }

    configuration = default_configuration.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as configfile:
                configuration_opened = json.load(configfile)
                for k, v in configuration_opened.items():
                    configuration[k] = v
        except Exception as e:
            print(e)
            os.remove(config_path)
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
    encoding = get_console_encoding()
    cert_mgr_path = os.path.join(config['csp_path'], 'certmgr.exe')
    if os.path.exists(cert_mgr_path):
        certs_data = {}
        try:
            result = subprocess.run(
                [cert_mgr_path, '-list'],
                capture_output=True, text=True, check=True,
                encoding=encoding,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout
            for i in output.split('-------')[1:]:
                rows = i.split('\n')
                cert = {}
                base_name = None
                for row in rows:
                    cleaned_row = ' '.join(row.split()).split(" : ")
                    if len(cleaned_row) == 2:
                        key, val = cleaned_row
                        cert[key] = val
                        if base_name is None and 'CN=' in val and 'CN=Казначейство России' not in val:
                            m = re.search(r'CN=([^\n]+)', val)
                            if not m:
                                continue
                            bn = m.group(1).split(',', 1)[0].strip()
                            if bn.lower() in ('федеральное казначейство',):
                                continue
                            base_name = bn
                if base_name:
                    exp_date = cert.get('Истекает', cert.get('Not valid after', ' '))[:10].replace('/', '.')
                    candidate = f"{base_name} ({exp_date})" if exp_date.strip() else base_name
                    if candidate in certs_data:
                        suffix = 1
                        while f"{candidate} ({suffix})" in certs_data:
                            suffix += 1
                        candidate = f"{candidate} ({suffix})"
                    certs_data[candidate] = cert
        except subprocess.CalledProcessError as e:
            print(f"Ошибка выполнения команды: {e}")
        return certs_data
    else:
        return {}


def filter_inappropriate_files(file_paths):
    return [file_path for file_path in file_paths if
     file_path.lower().endswith(ALLOWED_EXTENTIONS) and not os.path.basename(file_path).startswith(('~', "gf_"))]


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
                return 0
            elif os.path.isfile(f"{s_source_file}.sig"):
                return f"{s_source_file}.sig"
            else:
                print(result)
                return 0
        else:
            print(f"Не удается найти исходный файл [{s_source_file}].")
            return 0


def toggle_startup_registry(enable: bool):
    app_name = "DocumentSIGner"
    exe_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
    exe_path = os.path.join(os.path.dirname(exe_path), 'update.exe')
    exe_path_with_param = f'"{exe_path}" -autorun'
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, key, 0, reg.KEY_ALL_ACCESS) as reg_key:
            if enable:
                reg.SetValueEx(reg_key, app_name, 0, reg.REG_SZ, exe_path_with_param)
            else:
                try:
                    reg.DeleteValue(reg_key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"[!] Ошибка автозапуска через реестр: {e}")
        return False


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
        print("Invalid input format. Use numbers or ranges like '1-3, 5'.")
        return None
    return sorted(pages)


def normalize_pdf_in_place(file_path: str):
    temp_path = file_path + ".tmp"
    reader = PdfReader(file_path)
    writer = PdfWriter()
    for page in reader.pages:
        orig_width = float(page.mediabox.width)
        orig_height = float(page.mediabox.height)
        # Определим ориентацию
        is_landscape = orig_width > orig_height
        target_width, target_height = landscape(A4) if is_landscape else A4
        scale = min(target_width / orig_width, target_height / orig_height)
        new_width = orig_width * scale
        new_height = orig_height * scale
        x_offset = (target_width - new_width) / 2
        y_offset = (target_height - new_height) / 2
        # Создаём пустую страницу A4 (ориентированную)
        new_page = PageObject.create_blank_page(width=target_width, height=target_height)
        transformation = Transformation().scale(scale).translate(x_offset, y_offset)
        page.add_transformation(transformation)
        new_page.merge_page(page)
        writer.add_page(new_page)
    with open(temp_path, 'wb') as f:
        writer.write(f)
    os.replace(temp_path, file_path)


def get_stamp_coords_for_filepath(file_path, pages, stamp_image):
    from stamp_editor import PlaceImageStampOnA4
    dialog = PlaceImageStampOnA4(file_path, pages, stamp_image)
    if dialog.exec_() == QDialog.Accepted:
        dialog.pdf_document.close()
        results = {}
        pdf_reader = PdfReader(file_path)
        # Берём все данные, сохранённые в диалоге
        dialog_data = dialog.get_results()[file_path]
        print(dialog_data)
        for page_idx, data in dialog_data.items():
            if data is None:
                results[page_idx] = None
            page = pdf_reader.pages[page_idx]
            real_width = float(page.mediabox.width)
            real_height = float(page.mediabox.height)
            # Коэффициенты масштабирования между «экранной» отрисовкой и реальным PDF-размером
            page_image_w = dialog.page_frame.width()
            page_image_h = dialog.page_frame.height()
            scale_x = real_width / page_image_w
            scale_y = real_height / page_image_h
            # Позиция штампа в координатах PDF
            disp_x, disp_y = data['position']  # позиция в координатах виджета
            x = disp_x * scale_x
            y = disp_y * scale_y
            # Размер штампа в координатах PDF
            # Штамп на экране = оригинальная ширина (в пикселях) * current_scale
            disp_stamp_w = dialog.stamp_widget.stamp_original.width() * data['scale']
            disp_stamp_h = dialog.stamp_widget.stamp_original.height() * data['scale']
            w = disp_stamp_w * scale_x
            h = disp_stamp_h * scale_y
            results[page_idx] = (x, y, x + w, y + h)
        pdf_reader.stream.close()  # безопасное закрытие файла
        if results:
            print(results)
            return {file_path: results}
        else:
            return None
    else:
        dialog.pdf_document.close()
        return None


def create_stamp_image(cert_name, cert_info, stamp='regular'):
    fingerprint = cert_info.get('Серийный номер', cert_info.get('Serial', ' '))
    create_date = cert_info.get('Выдан', cert_info.get('Not valid before', ' '))[:10].replace('/','.')
    exp_date = cert_info.get('Истекает', cert_info.get('Not valid after', ' '))[:10].replace('/','.')
    stamp_path = add_text_to_stamp(cert_name, fingerprint, create_date, exp_date, stamp)
    return stamp_path


def add_text_to_stamp(cert_name, fingerprint, create_date, exp_date, stamp='regular'):
    template_path_main = os.path.join(os.path.dirname(sys.argv[0]), 'dcs.png')
    template_path_copy_in_law = os.path.join(os.path.dirname(sys.argv[0]), 'dcs-copy-in-law.png')
    template_path_copy_no_in_law = os.path.join(os.path.dirname(sys.argv[0]), 'dcs-copy-no-in-law.png')
    text_positions_main = {
        'cert_name': (20, 145),
        'fingerprint': (20, 185),
        'create_date': (20, 225),
    }
    text_positions_copy = {
        'cert_name': (670, 145),
        'fingerprint': (670, 185),
        'create_date': (670, 225),
        'in_law_date': (60, 200)
    }
    if stamp=='copy':
        template_path = template_path_copy_no_in_law
        text_positions = text_positions_copy
    elif stamp.startswith('copy-'):
        template_path = template_path_copy_in_law
        text_positions = text_positions_copy
    else:
        template_path = template_path_main
        text_positions = text_positions_main
    template_image = Image.open(template_path)
    draw = ImageDraw.Draw(template_image)
    font_path = 'times.ttf'
    font = ImageFont.truetype(font_path, 24)
    draw.text(text_positions['cert_name'], "Владелец:", fill='blue', font=font)
    draw.text(text_positions['cert_name'], "                          " + cert_name, fill='blue', font=font)
    draw.text(text_positions['fingerprint'], "Сертификат:", fill='blue', font=font)
    draw.text(text_positions['fingerprint'], "                          " + fingerprint[2:], fill='blue', font=font)
    draw.text(text_positions['create_date'], "Действителен:", fill='blue', font=font)
    draw.text(text_positions['create_date'], "                          " + f"c {create_date} по {exp_date}", fill='blue', font=font)
    if stamp.startswith('copy-'):
        draw.text(text_positions['in_law_date'],f"Вступил в законную силу {stamp.split('-')[1]}", fill='blue', font=ImageFont.truetype(font_path, 34))
    modified_image_path = os.path.join(os.path.dirname(sys.argv[0]), 'modified_stamp.png')
    template_image.save(modified_image_path)
    return modified_image_path


def add_to_context_menu():
    key_base = r'Software\Classes\*\shell\DocumentSIGner'
    command_key = key_base + r'\command'
    try:
        with reg.CreateKey(reg.HKEY_CURRENT_USER, key_base) as key:
            reg.SetValueEx(key, '', 0, reg.REG_SZ, 'Подписать с помощью DocumentSIGner')
        with reg.CreateKey(reg.HKEY_CURRENT_USER, command_key) as key:
            exe_path = f'"{os.path.abspath(sys.argv[0])}" "%1"'
            reg.SetValueEx(key, '', 0, reg.REG_SZ, exe_path)
        return 1
    except Exception:
        traceback.print_exc()
        QMessageBox.warning(None, 'Ошибка', "Не удалось изменить параметры реестра.")
        return 0


def remove_from_context_menu():
    try:
        key_path = r'*\shell\DocumentSIGner'
        reg.DeleteKey(reg.HKEY_CLASSES_ROOT, key_path + r'\command')
        reg.DeleteKey(reg.HKEY_CLASSES_ROOT, key_path)
    except:
        pass
    base_path = r'Software\Classes\*\shell\DocumentSIGner'
    try:
        reg.DeleteKey(reg.HKEY_CURRENT_USER, base_path + r'\command')
        reg.DeleteKey(reg.HKEY_CURRENT_USER, base_path)
        return 1
    except FileNotFoundError:
        return 1
    except Exception:
        traceback.print_exc()
        QMessageBox.warning(None, 'Ошибка', "Не удалось удалить пункт из контекстного меню.")
        return 0


def add_stamp(pdf_path, stamp_path, pagelist, custom_coords={}):

    def create_overlay_pdf_with_stamp(image_path, page_width, page_height, coords):
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(tmp_fd)
        c = canvas.Canvas(tmp_path, pagesize=(page_width, page_height))
        x0, y0, x1, y1 = coords
        width = x1 - x0
        height = y1 - y0
        y_rl = page_height - y1  # корректируем Y для ReportLab (0 внизу)
        c.drawImage(image_path, x0, y_rl, width=width, height=height, mask='auto')
        c.showPage()
        c.save()
        return tmp_path

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)
        if pagelist == 'all':
            pages_to_stamp = list(range(total_pages))
        else:
            pages_to_stamp = [(total_pages - 1 if p == -1 else p) for p in pagelist]
        if custom_coords or config.get('stamp_place', 0) == 1:
            pages_to_stamp = [k for k in custom_coords.keys()]
        print('Добавление штампа на страницы', pages_to_stamp)
        for idx, page in enumerate(reader.pages):
            if custom_coords and idx in custom_coords:
                coords = custom_coords[idx]
                if coords is None:
                    writer.add_page(page)
                    continue
            elif idx in pages_to_stamp:
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)
                img = Image.open(stamp_path)
                img_width = img.width / 4.5
                img_height = img.height / 4.5
                x0 = (page_width - img_width) / 2
                y0 = page_height - img_height - 25
                coords = (x0, y0, x0 + img_width, y0 + img_height)
            else:
                writer.add_page(page)
                continue
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            overlay_path = create_overlay_pdf_with_stamp(stamp_path, page_width, page_height, coords)
            overlay_reader = PdfReader(overlay_path)
            page.merge_page(overlay_reader.pages[0])
            os.remove(overlay_path)
            writer.add_page(page)
            overlay_reader.stream.close()
        temp_out = pdf_path + '.tmp'
        with open(temp_out, 'wb') as f_out:
            writer.write(f_out)
        reader.stream.close()
        writer.close()
        os.replace(temp_out, pdf_path)
    except Exception as e:
        print(f"[!] Не удалось вставить штамп в {pdf_path}: {e}")
        traceback.print_exc()
    return pdf_path


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
    if filtered_filepaths:
        dialog = FileDialog(filtered_filepaths)
        dialog.show()
        dialog.activateWindow()
    else:
        QMessageBox.information(None, 'Ошибка', "Поддерживаемые файлы не обнаружены")
    return dialog


class CustomListWidgetItem(QWidget):
    def __init__(self, file_path, file_id=None, name=None, sig_pages=None):
        super().__init__()
        self.stamp_date = ''
        self.file_path = file_path.lower()
        self.file_path_orig = file_path
        self.is_file_empty = os.path.isfile(file_path) and os.path.getsize(file_path) == 0
        self.gf_file_path = None
        if self.file_path.endswith('.pdf'):
            # Получаем директорию и имя файла
            directory, filename = os.path.split(self.file_path)
            self.gf_file_path = os.path.join(directory, f"gf_{filename}")
        self.file_id = file_id
        self.name = name if name else os.path.basename(file_path)
        self.name = "[ПУСТОЙ ФАЙЛ]" + self.name if self.is_file_empty else self.name
        self.sig_pages = sig_pages
        self.page_fragment = ""  # Переменная для хранения найденного фрагмента
        # Главный горизонтальный layout
        main_layout = QHBoxLayout()
        # Левая часть: чекбокс и лейбл
        left_layout = QHBoxLayout()
        self.chb = QCheckBox()
        self.chb.setDisabled(self.is_file_empty)
        left_layout.addWidget(self.chb)

        self.file_label = QLabel(self.name)
        self.file_label.mouseDoubleClickEvent = self.open_file
        self.file_label.setMinimumWidth(400)
        self.file_label.setToolTip(self.name)
        self.file_label.setWordWrap(True)
        left_layout.addWidget(self.file_label)
        left_layout.addStretch()  # Добавляем растяжение для выравнивания
        main_layout.addLayout(left_layout)
        # Добавляем вертикальную линию
        vertical_line = QFrame()
        vertical_line.setFrameShape(QFrame.VLine)
        vertical_line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(vertical_line)
        # Радиокнопки
        # Правая часть: два горизонтальных блока
        right_layout = QVBoxLayout()
        # Верхний блок с радиокнопками и вводом страниц
        top_radio_layout = QHBoxLayout()
        top_radio_layout.addWidget(QLabel('Страницы штампа: '))
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
        self.radio_custom = QRadioButton("")
        self.radio_custom.setEnabled(self.file_path.endswith('.pdf'))
        self.radio_custom.setMaximumWidth(20)
        top_radio_layout.addWidget(self.radio_none)
        top_radio_layout.addWidget(self.radio_first)
        top_radio_layout.addWidget(self.radio_last)
        top_radio_layout.addWidget(self.radio_all)
        top_radio_layout.addWidget(self.radio_custom)
        # Поле для ввода своих страниц
        self.custom_pages = QLineEdit()
        self.custom_pages.setPlaceholderText("Введите страницы")
        self.custom_pages.setEnabled(self.file_path.endswith('.pdf'))
        self.custom_pages.textEdited.connect(lambda: self.radio_custom.setChecked(True))
        self.custom_pages.editingFinished.connect(self.validate_pages_input)
        self.custom_pages.setFixedWidth(115)  # Фиксированная ширина
        top_radio_layout.addWidget(self.custom_pages)
        if self.sig_pages:
            pagelist = check_chosen_pages(self.sig_pages)
            if pagelist:
                self.custom_pages.setText(', '.join(pagelist))
                self.radio_custom.setChecked(True)  # Явно включаем радиокнопку
        elif self.sig_pages is not None:
            self.radio_none.setChecked(True)
        right_layout.addLayout(top_radio_layout)
        # Нижний блок с радиокнопками и вводом даты
        bottom_radio_layout = QHBoxLayout()
        bottom_radio_layout.addWidget(QLabel('Вид штампа:             '))
        # Создаем отдельную группу для нижнего ряда радиокнопок
        self.stamp_radio_group = QButtonGroup(self)
        self.radio_standard = QRadioButton("Обычн.")
        self.radio_standard.setEnabled(self.file_path.endswith('.pdf'))
        self.radio_standard.setChecked(config.get('default_stamp_type', 0) == 0)
        self.radio_verified_not_in_law = QRadioButton("Коп. верна не вступ.")
        self.radio_verified_not_in_law.setEnabled(self.file_path.endswith('.pdf'))
        self.radio_verified_not_in_law.setChecked(config.get('default_stamp_type', 0) == 1)
        self.radio_verified_in_law = QRadioButton("Коп. верна вступ.")
        self.radio_verified_in_law.setEnabled(self.file_path.endswith('.pdf'))
        # Добавляем кнопки в группу
        self.stamp_radio_group.addButton(self.radio_standard)
        self.stamp_radio_group.addButton(self.radio_verified_not_in_law)
        self.stamp_radio_group.addButton(self.radio_verified_in_law)
        bottom_radio_layout.addWidget(self.radio_standard)
        bottom_radio_layout.addWidget(self.radio_verified_not_in_law)
        bottom_radio_layout.addWidget(self.radio_verified_in_law)
        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("Вступил(дд.мм.гггг)")
        self.date_input.setFixedWidth(115)
        self.date_input.textEdited.connect(lambda: self.radio_verified_in_law.setChecked(True))
        self.parse_file_name_for_pages_and_stamps()
        bottom_radio_layout.addWidget(self.date_input)
        if config.get('default_stamp_type', 0) != 2:
            right_layout.addLayout(bottom_radio_layout)
        # Добавляем правую часть в главный layout
        main_layout.addLayout(right_layout)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setLayout(main_layout)

    def validate_pages_input(self):
        text = self.custom_pages.text().strip()
        if not text:  # пустое — не проверяем
            self.custom_pages.setStyleSheet("")
            return
        try:
            pages = check_chosen_pages(text)
            if pages is None:
                raise ValueError
            # Если всё ок — убираем подсветку
            self.custom_pages.setStyleSheet("")
        except Exception:
            # Подсветка красным
            self.custom_pages.setStyleSheet("background-color: rgba(255, 0, 0, 128);")
            QMessageBox.warning(self, "Ошибка",
                                "Неверно указаны страницы для штампа.\nИспользуйте числа или диапазоны (например, 1-3, 5).")

    def show_context_menu(self, pos):
        menu = QMenu(self)
        open_in_folder_action = QAction("Показать в папке", self)
        open_in_folder_action.triggered.connect(lambda: self.open_in_explorer(self.file_path))
        menu.addAction(open_in_folder_action)
        menu.exec_(self.mapToGlobal(pos))

    def open_file(self, event):
        if self.gf_file_path and os.path.exists(self.gf_file_path):
            os.startfile(os.path.normpath(self.gf_file_path))
        else:
            os.startfile(self.file_path)

    def parse_file_name_for_pages_and_stamps(self):
        # Извлечение страниц из имени файла
        pattern = r'\{(.*?)\}'
        match = re.search(pattern, os.path.basename(self.file_path))
        if match:
            self.page_fragment = match.group(0)
            pages = match.group(1)
            self.custom_pages.setText(pages)
            self.radio_custom.setChecked(True)

        # Извлечение вида штампа и даты
        if "копия" in os.path.basename(self.file_path_orig.lower()):
            if match := re.search(r'копия-(\d{2}\.\d{2}\.\d{4})', os.path.basename(self.file_path)):
                self.stamp_date = match.group(1).split('-', 1)[-1]
                self.radio_verified_in_law.setChecked(True)
                self.date_input.setText(self.stamp_date)
            else:
                self.radio_verified_not_in_law.setChecked(True)

    def get_clean_file_path(self):
        if self.page_fragment:
            return os.path.basename(self.file_path).replace(self.page_fragment, '')
        else:
            return self.file_path

    def set_file_label_background(self, color):
        self.file_label.setStyleSheet(f'background-color: {color}; border-radius: 4px; padding-left: 3px; padding-right: 3px; margin-right: 3px')

    def open_in_explorer(self, filepath: str):
        filepath = filepath.replace('/', '\\')
        subprocess.Popen(fr'explorer /select,"{filepath}')


class FileDialog(QDialog):
    def __init__(self, file_paths, tray_gui=None):
        super().__init__()
        self.current_session_stamps = {}
        self.certs_data = get_cert_data()
        self.tray_gui = tray_gui
        self.setWindowIcon(QIcon(resource_path('icons8-legal-document-64.ico')))
        self.certs_list = list(self.certs_data.keys())
        self.setWindowTitle("Подписание файлов")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        self.resize(600, 500)
        self.setMaximumWidth(1900)
        self.setAcceptDrops(True)
        self.rules_file = os.path.join(config_folder, 'rules.txt')
        # Загрузка и проверка файла по правилам из rules.txt
        if os.path.exists(self.rules_file):
            with open(self.rules_file, 'r') as file:
                self.rules = file.readlines()
        else:
            self.rules = []
        self.instruction_label = QLabel("Укажите страницы для размещения/тип штампа на документе (только для PDF), выберите сертификат из списка и нажмите 'Подписать'")
        font = self.instruction_label.font()
        font.setPointSize(10)
        self.instruction_label.setFont(font)
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.instruction_label)
        self.file_list = QListWidget()
        self.file_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.file_list.setAcceptDrops(True)
        self.file_list.setDropIndicatorShown(True)
        self.file_list.dragEnterEvent = self.dragEnterEvent
        self.file_list.dragMoveEvent = self.dragMoveEvent
        self.file_list.setDragDropMode(QAbstractItemView.DropOnly)
        self.file_list.dropEvent = self.dropEvent_custom
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

        self.sign_original = QCheckBox('Ставить штамп на оригинале документа (Если нет, будет создана копия с нанесенным штампом)')
        self.sign_original.setChecked(config['stamp_on_original'])
        self.sign_original.setToolTip("""
        Если включено, штамп наносится на оригинал, и создается подпись.
        Если выключено, для оригинала создается подпись, а затем создается копия с нанесенным штампом.
        Таким образом оригинал останется чистым и в то же время появится версия для печати.
        """)
        self.sign_original.setFont(font)
        self.layout.addWidget(self.sign_original)
        self.fit_in_a4 = QCheckBox('Масштабировать страницы до формата А4')
        self.fit_in_a4.setChecked(config['normalize_to_a4'])
        self.fit_in_a4.setFont(font)
        self.layout.addWidget(self.fit_in_a4)

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

        self.movie = QMovie(resource_path('35.gif'))
        self.movie.setScaledSize(self.loading_label.size())  # Масштабируем анимацию до размера QLabel

        self.sign_button_chosen = QPushButton("Подписать отмеченные")
        self.sign_button_chosen.setFixedHeight(28)
        self.sign_button_chosen.setFont(font)
        self.sign_button_chosen.clicked.connect(self.sign_chosen)
        layout_buttons.addWidget(self.sign_button_chosen)

        self.layout.addLayout(layout_buttons)

        self.setLayout(self.layout)

    def dragEnterEvent(self, event):
        """Обработка события при перетаскивании объекта."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Разрешить движение курсора при перетаскивании."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent_custom(self, event):
        """Обработка события при отпускании объекта."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                self.append_new_file_to_list(file_path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def request_stamp_positions_from_user(self, files_to_sign):
        for idx in files_to_sign:
            item = self.file_list.item(idx)
            widget = self.file_list.itemWidget(item)
            file_path = widget.file_path
            if file_path.lower().endswith('.pdf'):
                if self.fit_in_a4.isChecked():
                    normalize_pdf_in_place(file_path)
                file_path, pages, stamp = self.get_filepath_and_pages_for_sign(idx)
                stamp_image = create_stamp_image(self.certificate_comboBox.currentText(),
                                                 self.certs_data[self.certificate_comboBox.currentText()], stamp)
                if file_path and pages:
                    file_path_coords = get_stamp_coords_for_filepath(file_path, pages, stamp_image)
                    if file_path_coords and file_path_coords.get(file_path):  # убедимся, что есть хоть одна страница
                        self.current_session_stamps.update(file_path_coords)
                    else:
                        self.current_session_stamps[file_path] = None

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
        self.loading_label.show()
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
        self.block_buttons(True)
        self.loading_label.show()
        self.loading_label.setMovie(self.movie)
        self.movie.start()
        if config.get('stamp_place', 0) == 1:
            self.request_stamp_positions_from_user(files_to_sign)
        if files_to_sign:
            self.thread = SignAllFilesThread(self, files_to_sign)
            self.thread.result.connect(self.on_sign_all_result)
            self.thread.start()
        else:
            QMessageBox.information(self, 'Ничего не выбрано', 'Выберите документы для подписи.')
            self.movie.stop()
            self.loading_label.clear()
            self.block_buttons(False)

    def on_sign_all_result(self, fuckuped_files, index_list_red, index_list_green):
        try:
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
            if self.tray_gui:
                self.tray_gui.update_label_text()
        except:
            traceback.print_exc()

    def block_buttons(self, block):
        self.sign_button_all.setEnabled(not block)
        self.sign_button_chosen.setEnabled(not block)

    def get_filepath_and_pages_for_sign(self, index): ## добавить получение типа штампа
        item = self.file_list.item(index)
        widget = self.file_list.itemWidget(item)
        file_path = widget.file_path
        file_path_clean = widget.get_clean_file_path()
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
        if widget.radio_verified_in_law.isChecked():
            stamp = f'copy-{widget.date_input.text()}'
        elif widget.radio_verified_not_in_law.isChecked():
            stamp = 'copy'
        else:
            stamp = 'regular'
        return file_path, pages, stamp

    def sign_file(self, index):
        try:
            filepath_to_stamp = ''
            file_path, pages, stamp = self.get_filepath_and_pages_for_sign(index)
            print(f"Файл: {file_path}, Страницы: {pages}")
            custom_coords = self.current_session_stamps.get(file_path)
            backup_file = shutil.copy(file_path, file_path + '_bkp')
            if file_path.lower().endswith('.pdf') and (pages or custom_coords):
                stamp_image_path = create_stamp_image(self.certificate_comboBox.currentText(), self.certs_data[self.certificate_comboBox.currentText()], stamp)
                if not self.sign_original.isChecked():
                    filepath_to_stamp = os.path.join(os.path.dirname(file_path),
                                                     f'gf_{os.path.basename(file_path)}')
                    shutil.copy(file_path, filepath_to_stamp)
                    _ = add_stamp(filepath_to_stamp, stamp_image_path, pages, custom_coords)
                else:
                    add_stamp(file_path, stamp_image_path, pages, custom_coords)
            sign_path = sign_document(file_path, self.certs_data[self.certificate_comboBox.currentText()])
            if sign_path:
                os.remove(backup_file)
                for rule in self.rules:
                    source_dir, patterns, dest_dir, _ = rule.strip().split('|')
                    source_dir, patterns, dest_dir = source_dir.lower(), patterns, dest_dir.lower()
                    if file_path.startswith(source_dir):
                        patterns_list = patterns.split(';')
                        all_patterns_match = True
                        for pattern in patterns_list:
                            if not fnmatch.fnmatch(os.path.basename(file_path), pattern):
                                all_patterns_match = False
                                break
                        if all_patterns_match:
                            if os.path.dirname(file_path) != os.path.abspath(dest_dir):
                                new_file_path = os.path.join(dest_dir, os.path.basename(file_path))
                                shutil.move(file_path, dest_dir)
                                shutil.move(sign_path, dest_dir)
                                item = self.file_list.item(index)
                                widget = self.file_list.itemWidget(item)
                                widget.file_path = new_file_path
                                if filepath_to_stamp:
                                    shutil.move(filepath_to_stamp, dest_dir)
            else:
                print(f'Не удалось подписать {file_path}')
                if filepath_to_stamp and os.path.exists(filepath_to_stamp):
                    os.unlink(filepath_to_stamp)
                shutil.move(backup_file, file_path)
                return 1, '', file_path
        except Exception as e:
            print(f'Не удалось подписать: {e}')
            traceback.print_exc()
            return 1, e, file_path
        config['last_cert'] = self.certificate_comboBox.currentText()
        save_config()
        return 0, '', file_path

    def append_new_file_to_list(self, file_path):
        item = QListWidgetItem(self.file_list)
        widget = CustomListWidgetItem(file_path)
        item.setSizeHint(widget.sizeHint())
        if self.width() < widget.sizeHint().width() + 35:
            self.setFixedWidth(widget.sizeHint().width() + 35)
        self.file_list.setItemWidget(item, widget)
        print(file_path, "добавлен в список")
        return 1

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
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect(('localhost', 65432))
            data = '\n'.join(file_paths)  # 🔄 теперь это список строк, включая пути с пробелами
            client_socket.sendall(data.encode('utf-8'))
            client_socket.close()
            return 1
        except ConnectionRefusedError:
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
        self.new_files = []  # Список новых файлов
        self.lock = Lock()
        self.notification_timer = None

    def on_created(self, event):
        if not event.is_directory:
            Thread(target=self.process_file, args=(event.src_path,), daemon=True).start()

    def process_file(self, fp):
        time.sleep(2)  # Ожидание, чтобы сигнатурный файл успел появиться
        fn = os.path.basename(fp.lower())
        fp = fp.lower()
        if fp.endswith(ALLOWED_EXTENTIONS) and not fn.startswith(('~', "gf_")) and not os.path.exists(fp + '.sig') and not os.path.exists(fp + '..sig') and not os.path.exists(fp + '.1.sig'):
            self.add_new_file(fp)

    def add_new_file(self, fp):
        with self.lock:
            self.new_files.append(fp)
            if self.notification_timer is None:
                self.notification_timer = Timer(2, self.send_notification)
                self.notification_timer.start()

    def send_notification(self):
        with self.lock:
            if len(self.new_files) == 1:
                self.notify_callback(self.new_files[0])
            else:
                self.notify_callback(f"{len(self.new_files)} новых файлов")
            self.new_files.clear()
            self.notification_timer = None


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


def update_updater():
    import configparser
    config = configparser.ConfigParser()
    config.read('update.cfg')
    reference_folder = config['Settings']['reference_folder']
    updater_files = ['update.exe', 'update.cfg']
    for file in updater_files:
        local_file_path = os.path.join(os.getcwd(), file)
        reference_file_path = os.path.join(reference_folder, file)
        if os.path.exists(reference_file_path) and os.path.exists(local_file_path):
            if os.path.getmtime(reference_file_path) > os.path.getmtime(local_file_path):
                shutil.copy2(reference_file_path, local_file_path)
                print(f"Updated {file} to the latest version.")
            else:
                print(f'{file} is no need in updates')