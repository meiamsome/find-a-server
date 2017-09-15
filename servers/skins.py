import httplib
import StringIO

from PIL import Image

from django.core.cache import cache
from django.shortcuts import get_object_or_404, HttpResponse, Http404
from django.test.client import RequestFactory
from django.utils.cache import get_cache_key
from django.views.decorators.cache import cache_page


from servers.models import MinecraftAccount


@cache_page(7200)
def full(request, player_uuid):
    player = get_object_or_404(
        MinecraftAccount,
        UUID__iexact=int("".join(player_uuid.split("-")), 16)
    )
    if player.name is None:
        raise Http404
    try:
        conn = httplib.HTTPConnection("s3.amazonaws.com")
        conn.request("GET", "/MinecraftSkins/%s.png" % player.name)
        res = conn.getresponse()
        if res.status == 200:
            return HttpResponse(res.read(), content_type="image/png")
    except:
        pass
    with open('servers/default_skin.png', 'r') as file:
        return HttpResponse(file.read(), content_type="image/png")


@cache_page(7200)
def head(request, player_uuid, dimension=8):
    try:
        dim = int(dimension)
    except:
        raise Http404
    if dim > 1024:
        raise Http404
    dim2 = dim
    while dim2 > 8:
        dim3 = dim2 / 2
        if dim3 * 2 != dim2:
            raise Http404
        dim2 = dim3
    if dim2 != 8:
        raise Http404
    req = RequestFactory().get("/players/" + player_uuid + "/skin/full.png")
    ckey = get_cache_key(req)
    data = None
    if ckey:
        data = cache.get(ckey)
        if data is None:
            data = full(req, player_uuid)
            if data is None:
                raise Http404
            cache.set(ckey, data)
        data = data.content
    else:
        try:
            conn = httplib.HTTPConnection(request.META['SERVER_NAME'])
            conn.request("GET", req.path)
            res = conn.getresponse()
            if res.status != 200:
                raise Http404
            data = res.read()
        except:
            pass
    if data is None:
        data = full(req, player_uuid).content
    img = Image.open(StringIO.StringIO(data)).convert("RGBA")
    img_base = img.crop((8, 8, 16, 16))
    img_hair = img.crop((40, 8, 48, 16))
    pixel_color = img.getpixel((0, 0))
    pix_data = img_hair.load()
    for y in xrange(img_hair.size[1]):
        for x in xrange(img_hair.size[0]):
            if pix_data[x, y] == pixel_color:
                pix_data[x, y] = (0, 0, 0, 0)
    img_base.paste(img_hair, None, img_hair)
    resp = HttpResponse(content_type="image/png")
    img_base.resize((dim, dim)).save(resp, "PNG")
    return resp
