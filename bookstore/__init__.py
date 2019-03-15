import pymysql
pymysql.install_as_MySQLdb()

from .celeryapp import app as celery_app

__all__ = ['celery_app']
