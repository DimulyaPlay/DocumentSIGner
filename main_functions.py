import json
import io
import os
import socket
import shutil
import traceback
import subprocess
import re
import sys
import locale
import tempfile
from functools import lru_cache
from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import ArrayObject, Fit, FloatObject, NameObject, RectangleObject
from threading import Lock, Timer, Thread
from reportlab.pdfgen import canvas
import winreg as reg
from PySide2.QtWidgets import (QAbstractItemView, QAction, QDialog,
                               QMenu, QVBoxLayout, QListWidget, QTableWidget,
                               QTableWidgetItem, QListWidgetItem, QHBoxLayout,
                               QLabel, QRadioButton, QLineEdit, QPushButton,
                               QFileDialog, QWidget, QComboBox, QCheckBox, QMessageBox,
                               QButtonGroup, QFrame)
from PySide2.QtCore import Qt, QThread, Signal
from PySide2.QtGui import QIcon, QMovie
from PIL import Image, ImageDraw, ImageFont
from queue import Queue
import fnmatch
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
config_folder = os.path.join(os.path.expanduser('~/Documents'), 'DocumentSIGner')
os.makedirs(config_folder, exist_ok=True)
config_file = os.path.join(config_folder, 'config.json')
file_paths_queue = Queue()

ALLOWED_EXTENSIONS = ('.blp', '.bmp', '.dib', '.bufr', '.cur', '.pcx', '.dcx', '.dds', '.ps', '.eps', '.fit',
               '.fits', '.fli', '.flc', '.fpx', '.ftc', '.ftu', '.gbr', '.gif', '.grib', '.h5', '.hdf',
               '.png', '.apng', '.jp2', '.j2k', '.jpc', '.jpf', '.jpx', '.j2c', '.icns', '.ico', '.im',
               '.iim', '.tif', '.tiff', '.jfif', '.jpe', '.jpg', '.jpeg', '.mic', '.mpg', '.mpeg', '.mpo',
               '.msp', '.palm', '.pcd', '.pxr', '.pbm', '.pgm', '.ppm', '.pnm', '.psd', '.bw',
               '.rgb', '.rgba', '.sgi', '.ras', '.tga', '.icb', '.vda', '.vst', '.webp', '.wmf', '.emf',
               '.xbm', '.xpm', '.doc', '.docx', '.pdf', '.docm', '.xlsm',
               '.rtf', '.ods', '.odt', '.xlsx', '.xls', '.txt')
# Совместимость со старыми внешними импортами с опечаткой.
ALLOWED_EXTENTIONS = ALLOWED_EXTENSIONS


def _write_json_atomic(path, value):
    directory = os.path.dirname(path) or '.'
    fd, temp_path = tempfile.mkstemp(prefix='.config-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as configfile:
            json.dump(value, configfile, ensure_ascii=False, indent=4)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def read_create_config(config_path):
    default_configuration = {
        "stamp_on_original": True,
        "csp_path": r"C:\Program Files\Crypto Pro\CSP",
        'last_cert': '',
        'widget_visible': False,
        "context_menu": False,
        'autorun': False,
        'default_page': 2,
        'stamp_place': 1,
        'notify': False,
        'normalize_to_a4': False
    }

    configuration = default_configuration.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as configfile:
                configuration_opened = json.load(configfile)
                if isinstance(configuration_opened, dict):
                    configuration.update(configuration_opened)
        except Exception as e:
            print(f'Не удалось прочитать конфигурацию: {e}')
    if not os.path.exists(config_path) or configuration != locals().get('configuration_opened'):
        _write_json_atomic(config_path, configuration)
    return configuration


def save_config():
    _write_json_atomic(config_file, config)


config = read_create_config(config_file)


@lru_cache(maxsize=1)
def get_console_encoding():
    try:
        result = subprocess.run('chcp',
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                shell=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        output_raw = result.stdout or b''
    except Exception:
        return locale.getpreferredencoding(False) or 'cp866'

    output = ''
    for candidate_encoding in ('cp866', 'cp1251', locale.getpreferredencoding(False), 'utf-8'):
        if not candidate_encoding:
            continue
        try:
            output = output_raw.decode(candidate_encoding)
            break
        except UnicodeDecodeError:
            continue
    if not output:
        output = output_raw.decode('cp866',
                                   errors='ignore')

    match = re.search(r'(\d+)',
                      output)
    if match:
        codepage = int(match.group(1))
        return f'cp{codepage}'
    return locale.getpreferredencoding(False) or 'cp866'


SUBJECT_CN_RE = re.compile(r'(?:^|,\s*)CN=([^,]+)')
_certificate_cache = {'loaded_at': 0.0, 'data': {}}
_certificate_cache_lock = Lock()
CERTIFICATE_CACHE_SECONDS = 30


def get_cert_data(force_refresh=False):
    with _certificate_cache_lock:
        cache_age = time.monotonic() - _certificate_cache['loaded_at']
        if not force_refresh and cache_age < CERTIFICATE_CACHE_SECONDS:
            return _certificate_cache['data'].copy()

    encoding = get_console_encoding()
    cert_mgr_path = os.path.join(config['csp_path'], 'certmgr.exe')
    certs_data = {}
    if os.path.exists(cert_mgr_path):
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
                        if base_name is None and key in ('Субъект', 'Subject'):
                            m = SUBJECT_CN_RE.search(val)
                            if m:
                                base_name = m.group(1).strip()
                if base_name:
                    exp_date = cert.get('Истекает', cert.get('Not valid after', ' '))[:10].replace('/', '.')
                    candidate = f"{base_name} ({exp_date})" if exp_date.strip() else base_name
                    if candidate in certs_data:
                        suffix = 1
                        while f"{candidate} ({suffix})" in certs_data:
                            suffix += 1
                        candidate = f"{candidate} ({suffix})"
                    cert['__base_name'] = base_name
                    certs_data[candidate] = cert
        except subprocess.CalledProcessError as e:
            print(f"Ошибка выполнения команды: {e}")
    with _certificate_cache_lock:
        _certificate_cache['loaded_at'] = time.monotonic()
        _certificate_cache['data'] = certs_data
    return certs_data.copy()


def filter_inappropriate_files(file_paths):
    return [file_path for file_path in file_paths if
     file_path.lower().endswith(ALLOWED_EXTENSIONS) and not os.path.basename(file_path).startswith(('~', "gf_"))]


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


def decode_document(s_source_file, cert_data):
    parent_dir = os.path.dirname(s_source_file)
    file_name = os.path.basename(s_source_file)              # Archive_...zip.enc
    base_name = file_name[:-4]                               # Archive_...zip
    # Делаем папку с суффиксом .decoded
    folder_name = f"{file_name}.decoded"
    output_dir = os.path.join(parent_dir, folder_name)
    os.makedirs(output_dir, exist_ok=True)
    decoded_path = os.path.join(output_dir, base_name)
    command = [
        os.path.join(config['csp_path'], 'csptest.exe'),
        "-sfenc", "-decrypt",
        "-in", s_source_file,
        "-out", decoded_path,
        "-my", cert_data.get('SHA1 отпечаток', cert_data.get('SHA1 Hash', '')),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding='cp866',
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    if result.returncode == 2148081675:
        print('Не удалось найти закрытый ключ для расшифровки')
        return False
    for _ in range(10):
        if os.path.exists(decoded_path):
            # Переносим исходный .enc в папку
            try:
                new_enc_path = os.path.join(output_dir, file_name)
                if os.path.abspath(s_source_file) != os.path.abspath(new_enc_path):
                    shutil.move(s_source_file, new_enc_path)
                return True
            except Exception as e:
                print(f"Не удалось переместить {s_source_file} в {output_dir}: {e}")
                return False
        time.sleep(0.1)
    print("Warning: decoded file not found after decryption")
    return False


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
                start, end = map(int, part.split('-', 1))
                if start < 1 or end < 1:
                    raise ValueError
                if start > end:
                    start, end = end, start  # Переставляем местами, если диапазон введен в обратном порядке
                pages.update(range(start - 1, end))  # Индексация с нуля
            else:
                page = int(part)
                if page < 1:
                    raise ValueError
                pages.add(page - 1)  # Добавляем одиночные страницы, с учетом индексации с нуля
    except ValueError:
        print("Invalid input format. Use numbers or ranges like '1-3, 5'.")
        return None
    return sorted(pages)


A4_PORTRAIT = (595.275590551, 841.88976378)
PDF_COORDINATE_DECIMAL_PLACES = 5
PDF_POINT_ARRAY_KEYS = ('/QuadPoints', '/Vertices', '/L', '/CL')
PDF_PAGE_REPLACED_KEYS = {
    '/Contents', '/Resources', '/Annots', '/MediaBox', '/CropBox',
    '/BleedBox', '/TrimBox', '/ArtBox', '/Rotate', '/UserUnit', '/VP'
}


def _pdf_coordinate(value):
    """Keep generated PDF geometry within legacy Acrobat numeric limits."""
    return FloatObject(f'{float(value):.{PDF_COORDINATE_DECIMAL_PLACES}f}')


def _pdf_rectangle(values):
    return RectangleObject(tuple(_pdf_coordinate(value) for value in values))


def _compact_transformation(transform):
    return tuple(_pdf_coordinate(value) for value in transform.ctm)


def _page_is_a4(page, tolerance=2.0):
    user_unit = float(page.user_unit)
    width = float(page.mediabox.width) * user_unit
    height = float(page.mediabox.height) * user_unit
    a4_width, a4_height = A4_PORTRAIT
    return (
        abs(width - a4_width) <= tolerance and abs(height - a4_height) <= tolerance
    ) or (
        abs(width - a4_height) <= tolerance and abs(height - a4_width) <= tolerance
    )


def _rotation_to_content_transform(page):
    rotation = int(page.rotation) % 360
    if not rotation:
        return None
    media_box = page.mediabox
    center_x = float(media_box.left + media_box.width / 2)
    center_y = float(media_box.bottom + media_box.height / 2)
    transform = Transformation().translate(-center_x, -center_y).rotate(-rotation)
    corners = (
        media_box.lower_left, media_box.upper_left,
        media_box.upper_right, media_box.lower_right,
    )
    transformed = [transform.apply_on((float(point[0]), float(point[1]))) for point in corners]
    return transform.translate(
        -min(point[0] for point in transformed),
        -min(point[1] for point in transformed),
    )


def _transform_flat_points(values, transform):
    if not isinstance(values, ArrayObject) or len(values) % 2:
        return
    for index in range(0, len(values), 2):
        x, y = transform.apply_on((float(values[index]), float(values[index + 1])))
        values[index] = _pdf_coordinate(x)
        values[index + 1] = _pdf_coordinate(y)


def _transform_annotation_geometry(page, transform):
    annotation_refs = page.get('/Annots')
    if annotation_refs is None:
        return
    annotation_refs = annotation_refs.get_object()
    if not isinstance(annotation_refs, ArrayObject):
        return
    for annotation_ref in annotation_refs:
        annotation = annotation_ref.get_object()
        rectangle = annotation.get('/Rect')
        if isinstance(rectangle, ArrayObject) and len(rectangle) == 4:
            left, bottom, right, top = (float(value) for value in rectangle)
            corners = (
                (left, bottom), (left, top), (right, top), (right, bottom)
            )
            transformed = [transform.apply_on(point) for point in corners]
            annotation[NameObject('/Rect')] = _pdf_rectangle((
                min(point[0] for point in transformed),
                min(point[1] for point in transformed),
                max(point[0] for point in transformed),
                max(point[1] for point in transformed),
            ))
        for key in PDF_POINT_ARRAY_KEYS:
            _transform_flat_points(annotation.get(key), transform)
        ink_lists = annotation.get('/InkList')
        if isinstance(ink_lists, ArrayObject):
            for ink_points in ink_lists:
                _transform_flat_points(ink_points, transform)


def _transfer_rotation_to_content(page, transform):
    """Apply rotation while keeping coordinates safe for legacy PDF readers."""
    page.rotation = 0
    page.add_transformation(_compact_transformation(transform))
    for box_name in ('/MediaBox', '/CropBox', '/BleedBox', '/TrimBox', '/ArtBox'):
        if box_name not in page:
            continue
        box = RectangleObject(page[box_name])
        corners = (
            box.lower_left, box.upper_left, box.upper_right, box.lower_right,
        )
        transformed = [
            transform.apply_on((float(point[0]), float(point[1])))
            for point in corners
        ]
        page[NameObject(box_name)] = _pdf_rectangle((
            min(point[0] for point in transformed),
            min(point[1] for point in transformed),
            max(point[0] for point in transformed),
            max(point[1] for point in transformed),
        ))


def _fit_page_to_a4(page, writer):
    original_parent = page.get('/Parent')
    rotation_transform = _rotation_to_content_transform(page)
    if rotation_transform is not None:
        _transform_annotation_geometry(page, rotation_transform)
        _transfer_rotation_to_content(page, rotation_transform)

    visible_box = RectangleObject(page.cropbox)
    source_width = float(visible_box.width)
    source_height = float(visible_box.height)
    if source_width <= 0 or source_height <= 0:
        raise ValueError('PDF содержит страницу с некорректным размером')

    portrait_width, portrait_height = A4_PORTRAIT
    if source_width > source_height:
        target_width, target_height = portrait_height, portrait_width
    else:
        target_width, target_height = portrait_width, portrait_height
    scale = min(target_width / source_width, target_height / source_height)
    fitted_width = source_width * scale
    fitted_height = source_height * scale
    offset_x = (target_width - fitted_width) / 2
    offset_y = (target_height - fitted_height) / 2
    fit_transform = Transformation((
        scale, 0, 0, scale,
        offset_x - float(visible_box.left) * scale,
        offset_y - float(visible_box.bottom) * scale,
    ))
    page.add_transformation(_compact_transformation(fit_transform))
    _transform_annotation_geometry(page, fit_transform)

    # merge_page clips by TrimBox. Point it at the transformed CropBox so that
    # content hidden by the source PDF does not reappear in the A4 margins.
    page.trimbox = _pdf_rectangle((
        offset_x, offset_y, offset_x + fitted_width, offset_y + fitted_height
    ))
    target_page = PageObject.create_blank_page(
        pdf=page.pdf,
        width=_pdf_coordinate(target_width),
        height=_pdf_coordinate(target_height),
    )
    target_page.merge_page(page)
    # Content streams must be indirect PDF objects. add_page() normally performs
    # this step, but here the existing page object is replaced in place so that
    # outlines and AcroForm references keep pointing to the same page.
    contents = target_page.get('/Contents')
    if contents is not None and not hasattr(contents, 'idnum'):
        target_page[NameObject('/Contents')] = writer._add_object(contents)

    # Keep page-level features (parent tree, transitions, structure references),
    # while geometry and content come from the normalized A4 page.
    for key, value in page.items():
        if key not in PDF_PAGE_REPLACED_KEYS and key not in target_page:
            target_page[key] = value
    if original_parent is not None:
        target_page[NameObject('/Parent')] = original_parent
    page.clear()
    page.update(target_page)


def _copy_pdf_outline(items, reader, writer, parent=None):
    last_outline_item = None
    for item in items:
        if isinstance(item, list):
            if last_outline_item is not None:
                _copy_pdf_outline(item, reader, writer, parent=last_outline_item)
            continue
        page_number = reader.get_destination_page_number(item)
        if page_number is None or page_number < 0:
            last_outline_item = None
            continue
        fit = Fit(item.typ, tuple(item.dest_array[2:]))
        color = item.color
        if color is not None:
            color = tuple(float(component) for component in color)
        font_format = int(item.font_format or 0)
        last_outline_item = writer.add_outline_item(
            item.title,
            page_number,
            parent=parent,
            color=color,
            bold=bool(font_format & 2),
            italic=bool(font_format & 1),
            fit=fit,
        )


def _copy_pdf_catalog_features(reader, writer):
    # Preserve non-page catalog features in the actual output catalog.
    source_catalog = reader.trailer['/Root'].get_object()
    output_catalog = writer.root_object
    for key, value in source_catalog.items():
        if key in ('/Type', '/Pages', '/Outlines'):
            continue
        output_catalog[NameObject(key)] = value.clone(writer)


def normalize_pdf_in_place(file_path: str):
    reader = None
    writer = None
    output_path = None
    try:
        reader = PdfReader(file_path, strict=False)
        if reader.is_encrypted and not reader.decrypt(''):
            raise ValueError('Невозможно привести к A4 защищённый паролем PDF')
        if not reader.pages:
            raise ValueError('PDF не содержит страниц')
        original_page_count = len(reader.pages)
        pages_to_normalize = [index for index, page in enumerate(reader.pages) if not _page_is_a4(page)]
        if not pages_to_normalize:
            return False

        writer = PdfWriter()
        source_outline = reader.outline
        writer.clone_document_from_reader(reader)
        _copy_pdf_catalog_features(reader, writer)
        if reader.metadata:
            writer.add_metadata(reader.metadata)
        for page_index in pages_to_normalize:
            _fit_page_to_a4(writer.pages[page_index], writer)
        if source_outline:
            # clone_document_from_reader copies the catalog reference but not a
            # writable outline tree. Rebuild it against the cloned page objects.
            writer._root_object.pop('/Outlines', None)
            _copy_pdf_outline(source_outline, reader, writer)

        output_fd, output_path = tempfile.mkstemp(
            prefix='.document-signer-', suffix='.pdf', dir=os.path.dirname(file_path) or '.'
        )
        with os.fdopen(output_fd, 'wb') as output_file:
            writer.write(output_file)
            output_file.flush()
            os.fsync(output_file.fileno())
        writer.close()
        writer = None
        reader.stream.close()
        reader = None

        validation_reader = PdfReader(output_path, strict=False)
        try:
            if len(validation_reader.pages) != original_page_count:
                raise ValueError('После преобразования изменилось количество страниц PDF')
            if not all(_page_is_a4(page) for page in validation_reader.pages):
                raise ValueError('Проверка результата A4 не пройдена')
        finally:
            validation_reader.stream.close()
        os.replace(output_path, file_path)
        output_path = None
        return True
    finally:
        if writer is not None:
            writer.close()
        if reader is not None and reader.stream:
            reader.stream.close()
        if output_path and os.path.exists(output_path):
            os.unlink(output_path)


def get_stamp_coords_for_filepath(file_path, pages, stamp_image):
    from stamp_editor import PlaceImageStampOnA4
    dialog = PlaceImageStampOnA4(file_path, pages, stamp_image)
    if dialog.exec_() == QDialog.Accepted:
        results = {}
        pdf_reader = PdfReader(file_path)
        # Берём все данные, сохранённые в диалоге
        dialog_data = dialog.get_results()[file_path]
        print(dialog_data)
        try:
            for page_idx, data in dialog_data.items():
                if data is None:
                    results[page_idx] = None
                    continue
                page = pdf_reader.pages[page_idx]
                real_width = float(page.mediabox.width)
                real_height = float(page.mediabox.height)
                page_image_w, page_image_h = data.get(
                    'page_size', (dialog.page_frame.width(), dialog.page_frame.height())
                )
                scale_x = real_width / page_image_w
                scale_y = real_height / page_image_h
                disp_x, disp_y = data['position']
                x = disp_x * scale_x
                y = disp_y * scale_y
                disp_stamp_w = dialog.stamp_widget.stamp_original.width() * data['scale']
                disp_stamp_h = dialog.stamp_widget.stamp_original.height() * data['scale']
                w = disp_stamp_w * scale_x
                h = disp_stamp_h * scale_y
                results[page_idx] = (x, y, x + w, y + h)
        finally:
            pdf_reader.stream.close()
        if results:
            print(results)
            return {file_path: results}
        else:
            return None
    return None


def create_stamp_image(cert_name, cert_info, stamp='regular'):
    fingerprint = cert_info.get('Серийный номер', cert_info.get('Serial', ' '))
    create_date = cert_info.get('Выдан', cert_info.get('Not valid before', ' '))[:10].replace('/','.')
    exp_date = cert_info.get('Истекает', cert_info.get('Not valid after', ' '))[:10].replace('/','.')
    base_name = cert_info.get('__base_name', cert_name)
    stamp_path = add_text_to_stamp(base_name, fingerprint, create_date, exp_date, stamp)
    return stamp_path


def add_text_to_stamp(cert_name, fingerprint, create_date, exp_date, stamp='regular'):
    template_path_main = os.path.join(os.path.dirname(sys.argv[0]), 'dcs.png')
    template_path_copy = os.path.join(os.path.dirname(sys.argv[0]), 'dcs-copy.png')
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
    if stamp == 'copy':
        template_path = template_path_copy
        text_positions = text_positions_copy
    elif stamp == 'copy-nolaw':
        template_path = template_path_copy_no_in_law
        text_positions = text_positions_copy
    elif stamp.startswith('copy-'):  # copy-<дата>
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
    draw.text(text_positions['create_date'],"                          " + f"c {create_date} по {exp_date}",fill='blue',font=font)
    # Добавляем дату для сценария copy-<дата>
    if stamp.startswith('copy-') and stamp not in ('copy', 'copy-nolaw'):
        in_law_date = stamp.split('-', 1)[1]
        draw.text(text_positions['in_law_date'],f"Вступил в законную силу {in_law_date}",fill='blue',font=ImageFont.truetype(font_path, 34))
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
    except OSError:
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


def add_stamp(pdf_path, stamp_path, pagelist, custom_coords=None):
    custom_coords = custom_coords or {}

    def create_overlay_pdf_with_stamp(image_path, page_width, page_height, coords):
        overlay_stream = io.BytesIO()
        c = canvas.Canvas(overlay_stream, pagesize=(page_width, page_height))
        x0, y0, x1, y1 = coords
        width = x1 - x0
        height = y1 - y0
        y_rl = page_height - y1  # корректируем Y для ReportLab (0 внизу)
        c.drawImage(image_path, x0, y_rl, width=width, height=height, mask='auto')
        c.showPage()
        c.save()
        overlay_stream.seek(0)
        return overlay_stream

    temp_out = pdf_path + '.tmp'
    overlay_streams = []
    reader = None
    writer = None
    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        source_outline = reader.outline
        writer.clone_document_from_reader(reader)
        _copy_pdf_catalog_features(reader, writer)
        if reader.metadata:
            writer.add_metadata(reader.metadata)
        if source_outline:
            writer._root_object.pop('/Outlines', None)
            _copy_pdf_outline(source_outline, reader, writer)
        total_pages = len(reader.pages)
        if pagelist == 'all':
            pages_to_stamp = list(range(total_pages))
        else:
            pages_to_stamp = [(total_pages - 1 if p == -1 else p) for p in pagelist]
        if custom_coords or config.get('stamp_place', 0) == 1:
            pages_to_stamp = [k for k in custom_coords.keys()]
        print('Добавление штампа на страницы', pages_to_stamp)
        with Image.open(stamp_path) as stamp_image:
            stamp_size = (stamp_image.width / 4.5, stamp_image.height / 4.5)
        for idx, page in enumerate(writer.pages):
            if custom_coords and idx in custom_coords:
                coords = custom_coords[idx]
                if coords is None:
                    continue
            elif idx in pages_to_stamp:
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)
                img_width, img_height = stamp_size
                x0 = (page_width - img_width) / 2
                y0 = page_height - img_height - 25
                coords = (x0, y0, x0 + img_width, y0 + img_height)
            else:
                continue
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            overlay_stream = create_overlay_pdf_with_stamp(stamp_path, page_width, page_height, coords)
            # pypdf resolves some merged objects only during writer.write(). Keep
            # every in-memory overlay alive until the resulting PDF is serialized.
            overlay_streams.append(overlay_stream)
            overlay_reader = PdfReader(overlay_stream)
            # merge_page() does not import indirect objects from another PDF into
            # an already populated writer. Without cloning, the overlay's resource
            # references keep their original object numbers; in the output those
            # numbers can point to unrelated objects (for example /Catalog instead
            # of a Form XObject), producing a structurally invalid PDF.
            overlay_page = overlay_reader.pages[0].clone(writer)
            page.merge_page(overlay_page)
            contents = page.get('/Contents')
            if contents is not None and not hasattr(contents, 'idnum'):
                page[NameObject('/Contents')] = writer._add_object(contents)
        with open(temp_out, 'wb') as f_out:
            writer.write(f_out)
        os.replace(temp_out, pdf_path)
    except Exception as e:
        print(f"[!] Не удалось вставить штамп в {pdf_path}: {e}")
        traceback.print_exc()
        raise
    finally:
        for overlay_stream in overlay_streams:
            overlay_stream.close()
        if os.path.exists(temp_out):
            os.unlink(temp_out)
        if reader and reader.stream:
            reader.stream.close()
        if writer:
            writer.close()
    return pdf_path


def parse_rule_line(rule):
    """Возвращает четыре поля корректного правила или None для пустой/битой строки."""
    parts = [part.strip() for part in rule.strip().split('|')]
    return tuple(parts) if len(parts) == 4 else None


def get_matching_destination(file_path, rules):
    normalized_file = os.path.normcase(os.path.abspath(file_path))
    filename = os.path.basename(normalized_file)
    for rule in rules:
        parsed = parse_rule_line(rule)
        if not parsed:
            continue
        source_dir, patterns, destination, _ = parsed
        normalized_source = os.path.normcase(os.path.abspath(source_dir))
        try:
            if os.path.commonpath((normalized_file, normalized_source)) != normalized_source:
                continue
        except ValueError:
            continue
        pattern_list = [pattern.strip().lower() for pattern in patterns.split(';') if pattern.strip()]
        if pattern_list and all(fnmatch.fnmatch(filename.lower(), pattern) for pattern in pattern_list):
            return os.path.abspath(destination)
    return None


def execute_sign_job(job):
    """Подписывает один файл без обращения к Qt-виджетам (безопасно для QThread)."""
    file_path = job['file_path']
    stamped_copy = ''
    signature_path = f'{file_path}.sig'
    signature_existed = os.path.exists(signature_path)
    backup_path = None
    backup_ready = False
    moved_paths = []
    try:
        backup_fd, backup_path = tempfile.mkstemp(
            prefix=f'.{os.path.basename(file_path)}-', suffix='.bkp',
            dir=os.path.dirname(file_path) or '.',
        )
        os.close(backup_fd)
        shutil.copy2(file_path, backup_path)
        backup_ready = True
        pages = job['pages']
        custom_coords = job['custom_coords']
        if file_path.lower().endswith('.pdf') and (pages or custom_coords):
            stamp_image_path = create_stamp_image(job['certificate_name'], job['certificate_data'], job['stamp'])
            if not job['sign_original'] and not job['is_epos']:
                stamped_copy = os.path.join(os.path.dirname(file_path), f'gf_{os.path.basename(file_path)}')
                shutil.copy2(file_path, stamped_copy)
                add_stamp(stamped_copy, stamp_image_path, pages, custom_coords)
            else:
                add_stamp(file_path, stamp_image_path, pages, custom_coords)

        sign_path = sign_document(file_path, job['certificate_data'])
        if not sign_path:
            raise RuntimeError('Не удалось создать файл подписи')

        new_file_path = file_path
        destination = get_matching_destination(file_path, job['rules'])
        if destination and os.path.normcase(os.path.abspath(os.path.dirname(file_path))) != os.path.normcase(destination):
            if not os.path.isdir(destination):
                raise FileNotFoundError(f'Папка назначения не найдена: {destination}')
            for source in (file_path, sign_path, stamped_copy):
                if not source:
                    continue
                target = os.path.join(destination, os.path.basename(source))
                shutil.move(source, target)
                moved_paths.append((source, target))
            new_file_path = os.path.join(destination, os.path.basename(file_path))

        os.unlink(backup_path)
        return 0, '', file_path, new_file_path
    except Exception as error:
        rollback_errors = []
        for source, target in reversed(moved_paths):
            try:
                if os.path.exists(target) and not os.path.exists(source):
                    shutil.move(target, source)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        try:
            if backup_ready and backup_path and os.path.exists(backup_path):
                os.replace(backup_path, file_path)
            elif backup_path and os.path.exists(backup_path):
                os.unlink(backup_path)
        except OSError as rollback_error:
            rollback_errors.append(str(rollback_error))
        for generated_path in (stamped_copy, None if signature_existed else signature_path):
            try:
                if generated_path and os.path.exists(generated_path):
                    os.unlink(generated_path)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        message = str(error)
        if rollback_errors:
            message += f"; ошибки отката: {'; '.join(rollback_errors)}"
        return 1, message, file_path, file_path


def resource_path(relative_path):
    """ Возвращает корректный путь для доступа к ресурсам для PyInstaller """
    try:
        # PyInstaller создает временную папку и устанавливает переменную _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


_EPOS_RE = re.compile(
    r"^(?P<base>.+?)_EPOS_"
    r"(?P<message_id>\d+)-(?P<attachment_id>\d+)-(?P<stamp_type>\d+)-"
    r"(?P<stamp_date>\d+)-(?P<stamp_page_mode>\d+)-(?P<stamp_page_custom>[0-9,\-]+)$"
)


def parse_epos_filename(filename: str):
    """
    None -> обычный файл (игнор)
    dict -> EPOS-файл (параметры есть)
    """
    name, ext = os.path.splitext(filename)
    if "_EPOS_" not in name:
        return None
    m = _EPOS_RE.match(name)
    if not m:
        return None
    g = m.groupdict()

    # yyyymmdd -> dd.mm.yyyy (для UI)
    ddmmyyyy = ""
    d = int(g["stamp_date"])
    if d:
        s = f"{d:08d}"
        ddmmyyyy = f"{s[6:8]}.{s[4:6]}.{s[0:4]}"

    return {
        "original_filename": 'Email_' + g["base"] + ext,
        "message_id": int(g["message_id"]),
        "attachment_id": int(g["attachment_id"]),
        "stamp_type_code": int(g["stamp_type"]),          # 0..4
        "stamp_date_ui": ddmmyyyy,                        # "" или "dd.mm.yyyy"
        "stamp_page_mode_code": int(g["stamp_page_mode"]),# 0..4
        "stamp_page_custom": g["stamp_page_custom"],      # "0" или "1,2,4-6"
    }


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
        # Нижний блок с выбором вида штампа (фиксированный ряд)
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)
        bottom_layout.addWidget(QLabel('Вид штампа:'))
        # Радио-кнопки
        self.stamp_radio_group = QButtonGroup(self)
        self.radio_standard = QRadioButton("Обычный")
        self.radio_standard.setEnabled(self.file_path.endswith('.pdf'))
        self.radio_copy_group = QRadioButton("Копия верна")
        self.radio_copy_group.setEnabled(self.file_path.endswith('.pdf'))

        self.stamp_radio_group.addButton(self.radio_standard)
        self.stamp_radio_group.addButton(self.radio_copy_group)

        bottom_layout.addWidget(self.radio_standard)
        bottom_layout.addWidget(self.radio_copy_group)

        # Комбобокс (занимает место всегда)
        self.copy_combo = QComboBox()
        self.copy_combo.addItems([
            "Коп. верна",
            "Коп. верна не вступ. в з.с.",
            "Коп. верна вступ. в з.с."
        ])
        self.copy_combo.setFixedWidth(180)   # фикс ширину, чтобы не прыгал
        self.copy_combo.setEnabled(False)    # выключен, пока не выбрано "Копия верна"
        bottom_layout.addWidget(self.copy_combo)
        # Поле даты (занимает место всегда)
        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("Вступил(дд.мм.гггг)")
        self.date_input.setFixedWidth(115)
        self.date_input.setEnabled(False)
        bottom_layout.addWidget(self.date_input)

        # Логика переключений
        def on_copy_selected():
            self.copy_combo.setEnabled(self.radio_copy_group.isChecked())
            if not self.radio_copy_group.isChecked():
                self.date_input.setEnabled(False)
        self.radio_standard.toggled.connect(on_copy_selected)
        self.radio_copy_group.toggled.connect(on_copy_selected)

        def on_combo_changed(index):
            self.date_input.setEnabled(index == 2 and self.radio_copy_group.isChecked())
        self.copy_combo.currentIndexChanged.connect(on_combo_changed)

        # Установка значений по умолчанию из конфига
        default_stamp_type = config.get('default_stamp_type', 0)

        if default_stamp_type == 0:
            self.radio_standard.setChecked(True)
        elif default_stamp_type == 1:
            self.radio_copy_group.setChecked(True)
            self.copy_combo.setEnabled(True)
            self.copy_combo.setCurrentIndex(0)
        elif default_stamp_type == 2:
            # Автовыбор — оставляем "Обычный", но позже в логике можно скрыть элементы
            self.radio_standard.setChecked(True)

        right_layout.addLayout(bottom_layout)
        # Добавляем правую часть в главный layout
        main_layout.addLayout(right_layout)
        self.apply_epos_params_if_any()
        if not getattr(self, "epos_applied", False):
            self.parse_file_name_for_pages_and_stamps()
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
        target_path = self.gf_file_path if (self.gf_file_path and os.path.exists(self.gf_file_path)) else self.file_path
        if not os.path.exists(target_path):
            QMessageBox.warning(
                None,
                "Файл не найден",
                f"Файл «{os.path.basename(target_path)}» пропал из папки, возможно, его переименовали."
            )
            parent = self.parent()
            if isinstance(parent,
                          QListWidget):
                row = parent.indexAt(self.pos()).row()
                parent.takeItem(row)
            return
        os.startfile(target_path)

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
        filename_lower = os.path.basename(self.file_path_orig).lower()
        if "копия" in filename_lower:
            self.radio_copy_group.setChecked(True)
            self.copy_combo.setEnabled(True)
            from datetime import datetime
            if match := re.search(r'копия-(\d{2}\.\d{2}\.\d{4})', filename_lower):
                try:
                    date_obj = datetime.strptime(match.group(1), "%d.%m.%Y").date()
                    today = datetime.today().date()
                    if date_obj > today:
                        self.copy_combo.setCurrentIndex(1)  # "Коп. верна не вступ. в з.с."
                    else:
                        self.copy_combo.setCurrentIndex(2)  # "Коп. верна вступ. в з.с."
                        self.date_input.setEnabled(True)
                        self.date_input.setText(match.group(1))
                except ValueError:
                    self.copy_combo.setCurrentIndex(0)
            else:
                self.copy_combo.setCurrentIndex(0)
                self.date_input.setEnabled(False)

    def apply_epos_params_if_any(self):
        info = parse_epos_filename(os.path.basename(self.file_path_orig))
        if not info:
            self.epos_applied = False
            return
        self.epos_applied = True
        self.epos_info = info  # если нужно дальше (attachment_id и т.п.)
        # Красиво показываем исходное имя (без суффикса), но путь оставляем реальный
        self.name = info["original_filename"]
        self.file_label.setText(self.name if not self.is_file_empty else "[ПУСТОЙ ФАЙЛ]" + self.name)
        self.file_label.setToolTip(self.name)
        # Автовыбор на подпись
        self.chb.setChecked(True)
        # --- страницы штампа ---
        pm = info["stamp_page_mode_code"]
        if not self.file_path.endswith('.pdf'):
            self.radio_none.setChecked(True)
        else:
            if pm == 0:
                self.radio_none.setChecked(True)
            elif pm == 1:
                self.radio_first.setChecked(True)
            elif pm == 2:
                self.radio_last.setChecked(True)
            elif pm == 3:
                self.radio_all.setChecked(True)
            elif pm == 4:
                self.radio_custom.setChecked(True)
                pc = info["stamp_page_custom"]
                # "0" считаем как пусто
                self.custom_pages.setText("" if pc == "0" else pc)
        # --- вид штампа ---
        st = info["stamp_type_code"]
        # 1=standard
        if st == 1:
            self.radio_standard.setChecked(True)
        elif st in (2, 3, 4):
            self.radio_copy_group.setChecked(True)
            self.copy_combo.setEnabled(True)
            self.copy_combo.setCurrentIndex(1)
            # если дата есть — считаем, что "вступ. в з.с."
            if info["stamp_date_ui"]:
                self.copy_combo.setCurrentIndex(2)
                self.date_input.setEnabled(True)
                self.date_input.setText(info["stamp_date_ui"])
            else:
                self.copy_combo.setCurrentIndex(0)
                self.date_input.setEnabled(False)
                self.date_input.setText("")

    def get_clean_file_path(self):
        if self.page_fragment:
            directory, filename = os.path.split(self.file_path)
            clean_name = filename.replace(self.page_fragment, '')
            return os.path.join(directory, clean_name)
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
        self.reload_rules()
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

    def reload_rules(self):
        try:
            with open(self.rules_file, 'r') as rules_file:
                self.rules = rules_file.readlines()
        except FileNotFoundError:
            self.rules = []

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
                file_path, pages, stamp, _ = self.get_filepath_and_pages_for_sign(idx)
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

    def validate_file_existence(self,
                                indexes):
        """Проверяет, что все выбранные файлы существуют"""
        missing = []
        for idx in indexes:
            item = self.file_list.item(idx)
            widget = self.file_list.itemWidget(item)
            if not os.path.exists(widget.file_path):
                missing.append(widget.file_path)
        if missing:
            msg = '\n'.join(os.path.basename(fp) for fp in missing)
            QMessageBox.warning(
                self,
                "Файлы не найдены",
                f"Файлы пропали из папки (возможно, были переименованы):\n\n{msg}"
            )
            # Удаляем отсутствующие из списка
            for idx in sorted(indexes,
                              reverse=True):
                item = self.file_list.item(idx)
                widget = self.file_list.itemWidget(item)
                if not os.path.exists(widget.file_path):
                    row = self.file_list.row(item)
                    self.file_list.takeItem(row)
            return False
        return True

    def sign_all(self):
        self.current_session_stamps = {}
        self.reload_rules()
        if self.certificate_comboBox.currentText() not in self.certs_data:
            QMessageBox.warning(self, 'Сертификат не выбран', 'Выберите доступный сертификат для подписи.')
            return
        self.block_buttons(True)
        files_to_sign = self.get_file_indexes_for_sign(all=True)
        if not self.validate_file_existence(files_to_sign):
            self.block_buttons(False)
            return
        self.loading_label.show()
        self.loading_label.setMovie(self.movie)
        self.movie.start()
        if config.get('stamp_place', 0) == 1:
            files_to_sign = self.get_file_indexes_for_sign(all=True)
            self.request_stamp_positions_from_user(files_to_sign)
        jobs = [(index, self.build_sign_job(index)) for index in files_to_sign]
        self.thread = SignAllFilesThread(jobs, self)
        self.thread.result.connect(self.on_sign_all_result)
        self.thread.start()

    def sign_chosen(self):
        self.current_session_stamps = {}
        self.reload_rules()
        if self.certificate_comboBox.currentText() not in self.certs_data:
            QMessageBox.warning(self, 'Сертификат не выбран', 'Выберите доступный сертификат для подписи.')
            return
        files_to_sign = self.get_file_indexes_for_sign()
        self.block_buttons(True)
        self.loading_label.show()
        self.loading_label.setMovie(self.movie)
        self.movie.start()
        if not self.validate_file_existence(files_to_sign):
            self.movie.stop()
            self.loading_label.clear()
            self.block_buttons(False)
            return
        if config.get('stamp_place', 0) == 1:
            self.request_stamp_positions_from_user(files_to_sign)
        if files_to_sign:
            jobs = [(index, self.build_sign_job(index)) for index in files_to_sign]
            self.thread = SignAllFilesThread(jobs, self)
            self.thread.result.connect(self.on_sign_all_result)
            self.thread.start()
        else:
            QMessageBox.information(self, 'Ничего не выбрано', 'Выберите документы для подписи.')
            self.movie.stop()
            self.loading_label.clear()
            self.block_buttons(False)

    def on_sign_all_result(self, failed_files, index_list_red, index_list_green, moved_files):
        try:
            self.movie.stop()
            self.loading_label.clear()
            self.block_buttons(False)
            for idx in index_list_green:
                item = self.file_list.item(idx)
                widget = self.file_list.itemWidget(item)
                if idx in moved_files:
                    widget.file_path = moved_files[idx]
                    widget.file_path_orig = moved_files[idx]
                    widget.file_label.setToolTip(os.path.basename(moved_files[idx]))
                widget.set_file_label_background("rgba(0, 128, 0, 128)")
            if index_list_green:
                config['last_cert'] = self.certificate_comboBox.currentText()
                save_config()
            if failed_files:
                for idx in index_list_red:
                    item = self.file_list.item(idx)
                    widget = self.file_list.itemWidget(item)
                    widget.set_file_label_background("rgba(255, 0, 0, 128)")
                msg_lst = [f'{os.path.basename(fp)} — {err}' for fp, err in failed_files.items()]
                msg_str = '\n'.join(msg_lst)
                QMessageBox.warning(self, 'Ошибка', f'Возникли ошибки со следующими документами:\n{msg_str}')
            else:
                QMessageBox.information(self, 'Успех', 'Создание подписи завершено.')
            if self.tray_gui:
                self.tray_gui.update_label_text()
        except Exception:
            traceback.print_exc()

    def block_buttons(self, block):
        self.sign_button_all.setEnabled(not block)
        self.sign_button_chosen.setEnabled(not block)

    def get_filepath_and_pages_for_sign(self, index):
        item = self.file_list.item(index)
        widget = self.file_list.itemWidget(item)
        file_path = widget.file_path
        file_path_clean = widget.get_clean_file_path()
        if file_path != file_path_clean:
            try:
                if not os.path.exists(file_path_clean):  # только если нового файла ещё нет
                    shutil.move(file_path, file_path_clean)
                file_path = file_path_clean
                widget.file_path = file_path_clean
                widget.file_path_orig = file_path_clean
                widget.file_label.setToolTip(os.path.basename(file_path_clean))
                widget.file_label.setText(os.path.basename(file_path_clean))
            except Exception as e:
                print(f"[!] Ошибка при переименовании {file_path} -> {file_path_clean}: {e}")
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
        if widget.radio_standard.isChecked():
            stamp = 'regular'
        elif widget.radio_copy_group.isChecked():
            current_text = widget.copy_combo.currentText()
            if current_text.startswith("Коп. верна вступ"):
                date_val = widget.date_input.text().strip()
                stamp = f'copy-{date_val}'
            elif current_text.startswith("Коп. верна не вступ"):
                stamp = 'copy-nolaw'
            else:
                stamp = 'copy'
        else:
            stamp = 'regular'
        is_epos = bool(getattr(widget, 'epos_applied', False) or getattr(widget, 'epos_info', None))
        return file_path, pages, stamp, is_epos

    def build_sign_job(self, index):
        file_path, pages, stamp, is_epos = self.get_filepath_and_pages_for_sign(index)
        certificate_name = self.certificate_comboBox.currentText()
        return {
            'file_path': file_path,
            'pages': pages,
            'stamp': stamp,
            'is_epos': is_epos,
            'custom_coords': self.current_session_stamps.get(file_path),
            'certificate_name': certificate_name,
            'certificate_data': self.certs_data[certificate_name].copy(),
            'sign_original': self.sign_original.isChecked(),
            'rules': tuple(self.rules),
        }

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
    attempts = 10
    for _ in range(attempts):
        try:
            with socket.create_connection(('localhost', 65432), timeout=0.5) as client_socket:
                data = '\n'.join(file_paths)
                client_socket.sendall(data.encode('utf-8'))
            return 1
        except OSError:
            time.sleep(0.2)
    return 0


class QueueMonitorThread(QThread):
    file_path_signal = Signal(str)
    def run(self):
        while True:
            file_path = file_paths_queue.get()
            if file_path is None:
                file_paths_queue.task_done()
                break
            self.file_path_signal.emit(file_path)
            file_paths_queue.task_done()


class SignAllFilesThread(QThread):
    result = Signal(dict, object, object, dict)

    def __init__(self, jobs, parent=None):
        super().__init__(parent)
        self.jobs = jobs

    def run(self):
        failed_files = {}
        redlist = []
        greenlist = []
        moved_files = {}
        for index, job in self.jobs:
            res, err, file_path, new_file_path = execute_sign_job(job)
            if res:
                failed_files[file_path] = str(err)
                redlist.append(index)
            else:
                greenlist.append(index)
                if new_file_path != file_path:
                    moved_files[index] = new_file_path
        self.result.emit(failed_files, redlist, greenlist, moved_files)


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
        time.sleep(8)  # Ожидание, чтобы сигнатурный файл успел появиться
        fn = os.path.basename(fp).lower()
        if fp.lower().endswith(ALLOWED_EXTENSIONS) and not fn.startswith(('~', "gf_")) and not os.path.exists(fp + '.sig') and not os.path.exists(fp + '..sig') and not os.path.exists(fp + '.1.sig'):
            self.add_new_file(fp)

    def add_new_file(self, fp):
        if not os.path.exists(fp):
            return  # файл уже исчез
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

    def start(self):
        event_handler = FileWatchHandler(self.notify_callback)
        self.observer.schedule(event_handler, self.directory_to_watch, recursive=False)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        if self.observer.is_alive():
            self.observer.join(timeout=2)


def update_updater():
    import configparser
    updater_config = configparser.ConfigParser()
    app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    updater_config.read(os.path.join(app_dir, 'Update.cfg'), encoding='utf-8')
    reference_folder = updater_config.get('Settings', 'reference_folder', fallback='').strip()
    if not reference_folder:
        return
    for filename in ('Update.exe', 'Update.cfg'):
        local_file_path = os.path.join(app_dir, filename)
        reference_file_path = os.path.join(reference_folder, filename)
        if not os.path.isfile(reference_file_path):
            continue
        if not os.path.exists(local_file_path) or os.path.getmtime(reference_file_path) > os.path.getmtime(local_file_path):
            shutil.copy2(reference_file_path, local_file_path)
            print(f"Updated {filename} to the latest version.")


def install_certificates():
    """
    Устанавливает все сертификаты (.cer, .crt, .pem) из папки root_certificates
    в хранилище "Промежуточные центры сертификации" (CA)
    текущего пользователя (CurrentUser).
    """
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    cert_dir = os.path.join(exe_dir, 'root_certificates')
    if not os.path.exists(cert_dir):
        try:
            os.mkdir(cert_dir)
        except OSError:
            print(f"Папка не найдена и не удалось создать: {cert_dir}")
            return
    cert_extensions = (".cer", ".crt", ".pem")
    for filename in os.listdir(cert_dir):
        if not filename.lower().endswith(cert_extensions):
            continue
        cert_path = os.path.join(cert_dir, filename)
        try:
            subprocess.run(
                ["certutil", "-user", "-addstore", "CA", cert_path],
                check=True,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            print(f"Сертификат установлен в CA: {cert_path}")
        except subprocess.CalledProcessError as error:
            print(f"Не удалось установить сертификат {cert_path}: {error}")
