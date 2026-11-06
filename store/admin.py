from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CartItem, Order, OrderItem, Product, User

admin.site.register(User, UserAdmin)
admin.site.register([Product, CartItem, Order, OrderItem])
