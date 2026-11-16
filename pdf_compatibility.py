"""Structural checks for PDFs before they are saved or signed.

Do not repair broken resource references by deleting drawing commands: a lost
stamp or image cannot be reconstructed from a reference to the document catalog.
"""
import re

from pypdf import PdfReader
from pypdf.generic import ArrayObject, ContentStream, DictionaryObject, StreamObject


_LONG_REAL = re.compile(rb'(?<![\w.])[-+]?(?:\d*\.\d{12,})(?![\w.])')


def inspect_pdf_pages(document, compact=False):
    """Validate page resources; optionally reserialize legacy long real tokens.

    Parsing and serializing operands, rather than replacing bytes, preserves
    literal strings, inline images and encoded text. pypdf 5 writes real operands
    with bounded precision. Visit shared Form streams only once.
    """
    visited = set()
    needs_compaction = False

    def visit(container, location, is_page=False):
        nonlocal needs_compaction
        identity = id(container)
        if identity in visited:
            return
        visited.add(identity)
        resources = container.get('/Resources', DictionaryObject()).get_object()
        if not isinstance(resources, DictionaryObject):
            raise ValueError('Некорректные ресурсы PDF: ' + location)
        for category in ('/Font', '/XObject'):
            entries = resources.get(category, DictionaryObject()).get_object()
            if not isinstance(entries, DictionaryObject):
                raise ValueError('Некорректные ресурсы PDF: ' + location + category)
            for name, reference in entries.items():
                obj = reference.get_object()
                valid = isinstance(obj, DictionaryObject)
                if category == '/XObject':
                    valid = (isinstance(obj, StreamObject)
                             and obj.get('/Subtype') in ('/Image', '/Form', '/PS'))
                else:
                    valid = valid and obj.get('/Type') == '/Font'
                if not valid:
                    raise ValueError(
                        'Повреждён PDF: {} {} {} ссылается на {} вместо {}. '
                        'Нужен исходный документ до повреждения.'.format(
                            location, category, name,
                            obj.get('/Type', type(obj).__name__)
                            if isinstance(obj, DictionaryObject) else type(obj).__name__,
                            'изображения или Form' if category == '/XObject' else 'шрифта',
                        )
                    )
                if category == '/XObject' and obj.get('/Subtype') == '/Form':
                    visit(obj, location + ' ' + name)

        if is_page:
            contents = container.get('/Contents')
            if contents is None:
                return
            contents = contents.get_object()
            streams = contents if isinstance(contents, ArrayObject) else [contents]
            if any(not isinstance(s.get_object(), StreamObject) for s in streams):
                raise ValueError('Некорректный поток содержимого PDF: ' + location)
            data = b'\n'.join(s.get_object().get_data() for s in streams)
        else:
            data = container.get_data()
        if _LONG_REAL.search(data):
            needs_compaction = True
            if compact:
                if is_page:
                    parsed = ContentStream(container.raw_get('/Contents'), document)
                    # Materialize operations before get_data() to force serialization.
                    parsed.operations = list(parsed.operations)
                    container.replace_contents(parsed)
                else:
                    parsed = ContentStream(container, document)
                    parsed.operations = list(parsed.operations)
                    container.set_data(parsed.get_data())

    for index, page in enumerate(document.pages, 1):
        visit(page, 'страница {}'.format(index), is_page=True)
    return needs_compaction


def validate_pdf_file(path):
    reader = PdfReader(path, strict=True)
    try:
        inspect_pdf_pages(reader)
    finally:
        reader.close()
