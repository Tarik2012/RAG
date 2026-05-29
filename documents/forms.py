from django import forms
from .models import Document


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
                "accept": ".pdf,.csv,.py,.js,.ts,.java,.cs,.cpp,.go,.rb,.php,.swift,.kt,.html,.htm,.css,.json,.xml,.yaml,.yml,.md,.txt,.rst",
            }),
        }
