from django.shortcuts import redirect, reverse

# 登录装饰器,func为被包装方法名
def login_wrapper(func):

    def wrapper(request):
        # 判断是否登录
        if request.session.has_key('islogin'):
            #如果登录则执行原始的被包装方法func
            return func(request)
        else:
            # 如果没有登录则跳转到登录页面
            return redirect(reverse('user:register'))
    return wrapper