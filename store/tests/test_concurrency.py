from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.exceptions import ValidationError

from store.models import CartItem, Order, Product, User
from store.services import place_order


@skipUnlessDBFeature('has_select_for_update')
class CheckoutConcurrencyTests(TransactionTestCase):
    def test_two_buyers_cannot_purchase_the_last_item(self):
        product = Product.objects.create(name='Последний товар', price='10.00', stock=1)
        users = [User.objects.create_user(username=f'buyer{i}', balance=Decimal('20.00')) for i in range(2)]
        for user in users:
            CartItem.objects.create(user=user, product=product, quantity=1)
        barrier = Barrier(2)

        def checkout(user_id):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    place_order(user_id)
                    return 'ok'
                except ValidationError:
                    return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(checkout, [user.pk for user in users]))
        self.assertCountEqual(results, ['ok', 'rejected'])
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(sum(User.objects.values_list('balance', flat=True)), Decimal('30.00'))
