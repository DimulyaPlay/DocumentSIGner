# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'designerQqOaJk.ui'
##
## Created by: Qt User Interface Compiler version 5.14.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import (QCoreApplication, QMetaObject, QObject, QPoint,
    QRect, QSize, QUrl, Qt, QEvent)
from PySide2.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont,
    QFontDatabase, QIcon, QLinearGradient, QPalette, QPainter, QPixmap,
    QRadialGradient)
from PySide2.QtWidgets import *
from main_functions import handle_dropped_files

class Ui_MainWindow(QObject):
    def setupUi(self, MainWindow):
        if MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(60, 60)
        MainWindow.move(1600, 940)
        self.dialog = None
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.gridLayout = QGridLayout(self.centralwidget)
        self.gridLayout.setSpacing(2)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setContentsMargins(2, 2, 2, 2)
        self.frame = QFrame(self.centralwidget)
        self.frame.setObjectName(u"frame")
        self.frame.setStyleSheet(u".QFrame{background-color: rgba(255, 255, 255, 64); border: 2px solid black; border-radius: 12px;}")
        self.frame.setFrameShape(QFrame.Box)
        self.frame.setFrameShadow(QFrame.Plain)
        self.frame.setLineWidth(1)
        self.frame.setMidLineWidth(0)
        self.verticalLayout = QVBoxLayout(self.frame)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(self.frame)
        self.label.setObjectName(u"label")
        self.label.setMinimumSize(QSize(60, 60))
        font = QFont()
        font.setPointSize(40)
        self.label.setFont(font)
        self.label.setScaledContents(True)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMargin(-20)
        self.label.setIndent(0)
        self.verticalLayout.addWidget(self.label)
        self.gridLayout.addWidget(self.frame, 0, 0, 1, 1)
        MainWindow.setCentralWidget(self.centralwidget)
        MainWindow.setAcceptDrops(True)
        MainWindow.installEventFilter(self)
        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.label.setText(QCoreApplication.translate("MainWindow", u"\u270d\ufe0f", None))
    # retranslateUi

    def eventFilter(self, obj, event):
        if event.type() == QEvent.DragEnter:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Drop:
            urls = event.mimeData().urls()
            file_paths = []
            show = 0
            for url in urls:
                file_paths.append(url.toLocalFile())
            if self.dialog:
                for file_path in file_paths:
                    res = self.dialog.append_new_file_to_list(file_path)
                    if res:
                        show = 1
                if show:
                    self.dialog.show()
                    self.dialog.activateWindow()
                else:
                    QMessageBox.information(None, 'Ошибка', "Не обнаружено поддерживаемых файлов")
            else:
                self.dialog = handle_dropped_files(file_paths)
            return True
        return super().eventFilter(obj, event)


