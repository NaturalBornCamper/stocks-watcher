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
from apps.quant.views.ranks import stock, historical, month_view
from apps.quant.views.score import score_or_count

urlpatterns = [
    # Cronjobs
    path("cron/compile_sa_score/", cron.compile_sa_score, name="cron.sa.compile_sa_score"),
    path("cron/compile_sa_score_decayed/", cron.compile_sa_score_decayed, name="cron.sa.compile_sa_score_decayed"),
    path("cron/compile_sa_score_momentum/", cron.compile_sa_score_momentum, name="cron.sa.compile_sa_score_momentum"),

    # Seeking Alpha Ratings
    path("sa", score_or_count, {"value_to_display": "score"}, name="quant.sa"),
    path("sa/score", score_or_count, {"value_to_display": "score"}, name="quant.sa.score"),
    path("sa/score_decayed", score_or_count, {"value_to_display": "score_decay"}, name="quant.sa.score_decay"),
    path("sa/score_momentum", score_or_count, {"value_to_display": "score_momentum"}, name="quant.sa.score_momentum"),
    path("sa/count", score_or_count, {"value_to_display": "count"}, name="quant.sa.count"),
    path("sa/month", month_view, name="quant.sa.month"),
    path("sa/month/<str:date_str>", month_view, name="quant.sa.month_date"),
    path("sa/historical/<str:type>", historical, name="quant.sa.historical"),
    path("sa/historical/<str:type>/<str:date>", historical, name="quant.sa.historical_date"),
    path("sa/stock/<str:symbol>", stock, name="quant.sa.stock"),
]
