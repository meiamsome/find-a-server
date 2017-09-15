import errno
from string import ascii_letters
import socket


from django import forms
from django.forms import ValidationError
from django.utils.safestring import mark_safe

from minecraft.client import fake_client
from servers.models import Server, MinecraftAccount


class SubmitServerForm(forms.Form):
    server_name = forms.CharField(max_length=30)
    address = forms.CharField(max_length=30 + 6)

    def clean_address(self):
        split_addr = self.cleaned_data['address'].split(':')
        if len(split_addr) == 1:
            address = split_addr[0]
            port = 25565
        else:
            address = split_addr[0]
            try:
                port = int(split_addr[1])
            except ValueError:
                raise ValidationError(
                    "The address specified is invalid (':' mis-placed?)")
            if not 0 < port <= 65535:
                raise ValidationError("That port number is invalid.")
        try:
            server = Server.objects.get(address__iexact=address, port=port)
        except Server.DoesNotExist:
            pass
        else:
            raise ValidationError(mark_safe(
                "A server at that address is already tracked <a href=\""
                + server.get_absolute_url()
                + "\">here</a>"
            ))
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            try:
                test_sock.bind((address, 65535))
            except socket.error as err:
                test_sock.close()
                if err.errno != errno.EADDRNOTAVAIL:
                    raise
            else:
                test_sock.close()
                raise Exception()
        except Exception:
            raise ValidationError("The address provided is invalid.")
        # TODO IPv6
        # TODO Check IPs
        # ip = socket.gethostbyname(address).split(",")
        # servers = Server.objects.filter(ip=ip)
        # if not servers:
        try:
            fake_client.query((address, port), 2)
        except:
            raise ValidationError(
                "Could not query the server specified. "
                "Please check the address"
            )
        else:
            return address, port


class VoteForm(forms.Form):
    account_name = forms.CharField(
        max_length=16)

    def __init__(self, request):
        forms.Form.__init__(self, request.POST if request.POST else None)
        self.mode = False
        if request.user.is_authenticated():
            players = [(p.id, p.name) for p in MinecraftAccount.objects.filter(
                owner=request.user).order_by("name")]
            if players:
                self.fields.update({
                    'account_name': forms.ChoiceField(
                        choices=[
                            ('IMPORT_FROM_OTHER', 'Other (Please Specify)')
                        ] + players
                    ),
                    'other': forms.CharField(
                        max_length=16,
                        required=False
                    ),
                })
                self.mode = True

    def clean_account_name(self):
        if self.mode:
            if self.cleaned_data['account_name'] == "IMPORT_FROM_OTHER":
                try:
                    return self.cleaned_data['other']
                except KeyError:
                    return "IMPORT_FROM_OTHER"
            else:
                self.cleaned_data['account'] = int(
                    self.cleaned_data['account_name'])
                return None
        return self.cleaned_data['account_name']

    def clean_other(self):
        if self.cleaned_data['account_name'] == "IMPORT_FROM_OTHER":
            self.cleaned_data['account_name'] = self.cleaned_data['other']
        return self.cleaned_data['other']


class PlayerVerifyForm(forms.Form):
    token = forms.CharField(max_length=100)


VALID_USERNAME_CHARS = set(ascii_letters) | {'_'}


class PlayerHistoryForm(forms.Form):
    username = forms.CharField(max_length=16)
    add_if_not_exist = forms.CharField(
        initial="",
        widget=forms.widgets.HiddenInput(),
        required=False
    )

    def clean_username(self):
        for char in self.cleaned_data['username']:
            if char not in VALID_USERNAME_CHARS:
                raise ValidationError(
                    "Username has invalid characters. "
                    "Only A-Z 0-9 and _ are allowed."
                )
        return self.cleaned_data['username']
