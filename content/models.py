from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from .uploads import private_storage, private_upload_path, validate_image, validate_pdf


class PublicationStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    PUBLISHED = "published", "Опубликован"
    ARCHIVED = "archived", "Архив"


class PublicationQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=PublicationStatus.PUBLISHED, published_at__lte=timezone.now())


class Publication(models.Model):
    status = models.CharField(
        "Публикация",
        max_length=12,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField("Дата публикации", blank=True, null=True)
    order = models.PositiveIntegerField("Порядок", default=0)
    show_on_home = models.BooleanField("Показывать на главной", default=False)
    updated_at = models.DateTimeField("Последнее изменение", auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор изменения",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_changes",
    )
    objects = PublicationQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ("order", "pk")

    def save(self, *args, **kwargs):
        if self.status == PublicationStatus.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
            if kwargs.get("update_fields"):
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"published_at"}
        super().save(*args, **kwargs)

    @property
    def is_published(self):
        return (
            self.status == PublicationStatus.PUBLISHED
            and self.published_at is not None
            and self.published_at <= timezone.now()
        )


class SiteSettings(models.Model):
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    company_name = models.CharField("Название компании", max_length=200, blank=True)
    legal_name = models.CharField("Юридическое наименование", max_length=250, blank=True)
    email = models.EmailField("Электронная почта", blank=True)
    phone = models.CharField(
        "Телефон для ссылки",
        max_length=20,
        blank=True,
        validators=[RegexValidator(r"^\+?[0-9]{7,15}$", "Укажите международный номер без пробелов.")],
    )
    phone_label = models.CharField("Телефон для отображения", max_length=40, blank=True)
    address = models.TextField("Адрес", blank=True)
    footer_label = models.CharField("Подпись в подвале", max_length=300, blank=True)

    class Meta:
        verbose_name = "Контакты и сведения о компании"
        verbose_name_plural = "Контакты и сведения о компании"
        constraints = [models.CheckConstraint(condition=Q(singleton=1), name="site_settings_singleton")]

    def __str__(self):
        return "Контакты и сведения о компании"


class SiteText(models.Model):
    key = models.SlugField("Ключ поля", max_length=100, unique=True)
    label = models.CharField("Название поля", max_length=200)
    value = models.TextField("Текст", blank=True)
    updated_at = models.DateTimeField("Последнее изменение", auto_now=True)

    class Meta:
        verbose_name = "Текст сайта"
        verbose_name_plural = "Тексты сайта"
        ordering = ("key",)

    def __str__(self):
        return self.label


class Collection(Publication):
    source_key = models.SlugField(
        "Ключ первоначального импорта", unique=True, null=True, blank=True, editable=False
    )
    slug = models.SlugField("Адрес подборки", unique=True)
    title = models.CharField("Название", max_length=250)
    intro = models.TextField("Введение")
    image_base = models.SlugField("Ключ исходного изображения", blank=True, max_length=100)
    handbook_chapter = models.PositiveSmallIntegerField("Страница справочника", blank=True, null=True)

    class Meta(Publication.Meta):
        verbose_name = "Тематическая подборка"
        verbose_name_plural = "Тематические подборки"
        permissions = [("publish_collection", "Может публиковать подборки")]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("content:collection", kwargs={"slug": self.slug}, urlconf="config.main_urls")

    def clean(self):
        super().clean()
        if CollectionAlias.objects.filter(slug=self.slug).exclude(collection_id=self.pk).exists():
            raise ValidationError({"slug": "Этот адрес сохранён за другой подборкой."})

    def save(self, *args, **kwargs):
        old_slug = (
            type(self).objects.filter(pk=self.pk).values_list("slug", flat=True).first() if self.pk else None
        )
        super().save(*args, **kwargs)
        if old_slug and old_slug != self.slug:
            CollectionAlias.objects.get_or_create(slug=old_slug, defaults={"collection": self})

    @property
    def image_url(self):
        return static(f"assets/photos/optimized/{self.image_base}-bg-768.webp") if self.image_base else ""


class CollectionSection(models.Model):
    collection = models.ForeignKey(
        Collection, verbose_name="Подборка", related_name="sections", on_delete=models.CASCADE
    )
    title = models.CharField("Заголовок", max_length=250)
    body = models.TextField("Текст")
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Раздел подборки"
        verbose_name_plural = "Разделы подборки"
        ordering = ("order", "pk")


class Industry(Publication):
    source_key = models.SlugField(
        "Ключ первоначального импорта", unique=True, null=True, blank=True, editable=False
    )
    slug = models.SlugField("Ключ отраслевой сцены", unique=True)
    title = models.CharField("Название", max_length=200)
    caption = models.TextField("Описание")
    action_label = models.CharField("Текст ссылки", max_length=150)
    image_base = models.SlugField("Ключ исходного изображения", max_length=100)
    collection = models.ForeignKey(
        Collection, verbose_name="Материалы по направлению", blank=True, null=True, on_delete=models.SET_NULL
    )

    class Meta(Publication.Meta):
        verbose_name = "Отраслевой сценарий"
        verbose_name_plural = "Отраслевые сценарии"
        permissions = [("publish_industry", "Может публиковать отраслевые сценарии")]

    def __str__(self):
        return self.title

    @property
    def image_url(self):
        return static(f"assets/photos/optimized/{self.image_base}-bg-1536.webp")

    @property
    def image_srcset(self):
        return ", ".join(
            f"{static(f'assets/photos/optimized/{self.image_base}-bg-{size}.webp')} {size}w"
            for size in (768, 1536)
        )

    @property
    def mobile_image_url(self):
        return static(f"assets/photos/optimized/{self.image_base}-bg-mobile-720.webp")


class Document(Publication):
    source_key = models.SlugField(
        "Ключ первоначального импорта", unique=True, null=True, blank=True, editable=False
    )
    slug = models.SlugField("Постоянный адрес", unique=True)
    title = models.CharField("Название", max_length=300)
    description = models.TextField("Краткое описание", blank=True)
    material_type = models.CharField("Тип материала", max_length=100)
    file = models.FileField(
        "PDF", storage=private_storage, upload_to=private_upload_path, validators=[validate_pdf]
    )
    pages = models.PositiveSmallIntegerField("Страниц", null=True, blank=True)
    is_declaration = models.BooleanField("Декларация соответствия", default=False)
    category = models.CharField("Категория декларации", max_length=100, blank=True)
    registration = models.CharField("Регистрационный номер", max_length=200, blank=True)
    valid_until_label = models.CharField("Срок действия", max_length=150, blank=True)
    collections = models.ManyToManyField(
        Collection, verbose_name="Тематические подборки", related_name="documents", blank=True
    )
    industries = models.ManyToManyField(
        Industry, verbose_name="Направления", related_name="documents", blank=True
    )
    products = models.ManyToManyField(
        "catalog.Product", verbose_name="Товары", related_name="documents", blank=True
    )

    class Meta(Publication.Meta):
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        permissions = [("publish_document", "Может публиковать документы")]

    def __str__(self):
        return self.title

    @property
    def file_url(self):
        return reverse("content:document", kwargs={"slug": self.slug}, urlconf="config.main_urls")

    def get_absolute_url(self):
        return self.file_url

    def clean(self):
        super().clean()
        if DocumentAlias.objects.filter(path=f"slug:{self.slug}").exclude(document_id=self.pk).exists():
            raise ValidationError({"slug": "Этот адрес сохранён за другим документом."})

    def save(self, *args, **kwargs):
        old_slug = (
            type(self).objects.filter(pk=self.pk).values_list("slug", flat=True).first() if self.pk else None
        )
        super().save(*args, **kwargs)
        if old_slug and old_slug != self.slug:
            DocumentAlias.objects.get_or_create(path=f"slug:{old_slug}", defaults={"document": self})


class DocumentAlias(models.Model):
    path = models.CharField("Прежний путь или slug", max_length=250, unique=True)
    document = models.ForeignKey(Document, related_name="aliases", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Прежний адрес документа"
        verbose_name_plural = "Прежние адреса документов"


class CollectionAlias(models.Model):
    slug = models.SlugField("Прежний адрес подборки", unique=True)
    collection = models.ForeignKey(Collection, related_name="aliases", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Прежний адрес подборки"
        verbose_name_plural = "Прежние адреса подборок"


class Video(Publication):
    class Provider(models.TextChoices):
        RUTUBE = "rutube", "Rutube"
        YOUTUBE = "youtube", "YouTube"
        VIMEO = "vimeo", "Vimeo"

    title = models.CharField("Название", max_length=250)
    description = models.TextField("Описание", blank=True)
    provider = models.CharField("Видеосервис", max_length=20, choices=Provider.choices)
    provider_id = models.CharField(
        "Идентификатор видео",
        max_length=80,
        validators=[RegexValidator(r"^[a-zA-Z0-9_-]+$", "Только идентификатор видео, без HTML и URL.")],
    )
    cover = models.ImageField(
        "Обложка",
        blank=True,
        storage=private_storage,
        upload_to=private_upload_path,
        validators=[validate_image],
    )
    industries = models.ManyToManyField(Industry, verbose_name="Направления", blank=True)
    products = models.ManyToManyField(
        "catalog.Product", verbose_name="Товары", related_name="videos", blank=True
    )

    class Meta(Publication.Meta):
        verbose_name = "Видео"
        verbose_name_plural = "Видео"
        permissions = [("publish_video", "Может публиковать видео")]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        approved = getattr(settings, "CONTENT_VIDEO_PROVIDERS", ())
        if self.status == PublicationStatus.PUBLISHED and self.provider not in approved:
            raise ValidationError(
                {
                    "provider": "Перед публикацией согласуйте видеосервис и добавьте его в CONTENT_VIDEO_PROVIDERS."
                }
            )

    @property
    def external_url(self):
        prefixes = {
            "rutube": "https://rutube.ru/video/",
            "youtube": "https://www.youtube.com/watch?v=",
            "vimeo": "https://vimeo.com/",
        }
        return prefixes[self.provider] + self.provider_id

    @property
    def cover_url(self):
        return (
            reverse("content:video_cover", kwargs={"pk": self.pk}, urlconf="config.main_urls")
            if self.cover
            else ""
        )
