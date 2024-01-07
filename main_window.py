import sys
import os
import traceback
from PyQt5.QtWidgets import QMainWindow, QLineEdit, QComboBox, QFileDialog,\
    QPushButton, QFrame, QMessageBox, QTableWidget, QTableWidgetItem
from PyQt5.QtGui import QIcon
from PyQt5 import uic, Qt
from main_functions import *
from editor_window import EditorWindow
from connection_window import ConnectionWindow
import tempfile


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        ui_file = 'UI/main.ui'
        uic.loadUi(ui_file, self)
        icon = QIcon("UI/icons8-legal-document-64.png")
        self.setWindowIcon(icon)
        self.config = config
        if all([self.config['lineEdit_login'], self.config['lineEdit_password'], self.config['lineEdit_address']]):
            self.session = Connection(self.config['lineEdit_login'], self.config['lineEdit_password'], self.config['lineEdit_address'])
        else:
            self.session = None
        self.comboBox_certs = self.findChild(QComboBox, 'comboBox_certs')
        self.cert_names = get_cert_data(os.path.join(self.config['csp_path'], 'certmgr.exe'))
        self.comboBox_certs.addItems(self.cert_names.keys())
        if config['comboBox_certs'] in self.cert_names:
            self.comboBox_certs.setCurrentText(config['comboBox_certs'])
        self.comboBox_certs.currentTextChanged.connect(self.save_params)
        self.pushButton_editor = self.findChild(QPushButton, 'pushButton_editor')
        self.pushButton_editor.clicked.connect(self.open_editor)

        self.pushButton_connection = self.findChild(QPushButton, 'pushButton_connection')
        self.pushButton_connection.clicked.connect(self.open_connection)

        self.frame_dropzone = self.findChild(QFrame, 'frame_dropzone')
        self.frame_dropzone.dragEnterEvent = self.custom_drag_enter_event
        self.frame_dropzone.dropEvent = self.custom_drop_event

        self.tableWidget = self.findChild(QTableWidget, 'tableWidget')
        self.tableWidget.doubleClicked.connect(lambda item: self.double_click_handler(item))
        self.tableWidget.setContentsMargins(3, 3, 3, 3)
        self.tableWidget.setColumnWidth(0, 300)
        self.tableWidget.setColumnWidth(1, 100)
        self.update_file_list()
        self.show()

    def custom_drag_enter_event(self, event):
        mime_data = event.mimeData()
        if mime_data.hasUrls() and all(url.toLocalFile().lower().endswith('.pdf') for url in mime_data.urls()):
            event.acceptProposedAction()

    def custom_drop_event(self, event):
        mime_data = event.mimeData()

        if mime_data.hasUrls():
            file_paths = [url.toLocalFile() for url in mime_data.urls()]
            self.process_files(file_paths)

    def process_files(self, file_paths):
        self.sign_documents(file_paths)

    def agregate_folder(self):
        current_filelist = glob(config['lineEdit_input'] + '/*')
        current_filelist = [fp for fp in current_filelist if
                            os.path.isfile(fp) and not fp.endswith(('desktop.ini', 'swapfile.sys')) and is_file_locked(
                                fp)]
        self.sign_documents(current_filelist)

    def open_editor(self):
        self.editor = EditorWindow(self.config)
        res = self.editor.exec_()
        if res:
            self.config = self.editor.config
            save_config(self.config)

    def open_connection(self):
        self.connection_window = ConnectionWindow(self.config)
        res = self.connection_window.exec_()
        if res:
            self.config = self.connection_window.config
            save_config(self.config)

    def save_params(self):
        save_config(self.config)

    def set_user_dir(self, lineeditname):
        options = QFileDialog.Options()
        options |= QFileDialog.ShowDirsOnly
        directory = QFileDialog.getExistingDirectory(self, "Выбрать директорию", options=options)
        if directory != '':
            directory = directory.replace('/','\\')
            lineedit = self.findChild(QLineEdit, lineeditname)
            lineedit.setText(fr'{directory}')

    def show_success_notification(self, text):
        QMessageBox.information(self, ' ', text)

    def show_failure_notification(self):
        QMessageBox.critical(self, 'Ошибка', 'Ошибка при обработке файлов')

    def update_file_list(self):
        if self.session:
            file_list = self.session.get_filelist()
            self.tableWidget.setRowCount(0)
            for file_id, file_data in file_list.items():
                row_position = self.tableWidget.rowCount()
                self.tableWidget.insertRow(row_position)
                item = QTableWidgetItem(file_data['fileName'])
                item.setData(Qt.Qt.UserRole, file_data['id'])  # Сохранение полного пути в пользовательском атрибуте
                self.tableWidget.setItem(row_position, 0, item)
                sign_button = QPushButton('Подписать', self)
                sign_button.clicked.connect(lambda _, idx=file_data['id'], pages=file_data['sigPages']: self.sign_file(
                    idx, pages))
                self.tableWidget.setCellWidget(row_position, 1, sign_button)

    def sign_file(self, idx, pages):
        try:
            try:
                fpath = self.session.download_file(idx)
            except:
                traceback.print_exc()
                self.show_failure_notification()
                return
            if pages:
                fpath = add_stamp(fpath, self.comboBox_certs.currentText(), self.cert_names[self.comboBox_certs.currentText()], pages)
            doc_sig = sign_document(fpath, self.cert_names[self.comboBox_certs.currentText()])
            if doc_sig == 1:
                self.show_failure_notification()
            if os.path.isfile(doc_sig):
                res = self.session.set_file_signed(idx, fpath, doc_sig)
                if res:
                    self.show_success_notification(f'Документ подписан')
                else:
                    self.show_failure_notification()
                    return
        except:
            traceback.print_exc()
            self.show_failure_notification()
            return

    def double_click_handler(self, item):
        if item.column() == 0:
            file_id = item.data(Qt.Qt.UserRole)
            try:
                fpath = self.session.download_file(file_id)
                os.startfile(fpath)
            except:
                traceback.print_exc()


def DoubleClickEvent(file_path):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
        temp_file_path = temp_file.name
        shutil.copyfile(file_path, temp_file_path)
        os.startfile(temp_file_path)

