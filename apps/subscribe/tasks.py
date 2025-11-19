from celery import shared_task
from django.utils import timezone
from .models import Subscription, PinnedPost, SubscriptionHistory


@shared_task
def check_expired_subscriptions():
    now = timezone.now()
    expired_subscriptions = SubscriptionHistory.objects.filter(
        status='active',
        end_date__lt=now,
    )

    expired_count = 0
    pinned_posts_removed = 0

    for subscription in expired_subscriptions:
        subscription.delete()
        expired_count += 1

        try:
            pinned_post = subscription.user.pinned_posts
            pinned_post.delete()
            pinned_posts_removed += 1
        except PinnedPost.DoesNotExist:
            pass

        SubscriptionHistory.objects.create(
            subscription=subscription,
            action='expired',
            description='Subscription expired',
        )

    return {
        'expired_subscriptions': expired_count,
        'pinned_posts_removed': pinned_posts_removed,
    }

@shared_task
def send_subscription_expiry_reminder():
    from datetime import timedelta
    from django.core.mail import send_mail
    from django.conf import settings

    reminder_date = timezone.now() + timedelta(days=3)
    expired_soon_subscriptions = SubscriptionHistory.objects.filter(
        status='active',
        end_date__date=reminder_date,
        auto_renew=False
    )

    sent_count = 0
    for subscription in expired_soon_subscriptions:
        try:
            send_mail(
                subject='Your subscription expired soon',
                message=f'Dear {subscription.user.get_full_name() or subscription.user.username}, \n\n Your {subscription.plan.name} subscription expired soon at {reminder_date}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[subscription.user.email],
                fail_silently=True,
            )
            sent_count += 1
        except Exception as e:
            print(f'failed to send email to {subscription.user.email}: {e}')

    return {
        'reminder_sent': sent_count,
    }
