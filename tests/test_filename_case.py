import os
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide2.QtWidgets import QApplication

from main_functions import CustomListWidgetItem


class FilenameCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_widget_preserves_source_and_gf_filename_case(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, 'MixedCaseDocument.PDF')
            with open(source_path, 'wb') as source:
                source.write(b'not empty')

            widget = CustomListWidgetItem(source_path)
            try:
                self.assertEqual(source_path, widget.file_path)
                self.assertEqual(
                    os.path.join(directory, 'gf_MixedCaseDocument.PDF'),
                    widget.gf_file_path,
                )
            finally:
                widget.deleteLater()


if __name__ == '__main__':
    unittest.main()
