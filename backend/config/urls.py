"""Root URL configuration.

Every backend route lives under /api/. Anything else is the React app:
WhiteNoise serves the built files, and whatever it does not recognise falls
through to the catch-all below, which returns index.html.
"""

from django.urls import include, path, re_path

from routing.views import spa_index

urlpatterns = [
    path("api/", include("routing.urls")),
    # Everything that is not an API route belongs to the single-page app.
    re_path(r"^(?!api/).*$", spa_index, name="spa"),
]
