import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide2.QtWidgets import QApplication
from pypdf import PdfWriter
from stamp_editor import PlaceImageStampOnA4
import main_functions


class StampScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pdf = str(Path(self.temp.name) / 'sample.pdf')
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.add_blank_page(width=595, height=842)
        with open(self.pdf, 'wb') as stream:
            writer.write(stream)
        writer.close()
        self.stamp = str(Path(__file__).resolve().parents[1] / 'dcs.png')

    def test_editor_starts_at_configured_scale_and_slider_stays_in_sync(self):
        for scale in (25, 30, 35):
            dialog = PlaceImageStampOnA4(self.pdf, [0], self.stamp, initial_scale=scale)
            try:
                self.assertEqual(dialog.scale_slider.value(), scale)
                self.assertEqual(dialog.stamp_widget.current_scale, scale / 100)
                self.assertEqual(dialog.stamp_widget.stamp.width(),
                                 int(dialog.stamp_widget.stamp_original.width() * scale / 100))
                dialog.scale_slider.setValue(40)
                dialog.next_page()
                self.assertEqual(dialog.stamp_widget.current_scale, 0.4)
                self.assertEqual(dialog.scale_slider.value(), 40)
            finally:
                dialog.reject()

    def test_configured_scale_changes_exported_pdf_coordinates(self):
        def accept_current(dialog):
            dialog.apply_changes()
            return dialog.result()

        with patch.object(PlaceImageStampOnA4, 'exec_', accept_current):
            with patch.dict(main_functions.config, {'stamp_scale_percent': 25}):
                base = main_functions.get_stamp_coords_for_filepath(self.pdf, [0], self.stamp)
            with patch.dict(main_functions.config, {'stamp_scale_percent': 30}):
                enlarged = main_functions.get_stamp_coords_for_filepath(self.pdf, [0], self.stamp)
        base_rect = base[self.pdf][0]
        enlarged_rect = enlarged[self.pdf][0]
        self.assertAlmostEqual((enlarged_rect[2] - enlarged_rect[0]) /
                               (base_rect[2] - base_rect[0]), 1.2, delta=0.01)


if __name__ == '__main__':
    unittest.main()
