from datetime import timedelta

from django.db import models
from django.core.urlresolvers import reverse
from django.conf import settings


class Server(models.Model):
    name = models.CharField(max_length=30)
    address = models.CharField(max_length=30)
    port = models.IntegerField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True)
    verification = models.OneToOneField(
        'ServerVerificationKey',
        blank=True,
        null=True,
        related_name="server2"
    )
    score = models.IntegerField(db_index=True, default=0)
    rank = models.IntegerField(db_index=True, blank=True, null=True)
    online_mode = models.NullBooleanField(db_index=True, blank=True, null=True)
    protocol = models.IntegerField()

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('servers:server_detail', args=[self.pk])


class ServerVerificationKey(models.Model):
    DNS_METHOD = 0
    MOTD_METHOD = 1
    server = models.ForeignKey(Server)
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    verification_mode = models.PositiveSmallIntegerField(choices=(
        (DNS_METHOD, 'DNS'), (MOTD_METHOD, 'MOTD'),
    ))
    verification_code = models.CharField(max_length=24)

    class Meta:
        unique_together = (
            ('server', 'user', 'verification_mode'),
            ('server', 'verification_code', ),
        )


class UpTime(models.Model):
    server = models.ForeignKey(Server)
    checkTime = models.DateTimeField(db_index=True)
    status = models.BooleanField(db_index=True)
    playerCount = models.IntegerField()
    delta = models.IntegerField()

    def __unicode__(self):
        return "Uptime of " + self.server.name

    class Meta:
        index_together = (
            ('server', 'status', ),
            ('server', 'checkTime', 'status'),
        )


class UpTimeAggregate(models.Model):
    server = models.ForeignKey(Server)
    checkTime = models.DateTimeField(db_index=True)
    playerCount = models.IntegerField()
    up_time = models.IntegerField()
    total_time = models.IntegerField()

    class Meta:
        unique_together = (('server', 'checkTime', ), )


class QueryError(models.Model):
    server = models.ForeignKey(Server)
    time = models.DateTimeField(db_index=True)
    safe = models.BooleanField(db_index=True)
    description = models.TextField()


class MinecraftAccount(models.Model):
    # Minecraft account UUIDs are stored in 128bits, which needs just less
    # than 39 digits to represent.
    UUID = models.DecimalField(max_digits=39, decimal_places=0, unique=True)
    name = models.CharField(max_length=16, unique=True, blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True)
    playson = models.ManyToManyField(Server, through='PlayTime')
    verification_code = models.CharField(max_length=8)

    def __unicode__(self):
        if self.name is not None:
            return self.name
        return "%x" % self.UUID

    def get_absolute_url(self):
        uuid = ('%X' % self.UUID).zfill(32)
        uuid = uuid[:8] + "-" + uuid[8:12] + "-" + uuid[12:16] + "-"
        uuid += uuid[16:20] + "-" + uuid[20:]
        return reverse('servers:player_detail', args=[uuid])


class Names(models.Model):
    minecraft_account = models.ForeignKey(MinecraftAccount)
    name = models.CharField(max_length=16, db_index=True)
    start = models.DateTimeField()
    end = models.DateTimeField(null=True)


class PlayTime(models.Model):
    minecraft_account = models.ForeignKey(MinecraftAccount)
    server = models.ForeignKey(Server)
    end_time = models.DateTimeField(db_index=True)
    duration = models.IntegerField()

    @property
    def start_time(self):
        return self.end_time - timedelta(self.duration)

    def __unicode__(self):
        return unicode(self.minecraft_account) + u" played on " + \
               unicode(self.server) + u" for " + \
               unicode(self.duration) + u" seconds."


class FacebookSync(models.Model):
    playtime = models.OneToOneField(PlayTime)
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    fb_id = models.BigIntegerField()


class ExtraServerData(models.Model):
    VOTIFIER = 1
    server = models.ForeignKey(Server)
    type = models.IntegerField(choices=(
        (VOTIFIER, 'Votifier'),
    ), blank=False)
    content = models.TextField()

    class Meta:
        unique_together = (('server', 'type', ), )


class Vote(models.Model):
    minecraft_account = models.ForeignKey(MinecraftAccount, null=True)
    minecraft_name = models.CharField(max_length=16)
    ip = models.GenericIPAddressField(unpack_ipv4=True, db_index=True)
    server = models.ForeignKey(Server)
    time = models.DateTimeField(db_index=True)
    submitted = models.NullBooleanField(db_index=True, null=True, blank=True)
