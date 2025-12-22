from django.core.management.base import BaseCommand
from apps.subscribe.models import SubscriptionPlan


class Command(BaseCommand):
    help = 'Create default subscription plan'

    def handle(self, *args, **options):
        plan, created = SubscriptionPlan.objects.get_or_create(
            name='Premium Monthly',
            defaults={
                'price': 10.00,
                'duration_days': 30,
                'stripe_price_id': 'price_premium_monthly',  # here ID from stripe
                'features': {
                    'pin_posts': True,
                    'priority_support': True,
                    'analytics': True
                },
                'is_active': True,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created subscription plan {plan.name}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Already created subscription plan {plan.name}')
            )
