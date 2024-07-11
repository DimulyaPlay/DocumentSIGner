import shutil
import sys
from PySide2 import QtWidgets, QtGui, QtCore
from PySide2.QtCore import QTranslator, QLocale, QLibraryInfo
from widget_ui import Ui_MainWindow
from threading import Thread
from glob import glob
import time
import logging
import socket
from main_functions import resource_path, add_to_context_menu, remove_from_context_menu, RulesDialog, config, save_config, send_file_path_to_existing_instance, file_paths_queue, QueueMonitorThread, FileDialog, handle_dropped_files
import msvcrt
import os
import winshell

# C:\Users\CourtUser\Desktop\release\DocumentSIGner\venv\Scripts\pyinstaller.exe --windowed --console --noconfirm --icon "C:\Users\CourtUser\Desktop\release\DocumentSIGner\icons8-legal-document-64.ico" --add-data "C:\Users\CourtUser\Desktop\release\DocumentSIGner\icons8-legal-document-64.ico;." --add-data "C:\Users\CourtUser\Desktop\release\DocumentSIGner\dcs.png;."  C:\Users\CourtUser\Desktop\release\DocumentSIGner\documentSIGner.py


def exception_hook(exc_type, exc_value, exc_traceback):
    """
    Функция для перехвата исключений и отображения диалогового окна с ошибкой.
    """
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    error_dialog = QtWidgets.QErrorMessage()
    error_dialog.showMessage(error_msg)
    error_dialog.exec_()
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


class SystemTrayGui(QtWidgets.QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.activated.connect(self.show_menu)
        self.soed = None
        confirmations_path = os.path.join(os.path.dirname(sys.argv[0]), 'confirmations')
        if os.path.exists(confirmations_path):
            files = glob(f'{confirmations_path}/*')
            for file in files:
                os.remove(file)
        else:
            os.mkdir(confirmations_path)
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
        self.toggle_context_menu = menu.addAction("Пункт в контекстном меню")
        self.toggle_context_menu.setCheckable(True)
        self.toggle_context_menu.setChecked(config['context_menu'])
        self.toggle_context_menu.triggered.connect(self.toggle_context_menu_option)
        self.toggle_autorun = menu.addAction("Автозапуск приложения")
        self.toggle_autorun.setCheckable(True)
        self.toggle_autorun.setChecked(config['autorun'])
        self.toggle_autorun.triggered.connect(self.toggle_startup)
        self.open_rules_window = menu.addAction("Меню правил")
        self.open_rules_window.triggered.connect(self.open_rules)
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
        self.toggle_stamp_on_original.setChecked(config['stamp_on_original'])
        if config['widget_visible']:
            self.toggle_widget_visible.setChecked(True)
            self.widget.show()
        # Запуск сокет-сервера в отдельном потоке
        self.socket_server_thread = Thread(target=self.run_socket_server, daemon=True)
        self.socket_server_thread.start()
        self.dialog = None
        self.queue_thread = QueueMonitorThread()
        self.queue_thread.file_path_signal.connect(self.add_file_to_list)
        self.queue_thread.start()

    def add_file_to_list(self, file_path):
        if self.dialog:
            self.dialog.append_new_file_to_list(file_path)
            self.dialog.show()
            self.dialog.activateWindow()
        else:
            self.dialog = FileDialog([file_path])
            self.dialog.show()
            self.dialog.activateWindow()


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

    def open_rules(self):
        rules_file = 'rules.txt'
        self.rules_dialog = RulesDialog(rules_file)
        self.rules_dialog.show()
        self.rules_dialog.activateWindow()

    def toggle_widget(self):
        if self.toggle_widget_visible.isChecked():
            self.widget.show()
            config['widget_visible'] = True
        else:
            self.widget.hide()
            config['widget_visible'] = False
        save_config()

    def toggle_startup(self):
        def create_shortcut(shortcut_path):
            if not os.path.exists(shortcut_path):
                from win32com.client import Dispatch
                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.TargetPath = sys.argv[0]
                shortcut.WorkingDirectory = os.path.dirname(sys.argv[0])
                shortcut.save()

        startup_folder = winshell.startup()
        shortcut_path = os.path.join(startup_folder, f"DocumentSIGner.lnk")
        if self.toggle_autorun.isChecked():
            create_shortcut(shortcut_path)
            config['autorun'] = True
        else:
            if os.path.exists(shortcut_path):
                os.unlink(shortcut_path)
            config['autorun'] = False
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

    def toggle_context_menu_option(self):
        if self.toggle_context_menu.isChecked():
            add_to_context_menu()
            config['context_menu'] = True
        else:
            remove_from_context_menu()
            config['context_menu'] = False
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
        print('Socket server listening started')  # Лог для отладки
        while True:
            conn, addr = server_socket.accept()
            print('Connection accepted from', addr)  # Лог для отладки
            with conn:
                data = b''
                while True:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                if data:
                    file_path = data.decode()
                    print(f"Received file path: {file_path}")
                    file_paths_queue.put(file_path)

    def exit(self):
        QtWidgets.QApplication.quit()


def run_flask():
    app.run(host="127.0.0.1", port=config['port'], use_reloader=False, debug=False)

def is_port_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('localhost', 65432))
            return True
        except OSError:
            return False

def main():
    qt_app = QtWidgets.QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    translator = QTranslator()
    locale = QLocale.system().name()  # Получение системной локали
    path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)  # Путь к переводам Qt
    translator.load("qtbase_" + locale, path)
    qt_app.installTranslator(translator)
    global tray_gui
    tray_gui = SystemTrayGui(QtGui.QIcon(resource_path('icons8-legal-document-64.ico')))
    tray_gui.show()
    sys.exit(qt_app.exec_())


if __name__ == '__main__':
    lock_file_path = os.path.join(os.path.dirname(sys.argv[0]), 'app_instance.lock')
    # Попытка захватить блокировку файла
    lock_file = open(lock_file_path, 'w')
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        first_instance = True
        print('First instance')
    except:
        first_instance = False
        print('NOT First instance')
    if not first_instance:
        if len(sys.argv) > 1:
            file_paths = sys.argv[1:]
            result = send_file_path_to_existing_instance(file_paths)
            if result:
                sys.exit(0)
    else:
        if len(sys.argv) > 1:
            file_paths = sys.argv[1:]
            file_paths_queue.put(file_paths[0])
        from flask_app import *
        logging.getLogger("PySide2").setLevel(logging.WARNING)
        log_path = os.path.join(os.path.dirname(sys.argv[0]), 'log.log')
        logging.basicConfig(filename=log_path, level=logging.ERROR)
        sys.excepthook = exception_hook
        certs_data = get_cert_data()
        main()
