import os
import re
import tempfile
import unittest
from unittest import mock

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText
from pypdf.generic import (DecodedStreamObject, DictionaryObject, NameObject,
                           RectangleObject, TextStringObject)
from reportlab.pdfgen import canvas

import main_functions
from main_functions import (A4_PORTRAIT, add_stamp, execute_sign_job,
                            get_stamp_coords_for_preview, normalize_pdf_in_place)


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

    def test_legacy_long_numbers_are_repaired_even_on_a4(self):
        path = self.path('legacy-a4.pdf')
        writer = PdfWriter()
        page = writer.add_blank_page(*A4_PORTRAIT)
        stream = DecodedStreamObject()
        stream.set_data(b'q 1.018546462180603962011105068 0 0 1 0 0 cm '
                        b'0 0 100 100 re f Q')
        page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(path)
        writer.close()
        self.assertTrue(normalize_pdf_in_place(path))
        reader = PdfReader(path, strict=True)
        try:
            data = reader.pages[0].get_contents().get_data()
            self.assertNotIn(b'1.018546462180603962011105068', data)
            self.assertIn(b're', data)
            self.assertIn(b'cm', data)
        finally:
            reader.close()
        self.assertFalse(normalize_pdf_in_place(path))

    def test_catalog_instead_of_stamp_is_rejected_without_changes(self):
        path = self.path('broken-stamp.pdf')
        writer = PdfWriter()
        page = writer.add_blank_page(*A4_PORTRAIT)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/XObject'): DictionaryObject({
                NameObject('/Stamp'): writer._root_object.indirect_reference,
            }),
        })
        stream = DecodedStreamObject()
        stream.set_data(b'q /Stamp Do Q')
        page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(path)
        writer.close()
        with open(path, 'rb') as source:
            original = source.read()
        with self.assertRaisesRegex(ValueError, '/Catalog'):
            normalize_pdf_in_place(path)
        with self.assertRaisesRegex(ValueError, '/Catalog'):
            add_stamp(path, 'unused.png', [0])
        with open(path, 'rb') as result:
            self.assertEqual(original, result.read())

    def test_stamp_image_resources_survive_normalization_and_repeated_stamping(self):
        path = self.path('images.pdf')
        stamp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dcs.png')
        pdf_canvas = canvas.Canvas(path, pagesize=(400, 900))
        for _ in range(3):
            pdf_canvas.drawImage(stamp_path, 20, 200, width=200, height=100, mask='auto')
            pdf_canvas.showPage()
        pdf_canvas.save()
        normalize_pdf_in_place(path)
        with mock.patch.dict(main_functions.config, {'stamp_place': 0}):
            for _ in range(2):
                add_stamp(path, stamp_path, 'all')
        reader = PdfReader(path, strict=True)
        try:
            for page in reader.pages:
                objects = page['/Resources']['/XObject']
                self.assertTrue(objects)
                for reference in objects.values():
                    self.assertEqual('/Image', reference.get_object()['/Subtype'])
                    self.assertTrue(reference.get_object().get_data())
        finally:
            reader.close()

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

    def test_generated_coordinates_are_compact_for_legacy_adobe_reader(self):
        path = self.path('legacy-reader.pdf')
        pdf_canvas = canvas.Canvas(path, pagesize=(591.36, 837.12))
        pdf_canvas.rect(20, 20, 100, 100)
        pdf_canvas.save()

        self.assertTrue(normalize_pdf_in_place(path))
        reader = PdfReader(path, strict=True)
        try:
            page = reader.pages[0]
            for box in (page.mediabox, page.cropbox, page.trimbox):
                for value in box:
                    fractional = repr(value).partition('.')[2]
                    self.assertLessEqual(len(fractional), 5)

            contents = page.raw_get('/Contents').get_object()
            streams = contents if isinstance(contents, list) else [contents]
            content_bytes = b'\n'.join(
                stream.get_object().get_data() for stream in streams
            )
            numbers = re.findall(
                rb'(?<![A-Za-z0-9])[-+]?(?:\d+\.\d+|\.\d+|\d+)(?![A-Za-z0-9])',
                content_bytes,
            )
            self.assertTrue(numbers)
            self.assertLessEqual(max(map(len, numbers)), 12)
        finally:
            reader.stream.close()

    def test_annotation_is_transformed_and_preserved(self):
        path = self.path('annotation.pdf')
        writer = PdfWriter()
        writer.add_blank_page(width=400, height=800)
        writer.pages[0].rotate(90)
        writer.add_annotation(
            0,
            FreeText(text='test', rect=(40, 80, 140, 180)),
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

    def test_enlargement_to_a4_does_not_clip_right_edge(self):
        path = self.path('enlarge.pdf')
        pdf_canvas = canvas.Canvas(path, pagesize=(300, 400))
        pdf_canvas.setFillColorRGB(1, 0, 0)
        pdf_canvas.rect(270, 100, 20, 200, stroke=0, fill=1)
        pdf_canvas.save()
        normalize_pdf_in_place(path)
        document = pdfium.PdfDocument(path)
        page = document[0]
        bitmap = page.render(scale=1)
        try:
            image = bitmap.to_pil().convert('RGB')
            red = image.getpixel((555, image.height // 2))
            self.assertGreater(red[0], 200)
            self.assertLess(red[1], 40)
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
            resources = reader.pages[0]['/Resources'].get_object()
            for font_reference in resources.get('/Font', {}).get_object().values():
                self.assertEqual('/Font', font_reference.get_object().get('/Type'))
            for xobject_reference in resources.get('/XObject', {}).get_object().values():
                self.assertIn(
                    xobject_reference.get_object().get('/Subtype'),
                    ('/Form', '/Image', '/PS'),
                )
        finally:
            reader.stream.close()

    def test_a4_preview_uses_temporary_copy_and_preserves_original(self):
        path = self.path('signed-original.pdf')
        self.write_blank_pdf(path, [(400, 900, 0)])
        with open(path, 'rb') as source_file:
            original = source_file.read()
        preview_paths = []

        def fake_editor(preview_path, _pages, _stamp_image):
            preview_paths.append(preview_path)
            reader = PdfReader(preview_path)
            try:
                self.assertTrue(all(main_functions._page_is_a4(page) for page in reader.pages))
            finally:
                reader.stream.close()
            return {preview_path: {0: (10, 20, 110, 70)}}

        with mock.patch(
            'main_functions.get_stamp_coords_for_filepath', side_effect=fake_editor
        ):
            result = get_stamp_coords_for_preview(
                path, [0], 'stamp.png', normalize_to_a4=True
            )

        self.assertEqual({path: {0: (10, 20, 110, 70)}}, result)
        self.assertEqual(1, len(preview_paths))
        self.assertNotEqual(path, preview_paths[0])
        self.assertFalse(os.path.exists(preview_paths[0]))
        with open(path, 'rb') as source_file:
            self.assertEqual(original, source_file.read())

    def test_clean_original_mode_normalizes_only_gf_copy(self):
        path = self.path('existing-signature.pdf')
        self.write_blank_pdf(path, [(400, 900, 0)])
        with open(path, 'rb') as source_file:
            original = source_file.read()

        def fake_sign(source_path, _certificate_data):
            signature_path = source_path + '.sig'
            with open(signature_path, 'wb') as signature:
                signature.write(b'test signature')
            return signature_path

        job = {
            'file_path': path,
            'pages': [0],
            'stamp': 'regular',
            'is_epos': False,
            'custom_coords': {0: (10, 20, 110, 70)},
            'certificate_name': 'Test certificate',
            'certificate_data': {},
            'sign_original': False,
            'normalize_to_a4': True,
            'rules': (),
        }
        stamp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dcs.png')
        with mock.patch('main_functions.create_stamp_image', return_value=stamp_path), \
                mock.patch('main_functions.sign_document', side_effect=fake_sign):
            status, message, _, _ = execute_sign_job(job)

        self.assertEqual((0, ''), (status, message))
        with open(path, 'rb') as source_file:
            self.assertEqual(original, source_file.read())
        stamped_copy = self.path('gf_existing-signature.pdf')
        self.assertTrue(os.path.exists(stamped_copy))
        reader = PdfReader(stamped_copy)
        try:
            self.assertTrue(all(main_functions._page_is_a4(page) for page in reader.pages))
        finally:
            reader.stream.close()


if __name__ == '__main__':
    unittest.main()
