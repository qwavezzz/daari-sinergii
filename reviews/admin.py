from django.contrib import admin

from content.admin import PublicationAdmin
from .models import Review


@admin.register(Review)
class ReviewAdmin(PublicationAdmin):
    search_fields = ("author", "organization", "text")
    filter_horizontal = ("products", "industries")
