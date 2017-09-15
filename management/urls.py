from django.conf.urls import include, url
from views import manage_server


urlpatterns = (
    url(r'^server/(?P<server_id>\d+)/$', manage_server, name="server"),
)
