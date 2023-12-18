from PyQt5 import QtWidgets
import os
import sys
from main_functions import *
from main_window import MainWindow

# C:/Users/dimas/DocumentSIGner/venv/Scripts/pyinstaller.exe --noconfirm --onedir  --console --windowed --icon C:/Users/dimas/DocumentSIGner/icons8-legal-document-64.ico --add-data "C:/Users/dimas/DocumentSIGner/UI;UI" "C:/Users/dimas/DocumentSIGner/documentSIGner.py"
# C:/Users/CourtUser/Desktop/release/DocumentSIGner/venv/Scripts/pyinstaller.exe --noconfirm --onedir  --console --windowed --icon C:/Users/CourtUser/Desktop/release/DocumentSIGner/icons8-legal-document-64.ico --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/UI;UI" --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/dcs.png;." --add-data "C:/Users/CourtUser/Desktop/release/DocumentSIGner/times.ttf;." "C:/Users/CourtUser/Desktop/release/DocumentSIGner/documentSIGner.py"



if __name__ == '__main__':
    try:
        app = QtWidgets.QApplication(sys.argv)
        main_ui = MainWindow(config)
        app.exec_()
    except:
        traceback.print_exc()


