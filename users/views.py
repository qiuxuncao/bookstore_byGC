# coding:utf-8
from django.shortcuts import render, redirect, reverse
from django.http import JsonResponse
from django.contrib.auth.backends import ModelBackend
from users.models import Passport, Address
from order.models import OrderInfo, OrderBooks
import re
from django.shortcuts import render, redirect, reverse

from utils.decorator import login_wrapper
from utils.decorators import login_required
from django_redis import get_redis_connection
import redis
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from users.tasks import send_active_email
from django.conf import settings
from books.models import Books


# Create your views here.
def register(request):
    '''显示用户注册页面'''
    return render(request, 'users/register.html')


# users/views.py
def register_handle(request):
    '''进行用户注册处理'''
    # 接收数据
    username = request.POST.get('user_name')
    password = request.POST.get('pwd')
    email = request.POST.get('email')

    # 进行数据校验
    if not all([username, password, email]):
        # 有数据为空
        return render(request, 'users/register.html', {'errmsg': '所有参数不能为空!'})

    # 判断邮箱是否合法
    if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
        # 邮箱不合法
        return render(request, 'users/register.html', {'errmsg': '邮箱不合法!'})

    # 进行业务处理:注册，向账户系统中添加账户
    # Passport.objects.create(username=username, password=password, email=email)
    try:
        passport = Passport.objects.add_one_passport(username=username, password=password, email=email)
    except Exception as e:
        print("e: ", e) # 把异常打印出来
        return render(request, 'users/register.html', {'errmsg': '用户名已存在！'})

    serializer = Serializer(settings.SECRET_KEY, 3600)
    token = serializer.dumps({'confirm':passport.id}) # 返回bytes
    token = token.decode()

    #send_mail('尚硅谷书城用户激活', '', settings.EMAIL_FROM, [email], html_message='<a href="http://127.0.0.1:8000/user/active/%s/">http://127.0.0.1:8000/user/active/</a>' % token)
    send_active_email.delay(token, username, email)

    # 注册完，还是返回注册页。
    return redirect(reverse('books:index'))

def login(request):
    '''显示登录页面'''
    if request.COOKIES.get("username"):
        username = request.COOKIES.get("username")
        checked = 'checked'
    else:
        username = ''
        checked = ''
    context = {
        'username': username,
        'checked': checked,
    }

    return render(request, 'users/login.html', context)

def login_check(request):
    '''进行用户登录校验'''
    # 1.获取数据
    username = request.POST.get('username')
    password = request.POST.get('password')
    remember = request.POST.get('remember')
    verifycode = request.POST.get('verifycode')

    # 2.数据校验
    if not all([username, password, remember, verifycode]):
        # 有数据为空
        return JsonResponse({'res': 2, 'errmsg': 'data cannot be null'})

    if verifycode.upper() != request.session['verifycode']:
        return JsonResponse({'res': 2})

    # 3.进行处理:根据用户名和密码查找账户信息
    passport = Passport.objects.get_one_passport(username=username, password=password)

    if passport:
        next_url = reverse('books:index')
        jres = JsonResponse({'res': 1, 'next_url': next_url})

        # 判断是否需要记住用户名
        if remember == 'true':
            # 记住用户名
            jres.set_cookie('username', username, max_age=7*24*3600)
        else:
            # 不要记住用户名
            jres.delete_cookie('username')

        # 记住用户的登录状态
        request.session['islogin'] = True
        request.session['username'] = username
        request.session['passport_id'] = passport.id
        cache_clean()
        return jres
    else:
        # 用户名或密码错误
        return JsonResponse({'res': 0, 'errmsg': 'username or password cannot be wrong.'})

def logout(request):
    '''用户退出登录'''
    # 清空用户的session信息
    request.session.flush()
    cache_clean()
    # 跳转到首页
    return redirect(reverse('books:index'))

def cache_clean():
    r = redis.StrictRedis(host='localhost', port=6379, db=2)
    for key in r.keys():
        if 'bookstore-index' in key.decode('utf8'):
            print('key: ', key)
            r.delete(key) 

class CustomBackend(ModelBackend):
    def authenticate(self, username=None, password=None, **kwargs):
        try:
            user = Passport.objects.get_one_passport(username, password)
            return user
        except Exception as e:
            print("e: ", e)
            return None

@login_required
def user(request):
    '''用户中心-信息页'''
    passport_id = request.session.get('passport_id')
    # 获取用户的基本信息
    addr = Address.objects.get_default_address(passport_id=passport_id)

    conn = get_redis_connection('default')
    key = 'history_%d' % passport_id
    # 取出用户最近浏览的5个商品的id
    history_li = conn.lrange(key, 0, 4)
    # history_li = [21,20,11]
    # print(history_li)
    # 查询数据库,获取用户最近浏览的商品信息
    # books_li = Books.objects.filter(id__in=history_li)
    books_li = []
    for id in history_li:
        books = Books.objects.get_books_by_id(books_id=id)
        books_li.append(books)

    context = {
        'addr': addr,
        'page': 'user',
        'books_li': books_li
    }

    return render(request, 'users/user_center_info.html', context)

# @login_required
@login_wrapper
def address(request):
    '''用户中心-地址页'''
    # 获取登录用户的id
    passport_id = request.session.get('passport_id')

    if request.method == 'GET':
        # 显示地址页面
        # 查询用户的默认地址
        addr = Address.objects.get_default_address(passport_id=passport_id)
        return render(request, 'users/user_center_site.html', {'addr': addr, 'page': 'address'})
    else:
        # 添加收货地址
        # 1.接收数据
        recipient_name = request.POST.get('username')
        recipient_addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        recipient_phone = request.POST.get('phone')

        # 2.进行校验
        if not all([recipient_name, recipient_addr, zip_code, recipient_phone]):
            return render(request, 'users/user_center_site.html', {'errmsg': '参数不能为空!'})

        # 3.添加收货地址
        Address.objects.add_one_address(passport_id=passport_id,
                                        recipient_name=recipient_name,
                                        recipient_addr=recipient_addr,
                                        zip_code=zip_code,
                                        recipient_phone=recipient_phone)

        # 4.返回应答
        return redirect(reverse('user:address'))

from django.core.paginator import Paginator

@login_required
def order(request, page):
    '''用户中心-订单页'''
    # 查询用户的订单信息
    passport_id = request.session.get('passport_id')

    # 获取订单信息
    order_li = OrderInfo.objects.filter(passport_id=passport_id)

    # 遍历获取订单的商品信息
    # order->OrderInfo实例对象
    for order in order_li:
        # 根据订单id查询订单商品信息
        order_id = order.order_id
        order_books_li = OrderBooks.objects.filter(order_id=order_id)

        # 计算商品的小计
        # order_books ->OrderGoods实例对象
        for order_books in order_books_li:
            count = order_books.count
            price = order_books.price
            amount = count * price
            # 保存订单中每一个商品的小计
            order_books.amount = amount

        # 给order对象动态增加一个属性order_books_li,保存订单中商品的信息
        order.order_books_li = order_books_li
    
    paginator = Paginator(order_li, 3)      # 每页显示3个订单
    
    num_pages = paginator.num_pages
    
    if not page:        # 首次进入时默认进入第一页
        page = 1
    if page == '' or int(page) > num_pages:
        page = 1
    else:
        page = int(page)
        
    order_li = paginator.page(page)
    
    if num_pages < 5:
        pages = range(1, num_pages + 1)
    elif page <= 3:
        pages = range(1, 6)
    elif num_pages - page <= 2:
        pages = range(num_pages - 4, num_pages + 1)
    else:
        pages = range(page - 2, page + 3)

    context = {
        'order_li': order_li,
        'pages': pages,
    }

    return render(request, 'users/user_center_order.html', context)

def register_active(request, token):
    '''用户账户激活'''
    serializer = Serializer(settings.SECRET_KEY, 3600)
    try:
        info = serializer.loads(token)
        passport_id = info['confirm']
        # 进行用户激活
        passport = Passport.objects.get(id=passport_id)
        passport.is_active = True
        passport.save()
        # 跳转的登录页
        return redirect(reverse('user:login'))
    except SignatureExpired:
        # 链接过期
        return HttpResponse('激活链接已过期')

# users/views.py
from django.http import HttpResponse
from django.conf import settings
import os
def verifycode(request):
    #引入绘图模块
    from PIL import Image, ImageDraw, ImageFont
    #引入随机函数模块
    import random
    #定义变量，用于画面的背景色、宽、高
    bgcolor = (random.randrange(20, 100), random.randrange(
        20, 100), 255)
    width = 100
    height = 25
    #创建画面对象
    im = Image.new('RGB', (width, height), bgcolor)
    #创建画笔对象
    draw = ImageDraw.Draw(im)
    #调用画笔的point()函数绘制噪点
    for i in range(0, 100):
        xy = (random.randrange(0, width), random.randrange(0, height))
        fill = (random.randrange(0, 255), 255, random.randrange(0, 255))
        draw.point(xy, fill=fill)
    #定义验证码的备选值
    str1 = 'ABCD123EFGHIJK456LMNOPQRS789TUVWXYZ0'
    #随机选取4个值作为验证码
    rand_str = ''
    for i in range(0, 4):
        rand_str += str1[random.randrange(0, len(str1))]
    #构造字体对象
    font = ImageFont.truetype(os.path.join(settings.BASE_DIR, "Ubuntu-RI.ttf"), 15)
    #构造字体颜色
    fontcolor = (255, random.randrange(0, 255), random.randrange(0, 255))
    #绘制4个字
    draw.text((5, 2), rand_str[0], font=font, fill=fontcolor)
    draw.text((25, 2), rand_str[1], font=font, fill=fontcolor)
    draw.text((50, 2), rand_str[2], font=font, fill=fontcolor)
    draw.text((75, 2), rand_str[3], font=font, fill=fontcolor)
    #释放画笔
    del draw
    #存入session，用于做进一步验证
    request.session['verifycode'] = rand_str
    #内存文件操作
    import io
    buf = io.BytesIO()
    #将图片保存在内存中，文件类型为png
    im.save(buf, 'png')
    #将内存中的图片数据返回给客户端，MIME类型为图片png
    return HttpResponse(buf.getvalue(), 'image/png')
