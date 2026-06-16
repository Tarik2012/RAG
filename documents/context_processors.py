from documents.models import Project


def sidebar_projects(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "sidebar_projects": Project.objects.filter(user=request.user).order_by("-updated_at")[:10]
    }
