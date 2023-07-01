from django.contrib import admin

from watcher.models import Stock, Price, Alert


admin.site.register(Stock)
admin.site.register(Price)
admin.site.register(Alert)
