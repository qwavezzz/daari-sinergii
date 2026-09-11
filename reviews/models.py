from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from content.models import Publication, PublicationStatus
from content.uploads import private_storage, private_upload_path, validate_image


class Review(Publication):
    author = models.CharField("Имя автора", max_length=150)
    organization = models.CharField("Организация", max_length=200, blank=True)
    text = models.TextField("Текст отзыва")
    date = models.DateField("Дата отзыва")
    photo = models.ImageField(
        "Фотография или логотип",
        blank=True,
        storage=private_storage,
        upload_to=private_upload_path,
        validators=[validate_image],
    )
    products = models.ManyToManyField(
        "catalog.Product", related_name="reviews", verbose_name="Товары", blank=True
    )
    industries = models.ManyToManyField("content.Industry", verbose_name="Направления", blank=True)
    publication_basis = models.TextField(
        "Основание для публикации",
        blank=True,
        help_text="Внутренняя запись: источник и разрешение автора. На сайте не отображается.",
    )

    class Meta(Publication.Meta):
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        permissions = [("publish_review", "Может публиковать отзывы")]

    def __str__(self):
        return self.author

    def clean(self):
        super().clean()
        if self.status == PublicationStatus.PUBLISHED and not self.publication_basis.strip():
            raise ValidationError(
                {"publication_basis": "Укажите источник и основание публикации подлинного отзыва."}
            )

    @property
    def photo_url(self):
        return (
            reverse("content:review_photo", kwargs={"pk": self.pk}, urlconf="config.main_urls")
            if self.photo
            else ""
        )
