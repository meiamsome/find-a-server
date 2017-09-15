from django.contrib import admin

from servers.models import Server, UpTime, MinecraftAccount, PlayTime, \
    ExtraServerData


# Register your models here.
admin.site.register(Server)
admin.site.register(UpTime)
admin.site.register(MinecraftAccount)
admin.site.register(PlayTime)
admin.site.register(ExtraServerData)
