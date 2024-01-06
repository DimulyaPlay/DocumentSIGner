from PyQt5.QtWidgets import QDialog, QLineEdit
from PyQt5.QtGui import QIcon
from PyQt5 import uic


class ConnectionWindow(QDialog):
    def __init__(self, config):
        super().__init__()
        ui_file = 'UI/connection.ui'
        uic.loadUi(ui_file, self)
        icon = QIcon("UI/icons8-legal-document-64.png")
        self.setWindowIcon(icon)
        self.config = config
        self.lineEdit_address = self.findChild(QLineEdit, 'lineEdit_address')
        self.lineEdit_address.setText(self.config['lineEdit_address'])
        self.lineEdit_address.textChanged.connect(lambda: self.save_params('lineEdit_address'))
        self.lineEdit_login = self.findChild(QLineEdit, 'lineEdit_login')
        self.lineEdit_login.setText(self.config['lineEdit_login'])
        self.lineEdit_login.textChanged.connect(lambda: self.save_params('lineEdit_login'))
        self.lineEdit_password = self.findChild(QLineEdit, 'lineEdit_password')
        self.lineEdit_password.setText(self.config['lineEdit_password'])
        self.lineEdit_password.textChanged.connect(lambda: self.save_params('lineEdit_password'))
        self.lineEdit_password.setEchoMode(QLineEdit.Password)

    def save_params(self, lineEdit_name):
        lineEdit = self.findChild(QLineEdit, lineEdit_name)
        self.config[lineEdit_name] = lineEdit.text()
