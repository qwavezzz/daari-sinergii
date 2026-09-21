import mimetypes
from pathlib import Path

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_headers

from reviews.models import Review

from .models import Collection, CollectionAlias, Document, DocumentAlias, Video
from .services import editorial_context
from .seo import absolute_main_url, schema_context


def is_fragment(request):
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


def page_context(request, title, description):
    return {
        "page_title": title,
        "page_description": description,
        "canonical_url": request.build_absolute_uri(request.path),
    }


@require_GET
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
def home(request):
    context = editorial_context()
    context.update(schema_context(request))
    context.update(
        page_context(
            request,
            context["site_content"].get(
                "home_meta_title", "Дары Синергии — системы озонирования воды, масла и гидролаты"
            ),
            context["site_content"].get(
                "home_meta_description",
                "Системы озонирования воды, косметические масла и гидролаты. Материалы и документы компании.",
            ),
        )
    )
    response = render(
        request,
        "site/partials/landing_content.html" if is_fragment(request) else "site/landing.html",
        context,
    )
    patch_cache_control(response, no_cache=True)
    return response


@require_GET
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
def materials(request, slug=None):
    topic = None
    if slug:
        topic = Collection.objects.published().prefetch_related("sections").filter(slug=slug).first()
        if topic is None:
            alias = (
                CollectionAlias.objects.filter(slug=slug, collection__in=Collection.objects.published())
                .select_related("collection")
                .first()
            )
            if alias:
                return HttpResponsePermanentRedirect(alias.collection.get_absolute_url())
            raise Http404("Подборка не найдена")
    selected = request.GET.get("direction", "all")
    topics = Collection.objects.published()
    documents = Document.objects.published().filter(is_declaration=False)
    if topic:
        documents = documents.filter(collections=topic)
    elif selected != "all":
        direction = get_object_or_404(topics, slug=selected)
        documents = documents.filter(Q(collections=direction) | Q(source_key="handbook")).distinct()
    context = editorial_context()
    context.update(
        {
            "topic": topic,
            "topics": topics,
            "selected_direction": selected,
            "document_count": documents.count(),
            "document_page": Paginator(documents, 24).get_page(request.GET.get("page")),
            "topic_declarations": Document.objects.published().filter(is_declaration=True, collections=topic)
            if topic
            else Document.objects.none(),
        }
    )
    title = (
        topic.title
        if topic
        else context["site_content"].get("materials_title", "Материалы о технологии и применении")
    )
    intro = topic.intro if topic else context["site_content"].get("materials_intro", "")
    context.update(page_context(request, f"{title} — Дары Синергии", intro))
    context.update({"material_title": title, "material_intro": intro})
    context.update(schema_context(request, topic=topic, materials=True))
    response = render(
        request,
        "site/partials/materials_content.html" if is_fragment(request) else "site/materials.html",
        context,
    )
    patch_cache_control(response, no_cache=True)
    return response


def serve_private_file(file, *, attachment=False, filename=None, content_type=None):
    if not file or not file.storage.exists(file.name):
        raise Http404("Файл не найден")
    response = FileResponse(
        file.open("rb"),
        as_attachment=attachment,
        filename=filename or Path(file.name).name,
        content_type=content_type or mimetypes.guess_type(file.name)[0] or "application/octet-stream",
    )
    patch_cache_control(response, private=True, no_store=True)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@require_GET
def document(request, slug):
    item = Document.objects.published().filter(slug=slug).first()
    if item is None:
        alias = (
            DocumentAlias.objects.filter(path=f"slug:{slug}", document__in=Document.objects.published())
            .select_related("document")
            .first()
        )
        if alias:
            return HttpResponsePermanentRedirect(alias.document.file_url)
        raise Http404("Документ не найден")
    response = serve_private_file(
        item.file,
        attachment=request.GET.get("download") == "1",
        filename=f"{item.slug}.pdf",
        content_type="application/pdf",
    )
    response["Link"] = f'<{absolute_main_url(item.file_url)}>; rel="canonical"'
    return response


@require_GET
def legacy_document(request, path):
    alias = get_object_or_404(
        DocumentAlias.objects.select_related("document"),
        path=f"documents/{path}",
        document__in=Document.objects.published(),
    )
    return HttpResponsePermanentRedirect(alias.document.file_url)


@require_GET
def review_photo(request, pk):
    return serve_private_file(get_object_or_404(Review.objects.published(), pk=pk).photo)


@require_GET
def video_cover(request, pk):
    return serve_private_file(get_object_or_404(Video.objects.published(), pk=pk).cover)
