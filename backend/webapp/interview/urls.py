from django.urls import path
from interview.views import CreateInterviewView, GetInterviewView

urlpatterns = [
    path("create/", CreateInterviewView.as_view(), name="create_interview"),
    path("get/", GetInterviewView.as_view(), name="get_interview"),
]
