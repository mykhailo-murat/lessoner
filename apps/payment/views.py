import stripe
import json

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Payment, PaymentAttempt, Refund, WebhookEvent
from .serializers import (
    PaymentSerializer,
    PaymentCreateSerializer,
    PaymentAttemptSerializer,
    RefundSerializer,
    RefundCreateSerializer,
    StripeCheckoutSessionSerializer,
    PaymentStatusSerializer
)

from .services import StripeService, PaymentService, WebhookService
from apps.subscribe.models import Subscription, SubscriptionPlan
from .. import payment


class PaymentListView(generics.ListAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).select_related('subscription', 'subscription__plan').order_by('-created_at')


class PaymentDetailView(generics.RetrieveAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).select_related('subscription', 'subscription__plan')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_checkout_session(request):
    serializer = PaymentCreateSerializer(data=request.data, context={'request': request})

    if serializer.is_valid():
        try:
            with transaction.atomic():
                plan_id = serializer.validated_data['subscription_plan_id']
                plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)

                payment, subscription = PaymentService.create_subscription_payment(request.user, plan)

                success_url = serializer.validated_data.get(
                    'success_url',
                    f'{settings.FRONTEND_URL}/payment/success?session_id={CHECKOUT_SESSEION_ID}'
                )
                cancel_url = serializer.validated_data.get('cancel_url', f'{settings.FRONTEND_URL}/payment/cancel')

                session_data = StripeService.create_checkout_session(
                    payment, success_url, cancel_url
                )

                if session_data:
                    response_serializer = StripeCheckoutSessionSerializer(session_data)
                    return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                else:
                    return Response({
                        'error': 'Failed to create checkout session',
                    }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_status(request, payment_id):
    try:
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)

        if payment.stripe_session_id and payment_status in ['pending', 'processing']:
            session_info = StripeService.retrieve_session(payment.stripe_session_id)

            if session_info:
                if session_info['status'] == 'complete':
                    PaymentService.process_successful_payment(payment)
                elif session_info['status'] == 'failed':
                    PaymentService.process_failed_payment(payment, 'session failed')

        response_data = {
            'payment_id': payment_id,
            'status': payment.status,
            'message': f'Payment is {payment.status}',
            'subscription_activated': False
        }

        if payment.is_successful and payment.subscription:
            response_data['subscription_activated'] = payment.subscription.is_active
            response_data['message'] = 'Payment is successful and subscription is active'

        serializer = PaymentStatusSerializer(response_data)
        return Response(serializer.data)

    except Payment.DoesNotExist:
        return Response({
            'error': 'Payment does not exist',
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_payment(request, payment_id):
    try:
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)

        if not payment.is_pending:
            return Response({
                'error': 'Payment is not pending',
            }, status=status.HTTP_400_BAD_REQUEST)
        payment.status = 'cancelled'
        payment.save()

        if payment.subscription:
            payment.subscription.cancel_subscription()

        return Response({
            'message': 'Payment has been cancelled',
        })

    except Payment.DoesNotExist:
        return Response({
            'error': 'Payment does not exist',
        }, status=status.HTTP_404_NOT_FOUND)


class RefundListView(generics.ListAPIView):
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Refund.objects.all().select_related('payment', 'payment__user', 'created_by').order_by('-created_at')


class RefundDetailView(generics.RetrieveAPIView):
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Refund.objects.all().select_related('payment', 'payment__user', 'created_by')


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def create_refund(request, payment_id):
    try:
        payment = get_object_or_404(Payment, id=payment_id)

        if not payment.can_be_refunded:
            return Response({
                'error': 'Payment is non refundable',
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = RefundCreateSerializer(data=request.data, context={'payment_id': payment_id})

        if serializer.is_valid():
            with transaction.atomic():
                refund = serializer.save(
                    payment=payment,
                    created_by=request.user,
                )

                success = StripeService.refund_payment(
                    payment,
                    refund.amount,
                    refund.reason
                )

                if success:
                    refund.process_refund()

                    if refund.amount == payment.amount and payment.subscription:
                        PaymentService.cancel_subscription(payment.subscription)

                    response_serializer = RefundSerializer(refund)
                    return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                else:
                    refund.status = 'failed'
                    refund.save()
                    return Response({
                        'error': 'Failed to create refund',
                    }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Payment.DoesNotExist:
        return Response({
            'error': 'Payment does not exist',
        }, status=status.HTTP_404_NOT_FOUND)

