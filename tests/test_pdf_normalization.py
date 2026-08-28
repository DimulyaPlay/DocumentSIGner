import os
import tempfile
import unittest

import pypdfium2 as pdfium
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import AnnotationBuilder, NameObject, RectangleObject, TextStringObject
from reportlab.pdfgen import canvas

from main_functions import A4_PORTRAIT, add_stamp, normalize_pdf_in_place


class PdfNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix='document-signer-tests-')

    def tearDown(self):
        self.temp_dir.cleanup()

    def path(self, name):
        return os.path.join(self.temp_dir.name, name)

    def write_blank_pdf(self, path, pages, metadata=None, password=None):
        writer = PdfWriter()
        for width, height, rotation in pages:
            writer.add_blank_page(width=width, height=height)
            if rotation:
                writer.pages[-1].rotate(rotation)
        if metadata:
            writer.add_metadata(metadata)
        if password:
            writer.encrypt(password)
        with open(path, 'wb') as output_file:
            writer.write(output_file)
        writer.close()

    def test_already_a4_is_not_rewritten(self):
        path = self.path('already-a4.pdf')
        self.write_blank_pdf(path, [(A4_PORTRAIT[0], A4_PORTRAIT[1], 0)])
        with open(path, 'rb') as source_file:
            original = source_file.read()

        self.assertFalse(normalize_pdf_in_place(path))
        with open(path, 'rb') as result_file:
            self.assertEqual(original, result_file.read())

    def test_mixed_pages_keep_count_orientation_and_metadata(self):
        path = self.path('mixed.pdf')
        self.write_blank_pdf(
            path,
            [(400, 900, 0), (900, 400, 0), (400, 900, 90)],
            metadata={'/Title': 'DocumentSIGner normalization test'},
        )

        self.assertTrue(normalize_pdf_in_place(path))
        reader = PdfReader(path)
        try:
            self.assertEqual(3, len(reader.pages))
            self.assertEqual('DocumentSIGner normalization test', reader.metadata.title)
            expected = (
                A4_PORTRAIT,
                (A4_PORTRAIT[1], A4_PORTRAIT[0]),
                (A4_PORTRAIT[1], A4_PORTRAIT[0]),
            )
            for page, (width, height) in zip(reader.pages, expected):
                self.assertAlmostEqual(width, float(page.mediabox.width), places=3)
                self.assertAlmostEqual(height, float(page.mediabox.height), places=3)
                self.assertEqual(0, page.rotation)
        finally:
            reader.stream.close()

    def test_annotation_is_transformed_and_preserved(self):
        path = self.path('annotation.pdf')
        writer = PdfWriter()
        writer.add_blank_page(width=400, height=800)
        writer.pages[0].rotate(90)
        writer.add_annotation(
            0,
            AnnotationBuilder.free_text('test', rect=(40, 80, 140, 180)),
        )
        with open(path, 'wb') as output_file:
            writer.write(output_file)
        writer.close()

        self.assertTrue(normalize_pdf_in_place(path))
        reader = PdfReader(path)
        try:
            page = reader.pages[0]
            annotations = page['/Annots'].get_object()
            self.assertEqual(1, len(annotations))
            rectangle = [float(value) for value in annotations[0].get_object()['/Rect']]
            self.assertLess(rectangle[0], rectangle[2])
            self.assertLess(rectangle[1], rectangle[3])
            self.assertGreaterEqual(min(rectangle), 0)
            self.assertLessEqual(rectangle[2], float(page.mediabox.width))
            self.assertLessEqual(rectangle[3], float(page.mediabox.height))
        finally:
            reader.stream.close()

    def test_cropbox_is_clipped_and_content_remains_vector(self):
        path = self.path('cropped.pdf')
        pdf_canvas = canvas.Canvas(path, pagesize=(600, 1000))
        pdf_canvas.setFillColorRGB(1, 0, 0)
        pdf_canvas.rect(0, 0, 600, 1000, stroke=0, fill=1)
        pdf_canvas.save()
        reader = PdfReader(path)
        writer = PdfWriter()
        page = reader.pages[0]
        page.cropbox = RectangleObject((100, 100, 500, 900))
        writer.add_page(page)
        with open(path + '.crop', 'wb') as output_file:
            writer.write(output_file)
        writer.close()
        reader.stream.close()
        os.replace(path + '.crop', path)

        self.assertTrue(normalize_pdf_in_place(path))
        document = pdfium.PdfDocument(path)
        page = document[0]
        bitmap = page.render(scale=1)
        try:
            image = bitmap.to_pil().convert('RGB')
            middle = image.getpixel((image.width // 2, image.height // 2))
            margin = image.getpixel((10, image.height // 2))
            self.assertGreater(middle[0], 200)
            self.assertLess(middle[1], 40)
            self.assertGreater(min(margin), 240)
        finally:
            bitmap.close()
            page.close()
            document.close()

    def test_password_failure_does_not_modify_source(self):
        path = self.path('encrypted.pdf')
        self.write_blank_pdf(path, [(400, 800, 0)], password='secret')
        with open(path, 'rb') as source_file:
            original = source_file.read()

        with self.assertRaisesRegex(ValueError, 'паролем'):
            normalize_pdf_in_place(path)
        with open(path, 'rb') as result_file:
            self.assertEqual(original, result_file.read())

    def test_outline_and_stamp_survive_full_workflow(self):
        path = self.path('workflow.pdf')
        writer = PdfWriter()
        writer.add_blank_page(width=500, height=1000)
        writer.add_outline_item('First page', 0)
        writer._root_object[NameObject('/Lang')] = TextStringObject('ru-RU')
        with open(path, 'wb') as output_file:
            writer.write(output_file)
        writer.close()

        self.assertTrue(normalize_pdf_in_place(path))
        stamp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dcs.png')
        add_stamp(path, stamp_path, [0], {0: (50, 50, 250, 150)})

        reader = PdfReader(path)
        try:
            self.assertEqual(1, len(reader.pages))
            self.assertEqual('First page', reader.outline[0].title)
            self.assertEqual('ru-RU', reader.trailer['/Root']['/Lang'])
            self.assertIsNotNone(reader.pages[0].get_contents())
        finally:
            reader.stream.close()


if __name__ == '__main__':
    unittest.main()
