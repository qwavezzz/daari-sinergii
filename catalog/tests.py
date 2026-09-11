from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from .models import ProductImage, validate_image
from orders.test_support import fixture_cart


class PublicationTests(TestCase):
    def setUp(self):
        _, self.product, _ = fixture_cart()

    def test_draft_product_is_not_accessible_in_full_or_htmx(self):
        self.product.status = "draft"
        self.product.save(update_fields=["status"])
        for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
            response = self.client.get(self.product.get_absolute_url(), HTTP_HOST="shop.localhost", **headers)
            self.assertEqual(response.status_code, 404)

    def test_unpublishing_product_closes_previously_known_image_url(self):
        with TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=Path(directory)):
            stream = BytesIO()
            Image.new("RGB", (10, 10)).save(stream, "PNG")
            image = ProductImage.objects.create(
                product=self.product,
                image=SimpleUploadedFile("photo.png", stream.getvalue(), content_type="image/png"),
                alt="Тест",
            )
            url = image.image.url
            response = self.client.get(url, HTTP_HOST="shop.localhost")
            self.assertEqual(response.status_code, 200)
            # Consume through Django's test-client wrapper so it closes the file
            # without closing PostgreSQL's surrounding TestCase transaction.
            self.assertEqual(b"".join(response.streaming_content), stream.getvalue())
            self.product.status = "draft"
            self.product.save(update_fields=["status"])
            self.assertEqual(self.client.get(url, HTTP_HOST="shop.localhost").status_code, 404)

    def test_mismatched_image_extension_rejected(self):
        stream = BytesIO()
        Image.new("RGB", (10, 10)).save(stream, "PNG")
        with self.assertRaises(ValidationError):
            validate_image(SimpleUploadedFile("pretend.jpg", stream.getvalue()))
