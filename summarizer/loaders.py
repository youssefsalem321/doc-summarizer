"""قراءة النصوص من txt / pdf / docx."""
import io
from pathlib import Path


def load_text(source, filename: str | None = None) -> str:
    """source: مسار ملف (str/Path) أو bytes (من رفع ملف في الواجهة)."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        filename = path.name
        data = path.read_bytes()
    else:
        data = source
    if not filename:
        raise ValueError("filename مطلوب عند تمرير bytes")

    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md", ".eml"):
        return data.decode("utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError("الـ PDF مفيهوش نص (غالبًا scan) - محتاج OCR.")
        return text
    if ext == ".docx":
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"نوع الملف غير مدعوم: {ext}")
