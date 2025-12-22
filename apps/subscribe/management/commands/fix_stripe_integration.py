import stripe
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.subscribe.models import SubscriptionPlan

stripe.api_key = settings.STRIPE_SECRET_KEY


class Command(BaseCommand):
    help = 'Fix Stripe integration - creating real product and prices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreate even if stripe_price_id exists'
        )

    def handle(self, *args, **options):
        force = options['force']

        try:
            stripe.Balance.retrieve()
            self.stdout.write(self.style.SUCCESS('Successfully fetched'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            return

        plans = SubscriptionPlan.objects.filter(is_active=True)

        for plan in plans:
            self.stdout.write(f'Processing {plan.name}')

            if plan.stripe_price_id and not force and plan.stripe_price_id.startswith('price_1'):
                self.stdout.write(f'Skipping {plan.name}')
                continue
            try:
                product = stripe.Product.create(
                    name=plan.name,
                    description=f'Subscription plan = {plan.name}',
                    metadata={
                        'plan_id': plan.id,
                        'django_model': 'SubscriptionPlan',
                        'created_by': 'django_management_command'
                    }
                )
                self.stdout.write(f'Product Created: {product.id}')

                price = stripe.Price.create(
                    product=product.id,
                    unit_amount=int(plan.price * 100),
                    currency='USD',
                    recurring={'interval': 'month'},
                    metadata={
                        'plan_id': plan.id,
                        'django_model': 'SubscriptionPlan',
                    }
                )
                self.stdout.write(f'Price Created: {price.id}')

                # upd plan
                old_id = plan.stripe_price_id
                plan.stripe_price_id = price.id
                plan.save()

                self.stdout.write(self.style.SUCCESS(f'Successfully updated {old_id} -> {price.id}'))

            except stripe.error.StripeError as e:
                self.stdout.write(
                    self.style.ERROR(f'Stripe Error: Plan - {plan.name},   {e}')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error: {e}')
                )
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {plans.count()} products')
        )
