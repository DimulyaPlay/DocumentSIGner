import sys
from threading import Event, Thread
from PySide2.QtCore import QTranslator, QLocale, QLibraryInfo
from PySide2 import QtWidgets, QtGui, QtCore
import socket
from main_functions import (ALLOWED_EXTENSIONS, FileDialog, FileWatcher,
                            QueueMonitorThread, RulesDialog, add_to_context_menu,
                            config, config_folder, decode_document,
                            file_paths_queue, filter_inappropriate_files,
                            get_cert_data, install_certificates,
                            parse_rule_line, remove_from_context_menu,
                            resource_path, save_config,
                            send_file_path_to_existing_instance,
                            toggle_startup_registry, update_updater)
import msvcrt
import os
import traceback

# .venv\Scripts\pyinstaller.exe --windowed --noconfirm --noupx --contents-directory "." --icon "icons8-legal-document-64.ico" --add-data "icons8-legal-document-64.ico;." --add-data "35.gif;." --add-data "Update.exe;." --add-data "Update.cfg;." --add-data "dcs.png;." --add-data "dcs-copy-in-law.png;." --add-data "dcs-copy.png;." --add-data "dcs-copy-no-in-law.png;." documentSIGner.py

version = 'Версия 2.9.1'


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
    notification_signal = QtCore.Signal(str)
    files_scanned_signal = QtCore.Signal(object)

    def __init__(self, icon, parent=None):
        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.activated.connect(self.show_menu)
        self.notifiers = []
        self.notification_signal.connect(self.notify_new_file)
        self.files_scanned_signal.connect(self._on_files_scanned)
        self._file_scan_running = False
        self._open_dialog_after_scan = False
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

        self.normalize_a4_action = menu.addAction("Вписывать страницы в формат A4")
        self.normalize_a4_action.setCheckable(True)
        self.normalize_a4_action.setChecked(config.get('normalize_to_a4', False))
        self.normalize_a4_action.triggered.connect(self.toggle_normalize_to_a4)

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
        self.socket_stop_event = Event()
        self.server_socket = None
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
        toggle_startup_registry(config['autorun'])

    def start_doc_count_monitor(self):
        self.icon_timer = QtCore.QTimer()
        self.icon_timer.timeout.connect(self.update_label_text)
        self.icon_timer.start(30000)  # каждые 30 секунд

    def update_label_text(self, files_for_sign=None):
        if files_for_sign is None:
            self.refresh_file_list()
            return
        try:
            number = len(files_for_sign)
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

    def refresh_file_list(self, open_dialog=False):
        if open_dialog:
            self._open_dialog_after_scan = True
        if self._file_scan_running:
            return
        self._file_scan_running = True
        Thread(target=self._scan_files, daemon=True).start()

    def _scan_files(self):
        self.files_scanned_signal.emit(self.get_list_for_sign())

    def _on_files_scanned(self, files_for_sign):
        self._file_scan_running = False
        self.update_label_text(files_for_sign)
        if not self._open_dialog_after_scan:
            return
        self._open_dialog_after_scan = False
        if self.dialog.isVisible():
            self.dialog.activateWindow()
        elif files_for_sign:
            for file_path in files_for_sign:
                self.add_file_to_list(file_path)
            self.dialog.show()
            self.dialog.activateWindow()
        else:
            self.showMessage(
                "Пусто",
                "Документов на подпись не обнаружено.",
                QtWidgets.QSystemTrayIcon.Information,
                300
            )

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
        # Context-menu activation is handled by QSystemTrayIcon itself. Running a
        # directory scan here delayed the native tray menu, especially on shares.
        if reason != QtWidgets.QSystemTrayIcon.Trigger and reason != 'activate':
            return
        self.dialog.fit_in_a4.setChecked(config['normalize_to_a4'])
        self.dialog.sign_original.setChecked(config['stamp_on_original'])
        try:
            if self.dialog.isVisible():
                self.dialog.activateWindow()
                return
            self.refresh_file_list(open_dialog=True)
        except Exception:
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
            certificate_data = None
            seen_paths = set()
            for rule in rules:
                parsed_rule = parse_rule_line(rule)
                if not parsed_rule:
                    continue
                source_dir, _, _, for_sign_dir = parsed_rule
                if not os.path.exists(source_dir):
                    continue
                # print('checking dir', source_dir)
                # Получение всех файлов в корневой директории
                for file_name in os.listdir(source_dir):
                    file_name_lower = file_name.lower()
                    if file_name_lower in ('thumbs.db', 'desktop.ini') or for_sign_dir.casefold() == 'нет' or file_name_lower.startswith(('gf_', '~')):
                        continue
                    file_path = os.path.join(source_dir, file_name)
                    normalized_path = os.path.normcase(os.path.abspath(file_path))
                    if normalized_path in seen_paths:
                        continue
                    # Пропускаем файлы с окончанием .sig
                    if file_name_lower.endswith('.sig') or os.path.isdir(file_path):
                        continue
                    # Пропускаем файлы, у которых есть копия с окончанием .sig
                    sig_file_path = file_path + '.sig'
                    if os.path.exists(sig_file_path):
                        continue
                    # --- если это .enc расшифровать и пропустить ---
                    if file_name_lower.endswith('.enc'):
                        if certificate_data is None:
                            certs_data = get_cert_data()
                            certificate_data = certs_data.get(config['last_cert'])
                        if certificate_data:
                            try:
                                decode_document(file_path, certificate_data)
                            except Exception:
                                traceback.print_exc()
                        continue  # сам .enc в список не идёт

                    # --- обычные файлы ---
                    matching_files.append(file_path)
                    seen_paths.add(normalized_path)
            return filter_inappropriate_files(matching_files)
        except Exception:
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

    def toggle_normalize_to_a4(self):
        config['normalize_to_a4'] = self.normalize_a4_action.isChecked()
        save_config()

    def toggle_notifier(self):
        if self.toggle_notify.isChecked():
            self.create_notifiers()
            config['notify'] = True
        else:
            self.stop_notifiers()
            config['notify'] = False
        save_config()

    def create_notifiers(self):
        self.stop_notifiers()
        if os.path.exists(self.rules_file):
            with open(self.rules_file, 'r') as file:
                rules = file.readlines()
        else:
            rules = []
        for rule in rules:
            parsed_rule = parse_rule_line(rule)
            if not parsed_rule:
                continue
            source_dir, _, _, for_sign_dir = parsed_rule
            if not os.path.exists(source_dir):
                continue
            if for_sign_dir.casefold() == 'да':
                watcher = FileWatcher(source_dir, self.notification_signal.emit)
                watcher.start()
                self.notifiers.append(watcher)

    def stop_notifiers(self):
        for watcher in self.notifiers:
            watcher.stop()
        self.notifiers.clear()

    def notify_new_file(self, fp):
        self.showMessage(
            "Получены документы подпись.",
            f"{os.path.basename(fp)}\n(нажмите здесь, чтобы открыть меню подписи)",
            QtWidgets.QSystemTrayIcon.Information,
            2500  # Время отображения уведомления в миллисекундах
        )

    def run_socket_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.settimeout(0.5)
            self.server_socket.bind(('localhost', 65432))
            self.server_socket.listen()
            while not self.socket_stop_event.is_set():
                try:
                    conn, _ = self.server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with conn:
                    conn.settimeout(2)
                    chunks = []
                    total_size = 0
                    while total_size < 1024 * 1024:
                        try:
                            chunk = conn.recv(4096)
                        except socket.timeout:
                            break
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total_size += len(chunk)
                    for file_path in b''.join(chunks).decode('utf-8', errors='replace').strip().splitlines():
                        if file_path == 'activate' or (
                            file_path.lower().endswith(ALLOWED_EXTENSIONS)
                            and not os.path.basename(file_path).startswith(('~', 'gf_'))
                        ):
                            file_paths_queue.put(file_path)
        except OSError as error:
            if not self.socket_stop_event.is_set():
                print(f'Ошибка локального сокет-сервера: {error}')
        finally:
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None

    def exit(self):
        self.stop_notifiers()

        if hasattr(self, 'queue_thread'):
            file_paths_queue.put(None)  # Завершает QueueMonitorThread
            self.queue_thread.wait()

        if hasattr(self, 'socket_server_thread'):
            self.socket_stop_event.set()
            try:
                if self.server_socket:
                    self.server_socket.close()
            except OSError:
                pass
            self.socket_server_thread.join(timeout=2)

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
    Thread(target=run_startup_maintenance, daemon=True).start()
    tray_gui.showMessage(
        "Приложение запущено.",
        f"Нажмите на значок, чтобы открыть список документов на подпись",
        QtWidgets.QSystemTrayIcon.Information,
        1000  # Время отображения уведомления в миллисекундах
    )
    sys.exit(qt_app.exec_())


def run_startup_maintenance():
    for maintenance_task in (update_updater, install_certificates):
        try:
            maintenance_task()
        except Exception:
            traceback.print_exc()


if __name__ == '__main__':
    lock_file_path = os.path.join(os.path.dirname(sys.argv[0]), 'app_instance.lock')
    # Попытка захватить блокировку файла
    lock_file = open(lock_file_path, 'w')
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        first_instance = True
        print('First instance')
    except OSError:
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
        if getattr(sys, 'frozen', False) or '__compiled__' in globals():
            exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            log_out = os.path.join(exe_dir, 'console_output.log')
            log_err = os.path.join(exe_dir, 'console_errors.log')
            sys.stdout = open(log_out, 'a', buffering=1)
            sys.stderr = open(log_err, 'a', buffering=1)
        if len(sys.argv) > 1:
            file_paths = sys.argv[1:]
            if file_paths[0].lower().endswith(ALLOWED_EXTENSIONS) and not os.path.basename(file_paths[0]).startswith(('~', "gf_")):
                file_paths_queue.put(file_paths[0])
        sys.excepthook = exception_hook
        main()
