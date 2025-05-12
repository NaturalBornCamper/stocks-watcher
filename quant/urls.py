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

from quant.views import cron
from quant.views.score import stock, score_or_count, historical

urlpatterns = [
    # Cronjobs
    path("cron/compile_quant/", cron.compile_quant, name="cron.compile_quant"),
    path("cron/compile_quant_decay/", cron.compile_quant_decay, name="cron.compile_quant_decay"),

    # Quant
    path("", score_or_count, {"value_to_display": "score"}, name="quant"),
    path("score", score_or_count, {"value_to_display": "score"}, name="quant.score"),
    path("score_decay", score_or_count, {"value_to_display": "score_decay"}, name="quant.score_decay"),
    path("count", score_or_count, {"value_to_display": "count"}, name="quant.count"),
    path("historical/<str:type>", historical, name="quant.historical"),
    path("historical/<str:type>/<str:date>", historical, name="quant.historical_date"),
    path("stock/<str:sa_stock>", stock, name="quant.stock"),
]
