from django.conf.urls import url, include

from servers import views, server_views, skins, player_views

server_patterns = [
    url(r'^submit/', views.submit_server,
        name="submit"),
    url(r'^(?P<server_id>\d+)/', include([
        url(r'^$', server_views.server_detail,
            name='server_detail'),
        url(
            r'^verify/$', server_views.server_verify, name="server_verify"),
        url(r'^verify/(?P<type>\d)/$',
            server_views.server_verify_check),
        url(r'^players/$',
            views.player_list_with_server),
        url(
            r'^players/(?P<player_uuid>[0-9A-F]{8}'
            '(-[0-9A-F]{4}){3}-[0-9A-F]{12})/$',
            views.player_detail),
    ])),
]

player_patterns = [
    url(r'^$', views.player_list, name="players"),
    url(r'^list/$', player_views.player_list, name="player_list"),
    url(r'^by-username/$', player_views.find_player, name="player_search"),
    url(
        r'^by-username/(?P<username>[0-9A-Za-z_]{0,16})/$',
        player_views.find_player,
        name="find_player"
    ),
    url(r'^name-changes/$', player_views.recent_name_changes),
    url(
        r'^(?P<player_uuid>[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12})/',
        include([
            url(r'^$', views.player_detail, name="player_detail"),
            url(r'^verify/$', views.player_verify, name="player_verify"),
            url(r'^verify_token/$', views.player_verify_token),
            url(
                r'^skin/',
                include([
                    url(r'^full.png$', skins.full, name="full_skin"),
                    url(r'^head.png$', skins.head),
                    url(r'^head-(?P<dimension>\d*).png$', skins.head),
                ])
            ),
        ])
    ),

]

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^scripts/ads.js$', views.ad),
    url(r'^servers/', include(server_patterns)),
    url(r'^players/', include(player_patterns)),
    url(r'^stats/$', views.statistics, name="stats"),
]
