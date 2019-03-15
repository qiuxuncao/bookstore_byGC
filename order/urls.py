# coding:utf-8
from django.conf.urls import url
from order import views

urlpatterns = [
    url(r'^place/$', views.order_place, name='place'), # 订单提交页面
    url(r'^commit/$', views.order_commit, name='commit'), # 生成订单
    url(r'^pay/$', views.order_pay, name='pay'),
]
