import logging
import time
from datetime import date
from random import choice
from urllib.parse import urlparse, urlunparse

import arrow
import requests
from arrow.parser import TzinfoParser
from van import Fan, Config

TZ = TzinfoParser.parse('+08:00')
START_DATE = arrow.get(date(2017, 5, 23), tzinfo=TZ)
NOW = arrow.now(TZ)


def get(year, month):
    url = 'http://www.google.com/doodles/json/{year}/{month}?hl=zh_CN'.format(year=year, month=month)
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
        return resp.json()
    else:
        return None


def get_latest():
    curr_month = get(NOW.year, NOW.month)
    latest = curr_month[0]
    date_array = latest['run_date_array']
    date = arrow.get(*date_array)
    if date.date() < NOW.date():
        return None
    else:
        return latest


def get_today_in_history():
    for gap in range(1, 10):
        history_month = get(NOW.year - gap, NOW.month) or []
        for history_day in history_month:
            day = arrow.get(*history_day['run_date_array'])
            if day.day == NOW.day:
                return history_day
            if day.day < NOW.day:
                break
        time.sleep(1)
    return None


def get_random():
    while True:
        year = choice(range(1990, NOW.year))
        month = choice(range(1, 13))
        doodles = get(year, month)
        if doodles:
            return choice(doodles)


def get_doodle():
    latest = get_latest()
    if latest:
        return latest
    else:
        history_day = get_today_in_history()
        if history_day:
            return history_day
        else:
            return get_random()


def gen_status(doodle):
    link = 'https://www.google.com/doodles/' + doodle['name']
    text = '【{0[0]}年{0[1]}月{0[2]}日】 {1} ➔{2} #GoogleDoodle#'.format(
            doodle['run_date_array'],
            doodle['title'],
            link)
    photo_url = urlunparse(urlparse(doodle['hires_url'], scheme='http'))
    return text, photo_url


class MyConfig(Config):
    consumer_key = 'b55d535f350dcc59c3f10e9cf43c1749'
    consumer_secret = 'e9d72893b188b6340ad35f15b6aa7837'


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s %(filename)s:%(lineno)d %(levelname)s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    fan = Fan.get(cfg=MyConfig())

    if NOW.hour <= 12:
        doodle = get_doodle()
    else:
        doodle = get_random()
    status, photo = gen_status(doodle)

    success, _ = fan.update_status(status, photo=photo)
    while not success:
        doodle = get_random()
        status, photo = gen_status(doodle)
        success, _ = fan.update_status(status, photo=photo)
        time.sleep(1)


if __name__ == '__main__':
    main()
