import io
import zipfile
from pathlib import Path

from docx import Document
from PIL import Image
from pypdf import PdfReader

from .config import settings

ALLOWED_SUFFIXES = {".pdf", ".docx", ".md", ".txt", ".png", ".jpg", ".jpeg"}


def validate_upload(name: str, content: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("仅支持 PDF、DOCX、MD/TXT、PNG/JPG")
    if not content:
        raise ValueError("文件内容为空")
    if len(content) > settings.upload_max_bytes:
        raise ValueError("文件超过 20 MB 上限")
    if suffix == ".pdf" and not content.startswith(b"%PDF"):
        raise ValueError("文件内容不是有效 PDF")
    if suffix == ".docx":
        _validate_docx_archive(content)
    return suffix


def _validate_docx_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            expanded = sum(item.file_size for item in infos)
            if len(infos) > 3000 or expanded > 100 * 1024 * 1024:
                raise ValueError("DOCX 解压后内容过大")
            if any(".." in Path(item.filename).parts for item in infos):
                raise ValueError("DOCX 包含非法路径")
    except zipfile.BadZipFile as exc:
        raise ValueError("文件内容不是有效 DOCX") from exc


def extract_text(name: str, content: bytes) -> str:
    suffix = validate_upload(name, content)
    if suffix in {".md", ".txt"}:
        text = content.decode("utf-8", errors="replace")
    elif suffix == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > settings.upload_max_pages:
            raise ValueError("PDF 页数超过限制")
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".docx":
        document = Document(io.BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    else:
        Image.MAX_IMAGE_PIXELS = 30_000_000
        image = Image.open(io.BytesIO(content))
        image.verify()
        image = Image.open(io.BytesIO(content))
        try:
            import pytesseract

            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
        except Exception as exc:
            raise ValueError("图片 OCR 不可用，请确认已安装 Tesseract 中文语言包") from exc
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(normalized) < 20:
        raise ValueError("没有提取到足够的文本内容")
    return normalized[:120_000]

