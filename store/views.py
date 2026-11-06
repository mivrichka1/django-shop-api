from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CartItem, Order, Product
from .serializers import (AddCartItemSerializer, CartItemSerializer, ChangeCartItemSerializer,
                          OrderSerializer, ProductSerializer, ProfileSerializer,
                          RegistrationSerializer, TopUpSerializer)
from .services import add_to_cart, change_cart_item, place_order, top_up


class RegistrationView(generics.CreateAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.AllowAny]


class ProfileView(generics.RetrieveAPIView):
    serializer_class = ProfileSerializer
    def get_object(self):
        return self.request.user


class TopUpView(APIView):
    @extend_schema(request=TopUpSerializer, responses={200: ProfileSerializer})
    def post(self, request):
        serializer = TopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = top_up(request.user.pk, serializer.validated_data['amount'])
        return Response(ProfileSerializer(user).data)


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    def get_queryset(self):
        qs = Product.objects.all()
        return qs if self.request.user.is_staff else qs.filter(is_active=True)
    def get_permissions(self):
        return [permissions.AllowAny()] if self.action in ('list', 'retrieve') else [permissions.IsAdminUser()]


class CartView(APIView):
    @extend_schema(responses=CartItemSerializer(many=True))
    def get(self, request):
        items = CartItem.objects.filter(user=request.user).select_related('product')
        return Response(CartItemSerializer(items, many=True).data)

    @extend_schema(request=AddCartItemSerializer, responses={201: CartItemSerializer})
    def post(self, request):
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = add_to_cart(request.user.pk, **serializer.validated_data)
        return Response(CartItemSerializer(item).data, status=status.HTTP_201_CREATED)


class CartItemView(APIView):
    @extend_schema(request=ChangeCartItemSerializer, responses=CartItemSerializer)
    def patch(self, request, pk):
        serializer = ChangeCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = change_cart_item(request.user.pk, pk, quantity=serializer.validated_data['quantity'])
        return Response(CartItemSerializer(item).data)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        change_cart_item(request.user.pk, pk, delete=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrderView(generics.ListAPIView):
    serializer_class = OrderSerializer
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')

    @extend_schema(request=None, responses={201: OrderSerializer})
    def post(self, request):
        order = place_order(request.user.pk)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')
