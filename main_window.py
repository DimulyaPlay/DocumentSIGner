import sys
import os
import traceback
from PyQt5.QtWidgets import QMainWindow, QLabel, QLineEdit, QCheckBox, QComboBox, QToolButton, QFileDialog,\
    QPushButton, QFrame, QMessageBox, QListWidget, QListWidgetItem, QWidget, QHBoxLayout
from PyQt5.QtGui import QIcon
from PyQt5 import uic, QtCore
from main_functions import *


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        ui_file = 'UI/main.ui'
        uic.loadUi(ui_file, self)
        icon = QIcon("UI/icons8-legal-document-64.png")
        self.setWindowIcon(icon)
        self.config = config

        toolButton_update = self.findChild(QToolButton, 'toolButton_update')
        toolButton_update.clicked.connect(self.update_file_list)

        toolButton_input = self.findChild(QToolButton, 'toolButton_input')
        toolButton_input.clicked.connect(lambda: self.set_user_dir('lineEdit_input'))
        toolButton_output = self.findChild(QToolButton, 'toolButton_output')
        toolButton_output.clicked.connect(lambda: self.set_user_dir('lineEdit_output'))

        toolButton_open_input = self.findChild(QToolButton, 'toolButton_open_input')
        toolButton_open_input.clicked.connect(lambda: os.startfile(self.config['lineEdit_input'].replace('/','\\')))
        toolButton_open_output = self.findChild(QToolButton, 'toolButton_open_output')
        toolButton_open_output.clicked.connect(lambda: os.startfile(self.config['lineEdit_output'].replace('/','\\')))

        self.lineEdit_input = self.findChild(QLineEdit, 'lineEdit_input')
        self.lineEdit_input.setText(self.config['lineEdit_input'])
        self.lineEdit_input.textChanged.connect(self.save_params)

        self.lineEdit_output = self.findChild(QLineEdit, 'lineEdit_output')
        self.lineEdit_output.setText(self.config['lineEdit_output'])
        self.lineEdit_output.textChanged.connect(self.save_params)

        toolButton_open_output1 = self.findChild(QToolButton, 'toolButton_open_output1')
        toolButton_open_output1.clicked.connect(lambda: os.startfile(self.config['lineEdit_output1'].replace('/','\\')))

        self.lineEdit_prefix = self.findChild(QLineEdit, 'lineEdit_prefix')
        self.lineEdit_prefix.setText(self.config['lineEdit_prefix'])
        self.lineEdit_prefix.textChanged.connect(self.save_params)

        self.checkBox_copy = self.findChild(QCheckBox, 'checkBox_copy')
        self.checkBox_copy.setChecked(self.config['checkBox_copy'])
        self.checkBox_copy.stateChanged.connect(self.save_params)

        self.lineEdit_output1 = self.findChild(QLineEdit, 'lineEdit_output1')
        self.lineEdit_output1.setText(self.config['lineEdit_output1'])
        self.lineEdit_output1.textChanged.connect(self.save_params)

        self.lineEdit_prefix1 = self.findChild(QLineEdit, 'lineEdit_prefix1')
        self.lineEdit_prefix1.setText(self.config['lineEdit_prefix1'])
        self.lineEdit_prefix1.textChanged.connect(self.save_params)

        self.checkBox_copy1 = self.findChild(QCheckBox, 'checkBox_copy1')
        self.checkBox_copy1.setChecked(self.config['checkBox_copy1'])
        self.checkBox_copy1.stateChanged.connect(self.save_params)

        self.checkBox_first_page = self.findChild(QCheckBox, 'checkBox_first_page')
        self.checkBox_first_page.setChecked(self.config['checkBox_first_page'])
        self.checkBox_first_page.stateChanged.connect(self.save_params)

        self.checkBox_last_page = self.findChild(QCheckBox, 'checkBox_last_page')
        self.checkBox_last_page.setChecked(self.config['checkBox_last_page'])
        self.checkBox_last_page.stateChanged.connect(self.save_params)

        self.checkBox_all_pages = self.findChild(QCheckBox, 'checkBox_all_pages')
        self.checkBox_all_pages.setChecked(self.config['checkBox_all_pages'])
        self.checkBox_all_pages.stateChanged.connect(self.save_params)

        self.lineEdit_chosen_pages = self.findChild(QLineEdit, 'lineEdit_chosen_pages')
        self.lineEdit_chosen_pages.setText(self.config['lineEdit_chosen_pages'])
        self.lineEdit_chosen_pages.textChanged.connect(self.save_params)

        self.comboBox_certs = self.findChild(QComboBox, 'comboBox_certs')
        self.cert_names = get_cert_data(os.path.join(self.config['csp_path'], 'certmgr.exe'))
        self.comboBox_certs.addItems(self.cert_names.keys())
        if config['comboBox_certs'] in self.cert_names:
            self.comboBox_certs.setCurrentText(config['comboBox_certs'])
        self.comboBox_certs.currentTextChanged.connect(self.save_params)

        self.pushButton = self.findChild(QPushButton, 'pushButton')
        self.pushButton.clicked.connect(self.agregate_folder)

        self.frame_dropzone = self.findChild(QFrame, 'frame_dropzone')
        # Переназначение обработчиков событий
        self.frame_dropzone.dragEnterEvent = self.custom_drag_enter_event
        self.frame_dropzone.dropEvent = self.custom_drop_event

        self.listWidget_filelist = self.findChild(QListWidget, 'listWidget_filelist')
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
            # Ваш код для обработки нескольких файлов
            self.process_files(file_paths)

    def process_files(self, file_paths):
        self.sign_documents(file_paths)

    def agregate_folder(self):
        current_filelist = glob(config['lineEdit_input'] + '/*')
        current_filelist = [fp for fp in current_filelist if
                            os.path.isfile(fp) and not fp.endswith(('desktop.ini', 'swapfile.sys')) and is_file_locked(
                                fp)]
        self.sign_documents(current_filelist)

    def sign_documents(self, documents_list):
        doc_signed_count = 0
        for doc in documents_list:
            if doc.endswith('.pdf') and not os.path.exists(doc+'.sig'):
                print(doc)
                try:
                    if any((check_chosen_pages(self.config['lineEdit_chosen_pages']), self.config['checkBox_first_page'], self.config['checkBox_last_page'], self.config['checkBox_all_pages'])):
                        pagelist = []
                        if self.config['checkBox_first_page']:
                            pagelist.append(1)
                        pagelist.extend(check_chosen_pages(self.config['lineEdit_chosen_pages']))
                        if self.config['checkBox_last_page']:
                            pagelist.append(-1)
                        pagelist = list(set(pagelist))
                        if self.config['checkBox_all_pages']:
                            pagelist = 'all'
                        doc = add_stamp(doc, self.comboBox_certs.currentText(), self.cert_names[self.comboBox_certs.currentText()], pagelist)
                    doc_sig = sign_document(doc, self.cert_names[self.comboBox_certs.currentText()])
                    if doc_sig == 1:
                        self.show_failure_notification()
                    if os.path.isfile(doc_sig):
                        doc_signed_count += 1
                        if self.config['checkBox_copy']:
                            if self.config['lineEdit_prefix']:
                                if os.path.basename(doc).startswith(self.config['lineEdit_prefix']):
                                    shutil.copy(doc, self.config['lineEdit_output'])
                                    shutil.copy(doc_sig, self.config['lineEdit_output'])
                            else:
                                shutil.copy(doc, self.config['lineEdit_output'])
                                shutil.copy(doc_sig, self.config['lineEdit_output'])
                        if self.config['checkBox_copy1']:
                            if self.config['lineEdit_prefix1']:
                                if os.path.basename(doc).startswith(self.config['lineEdit_prefix1']):
                                    shutil.copy(doc, self.config['lineEdit_output1'])
                                    shutil.copy(doc_sig, self.config['lineEdit_output1'])
                            else:
                                shutil.copy(doc, self.config['lineEdit_output1'])
                                shutil.copy(doc_sig, self.config['lineEdit_output1'])
                except:
                    traceback.print_exc()
                    self.show_failure_notification()
            else:
                continue
        if doc_signed_count > 0:
            self.show_success_notification(f'Подписано {doc_signed_count} документов')
        else:
            self.show_success_notification(f'Подходящие документы не обнаружены. '
                                           f'Все файлы уже подписаны или не соответствуют подходящему формату.')

    def save_params(self):
        self.config['comboBox_certs'] = self.comboBox_certs.currentText()
        self.config['lineEdit_input'] = self.lineEdit_input.text()
        self.config['lineEdit_prefix'] = self.lineEdit_prefix.text()
        self.config['lineEdit_output'] = self.lineEdit_output.text()
        self.config['checkBox_copy'] = self.checkBox_copy.isChecked()
        self.config['lineEdit_output1'] = self.lineEdit_output1.text()
        self.config['lineEdit_prefix1'] = self.lineEdit_prefix1.text()
        self.config['checkBox_copy1'] = self.checkBox_copy1.isChecked()
        self.config['checkBox_first_page'] = self.checkBox_first_page.isChecked()
        self.config['checkBox_last_page'] = self.checkBox_last_page.isChecked()
        self.config['checkBox_all_pages'] = self.checkBox_all_pages.isChecked()
        self.config['lineEdit_chosen_pages'] = self.lineEdit_chosen_pages.text()
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
        if config['lineEdit_input']:
            current_filelist = glob(config['lineEdit_input'] + '/*')
            current_filelist = [fp for fp in current_filelist if
                                os.path.isfile(fp) and not fp.endswith(('desktop.ini', 'swapfile.sys')) and is_file_locked(
                                    fp)]
            new_filelist = [fp for fp in current_filelist if fp.endswith('.pdf') and not os.path.exists(fp+'.sig')]
            self.listWidget_filelist.clear()
            if new_filelist:
                self.listWidget_filelist.clear()
                for file_path in new_filelist:
                    item = QListWidgetItem(self.listWidget_filelist)
                    widget = QWidget()
                    layout = QHBoxLayout()
                    layout.setContentsMargins(3,3,3,3)
                    file_name_label = QLabel(os.path.basename(file_path))
                    file_name_label.mouseDoubleClickEvent = lambda _, file=file_path: os.startfile(file)
                    layout.addWidget(file_name_label)
                    sign_button = QPushButton('Подписать')
                    sign_button.setMaximumWidth(72)
                    sign_button.clicked.connect(lambda _, file=file_path: self.sign_documents([file]))
                    layout.addWidget(sign_button)
                    widget.setLayout(layout)
                    item.setSizeHint(widget.sizeHint())
                    self.listWidget_filelist.setItemWidget(item, widget)

