from rest_framework import serializers
from decimal import Decimal
from .models import Payment, PaymentAttempt, Refund, WebhookEvent


class PaymentSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    subscription_info = serializers.SerializerMethodField()
    is_successful = serializers.ReadOnlyField()
    is_pending = serializers.ReadOnlyField()
    can_be_refunded = serializers.ReadOnlyField()

    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'user_info', 'subscription', 'subscription_info',
            'amount', 'currency', 'status', 'payment_method', 'description', 'is_successful', 'is_pending', 'can_be_refunded', 'created_at',
            'updated_at', 'processed_at'
        ]
        read_only_fields = [
            'id', 'user', 'status', 'created_at', 'updated_at', 'processed_at'
        ]

    def get_user_info(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'email': obj.user.email,
        }

    def get_subscription_info(self, obj):
        if obj.subscription:
            return {
                'id': obj.subscription.id,
                'plan_name': obj.subscription.plan.name,
                'start_date': obj.subscription.start_date,
                'end_date': obj.subscription.end_date,
                'status': obj.subscription.status,
            }
        return None


class PaymentCreateSerializer(serializers.Serializer):
    subscription_plan_id = serializers.IntegerField()
    payment_method = serializers.CharField(
        choices=Payment.PAYMENT_METHOD_CHOICES,
        default='stripe'
    )
    success_url = serializers.URLField(required=False)
    cancel_url = serializers.URLField(required=False)

    def validate_subscription_plan_id(self, value):
        from apps.subscribe.models import SubscriptionPlan

        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError('Subscription plan does not exist')

        return value

    def validate(self, attrs):
        user = self.context['request'].user

        if hasattr(user, 'subscription') and user.subscription.is_active:
            raise serializers.ValidationError({
                'non_field_error': ['This field is required.']
            })

        pending_payments = Payment.objects.filter(
            user=user,
            status__in=['pending', 'processing']
        ).exists()
        if pending_payments:
            raise serializers.ValidationError({
                'non_field_error': ['User has pending payments.']
            })

        return attrs


class PaymentAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAttempt
        fields = [
            'id', 'stripe_charge_id', 'status', 'error_message', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class RefundSerializer(serializers.ModelSerializer):
    payment_info = serializers.SerializerMethodField()
    created_by_info = serializers.SerializerMethodField()
    is_partials = serializers.ReadOnlyField()

    class Meta:
        model = Refund
        fields = [
            'id', 'payment', 'payment_info', 'amount', 'reason', 'status', 'is_partials', 'created_by', 'created_at',
            'created_by_info', 'created_at', 'processed_at'
        ]
        read_only_fields = ['id', 'created_at', 'status', 'processed_at']

    def get_payment_info(self, obj):
        return {
            'id': obj.payment.id,
            'amount': obj.payment.amount,
            'currency': obj.payment.currency,
            'status': obj.payment.status,
            'user': obj.payment.user.username
        }

    def get_created_by_info(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'username': obj.created_by.username,
            }
        return None

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Refund amount must be greater than zero')
        return value

    # common validation for refunds
    def validate(self, attrs):
        payment_id = self.context.get('payment_id')
        if payment_id:
            try:
                payment = Payment.objects.get(id=payment_id)
            except Payment.DoesNotExist:
                raise serializers.ValidationError('Payment does not exist')

            if not payment.can_be_refunded:
                raise serializers.ValidationError('This payment is not refunded')

            total_refunded = payment.refunds.filter(
                status='succeeded'
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

            if attrs['amount'] > (payment.amount - total_refunded):
                raise serializers.ValidationError(
                    'Refund amount exceeds remaining payment amount'
                )

        return attrs


class RefundCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = ['amount', 'reason']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Refund amount must be greater than zero')
        return value


class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = [
            'id', 'provider', 'event_id', 'event_type', 'status', 'processed_at', 'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class StripeCheckoutSessionSerializer(serializers.Serializer):
    checkout_url = serializers.URLField(read_only=True)
    session_id = serializers.CharField(read_only=True)
    payment_id = serializers.IntegerField(read_only=True)


class PaymentStatusSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField()
    status = serializers.CharField()
    message = serializers.CharField()
    subscription_activated = serializers.BooleanField(default=False)
