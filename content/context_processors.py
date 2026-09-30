from .models import SiteSettings
from .customer_content import customer_links


def site_content(request):
    return {"site_settings": SiteSettings.objects.first(), "customer_links": customer_links()}
