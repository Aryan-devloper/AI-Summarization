from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.contrib.auth.models import User
from .models import UserProfile, SUMMARY_TYPES


class RegisterForm(UserCreationForm):
    usable_password = None
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=50, required=False)
    last_name = forms.CharField(max_length=50, required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        if commit:
            user.save()
            UserProfile.objects.get_or_create(user=user)
        return user


class ProfileUpdateForm(forms.ModelForm):
    first_name = forms.CharField(max_length=50, required=False)
    last_name = forms.CharField(max_length=50, required=False)
    email = forms.EmailField(required=True)

    class Meta:
        model = UserProfile
        fields = ['bio', 'avatar_color']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email

    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.user:
            self.user.first_name = self.cleaned_data.get('first_name', '')
            self.user.last_name = self.cleaned_data.get('last_name', '')
            self.user.email = self.cleaned_data.get('email', '')
            if commit:
                self.user.save()
        if commit:
            profile.save()
        return profile


class SummarizeForm(forms.Form):
    text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10}),
        min_length=50,
        max_length=50000,
    )
    summary_type = forms.ChoiceField(choices=SUMMARY_TYPES)


class ForgotPasswordRequestForm(forms.Form):
    email = forms.EmailField()


class ForgotPasswordOTPForm(forms.Form):
    otp = forms.CharField(max_length=15, min_length=6)

    def clean_otp(self):
        otp = self.cleaned_data.get('otp', '').strip()
        # Extract only digits (removes spaces, dashes, newlines, etc.)
        digits = ''.join(c for c in otp if c.isdigit())
        if len(digits) != 6:
            raise forms.ValidationError('Please enter a valid 6-digit verification code.')
        return digits



class SetNewPasswordForm(forms.Form):
    new_password1 = forms.CharField(widget=forms.PasswordInput)
    new_password2 = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('new_password1')
        password2 = cleaned_data.get('new_password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('The two password fields did not match.')
        return cleaned_data
