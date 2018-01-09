import logging
import os
import threading
from queue import Queue

import cymysql
from van import User

log = logging.getLogger(__name__)

conn = None  # type: cymysql.Connection


def create_db():
    create_db = '''
    CREATE DATABASE fanfou;
    USE fanfou;
    CREATE TABLE user(
    id VARCHAR(30) PRIMARY KEY ,
    unique_id VARCHAR(20),
    name VARCHAR(50),
    screen_name VARCHAR(50),
    location VARCHAR(20),
    gender ENUM('男','女',''),
    birthday VARCHAR(20),
    description VARCHAR(300),
    url VARCHAR(100),
    protected BOOL,
    followers_count INT UNSIGNED,
    friends_count INT UNSIGNED,
    favourites_count INT UNSIGNED,
    statuses_count INT UNSIGNED,
    photo_count INT UNSIGNED,
    created_at VARCHAR(30),
    utc_offset INT,
    profile_image_url VARCHAR(100),
    profile_image_url_large VARCHAR(100)
    )
    CHARSET=utf8,
    ENGINE='InnoDB'
    '''
    with connect() as c:
        c.execute(create_db)
        c.commit()


def connect():
    global conn
    if conn is None:
        user = os.environ['USERNAME']
        password = os.environ['PASSWORD']
        conn = cymysql.connect(host='localhost', db='fanfou', user=user, passwd=password)
    return conn


def store(user: User):
    sql = "INSERT INTO user(id,unique_id,name) VALUES ('0.id','0.unique_id','0.name')".format(user)
    with conn as c:
        c.execute(sql)


def crawl(q: Queue):
    while True:
        user_id = q.get()
        try:
            user = User(id=user_id, fill=True)
            store(user)
        except Exception as e:
            log.exception('crawl failed')
        q.task_done()


if __name__ == '__main__':
    users = open('users.txt', encoding='utf8')
    concurrent = 10
    q = Queue(2 * concurrent)
    for i in range(concurrent):
        t = threading.Thread(target=crawl, args=(q,))
        t.daemon = True
        t.start()
    for i, user_id in enumerate(users):
        q.put(user_id)
    q.join()
