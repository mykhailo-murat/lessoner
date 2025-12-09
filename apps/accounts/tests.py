from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from .serializers import UserRegistrationSerializer

User = get_user_model()


class UserModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='john_doe',
            email='john@example.com',
            password='securepassword123',
            first_name='John',
            last_name='Doe'
        )

    def test_user_str_returns_email(self):
        self.assertEqual(str(self.user), 'john@example.com')

    def test_user_full_name_property(self):
        self.assertEqual(self.user.full_name, 'John Doe')

    def test_email_must_be_unique(self):
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username='jane_doe',
                email='john@example.com',
                password='anotherpassword'
            )

    def test_can_create_user_with_required_fields(self):
        user = User.objects.create_user(
            username='new_user',
            email='new@example.com',
            password='pass1234'
        )
        self.assertTrue(isinstance(user, User))
        self.assertEqual(user.email, 'new@example.com')
        self.assertTrue(user.check_password('pass1234'))

    def test_created_at_and_updated_at_auto_fields(self):
        self.assertIsNotNone(self.user.created_at)
        self.assertIsNotNone(self.user.updated_at)


class UserRegistrationAPITest(APITestCase):
    def setUp(self):
        self.url = reverse('register')  # urls.py
        self.user_data = {
            'email': 'newuser@example.com',
            'username': 'newuser',
            'password': 'TestPass123!',
            'first_name': 'New',
            'last_name': 'User'
        }

    def test_successful_registration(self):
        response = self.client.post(self.url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.first().email, self.user_data['email'])

    def test_missing_required_field(self):
        data = self.user_data.copy()
        data.pop('email')
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_duplicate_email_registration(self):
        User.objects.create_user(
            email='newuser@example.com',
            username='existinguser',
            password='SomePass123'
        )
        response = self.client.post(self.url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)


class UserRegistrationSerializerTest(TestCase):

    def setUp(self):
        self.valid_data = {
            'email': 'test@example.com',
            'username': 'testuser',
            'password': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'first_name': 'Test',
            'last_name': 'User'
        }

    # ---- POSITIVE ----
    def test_valid_data_creates_user(self):
        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertEqual(user.email, self.valid_data['email'])
        self.assertEqual(user.username, self.valid_data['username'])
        self.assertTrue(user.check_password(self.valid_data['password']))
        self.assertFalse(hasattr(user, 'password2'))  # повинно бути видалено

    # ---- NEGATIVE ----
    def test_passwords_do_not_match(self):
        data = self.valid_data.copy()
        data['password2'] = 'Different123!'
        serializer = UserRegistrationSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)

    def test_duplicate_email_not_allowed(self):
        User.objects.create_user(
            email='test@example.com',
            username='existing',
            password='SomePass123'
        )

        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

    def test_missing_required_field(self):
        data = self.valid_data.copy()
        data.pop('email')

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

    def test_password_too_weak(self):
        data = self.valid_data.copy()
        data['password'] = data['password2'] = '123'

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)

    def test_invalid_email_format(self):
        data = self.valid_data.copy()
        data['email'] = 'not-an-email'

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)
