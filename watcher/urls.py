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
from django.contrib import admin
from django.urls import path

from watcher.views import cron, quant

urlpatterns = [
    path("admin/", admin.site.urls),

    # Cronjobs
    path("cron/fetch_prices/", cron.fetch_prices, name="cron.fetch_prices"),
    path("cron/send_alerts/", cron.send_alerts, name="cron.send_alerts"),
    path("cron/compile_quant/", cron.compile_quant, name="cron.compile_quant"),
    path("cron/compile_quant_decay/", cron.compile_quant_decay, name="cron.compile_quant_decay"),

    # Quant
    path("quant/", quant.score_or_count, {"value_to_display": "score"}, name="quant"),
    path("quant/score", quant.score_or_count, {"value_to_display": "score"}, name="quant.score"),
    path("quant/score_decay", quant.score_or_count, {"value_to_display": "score_decay"}, name="quant.score_decay"),
    path("quant/count", quant.score_or_count, {"value_to_display": "count"}, name="quant.count"),
    path("quant/historical/<type>/<date>", quant.historical, name="quant.stock"),
    path("quant/stock/<sa_stock>", quant.stock, name="quant.stock"),
]