from django.conf.urls import url
from django.contrib.auth.views import login, logout, password_reset, \
    password_reset_done, password_reset_confirm, password_reset_complete
from django.contrib import admin

from users.views import register, self_view, user_detail

admin.autodiscover()

urlpatterns = (
    url(r'^logout/$', logout, name="logout"),
    url(r'^login/$', login, name="login"),
    url(r'^register/$', register, name="register"),
    url(r'^reset/$', password_reset, name="password_reset"),
    url(r'^reset/sent/$', password_reset_done, name="password_reset_done"),
    url(r'^reset/(?P<uidb64>[A-Za-z0-9]*)/(?P<token>.*)/$',
        password_reset_confirm, name="password_reset_confirm"),
    url(r'^reset/complete/$', password_reset_complete,
        name="password_reset_complete"),
    url(r'^me/$', self_view, name='self_view'),
    url(r'^info/(?P<username>[A-Za-z0-9_@+.-]*)/$',
        user_detail, name='user_info'),
)
