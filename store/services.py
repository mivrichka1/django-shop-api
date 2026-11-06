import logging
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import CartItem, Order, OrderItem, Product, User

logger = logging.getLogger("store.orders")
MAX_BALANCE = Decimal("9999999999.99")


def top_up(user_id, amount):
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        if user.balance + amount > MAX_BALANCE:
            raise ValidationError({"amount": "Превышен максимальный баланс."})
        user.balance += amount
        user.save(update_fields=["balance"])
        return user


def add_to_cart(user_id, product_id, quantity):
    with transaction.atomic():
        # Блокировка сериализует изменения корзины и оформление заказа.
        User.objects.select_for_update().get(pk=user_id)
        product = Product.objects.filter(pk=product_id, is_active=True).first()
        if not product:
            raise ValidationError(
                {"product": "Товар не найден или недоступен."}
            )
        item = CartItem.objects.filter(
            user_id=user_id, product=product
        ).first()
        if item:
            if item.quantity + quantity > 2147483647:
                raise ValidationError(
                    {"quantity": "Слишком большое количество."}
                )
            item.quantity += quantity
            item.save(update_fields=["quantity"])
        else:
            item = CartItem.objects.create(
                user_id=user_id, product=product, quantity=quantity
            )
        return item


def change_cart_item(user_id, item_id, quantity=None, delete=False):
    from django.shortcuts import get_object_or_404

    with transaction.atomic():
        User.objects.select_for_update().get(pk=user_id)
        item = get_object_or_404(
            CartItem.objects.select_related("product"),
            pk=item_id,
            user_id=user_id,
        )
        if delete:
            item.delete()
        else:
            item.quantity = quantity
            item.save(update_fields=["quantity"])
        return item


def place_order(user_id):
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        items = list(CartItem.objects.filter(user=user).order_by("product_id"))
        if not items:
            raise ValidationError({"cart": "Корзина пуста."})
        product_ids = [item.product_id for item in items]
        products = {
            p.pk: p
            for p in Product.objects.select_for_update()
            .filter(pk__in=product_ids)
            .order_by("pk")
        }
        total = Decimal("0.00")
        for item in items:
            product = products.get(item.product_id)
            if product is None or not product.is_active:
                raise ValidationError(
                    {"cart": f"Товар {item.product_id} недоступен."}
                )
            if product.stock < item.quantity:
                raise ValidationError(
                    {
                        "stock": f"Недостаточно товара «{product.name}» "
                        "на складе."
                    }
                )
            total += product.price * item.quantity
        if total > user.balance:
            raise ValidationError({"balance": "Недостаточно средств."})
        order = Order.objects.create(user=user, total=total)
        for item in items:
            product = products[item.product_id]
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                unit_price=product.price,
                quantity=item.quantity,
            )
            product.stock -= item.quantity
            product.save(update_fields=["stock"])
        user.balance -= total
        user.save(update_fields=["balance"])
        CartItem.objects.filter(pk__in=[item.pk for item in items]).delete()
        transaction.on_commit(
            lambda: logger.info(
                "Order %s created for user %s; total=%s",
                order.pk,
                user.pk,
                total,
            )
        )
        return order
