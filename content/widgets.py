from django import forms


class PrivateFileInput(forms.ClearableFileInput):
    """Retain replace/clear controls without resolving a private storage URL."""

    template_name = "content/widgets/private_file.html"

    def is_initial(self, value):
        return bool(value)
