from datetime import datetime

from django import forms
from django.contrib.auth import get_user_model
from django.utils.timezone import utc


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())
    repeat_password = forms.CharField(widget=forms.PasswordInput())

    def clean_repeat_password(self):
        if self.cleaned_data['password'] != \
                self.cleaned_data['repeat_password']:
            raise forms.ValidationError(
                "The two passwords you specified do not match."
            )
        return self.cleaned_data['password']

    def save(self, commit=True):
        user = forms.ModelForm.save(self, False)
        user.last_login = datetime.utcnow().replace(tzinfo=utc)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user

    class Meta:
        model = get_user_model()
        fields = ['username', 'email']
