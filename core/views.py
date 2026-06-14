from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render
from documents.models import Document, DocumentChunk


def home(request):
    context = {}
    if request.user.is_authenticated:
        docs = Document.objects.filter(owner=request.user)
        context = {
            "total_documents": docs.count(),
            "processed_documents": docs.filter(status="processed").count(),
            "total_chunks": DocumentChunk.objects.filter(document__owner=request.user).count(),
        }
    return render(request, "core/home.html", context)


def signup(request):
    if request.user.is_authenticated:
        return redirect("documents:list")
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("documents:list")
    else:
        form = UserCreationForm()
    return render(request, "registration/signup.html", {"form": form})
