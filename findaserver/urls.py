from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import render

admin.autodiscover()

urlpatterns = [
    # Examples:
    # url(r'^$', 'findaserver.views.home', name='home'),
    # url(r'^blog/', include('blog.urls')),
    url(r'^robots.txt$', lambda r: HttpResponse(
        "User-agent: *\nDisallow:",
        content_type="text/plain")),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^users/', include('users.urls')),
    url(r'^management/', include('management.urls', namespace="management")),
    # url(r'^facebook/', include('django_facebook.urls')),
    url(r'^privacy/$', lambda r: render(r, 'privacy.html')),
    url(r'^', include('servers.urls', namespace='servers')),
]
