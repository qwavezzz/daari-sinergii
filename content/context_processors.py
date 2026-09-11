from .models import SiteSettings


def site_content(request):
    return {"site_settings": SiteSettings.objects.first()}
