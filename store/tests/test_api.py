from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from store.models import CartItem, Order, Product, User


class ShopAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='buyer', password='StrongPassword42!', balance=Decimal('100.00'))
        self.other = User.objects.create_user(username='other', password='StrongPassword42!')
        self.admin = User.objects.create_user(username='staff', password='StrongPassword42!', is_staff=True)
        self.product = Product.objects.create(name='Книга', price='12.50', stock=5)

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)

    def test_registration_jwt_and_profile(self):
        response = self.client.post('/api/auth/register/', {'username': 'new', 'password': 'SafePassphrase123!', 'email': 'new@example.com'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('password', response.data)
        response = self.client.post('/api/auth/token/', {'username': 'new', 'password': 'SafePassphrase123!'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
        self.assertEqual(self.client.get('/api/profile/').data['balance'], '0.00')
        self.assertEqual(self.client.post('/api/auth/token/refresh/', {'refresh': response.data['refresh']}, format='json').status_code, 200)

    def test_registration_validates_password(self):
        response = self.client.post('/api/auth/register/', {'username': 'new', 'password': '123'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_product_permissions_and_validation(self):
        self.assertEqual(self.client.get('/api/products/').status_code, 200)
        self.assertEqual(self.client.post('/api/products/', {'name': 'A', 'price': '1.00', 'stock': 1}, format='json').status_code, 401)
        self.auth()
        self.assertEqual(self.client.post('/api/products/', {'name': 'A', 'price': '1.00', 'stock': 1}, format='json').status_code, 403)
        self.auth(self.admin)
        self.assertEqual(self.client.post('/api/products/', {'name': 'A', 'price': '-1', 'stock': 1}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/products/', {'name': 'A', 'price': '1.00', 'stock': 1}, format='json').status_code, 201)
        self.assertEqual(self.client.patch(f'/api/products/{self.product.pk}/', {'stock': 4}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(f'/api/products/{self.product.pk}/').status_code, 204)

    def test_topup_validation(self):
        self.auth()
        self.assertEqual(self.client.post('/api/profile/top-up/', {'amount': '-1'}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/profile/top-up/', {'amount': '2.555'}, format='json').status_code, 400)
        response = self.client.post('/api/profile/top-up/', {'amount': '15.25'}, format='json')
        self.assertEqual(response.data['balance'], '115.25')

    def test_cart_crud_and_ownership(self):
        self.auth()
        self.assertEqual(self.client.post('/api/cart/', {'product_id': self.product.pk, 'quantity': 0}, format='json').status_code, 400)
        response = self.client.post('/api/cart/', {'product_id': self.product.pk, 'quantity': 2}, format='json')
        pk = response.data['id']
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.post('/api/cart/', {'product_id': self.product.pk, 'quantity': 1}, format='json').data['quantity'], 3)
        self.assertEqual(self.client.patch(f'/api/cart/{pk}/', {'quantity': 4}, format='json').data['quantity'], 4)
        self.auth(self.other)
        self.assertEqual(self.client.get('/api/cart/').data, [])
        self.assertEqual(self.client.delete(f'/api/cart/{pk}/').status_code, 404)
        self.auth()
        self.assertEqual(self.client.delete(f'/api/cart/{pk}/').status_code, 204)

    def test_checkout_success_and_snapshot(self):
        self.auth()
        CartItem.objects.create(user=self.user, product=self.product, quantity=2)
        with self.assertLogs('store.orders', level='INFO'):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.client.post('/api/orders/', {}, format='json')
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['total'], '25.00')
        self.user.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.user.balance, Decimal('75.00'))
        self.assertEqual(self.product.stock, 3)
        self.assertFalse(CartItem.objects.filter(user=self.user).exists())
        self.product.delete()
        order = self.client.get(f"/api/orders/{response.data['id']}/")
        self.assertEqual(order.data['items'][0]['product_name'], 'Книга')
        self.auth(self.other)
        self.assertEqual(self.client.get(f"/api/orders/{response.data['id']}/").status_code, 404)

    def test_failed_checkout_does_not_mutate(self):
        self.auth()
        self.assertEqual(self.client.post('/api/orders/').status_code, 400)
        item = CartItem.objects.create(user=self.user, product=self.product, quantity=6)
        self.assertEqual(self.client.post('/api/orders/').status_code, 400)
        item.quantity = 2
        item.save()
        self.user.balance = Decimal('1.00')
        self.user.save()
        self.assertEqual(self.client.post('/api/orders/').status_code, 400)
        self.product.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(self.user.balance, Decimal('1.00'))
        self.assertTrue(CartItem.objects.filter(pk=item.pk).exists())
        self.assertFalse(Order.objects.exists())

    def test_inactive_product_rejected_at_checkout(self):
        self.auth()
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        self.product.is_active = False
        self.product.save()
        self.assertEqual(self.client.post('/api/orders/').status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
