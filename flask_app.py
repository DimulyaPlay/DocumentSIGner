from main_functions import get_cert_data, config
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import tempfile
import zipfile
import os
import shutil
import traceback

app = Flask(__name__)
CORS(app)


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