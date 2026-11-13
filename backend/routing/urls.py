"""URL routes for the routing app."""

from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("geocode", views.geocode_search, name="geocode"),
    path("plan", views.plan, name="plan"),
    path("heatmap", views.heatmap, name="heatmap"),
]
