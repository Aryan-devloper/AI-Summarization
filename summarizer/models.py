from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar_color = models.CharField(max_length=20, default='violet')
    bio = models.TextField(blank=True, max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s profile"

    def get_initials(self):
        fn = self.user.first_name
        ln = self.user.last_name
        if fn and ln:
            return f"{fn[0]}{ln[0]}".upper()
        return self.user.username[:2].upper()


SUMMARY_TYPES = [
    ('short', 'Short Summary'),
    ('medium', 'Medium Summary'),
    ('detailed', 'Detailed Summary'),
    ('bullets', 'Bullet Points'),
    ('keypoints', 'Key Points'),
]


class Summary(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='summaries')
    original_text = models.TextField()
    summary = models.TextField()
    summary_type = models.CharField(max_length=20, choices=SUMMARY_TYPES, default='short')
    title = models.CharField(max_length=200, blank=True)
    word_count_original = models.IntegerField(default=0)
    word_count_summary = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.summary_type} - {self.created_at.strftime('%Y-%m-%d')}"

    def get_preview(self):
        return self.summary[:150] + '...' if len(self.summary) > 150 else self.summary

    def compression_ratio(self):
        if self.word_count_original > 0:
            ratio = round((1 - self.word_count_summary / self.word_count_original) * 100)
            return max(0, min(100, ratio))
        return 0


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_otps')
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.email} - {self.otp}'

    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at
