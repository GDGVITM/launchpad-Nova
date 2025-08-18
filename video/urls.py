from django.urls import path
from .views import ManimView, VideoDownloadView

urlpatterns = [
    path("video/", ManimView.as_view(), name="manim"),
    path("video/download/<str:filename>/", VideoDownloadView.as_view(), name="video_download"),
]
