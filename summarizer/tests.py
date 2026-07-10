from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from summarizer.models import PasswordResetOTP

class ForgotPasswordTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='testpassword123'
        )
        self.request_url = reverse('forgot_password')
        self.verify_url = reverse('forgot_password_verify')

    def test_otp_flow_success(self):
        # 1. Request OTP
        response = self.client.post(self.request_url, {'email': 'testuser@example.com'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.verify_url)

        # 2. Get the OTP from the database
        otp_record = PasswordResetOTP.objects.filter(user=self.user, is_used=False).first()
        self.assertIsNotNone(otp_record)
        self.assertTrue(otp_record.is_valid())

        # 3. Verify the OTP
        response = self.client.post(self.verify_url, {'otp': otp_record.otp})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('forgot_password_set_new_password'))

        # Check that OTP is now marked as used
        otp_record.refresh_from_db()
        self.assertTrue(otp_record.is_used)

