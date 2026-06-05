from __future__ import annotations

import re
import secrets
import string
from pathlib import Path


def generate_otp(length: int = 6) -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def _clean_extracted_text(text: str) -> str:
    text = re.sub(r'\r\n?', '\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_text_from_upload(uploaded_file) -> tuple[str | None, str | None]:
    filename = (uploaded_file.name or '').lower()
    suffix = Path(filename).suffix

    try:
        if suffix == '.pdf':
            try:
                from pypdf import PdfReader
            except ImportError:
                return None, 'PDF support is not installed. Install pypdf to enable PDF uploads.'

            reader = PdfReader(uploaded_file)
            extracted_text = []
            for page in reader.pages:
                extracted_text.append(page.extract_text() or '')
            text = '\n'.join(extracted_text)
        elif suffix == '.docx':
            try:
                from docx import Document
            except ImportError:
                return None, 'DOCX support is not installed. Install python-docx to enable Word uploads.'

            document = Document(uploaded_file)
            text = '\n'.join(paragraph.text for paragraph in document.paragraphs)
        else:
            raw_bytes = uploaded_file.read()
            for encoding in ('utf-8', 'utf-16', 'latin-1'):
                try:
                    text = raw_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    text = ''
            if not text:
                return None, 'Unsupported document format. Use PDF, DOCX, or a plain text file.'
    except Exception as exc:
        return None, f'Unable to read the uploaded file: {exc}'

    cleaned_text = _clean_extracted_text(text)
    if not cleaned_text:
        return None, 'No readable text was found in the uploaded file.'
    return cleaned_text, None
