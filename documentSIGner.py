from main_functions import *

# C:/Users/dimas/DocumentSIGner/venv/Scripts/pyinstaller.exe --noconfirm --onedir  --console --windowed --icon C:/Users/dimas/DocumentSIGner/icons8-legal-document-64.ico --add-data "C:/Users/dimas/DocumentSIGner/UI;UI" "C:/Users/dimas/DocumentSIGner/documentSIGner.py"
# C:/Users/CourtUser/Desktop/release/DocumentSIGner/venv/Scripts/pyinstaller.exe --noconfirm --onedir --windowed --icon C:/Users/CourtUser/Desktop/release/DocumentSIGner/icons8-legal-document-64.ico --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/UI;UI" --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/dcs.png;." --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/times.ttf;." "C:/Users/CourtUser/Desktop/release/DocumentSIGner/documentSIGner.py"
# C:/Users/CourtUser/Desktop/release/DocumentSIGner/venv/Scripts/pyinstaller.exe --noconfirm --onedir  --console --icon C:/Users/CourtUser/Desktop/release/DocumentSIGner/icons8-legal-document-64.ico --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/UI;UI" --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/dcs.png;." --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/times.ttf;." "C:/Users/CourtUser/Desktop/release/DocumentSIGner/documentSIGner.py"
import os
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from PyQt5.QtWidgets import QApplication, QMessageBox
from threading import Thread

app = Flask(__name__)

# Укажите папку для сохранения загруженных документов
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}  # Разрешенные расширения файлов

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Флаг для отслеживания подтверждения на стороне клиента
confirmation_received = False


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Функция для отображения окна подтверждения на стороне клиента
def show_confirmation_dialog():
    global confirmation_received
    app = QApplication([])
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText("Вы уверены, что хотите подписать документ?")
    msg_box.setWindowTitle("Подтверждение")
    msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

    # Запустите цикл обработки событий для отображения окна
    result = msg_box.exec_()

    if result == QMessageBox.Yes:
        confirmation_received = True


# Маршрут для получения списка установленных сертификатов
@app.route('/get_certs', methods=['GET'])
def get_certs():
    # Ваш код для получения списка сертификатов
    # Верните список в формате JSON, например:
    certs_list = [
        {'name': 'Cert1', 'issuer': 'Issuer1'},
        {'name': 'Cert2', 'issuer': 'Issuer2'},
        # Добавьте дополнительные данные о сертификатах
    ]
    return jsonify({'certificates': certs_list})


# Маршрут для создания файла подписи для переданного документа
@app.route('/create_sign', methods=['POST'])
def create_sign():
    global confirmation_received
    # Проверьте, что файл был отправлен в запросе

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'})

    confirmation_thread = Thread(target=show_confirmation_dialog)
    confirmation_thread.start()
    confirmation_thread.join()

    file = request.files['file']

    # Проверьте, что файл имеет разрешенное расширение
    if file and allowed_file(file.filename):
        # Сохраните файл в папку uploads
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        if confirmation_received:
            signature_file = f"signature_for_{filename}.txt"
            return jsonify({'signature_file': signature_file})
        else:
            return jsonify({'error': 'Operation canceled by user'})
    else:
        return jsonify({'error': 'Invalid file'})


# Запуск Flask приложения
if __name__ == '__main__':
    app.run(debug=True, port=4999)









# Маршрут для создания файла подписи для переданного документа
@app.route('/create_sign', methods=['POST'])
def create_sign():
    # Проверьте, что файл был отправлен в запросе
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'})

    file = request.files['file']

    # Проверьте, что файл имеет разрешенное расширение
    if file and allowed_file(file.filename):
        # Сохраните файл в папку uploads
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Ваш код для создания файла подписи
        # Верните файл подписи в формате, который вам необходим
        signature_file = f"signature_for_{filename}.txt"

        return jsonify({'signature_file': signature_file})
    else:
        return jsonify({'error': 'Invalid file'})


# Запуск Flask приложения
if __name__ == '__main__':
    app.run(debug=True, port=5000)

