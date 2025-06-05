import sys
import time
from threading import Thread, Lock
from PySide2.QtCore import QTranslator, QLocale, QLibraryInfo
from PySide2 import QtWidgets, QtGui, QtCore
import socket
from main_functions import resource_path, toggle_startup_registry, filter_inappropriate_files, config_folder, update_updater, FileWatcher, add_to_context_menu, remove_from_context_menu, RulesDialog, config, save_config, send_file_path_to_existing_instance, file_paths_queue, QueueMonitorThread, FileDialog, handle_dropped_files
import msvcrt
import os
import traceback

# .venv\Scripts\pyinstaller.exe --windowed --noconfirm --contents-directory "." --icon "icons8-legal-document-64.ico" --add-data "icons8-legal-document-64.ico;." --add-data "35.gif;." --add-data "Update.exe;." --add-data "Update.cfg;." --add-data "dcs.png;." --add-data "dcs-copy-in-law.png;." --add-data "dcs-copy-no-in-law.png;." documentSIGner.py

version = 'Версия 2.6 Сборка 050620251'


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
        self.dialog = FileDialog([], tray_gui=self)
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
        self.last_icon_count = -1
        self.icon = QtGui.QIcon(resource_path('icons8-legal-document-64.ico'))
        self.setIcon(self.icon)
        self.start_doc_count_monitor()
        self.update_label_text()
        if config['notify']:
            self.create_notifiers()

    def start_doc_count_monitor(self):
        self.icon_timer = QtCore.QTimer()
        self.icon_timer.timeout.connect(self.update_label_text)
        self.icon_timer.start(30000)  # каждые 30 секунд

    def update_label_text(self):
        try:
            number = len(self.get_list_for_sign())
            if number == self.last_icon_count:
                return
            self.last_icon_count = number
            base_icon = QtGui.QIcon(resource_path('icons8-legal-document-64.ico'))
            pixmap = base_icon.pixmap(48, 48)
            painter = QtGui.QPainter(pixmap)
            if number > 0:
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setPen(QtGui.QColor("red"))
                painter.setBrush(QtGui.QColor("red"))
                painter.drawEllipse(15, 14, 32, 33)
                painter.setFont(QtGui.QFont("Arial", 20, QtGui.QFont.Bold))
                painter.setPen(QtGui.QColor("white"))
                x_offset = 5 if number > 9 else 2
                painter.drawText(QtCore.QPointF(24 - x_offset, 41), str(number))
            painter.end()
            self.setIcon(QtGui.QIcon(pixmap))

        except Exception as e:
            print("Ошибка обновления иконки с количеством:", e)

    def add_file_to_list(self, file_path):
        if file_path == 'activate':
            self.show_menu('activate')
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
        self.update_label_text()
        try:
            if self.dialog.isVisible():
                self.dialog.activateWindow()
                return
            if reason == QtWidgets.QSystemTrayIcon.Trigger or reason == 'activate':
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
                # print('checking dir', source_dir)
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
                    # print('found file', file_path)
                    matching_files.append(file_path)
            return filter_inappropriate_files(matching_files)
        except:
            traceback.print_exc()
            return []

    def open_rules(self):
        self.rules_dialog = RulesDialog(self.rules_file)
        self.rules_dialog.show()
        self.rules_dialog.activateWindow()

    def toggle_startup(self):
        desired_state = self.toggle_autorun.isChecked()
        result = toggle_startup_registry(desired_state)

        if result:
            config['autorun'] = desired_state
        else:
            self.toggle_autorun.setChecked(not desired_state)
            QtWidgets.QMessageBox.warning(
                None,
                "Ошибка",
                "Не удалось изменить автозапуск. Возможно, недостаточно прав."
            )
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
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
                    received = data.decode('utf-8')
                    paths = received.strip().splitlines()
                    from main_functions import ALLOWED_EXTENTIONS
                    for file_path in paths:
                        if (file_path.lower().endswith(ALLOWED_EXTENTIONS)
                            and not os.path.basename(file_path).startswith(('~', 'gf_'))) or file_path == 'activate':
                            file_paths_queue.put(file_path)

    def exit(self):
        if hasattr(self, 'notifiers'):
            for watcher, thread in self.notifiers:
                if hasattr(watcher, 'observer'):
                    watcher.observer.stop()
                    watcher.observer.join()

        if hasattr(self, 'queue_thread'):
            file_paths_queue.put(None)  # Завершает QueueMonitorThread
            self.queue_thread.wait()

        if hasattr(self, 'socket_server_thread'):
            # Нельзя завершить socket.accept() напрямую, но можно закрыть сокет, если сделать его self-свойством
            try:
                self.server_socket.close()
            except:
                pass

        if first_instance:
            lock_file.close()
        QtWidgets.QApplication.quit()


def main():
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
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
            print('Переданы файлы:', file_paths)
            result = send_file_path_to_existing_instance(file_paths)
            if result:
                sys.exit(0)
        else:
            result = send_file_path_to_existing_instance(['activate'])
            if result:
                sys.exit(0)
    else:
        if getattr(sys, 'frozen', True) or '__compiled__' in globals():
            sys.stdout = open('console_output.log', 'a', buffering=1)
            sys.stderr = open('console_errors.log', 'a', buffering=1)
        try:
            update_updater()
        except Exception as e:
            print(e)
        if len(sys.argv) > 1:
            file_paths = sys.argv[1:]
            from main_functions import ALLOWED_EXTENTIONS
            if file_paths[0].lower().endswith(ALLOWED_EXTENTIONS) and not file_paths[0].startswith(('~', "gf_")):
                file_paths_queue.put(file_paths[0])
        sys.excepthook = exception_hook
        main()
