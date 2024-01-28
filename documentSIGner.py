from main_functions import *
import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)


@app.route('/get_certs', methods=['GET'])
def get_certs():
    certs_data = get_cert_data(os.path.join(config['csp_path'], 'certmgr.exe'))
    certs_list = list(certs_data.keys())
    return jsonify({'certificates': certs_list, 'last_cert': config['last_cert']})


@app.route('/sign_file', methods=['POST'])
def sign_file():
    file_to_sign = request.files['file']
    sig_pages = request.form['sigPages']
    selected_cert = request.headers.get('Selected-Certificate')

    # Подписываем файл и наносим штампы
    # ...

    signed_file_path = 'path_to_signed_file'  # Путь к подписанному файлу
    modified_document_path = 'path_to_modified_document'  # Путь к измененному документу

    # Создаем ZIP-архив
    zip_path = 'path_to_zip_file.zip'
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        zipf.write(signed_file_path, os.path.basename(signed_file_path))
        zipf.write(modified_document_path, os.path.basename(modified_document_path))

    return send_file(zip_path, as_attachment=True)


# Запуск Flask приложения
if __name__ == '__main__':
    app.run(debug=True, port=config['port'])
