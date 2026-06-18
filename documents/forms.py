from pathlib import Path
import filetype

from django import forms
from .models import Document

MAX_UPLOAD_SIZE_MB = 20
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

TEXT_EXTENSIONS = {
    ".csv", ".py", ".js", ".ts", ".java", ".cs", ".cpp", ".go", ".rb",
    ".php", ".swift", ".kt", ".html", ".htm", ".css",
    ".json", ".xml", ".yaml", ".yml", ".md", ".txt", ".rst",
}


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["original_name", "file"]

        widgets = {
            "original_name": forms.TextInput(attrs={
                "class": (
                    "block w-full rounded-md "
                    "border border-gray-300 "
                    "bg-white "
                    "px-3 py-2 "
                    "text-gray-900 "
                    "shadow-sm "
                    "focus:border-accent focus:ring-accent focus:ring-1 "
                    "sm:text-sm"
                ),
                "placeholder": "e.g. Company policies 2024"
            }),
            "file": forms.ClearableFileInput(attrs={
                "class": (
                    "block w-full text-sm text-gray-700 "
                    "file:mr-4 "
                    "file:rounded-md "
                    "file:border-0 "
                    "file:bg-gray-100 "
                    "file:px-4 "
                    "file:py-2 "
                    "file:text-sm "
                    "file:font-medium "
                    "file:text-gray-700 "
                    "hover:file:bg-gray-200"
                ),
                "accept": ".csv,.py,.js,.ts,.java,.cs,.cpp,.go,.rb,.php,.swift,.kt,.html,.htm,.css,.json,.xml,.yaml,.yml,.md,.txt,.rst",
            }),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return uploaded

        if uploaded.size > MAX_UPLOAD_SIZE:
            raise forms.ValidationError(
                f"El archivo supera el límite de {MAX_UPLOAD_SIZE_MB} MB."
            )

        head = uploaded.read(2048)
        uploaded.seek(0)
        kind = filetype.guess(head)
        ext = Path(uploaded.name or "").suffix.lower()

        if ext in TEXT_EXTENSIONS:
            if kind is not None:
                raise forms.ValidationError(
                    "El contenido no corresponde a un archivo de texto/código."
                )
            return uploaded

        raise forms.ValidationError("Tipo de archivo no soportado.")
