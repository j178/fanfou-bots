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
    Fan, Status, FanfouError, Timeline
)

log = logging.getLogger(__name__)
sess = requests.Session()
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
    with open('state.json', encoding='utf-8') as f:
        log.info('Restoring state from state.json')
        state = json.load(f)


def save_state():
    with open('state.json', 'wt', encoding='utf-8') as f:
        log.info('Dumping state to state.json')
        json.dump(state, f, indent=2, ensure_ascii=False, sort_keys=True)


def today_statistics():
    """记录统计信息"""
    global new_day

    today = date.today().isoformat()
    stat = state['stat']
    try:
        today_stat = stat[today]
    except KeyError:
        # 标记新的一天开始
        new_day = True
        today_stat = {}

    stat[today] = Counter(today_stat)
    return stat[today]


def conclude_yesterday():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    try:
        stat = Counter(state['stat'][yesterday])
    except KeyError as e:
        return None

    user_cnt = len(stat.keys())
    mention_cnt = sum(stat.values())

    conclusion = []
    conclusion.append('各位饭友好，新的一天到咯~')
    if mention_cnt > 0:
        conclusion.append(('在昨天里，本机器人收到了来自 {user} '
                           '位饭友、总计 {mention} 次的互动消息。')
                          .format(user=user_cnt, mention=mention_cnt))
        most_frequent = stat.most_common(1)[0]
        conclusion.append('其中饭友 @{user[0]} 与我互动了 {user[1]} 次，名列前茅！'
                          .format(user=most_frequent))
    else:
        conclusion.append('昨天没有小伙伴与我互动，本机器人读书看报，度过了愉快的一天。')

    conclusion.append('谢谢大家的热情，新的一天一起加油哦~')

    return '\n'.join(conclusion)


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
    if status.repost_comment is not None:
        text = status.repost_comment
    else:
        text = status.text
    text = status.process_text(text, pure=True)
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
    global new_day

    mentions = Timeline(fan, None, 'statuses/mentions', max_id=since_id)
    idle = 1
    while True:
        try:
            statuses = mentions.fetch_newer()
        except FanfouError as e:
            # Fanfou 有可能宕机了
            log.exception('Fetch new mentions error')
            time.sleep(3)

        log.info('Got %s new mentions', len(statuses))
        if not statuses:
            idle = min(idle * 1.5, 60)
        elif len(statuses) <= 3:
            idle = 3
        else:
            idle = 1

        stat = today_statistics()
        if new_day:
            conclusion = conclude_yesterday()
            if conclusion:
                log.info('Yesterday conclusion: %s', conclusion)
                try:
                    fan.update_status(conclusion + random.choice(emojis))
                except FanfouError as e:
                    log.exception('Update conclusion failed')
                else:
                    new_day = False

        for st in statuses:  # type:Status
            if st.user.id == fan.me.id:
                log.info('Ignore one mention by self')
                continue
            stat.update([st.user.screen_name])
            yield st

        state['mention_since_id'] = mentions._max_id
        save_state()
        log.info('Falling sleep for %s seconds', idle)
        time.sleep(idle)


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', level=logging.INFO)
    atexit.register(save_state)

    while True:
        try:
            restore_state()
            since_id = state['mention_since_id']
            for message in get_message(since_id):
                reply(message)
        except Exception as e:
            log.exception('Something bad happened')
            break
