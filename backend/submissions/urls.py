from django.urls import path

from .views import SaySafeSubmissionView, UnsafeSubmissionView

urlpatterns = [
    path("saysafe/", SaySafeSubmissionView.as_view(), name="saysafe"),
    path("unsafe/", UnsafeSubmissionView.as_view(), name="unsafe"),
]
