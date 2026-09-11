from reviews.models import Review

from .models import Document, Industry, SiteText, Video


def editorial_context():
    copy = dict(SiteText.objects.values_list("key", "value"))
    return {
        "site_content": copy,
        "contexts": Industry.objects.published().select_related("collection"),
        "compliance_documents": Document.objects.published().filter(is_declaration=True),
        "handbook": Document.objects.published().filter(source_key="handbook").first(),
        "homepage_reviews": Review.objects.published().filter(show_on_home=True)[:24],
        "homepage_videos": Video.objects.published().filter(show_on_home=True)[:12],
        "system_stages": [
            {"title": copy[f"stage_{index}_title"], "copy": copy.get(f"stage_{index}_copy", "")}
            for index in range(1, 5)
            if f"stage_{index}_title" in copy
        ],
    }
