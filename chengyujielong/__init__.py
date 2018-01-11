import atexit
import json
import logging
import random
import time
from collections import Counter
from datetime import date, timedelta

import requests
from requests.adapters import HTTPAdapter

import config

try:
    import config_private
except ImportError:
    pass
else:
    config.__dict__.update(config_private.__dict__)

from van import (
    Fan, Status, FanfouError, Timeline)

log = logging.getLogger(__name__)
sess = requests.session()
sess.mount('http://', HTTPAdapter(max_retries=5))

fan = Fan(config.FAN_APP_KEY,
          config.FAN_APP_SECRET,
          config.FAN_ACCESS_TOKEN)
state = {}
new_day = False
emojis = ('😀😃😄😁🤣😂😅😆☺️😊😇🙂😍😌😉😘😗😬🙄😵'
          '😛😋😝😜🐶🐱🐭🐹🐼🐻🦊🐰🐨🐯🦁🐮🐷🐽🐸🐵'
          '🍏🍎🍐🍊🍋🍌🍉🍇🍅🥝🥥🍍🍑🍒🍈🍓🍆🥑🥦🥒'
          '🌶🌽🥕🥔🍳🥚🧀🥨🥖🍞🥐🍠🥞🥓🥩🍗🍖🌭🍔🍟'
          '🍕🥪🥙🌮🥫🍤🍱🍣🍲🐥🐣🦅🦉🦇🐺🐗🐛🐝🦄🐴'
          '🦋🐌🐚🦑🐙🦕🦖🐟🐬🐳🐋🦈🐾🌚🌞🌝🐿🐩🐈☃️'
          )


def new_token():
    url = fan.authorization_url()
    print(url)
    pin = input('Pin: ').strip()
    token = fan.oauth(pin)
    print(token)


def restore_state():
    global state
    with open('state.json') as f:
        log.info('Restoring state from state.json')
        state = json.load(f)


def save_state():
    with open('state.json', 'w') as f:
        log.info('Dumping state to state.json')
        json.dump(state, f, indent=2)


def today_statistics():
    """记录统计信息"""
    global new_day
    today = date.today().isoformat()
    stat = state['stat']
    today_stat = stat.get(today)
    if not today_stat:
        # 标记新的一天开始
        new_day = True
        stat[today] = Counter()
    elif isinstance(today_stat, dict):
        stat[today] = Counter(stat[today])
    return stat[today]


def inc_mentions(user_id):
    today_statistics().update({user_id: 1})


def conclude_yesterday():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    stat = Counter(state['stat'][yesterday])
    user_cnt = len(stat.keys())
    most_frequent_user = stat.most_common(1)[0]
    mention_cnt = sum(stat.values())

    conclusion = '''\
各位饭友晚上好，新的一天到咯~
在昨天里，本机器人收到了来自 {user} 位饭友、总计 {mention} 次的互动消息，其中饭友 @{frequent[0]} 与我互动了 {frequent[1]} 次，名列前茅！
谢谢大家的热情，新的一天一起加油哦~
'''.format(user=user_cnt, mention=mention_cnt, frequent=most_frequent_user)

    return conclusion


def api(q, user):
    """
    http://docs.ruyi.ai/344886
    """
    url = 'http://api.ruyi.ai/v1/message'
    params = {
        'q': q.strip(),
        'app_key': config.RUYI_API_KEY,
        'user_id': user.id
    }
    try:
        r = sess.get(url, params=params)
    except requests.RequestException as e:
        log.exception('Request api error')
    else:
        try:
            data = r.json()
            if data['code'] == 200 or data['code'] == 0:
                response = data['result']['intents'][0]['outputs'][0]['property']['text'].strip()
                log.info('Got response from api: %s', response)
                return response
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.exception('Parse response error')
            return None


def reply(status: Status):
    text = status.repost_comment
    if text is None:
        text = status.process_text(status.text, pure=True)
    response = api(text, status.user)
    log.info('Question: %s', text)
    log.info('Anwser: %s', response)
    if response is not None:
        try:
            status.reply(response + random.choice(emojis))
        except FanfouError as e:
            log.exception('Reply error, sleep 1 second')
            time.sleep(1)


def get_message(since_id=None):
    mentions = Timeline(fan, None, 'statuses/mentions', max_id=since_id)
    idle = 1
    while True:
        try:
            statuses = mentions.fetch_newer()
        except FanfouError as e:
            log.exception('Fetch new mentions error')
            time.sleep(3)
            continue

        log.info('Got %s new mentions', len(statuses))
        if not statuses:
            idle = min(idle * 1.5, 30)
        elif len(statuses) <= 3:
            idle = 3
        else:
            idle = 1

        for st in statuses:  # type:Status
            if st.user.id == fan.me.id:
                log.info('Ignore one mention by self')
                continue
            inc_mentions(st.user.id)
            yield st

        state['mention_since_id'] = mentions._max_id
        save_state()
        log.info('Falling sleep for %s seconds', idle)
        time.sleep(idle)


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', level=logging.INFO)
    atexit.register(save_state)

    restore_state()
    since_id = state['mention_since_id']
    for message in get_message(since_id):
        reply(message)
        if new_day:
            conclustion = conclude_yesterday()
            log.info('Yesterday conclustion: %s', conclustion)
            fan.update_status(conclustion)
            new_day = False
