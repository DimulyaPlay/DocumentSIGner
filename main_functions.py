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
import fitz
import requests


config_path = os.path.dirname(sys.argv[0])
if not os.path.exists(config_path):
    os.mkdir(config_path)
config_file = os.path.join(config_path, 'config.json')

fingerprint_names = ('Серийный номер',)
date_make = ('Выдан',)
date_exp = ('Истекает',)


def read_create_config(config_file):
    default_configuration = {
        'comboBox_certs': 'Сертификат не выбран',
        'lineEdit_address': '127.0.0.1:5000',
        'lineEdit_login': '',
        'lineEdit_password': '',
        'rules': {},
        "csp_path": r"C:\Program Files\Crypto Pro\CSP"
    }
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as configfile:
                config = json.load(configfile)
        except Exception as e:
            print(e)
            os.remove(config_file)
            config = default_configuration
            with open(config_file, 'w') as configfile:
                json.dump(config, configfile)
    else:
        config = default_configuration
        with open(config_file, 'w') as configfile:
            json.dump(config, configfile)
    return config


config = read_create_config(config_file)


def save_config(config):
    try:
        with open(config_file, 'w') as json_file:
            json.dump(config, json_file)
        config = read_create_config(config_file)
    except:
        traceback.print_exc()


def get_cert_data(cert_mgr_path):
    if os.path.exists(cert_mgr_path):
        certs_data = {}
        try:
            result = subprocess.run([cert_mgr_path, '-list'], capture_output=True, text=True, check=True, encoding='cp866', creationflags=subprocess.CREATE_NO_WINDOW)
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


def is_file_locked(filepath):
    try:
        file_handle = open(filepath, 'a')
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except:
        return False


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
    create_date = cert_info.get('Выдан', cert_info.get('Not valid before', ' '))
    exp_date = cert_info.get('Истекает', cert_info.get('Not valid after', ' '))
    stamp_path = add_text_to_stamp(template_png_path, cert_name, fingerprint, create_date, exp_date)
    stamped_doc = add_stamp_to_pages(doc_path, stamp_path, pagelist)
    return stamped_doc


def add_text_to_stamp(template_path, cert_name, fingerprint, create_date, exp_date):
    template_image = Image.open(template_path)
    draw = ImageDraw.Draw(template_image)
    font_path = 'times.ttf'
    font = ImageFont.truetype(font_path, 22)
    text_positions = {
        'cert_name': (20, 145),
        'fingerprint': (20, 175),
        'create_date': (20, 205),
        'exp_date': (20, 235),
    }
    draw.text(text_positions['cert_name'], "Владелец сертификата: " + cert_name, fill='blue', font=font)
    draw.text(text_positions['fingerprint'], "Сертификат: " + fingerprint[2:], fill='blue', font=font)
    draw.text(text_positions['create_date'], "Действителен с: " + create_date, fill='blue', font=font)
    draw.text(text_positions['exp_date'], "Действителен по: " + exp_date, fill='blue', font=font)
    modified_image_path = "modified_stamp.png"
    template_image.save(modified_image_path)
    return modified_image_path


def add_stamp_to_pages(pdf_path, modified_stamp_path, pagelist):
    doc = fitz.open(pdf_path)
    img_stamp = fitz.Pixmap(modified_stamp_path)  # Загружаем изображение
    if pagelist == 'all':
        for page in doc:
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
            page_index = page-1
            if page == -1:
                page_index = -1
            img_width, img_height = img_stamp.width / 4.5, img_stamp.height / 4.5
            page_width = doc[page_index].rect.width
            page_height = doc[page_index].rect.height
            x0 = (page_width/2)
            y0 = page_height-img_height-25
            x1 = x0 + img_width
            y1 = y0 + img_height
            img_rect = fitz.Rect(x0, y0, x1, y1)
            doc[page_index].insert_image(img_rect, pixmap=img_stamp)
    doc.saveIncr()
    return pdf_path


def login(username, password, address):
    try:
        login_url = f'http://{address}/login'
        session = requests.Session()
        login_payload = {'first_name': username, 'password': password, 'lite': True}
        login_response = session.post(login_url, data=login_payload)
        if login_response.status_code == 200:
            print('login success')
            return session
        else:
            print('login failed')
            return None
    except:
        print('connection failed')
        traceback.print_exc()
        return None



def get_filelist(session, address):
    filelist_url = f'http://{address}/get_judge_filelist'
    filelist_response = session.get(filelist_url)
    return filelist_response.json()
