from pathlib import Path
from urllib.parse import quote
from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ProductImageStorage(FileSystemStorage):
    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return str(Path(settings.PRIVATE_MEDIA_ROOT).resolve())

    def url(self, name):
        return "/product-images/" + quote(Path(name).name) + "/"


product_image_storage = ProductImageStorage()
