from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.urls import reverse


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        verbose_name = 'category'
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class PostManager(models.Manager):
    def published(self):
        return self.filter(status='published')

    def pinned_posts(self):
        return self.filter(
            pin_info__isnull=False,
            pin_info__user__subscription_status='active',
            pin_info__user__subscrition_end_date__gt=models.functions.Now(),
            status='published'
        ).select_related('pin_info', 'pin_info__user', 'pin_info__user__subscription').order_by('pin_info__pinned_at')

    def regular_posts(self):
        return self.filter(pin_info__isnull=True, status='published')

    def with_subscription_info(self):
        return self.select_related('author', 'author__subscription', 'category').prefetch_related('pin_info')


class Post(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
    ]

    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    content = models.TextField()
    image = models.ImageField(upload_to='images/', blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, related_name='posts')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posts')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    views_count = models.PositiveIntegerField(default=0)

    objects = PostManager()

    class Meta:
        db_table = 'posts'
        verbose_name = 'post'
        verbose_name_plural = 'posts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['category', '-created_at']),
            models.Index(fields=['author', '-created_at'])
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('main:detail', kwargs={'slug': self.slug})

    def comments_count(self):
        return self.comments.filter(is_active=True).count()

    @property
    def is_pinned(self):
        return hasattr(self.pin_info, 'pin_info') and self.pin_info.pinned_at is not None

    @property
    def can_be_pinned_by_user(self):
        if self.status != 'published':
            return False
        return True

    def can_be_pinned_by(self, user):
        if not user or not user.is_authenticated:
            return False

        if self.author != user:
            return False

        if self.status != 'published':
            return False

        if not hasattr(user, 'subscription') or not user.subscription.is_active:
            return False

        return True

    def increment_views_count(self):
        self.views_count += 1
        self.save(update_fields=['views_count'])

    def get_pinned_info(self):
        if self.is_pinned:
            return {
                'is_pinned': True,
                'pinned_at': self.pin_info.pinned_at,
                'pinned_by': {
                    'id': self.pin_info.user.id,
                    'username': self.pin_info.user.username,
                    'has_active_subscription': self.pin_info.user.subscription.is_active
                }
            }
        return {
            'is_pinned': False,
        }
