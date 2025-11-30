from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Payment, WebhookEvent


@shared_task
def cleanup_old_payments():
    cutoff_date = timezone.now() - timedelta(days=90)

    old_payments = Payment.objects.filter(
        created_at__lt=cutoff_date,
        status__in=['failed', 'cancelled']
    )

    deleted_payments, _ = old_payments.delete()
    return {'deleted_payments': deleted_payments}


@shared_task
def cleanup_old_webhook_events():
    cutoff_date = timezone.now() - timedelta(days=30)

    old_events = WebhookEvent.objects.filter(
        created_at__lt=cutoff_date,
        status__in=['processed', 'ignored']
    )
    deleted_events, _ = old_events.delete()
    return {'deleted_events': deleted_events}


@shared_task
def retry_failed_webhook_events():
    from .services import WebhookService

    retry_cutoff = timezone.now() - timedelta(hours=1)

    failed_events = WebhookEvent.objects.filter(
        status='failed',
        created_at__gte=retry_cutoff,
    )[:50]

    processed_count = 0

    for event in failed_events:
        success = WebhookService.process_stripe_webhook(event.data)
        if success:
            event.mark_as_processed()
            processed_count += 1

    return {'processed_events': processed_count}
