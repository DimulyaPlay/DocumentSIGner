from main_functions import *
import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import tempfile
import zipfile

app = Flask(__name__)
CORS(app)

certs_data = get_cert_data(os.path.join(config['csp_path'], 'certmgr.exe'))

@app.route('/get_certs', methods=['GET'])
def get_certs():
    global certs_data
    certs_data = get_cert_data(os.path.join(config['csp_path'], 'certmgr.exe'))
    certs_list = list(certs_data.keys())
    return jsonify({'certificates': certs_list, 'last_cert': config['last_cert']})


@app.route('/sign_file', methods=['POST'])
def sign_file():
    file_to_sign = request.files['file']
    sig_pages = request.form.get('sigPages')
    file_type = request.form.get('fileType')
    selected_cert = request.form.get('selectedCert')
    if not selected_cert and selected_cert not in list(certs_data.keys()):
        message = 'Данные сертиката не обнаружены'
        return jsonify({'success':False, 'message':message})
    fd, filepath_to_sign = tempfile.mkstemp(f'.{file_type}')
    os.close(fd)
    file_to_sign.save(filepath_to_sign)
    if file_type and sig_pages:
        pages = check_chosen_pages(sig_pages)
        if pages:
            filepath_to_sign = add_stamp(filepath_to_sign, selected_cert, certs_data[selected_cert], pages)
            os.startfile(filepath_to_sign)
    filepath_sig = sign_document(filepath_to_sign, certs_data[selected_cert])
    if os.path.isfile(filepath_sig):
        fd, zip_to_send = tempfile.mkstemp(f'.zip')
        os.close(fd)
        with zipfile.ZipFile(zip_to_send, 'w') as zipf:
            zipf.write(filepath_to_sign, os.path.basename(filepath_to_sign))
            zipf.write(filepath_sig, os.path.basename(filepath_sig))
        os.startfile(zip_to_send)
        return send_file(zip_to_send, as_attachment=True)
    else:
        message = 'Не удалось подписать документ'
        return jsonify({'success':False, 'message':message})


# Запуск Flask приложения
if __name__ == '__main__':
    app.run(debug=True, port=config['port'])
