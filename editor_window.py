from PyQt5.QtWidgets import QCheckBox, QFileDialog,\
    QPushButton, QListWidget, QDialog, QInputDialog
from PyQt5.QtGui import QIcon
from PyQt5 import uic


class EditorWindow(QDialog):
    def __init__(self, config):
        super().__init__()
        ui_file = 'UI/editor.ui'
        uic.loadUi(ui_file, self)
        icon = QIcon("UI/icons8-legal-document-64.png")
        self.setWindowIcon(icon)
        self.config = config
        self.pushButton_add_in = self.findChild(QPushButton, 'pushButton_add_in')
        self.pushButton_add_in.clicked.connect(lambda: self.set_user_dir('listWidget_in'))
        self.pushButton_del_in = self.findChild(QPushButton, 'pushButton_del_in')
        self.pushButton_del_in.clicked.connect(lambda: self.removeSel('listWidget_in'))

        self.pushButton_add_out = self.findChild(QPushButton, 'pushButton_add_out')
        self.pushButton_add_out.clicked.connect(lambda: self.set_user_dir('listWidget_out'))
        self.pushButton_del_out = self.findChild(QPushButton, 'pushButton_del_out')
        self.pushButton_del_out.clicked.connect(lambda: self.removeSel('listWidget_out'))

        self.pushButton_add_filter = self.findChild(QPushButton, 'pushButton_add_filter')
        self.pushButton_add_filter.clicked.connect(lambda: self.set_user_string('listWidget_filters'))
        self.pushButton_del_filter = self.findChild(QPushButton, 'pushButton_del_filter')
        self.pushButton_del_filter.clicked.connect(lambda: self.removeSel('listWidget_filters'))

    def set_user_dir(self, listWidget_name):
        options = QFileDialog.Options()
        options |= QFileDialog.ShowDirsOnly
        directory = QFileDialog.getExistingDirectory(self, "Выбрать директорию", options=options)
        if directory != '':
            directory = directory.replace('/','\\')
            qlw = self.findChild(QListWidget, listWidget_name)
            qlw.addItem(fr'{directory}')

    def removeSel(self, listWidget_name):
        qlw = self.findChild(QListWidget, listWidget_name)
        listItems = qlw.selectedItems()
        if not listItems: return
        for item in listItems:
            qlw.takeItem(qlw.row(item))

    def set_user_string(self, listWidget_name):
        qlw = self.findChild(QListWidget, listWidget_name)
        user_str = QInputDialog(self)
        user_str.setOkButtonText('Принять')
        user_str.setCancelButtonText('Отменить')
        user_str.setLabelText('Впишите фильтр, например:\n'
                              '*.pdf - будет применяться к файлам с окончанием ".pdf"\n'
                              '*изв* - будет применяться к файлам, в названии которых есть "изв"\n'
                              'РР-* - будет применяться к файлам, начинающимся с "РР-"')
        user_str.setWindowTitle('Добавить фильтр')
        result = user_str.exec_()
        if result:
            qlw.addItem(fr'{user_str.textValue()}')
