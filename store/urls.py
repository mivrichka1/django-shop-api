from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    CartItemView,
    CartView,
    OrderDetailView,
    OrderView,
    ProductViewSet,
    ProfileView,
    RegistrationView,
    TopUpView,
)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
urlpatterns = [
    path("auth/register/", RegistrationView.as_view(), name="register"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/top-up/", TopUpView.as_view(), name="top-up"),
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/<int:pk>/", CartItemView.as_view(), name="cart-item"),
    path("orders/", OrderView.as_view(), name="orders"),
    path("orders/<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("", include(router.urls)),
]
