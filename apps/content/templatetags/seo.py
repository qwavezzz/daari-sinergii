from django import template
from django.utils.html import json_script
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def structured_data_script(data):
    if not data:
        return ""
    # json_script escapes <, > and &: CMS text cannot close the script element.
    html = json_script(data, element_id="page-structured-data")
    return mark_safe(html.replace('type="application/json"', 'type="application/ld+json"', 1))
