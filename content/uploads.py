"""Validated, private editorial media. No storage URL bypasses publication checks."""

import os
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    def __init__(self):
        super().__init__()

    @property
    def base_location(self):
        return getattr(settings, "PRIVATE_MEDIA_ROOT", settings.BASE_DIR / "var" / "private-media")

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Private media is only available through an authorized view.")


private_storage = PrivateMediaStorage()


def private_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"{instance._meta.app_label}/{instance._meta.model_name}/{uuid4().hex}{extension}"


def _read_header(value, size=32):
    opened_here = value.closed
    position = value.tell()
    try:
        value.seek(0)
        return value.read(size)
    finally:
        if opened_here:
            value.close()
        else:
            value.seek(position)


def validate_pdf(value):
    if Path(value.name).suffix.lower() != ".pdf":
        raise ValidationError("Загрузите документ PDF.")
    if value.size > getattr(settings, "CONTENT_DOCUMENT_MAX_BYTES", 30 * 1024 * 1024):
        raise ValidationError("Размер PDF превышает установленный лимит (по умолчанию 30 МБ).")
    if not _read_header(value).startswith(b"%PDF-"):
        raise ValidationError("Содержимое файла не соответствует формату PDF.")


def validate_image(value):
    from PIL import Image, UnidentifiedImageError

    allowed = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
    expected = allowed.get(Path(value.name).suffix.lower())
    if not expected:
        raise ValidationError("Разрешены изображения JPG, PNG и WebP.")
    if value.size > getattr(settings, "CONTENT_IMAGE_MAX_BYTES", 8 * 1024 * 1024):
        raise ValidationError("Изображение превышает установленный лимит (по умолчанию 8 МБ).")
    opened_here = value.closed
    position = value.tell()
    try:
        value.seek(0)
        with Image.open(value, formats=[expected]) as image:
            if image.format != expected or image.width * image.height > 40_000_000:
                raise ValidationError("Неверный формат или слишком большое разрешение изображения.")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("Не удалось прочитать изображение.") from exc
    finally:
        if opened_here:
            value.close()
        else:
            value.seek(position)
