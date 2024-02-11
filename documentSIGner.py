from main_functions import *
import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import tempfile
import zipfile
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import QTranslator, QLocale, QLibraryInfo
from threading import Thread
from glob import glob
import time

app = Flask(__name__)
CORS(app)

certs_data = get_cert_data(os.path.join(config['csp_path'], 'certmgr.exe'))

if os.path.exists('./confirmations'):
    files = glob('confirmations/*')
    for file in files:
        os.remove(file)
else:
    os.mkdir('./confirmations')


class SystemTrayGui(QtWidgets.QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.setToolTip(f'DocumentSIGner на порту {config["port"]}')
        menu = QtWidgets.QMenu(parent)
        exit_action = menu.addAction("Выход")
        exit_action.triggered.connect(self.exit)
        self.setContextMenu(menu)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.check_for_sign_requests)
        self.timer.start(500)  # Проверка каждую секунду

    def check_for_sign_requests(self):
        for file_path in glob("confirmations/waiting_*"):
            file_name = file_path.split("_", 1)[1]
            user_decision = self.confirm_signing(file_name)
            if user_decision:
                os.rename(file_path, f"accepted_{file_name}")
            else:
                os.rename(file_path, f"declined_{file_name}")

    def confirm_signing(self, file_name):
        msg_box = QtWidgets.QMessageBox()
        msg_box.setWindowIcon(QtGui.QIcon('icons8-legal-document-64.ico'))
        msg_box.setIcon(QtWidgets.QMessageBox.Question)
        msg_box.setWindowTitle("Получен запрос на подпись.")
        msg_box.setText(f"Вы хотите подписать файл {file_name}?")
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        msg_box.setWindowFlags(msg_box.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        return_value = msg_box.exec()
        return return_value == QtWidgets.QMessageBox.Yes

    def exit(self):
        QtWidgets.QApplication.quit()


@app.route('/get_certs', methods=['GET'])
def get_certs():
    global certs_data
    certs_data = get_cert_data(os.path.join(config['csp_path'], 'certmgr.exe'))
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
        file_to_sign.save(filepath_to_sign)
        if file_type and sig_pages:
            pages = check_chosen_pages(sig_pages)
            if pages:
                filepath_to_sign = add_stamp(filepath_to_sign, selected_cert, certs_data[selected_cert], pages)
        filepath_sig = sign_document(filepath_to_sign, certs_data[selected_cert])
        if os.path.isfile(filepath_sig):
            fd, zip_to_send = tempfile.mkstemp(f'.zip')
            os.close(fd)
            with zipfile.ZipFile(zip_to_send, 'w') as zipf:
                zipf.write(filepath_to_sign, os.path.basename(filepath_to_sign))
                zipf.write(filepath_sig, os.path.basename(filepath_sig))
            return send_file(zip_to_send, as_attachment=True)
        else:
            message = 'Не удалось подписать документ'
            return jsonify({'error': True, 'message': message})
    except Exception as e:
        traceback.print_exc()
        message = f'Не удалось подписать документ: {e}'
        return jsonify({'error': True, 'message': message})

def run_flask():
    app.run(debug=True, port=config['port'], use_reloader=False)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    translator = QTranslator()
    locale = QLocale.system().name()  # Получение системной локали
    path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)  # Путь к переводам Qt
    translator.load("qtbase_" + locale, path)
    app.installTranslator(translator)
    # Запускаем Flask в отдельном потоке
    thread = Thread(target=run_flask)
    thread.daemon = True
    thread.start()
    global tray_gui
    tray_gui = SystemTrayGui(QtGui.QIcon('icons8-legal-document-64.ico'))
    tray_gui.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
