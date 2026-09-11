from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase

from content.models import PublicationStatus
from .models import Review


class ReviewPublicationTests(TestCase):
    def test_published_review_requires_real_source_and_publication_basis(self):
        review = Review(
            author="Автор",
            text="Текст предоставленного отзыва",
            date=date(2026, 9, 11),
            status=PublicationStatus.PUBLISHED,
        )
        with self.assertRaises(ValidationError) as error:
            review.full_clean()
        self.assertIn("publication_basis", error.exception.message_dict)
        review.publication_basis = "Письмо автора с согласием на публикацию, хранится у компании."
        review.full_clean()
        review.save()
        self.assertEqual(Review.objects.published().count(), 1)

    def test_home_has_only_moderated_reviews_selected_for_home(self):
        review = Review.objects.create(
            author="Неопубликованный автор", text="Закрытый текст", date=date(2026, 9, 11), show_on_home=True
        )
        self.assertNotContains(self.client.get("/", HTTP_HOST=settings.MAIN_HOST), 'id="reviews"')
        review.status = PublicationStatus.PUBLISHED
        review.publication_basis = "Согласие автора получено"
        review.save()
        response = self.client.get("/", HTTP_HOST=settings.MAIN_HOST)
        self.assertContains(response, review.text)
        review.status = PublicationStatus.ARCHIVED
        review.save()
        self.assertNotContains(
            self.client.get("/", HTTP_HOST=settings.MAIN_HOST, HTTP_HX_REQUEST="true"), review.text
        )
