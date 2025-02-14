import sys
import requests
from PySide2 import QtWidgets, QtGui, QtCore
from PySide2.QtCore import QTranslator, QLocale, QLibraryInfo, Signal, Slot
from threading import Thread, Lock
from glob import glob
import socket
from main_functions import resource_path, config_folder, FileWatcher, add_to_context_menu, remove_from_context_menu, RulesDialog, config, save_config, send_file_path_to_existing_instance, file_paths_queue, QueueMonitorThread, FileDialog, handle_dropped_files
import msvcrt
import os
import winshell
import traceback

# venv\Scripts\pyinstaller.exe --windowed --noconfirm --icon "icons8-legal-document-64.ico" --add-data "icons8-legal-document-64.ico;." --add-data "Update.exe;." --add-data "Update.cfg;." --add-data "dcs.png;." --add-data "dcs-copy-in-law.png;." --add-data "dcs-copy-no-in-law.png;." documentSIGner.py

version = 'Версия 2.5 Сборка 100220251'

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

    global qt_app
    def __init__(self, icon, parent=None):
        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.activated.connect(self.show_menu)
        self.notifiers = []
        self.dialog = FileDialog([])
        self.messageClicked.connect(self.show_menu)
        self.rules_file = os.path.join(config_folder, 'rules.txt')
        menu = QtWidgets.QMenu(parent)
        menu.addAction(version).setDisabled(True)
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

        self.toggle_notify = menu.addAction("Уведомлять о новых")
        self.toggle_notify.setCheckable(True)
        self.toggle_notify.setChecked(config.get('notify', False))
        self.toggle_notify.triggered.connect(self.toggle_notifier)

        self.open_rules_window = menu.addAction("Меню правил")
        self.open_rules_window.triggered.connect(self.open_rules)

        # Создаем подменю для "Страница штампа по умолчанию"
        self.default_page_menu = QtWidgets.QMenu("Стр. штампа по ум.", menu)
        self.radio_none = QtWidgets.QAction("Нет", self.default_page_menu)
        self.radio_none.setCheckable(True)
        self.radio_none.setChecked(config.get('default_page', 2) == 0)
        self.radio_none.triggered.connect(lambda: self.set_default_page(0))
        self.radio_first = QtWidgets.QAction("Первая", self.default_page_menu)
        self.radio_first.setCheckable(True)
        self.radio_first.setChecked(config.get('default_page', 2) == 1)
        self.radio_first.triggered.connect(lambda: self.set_default_page(1))
        self.radio_last = QtWidgets.QAction("Последняя", self.default_page_menu)
        self.radio_last.setCheckable(True)
        self.radio_last.setChecked(config.get('default_page', 2) == 2)
        self.radio_last.triggered.connect(lambda: self.set_default_page(2))
        self.radio_all = QtWidgets.QAction("Все", self.default_page_menu)
        self.radio_all.setCheckable(True)
        self.radio_all.setChecked(config.get('default_page', 2) == 3)
        self.radio_all.triggered.connect(lambda: self.set_default_page(3))
        # Добавляем переключатели в подменю
        self.default_page_menu.addAction(self.radio_none)
        self.default_page_menu.addAction(self.radio_first)
        self.default_page_menu.addAction(self.radio_last)
        self.default_page_menu.addAction(self.radio_all)
        # Добавляем подменю в основное меню
        menu.addMenu(self.default_page_menu)

        # Создаем подменю для "Размещение штампа на странице"
        self.stamp_place_menu = QtWidgets.QMenu("Размещение штампа на странице", menu)
        self.radio_page_buttom = QtWidgets.QAction("Внизу страницы", self.stamp_place_menu)
        self.radio_page_buttom.setCheckable(True)
        self.radio_page_buttom.setChecked(config.get('stamp_place', 0) == 0)
        self.radio_page_buttom.triggered.connect(lambda: self.set_stamp_place(0))
        self.radio_per_page = QtWidgets.QAction("Указать для каждой страницы", self.stamp_place_menu)
        self.radio_per_page.setCheckable(True)
        self.radio_per_page.setChecked(config.get('stamp_place', 0) == 1)
        self.radio_per_page.triggered.connect(lambda: self.set_stamp_place(1))
        # Добавляем переключатели в подменю
        self.stamp_place_menu.addAction(self.radio_page_buttom)
        self.stamp_place_menu.addAction(self.radio_per_page)
        # Добавляем подменю в основное меню
        menu.addMenu(self.stamp_place_menu)

        # Создаем подменю для "Тип штампа по умолчанию"
        self.stamp_type_menu = QtWidgets.QMenu("Тип штампа по умолчанию", menu)
        self.radio_regular_stamp = QtWidgets.QAction("Обычный штамп", self.stamp_type_menu)
        self.radio_regular_stamp.setCheckable(True)
        self.radio_regular_stamp.setChecked(config.get('default_stamp_type', 0) == 0)
        self.radio_regular_stamp.triggered.connect(lambda: self.set_stamp_type(0))
        self.radio_copy_stamp = QtWidgets.QAction("Копия верна", self.stamp_type_menu)
        self.radio_copy_stamp.setCheckable(True)
        self.radio_copy_stamp.setChecked(config.get('default_stamp_type', 0) == 1)
        self.radio_copy_stamp.triggered.connect(lambda: self.set_stamp_type(1))
        self.radio_auto_stamp = QtWidgets.QAction("Автовыбор (скрыть элементы)", self.stamp_type_menu)
        self.radio_auto_stamp.setCheckable(True)
        self.radio_auto_stamp.setChecked(config.get('default_stamp_type', 0) == 2)
        self.radio_auto_stamp.triggered.connect(lambda: self.set_stamp_type(2))
        # Добавляем переключатели в подменю
        self.stamp_type_menu.addAction(self.radio_regular_stamp)
        self.stamp_type_menu.addAction(self.radio_copy_stamp)
        self.stamp_type_menu.addAction(self.radio_auto_stamp)
        # Добавляем подменю в основное меню
        menu.addMenu(self.stamp_type_menu)

        exit_action = menu.addAction("Выход")
        exit_action.triggered.connect(self.exit)
        self.setContextMenu(menu)
        self.toggle_stamp_on_original.setChecked(config['stamp_on_original'])
        # Запуск сокет-сервера в отдельном потоке
        self.socket_server_thread = Thread(target=self.run_socket_server, daemon=True)
        self.socket_server_thread.start()
        self.queue_thread = QueueMonitorThread()
        self.queue_thread.file_path_signal.connect(self.add_file_to_list)
        self.queue_thread.start()
        if config['notify']:
            self.create_notifiers()

    def add_file_to_list(self, file_path):
        if file_path == 'activate':
            self.show_menu()
            return
        res = self.dialog.append_new_file_to_list(file_path)
        if not res:
            return
        if not self.dialog.isActiveWindow() or self.dialog.isHidden():
            self.dialog.show()
            self.dialog.activateWindow()

    def set_default_page(self, page):
        config['default_page'] = page
        save_config()
        self.radio_none.setChecked(page == 0)
        self.radio_first.setChecked(page == 1)
        self.radio_last.setChecked(page == 2)
        self.radio_all.setChecked(page == 3)

    def set_stamp_place(self, page):
        config['stamp_place'] = page
        save_config()
        self.radio_page_buttom.setChecked(page == 0)
        self.radio_per_page.setChecked(page == 1)

    def set_stamp_type(self, stamp_type):
        config['default_stamp_type'] = stamp_type
        save_config()
        self.radio_regular_stamp.setChecked(stamp_type == 0)
        self.radio_copy_stamp.setChecked(stamp_type == 1)

    def show_menu(self, reason=QtWidgets.QSystemTrayIcon.Trigger):
        try:
            if self.dialog.isVisible():
                self.dialog.activateWindow()
                return
            if reason == QtWidgets.QSystemTrayIcon.Trigger:
                file_list_for_sign = self.get_list_for_sign()
                if file_list_for_sign:
                    for fp in file_list_for_sign:
                        self.add_file_to_list(fp)
                    self.dialog.show()
                    self.dialog.activateWindow()
                else:
                    self.showMessage(
                        "Пусто",
                        "Документов на подпись не обнаружено.",
                        QtWidgets.QSystemTrayIcon.Information,
                        300  # Время отображения уведомления в миллисекундах
                    )
        except:
            traceback.print_exc()

    def get_list_for_sign(self):
        try:
            matching_files = []
            # Загрузка и проверка файла по правилам из rules.txt
            if os.path.exists(self.rules_file):
                with open(self.rules_file, 'r') as file:
                    rules = file.readlines()
            else:
                rules = []
            for rule in rules:
                source_dir, _, _, for_sign_dir = rule.strip().split('|')
                print('checking dir', source_dir)
                # Получение всех файлов в корневой директории
                for file_name in os.listdir(source_dir):
                    if file_name in ['Thumbs.db', "desktop.ini"] or for_sign_dir == 'нет' or file_name.startswith(('gf_', '~')):
                        continue
                    file_path = os.path.join(source_dir, file_name)
                    if file_path in matching_files:
                        continue
                    # Пропускаем файлы с окончанием .sig
                    if file_name.endswith('.sig') or os.path.isdir(file_path):
                        continue
                    # Пропускаем файлы, у которых есть копия с окончанием .sig
                    sig_file_path = file_path + '.sig'
                    if os.path.exists(sig_file_path):
                        continue
                    print('found file', file_path)
                    matching_files.append(file_path)
            return matching_files
        except:
            traceback.print_exc()
            return []

    def open_rules(self):
        self.rules_dialog = RulesDialog(self.rules_file)
        self.rules_dialog.show()
        self.rules_dialog.activateWindow()

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

    def toggle_stamp(self):
        if self.toggle_stamp_on_original.isChecked():
            config['stamp_on_original'] = True
        else:
            config['stamp_on_original'] = False
        save_config()

    def toggle_context_menu_option(self):
        if self.toggle_context_menu.isChecked():
            res = add_to_context_menu()
            if res:
                config['context_menu'] = True
            else:
                self.toggle_context_menu.setChecked(False)
        else:
            res = remove_from_context_menu()
            if res:
                config['context_menu'] = False
            else:
                self.toggle_context_menu.setChecked(True)
        save_config()


    def toggle_notifier(self):
        if self.toggle_notify.isChecked():
            self.create_notifiers()
            config['notify'] = True
        else:
            self.notifiers = []
            config['notify'] = False
        save_config()

    def create_notifiers(self):
        self.notifiers = []  # Останавливаем предыдущие наблюдатели перед созданием новых
        if os.path.exists(self.rules_file):
            with open(self.rules_file, 'r') as file:
                rules = file.readlines()
        else:
            rules = []
        for rule in rules:
            source_dir, _, _, for_sign_dir = rule.strip().split('|')
            if for_sign_dir == 'да':
                watcher = FileWatcher(source_dir, self.notify_new_file)
                thread = Thread(target=watcher.run, daemon=True)
                thread.start()
                self.notifiers.append((watcher, thread))

    def notify_new_file(self, fp):
        self.showMessage(
            "Получены документы подпись.",
            f"{os.path.basename(fp)}\n(нажмите здесь, чтобы открыть меню подписи)",
            QtWidgets.QSystemTrayIcon.Information,
            2500  # Время отображения уведомления в миллисекундах
        )

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
                    from main_functions import ALLOWED_EXTENTIONS
                    if file_path.lower().endswith(ALLOWED_EXTENTIONS) and not file_path.startswith(('~', "gf_")):
                        file_paths_queue.put(file_path)

    def exit(self):
        if first_instance:
            lock_file.close()
        QtWidgets.QApplication.quit()


def main():
    qt_app = QtWidgets.QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    translator = QTranslator()
    locale = QLocale.system().name()  # Получение системной локали
    path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)  # Путь к переводам Qt
    translator.load("qtbase_" + locale, path)
    qt_app.installTranslator(translator)
    qt_app.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    global tray_gui
    tray_gui = SystemTrayGui(QtGui.QIcon(resource_path('icons8-legal-document-64.ico')))
    qt_app.tray_gui = tray_gui
    tray_gui.show()
    tray_gui.showMessage(
        "Приложение запущено.",
        f"Нажмите на значок, чтобы открыть список документов на подпись",
        QtWidgets.QSystemTrayIcon.Information,
        1000  # Время отображения уведомления в миллисекундах
    )
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
            result = send_file_path_to_existing_instance(['activate'])
            if result:
                sys.exit(0)
    else:
        if len(sys.argv) > 1:
            file_paths = sys.argv[1:]
            from main_functions import ALLOWED_EXTENTIONS
            if file_paths[0].lower().endswith(ALLOWED_EXTENTIONS) and not file_paths[0].startswith(('~', "gf_")):
                file_paths_queue.put(file_paths[0])
        sys.excepthook = exception_hook
        main()
