"""
URL configuration for main project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path

from apps.quant.views import cron
from apps.quant.views.score import stock, score_or_count, historical

urlpatterns = [
    # Cronjobs
    path("cron/compile_sa_score/", cron.compile_sa_score, name="cron.sa.compile_sa_score"),
    path("cron/compile_sa_score_decayed/", cron.compile_sa_score_decayed, name="cron.sa.compile_sa_score_decayed"),
    path("cron/compile_sa_delta_score/", cron.compile_sa_delta_score, name="cron.sa.compile_sa_delta_score"),

    # Seeking Alpha Ratings
    path("sa", score_or_count, {"value_to_display": "score"}, name="quant.sa"),
    path("sa/score", score_or_count, {"value_to_display": "score"}, name="quant.sa.score"),
    path("sa/score_decayed", score_or_count, {"value_to_display": "score_decay"}, name="quant.sa.score_decay"),
    path("sa/count", score_or_count, {"value_to_display": "count"}, name="quant.sa.count"),
    path("sa/historical/<str:type>", historical, name="quant.sa.historical"),
    path("sa/historical/<str:type>/<str:date>", historical, name="quant.sa.historical_date"),
    path("sa/stock/<str:sa_stock>", stock, name="quant.sa.stock"),
]
