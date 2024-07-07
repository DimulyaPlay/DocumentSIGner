import shutil
from main_functions import *
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import tempfile
import zipfile
from PySide2 import QtWidgets, QtGui, QtCore
from PySide2.QtCore import QTranslator, QLocale, QLibraryInfo
from widget_ui import Ui_MainWindow
from threading import Thread
from glob import glob
import time
import logging

app = Flask(__name__)
CORS(app)
# C:\Users\CourtUser\Desktop\release\DocumentSIGner\venv\Scripts\pyinstaller.exe --windowed --icon "C:\Users\CourtUser\Desktop\release\DocumentSIGner\icons8-legal-document-64.ico" --add-data "C:\Users\CourtUser\Desktop\release\DocumentSIGner\icons8-legal-document-64.ico;." --add-data "C:\Users\CourtUser\Desktop\release\DocumentSIGner\dcs.png;."  C:\Users\CourtUser\Desktop\release\DocumentSIGner\documentSIGner.py

logging.getLogger("PySide2").setLevel(logging.WARNING)
log_path = os.path.join(os.path.dirname(sys.argv[0]), 'log.log')
logging.basicConfig(filename=log_path, level=logging.ERROR)


def exception_hook(exc_type, exc_value, exc_traceback):
    """
    Функция для перехвата исключений и отображения диалогового окна с ошибкой.
    """
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    error_dialog = QtWidgets.QErrorMessage()
    error_dialog.showMessage(error_msg)
    error_dialog.exec_()
    sys.__excepthook__(exc_type, exc_value, exc_traceback)



sys.excepthook = exception_hook
certs_data = get_cert_data()

if os.path.exists('./confirmations'):
    files = glob('confirmations/*')
    for file in files:
        os.remove(file)
else:
    os.mkdir('./confirmations')


class SystemTrayGui(QtWidgets.QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.activated.connect(self.show_menu)
        self.soed = None
        menu = QtWidgets.QMenu(parent)
        self.toggle_soed_server = menu.addAction("СО ЭД сервер")
        self.toggle_soed_server.setCheckable(True)
        self.toggle_soed_server.triggered.connect(self.toggle_soed)
        self.toggle_widget_visible = menu.addAction("Отображать виджет")
        self.toggle_widget_visible.setCheckable(True)
        self.toggle_widget_visible.triggered.connect(self.toggle_widget)
        self.toggle_stamp_on_original = menu.addAction("Штамп на оригинале")
        self.toggle_stamp_on_original.setCheckable(True)
        self.toggle_stamp_on_original.triggered.connect(self.toggle_stamp)
        exit_action = menu.addAction("Выход")
        exit_action.triggered.connect(self.exit)
        self.setContextMenu(menu)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.check_for_sign_requests)
        self.timer.start(1000)  # Проверка каждую секунду
        self.widget = QtWidgets.QMainWindow()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.widget)
        self.widget.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.widget.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        # Запускаем Flask в отдельном потоке
        if config['soed']:
            self.toggle_soed_server.setChecked(True)
            self.soed = Thread(target=run_flask, daemon=True)
            self.soed.start()
            self.setToolTip(f'DocumentSIGner на порту {config["port"]}')
        else:
            self.setToolTip(f'DocumentSIGner отключен от сети.')
        if config['stamp_on_original']:
            self.toggle_stamp_on_original.setChecked(True)
        if config['widget_visible']:
            self.toggle_widget_visible.setChecked(True)
            self.widget.show()
        # Запуск сокет-сервера в отдельном потоке
        self.socket_server_thread = Thread(target=self.run_socket_server, daemon=True)
        self.socket_server_thread.start()

    def check_for_sign_requests(self):
        for file_path in glob("confirmations/waiting_*"):
            file_name = file_path.split("_", 1)[1]
            user_decision = self.confirm_signing(file_name)
            if user_decision:
                os.rename(file_path, f"accepted_{file_name}")
            else:
                os.rename(file_path, f"declined_{file_name}")

    def show_menu(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            self.contextMenu().popup(QtGui.QCursor.pos())

    def toggle_widget(self, event=None):
        if self.toggle_widget_visible.isChecked():
            self.widget.show()
            config['widget_visible'] = True
        else:
            self.widget.hide()
            config['widget_visible'] = False
        save_config()

    def toggle_soed(self):
        if self.toggle_soed_server.isChecked():
            self.soed = Thread(target=run_flask, daemon=True)
            self.soed.start()
            config['soed'] = True
            self.setToolTip(f'DocumentSIGner на порту {config["port"]}')
        else:
            self.soed = None
            config['soed'] = False
            self.setToolTip(f'DocumentSIGner отключен от сети.')
        save_config()

    def toggle_stamp(self):
        if self.toggle_stamp_on_original.isChecked():
            config['stamp_on_original'] = True
        else:
            self.soed = None
            config['stamp_on_original'] = False
        save_config()

    def confirm_signing(self, file_name):
        msg_box = QtWidgets.QMessageBox()
        msg_box.setWindowIcon(QtGui.QIcon(resource_path('icons8-legal-document-64.ico')))
        msg_box.setIcon(QtWidgets.QMessageBox.Question)
        msg_box.setWindowTitle("Получен запрос на подпись.")
        msg_box.setText(f"Вы хотите подписать файл {file_name}?")
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        msg_box.setWindowFlags(msg_box.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        return_value = msg_box.exec()
        return return_value == QtWidgets.QMessageBox.Yes

    def run_socket_server(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(('localhost', 65432))
        server_socket.listen()
        while True:
            conn, addr = server_socket.accept()
            with conn:
                data = b''
                while True:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                if data:
                    file_paths = data.decode().split('\n')
                    file_paths = [fp for fp in file_paths if fp]  # Удаление пустых строк
                    print(f"Received file paths: {file_paths}")
                    self.dialog = handle_dropped_files(file_paths)

    def exit(self):
        QtWidgets.QApplication.quit()


@app.route('/get_certs', methods=['GET'])
def get_certs():
    global certs_data
    certs_data = get_cert_data()
    certs_list = list(certs_data.keys())
    return jsonify({'certificates': certs_list, 'last_cert': config['last_cert']})


@app.route('/sign_file', methods=['POST'])
def sign_file():
    try:
        file_name = request.form.get('fileName')
        temp_file_path = f"./confirmations/waiting_{file_name}"
        open(temp_file_path, 'w').close()
        waiting_result = 0
        for _ in range(30):
            if os.path.exists(f"accepted_{file_name}"):
                os.remove(f"accepted_{file_name}")
                waiting_result = 1
                break
            elif os.path.exists(f"declined_{file_name}"):
                os.remove(f"declined_{file_name}")
                waiting_result = 2
                break
            time.sleep(0.5)
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if waiting_result == 0:
            return jsonify({'error': True, 'message': 'Время ожидания истекло'})
        elif waiting_result == 2:
            return jsonify({'error': True, 'message': 'Клиент отказал в подписи.'})
        file_to_sign = request.files['file']
        sig_pages = request.form.get('sigPages')
        file_type = request.form.get('fileType')
        selected_cert = request.form.get('selectedCert')
        if not selected_cert and selected_cert not in list(certs_data.keys()):
            message = 'Данные сертиката не обнаружены'
            return jsonify({'error': True, 'message': message})
        fd, filepath_to_sign = tempfile.mkstemp(f'.{file_type}')
        os.close(fd)
        filepath_to_stamp = os.path.join(os.path.dirname(filepath_to_sign), f'gf_{os.path.basename(filepath_to_sign)}')
        file_to_sign.save(filepath_to_sign)
        shutil.copy(filepath_to_sign, filepath_to_stamp)
        if file_type and sig_pages:
            pages = check_chosen_pages(sig_pages)
            if pages:
                filepath_to_stamp = add_stamp(filepath_to_stamp, selected_cert, certs_data[selected_cert], pages)
        filepath_sig = sign_document(filepath_to_sign, certs_data[selected_cert])
        if os.path.isfile(filepath_sig):
            fd, zip_to_send = tempfile.mkstemp(f'.zip')
            os.close(fd)
            with zipfile.ZipFile(zip_to_send, 'w') as zipf:
                zipf.write(filepath_to_sign, os.path.basename(filepath_to_sign))
                zipf.write(filepath_sig, os.path.basename(filepath_sig))
                zipf.write(filepath_to_stamp, os.path.basename(filepath_to_stamp))
            return send_file(zip_to_send, as_attachment=True)
        else:
            message = 'Не удалось подписать документ'
            return jsonify({'error': True, 'message': message})
    except Exception as e:
        traceback.print_exc()
        message = f'Не удалось подписать документ: {e}'
        return jsonify({'error': True, 'message': message})


def run_flask():
    app.run(host="127.0.0.1", port=config['port'], use_reloader=False, debug=False)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    translator = QTranslator()
    locale = QLocale.system().name()  # Получение системной локали
    path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)  # Путь к переводам Qt
    translator.load("qtbase_" + locale, path)
    app.installTranslator(translator)
    global tray_gui
    tray_gui = SystemTrayGui(QtGui.QIcon(resource_path('icons8-legal-document-64.ico')))
    tray_gui.show()
    if len(sys.argv) > 1:
        file_paths = sys.argv[1:]
        send_file_paths_to_existing_instance(file_paths)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
