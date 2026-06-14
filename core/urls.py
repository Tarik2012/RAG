from django.urls import path
from .views import home, signup

app_name = "core"

urlpatterns = [
    path("", home, name="home"),
    path("signup/", signup, name="signup"),
]
