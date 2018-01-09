import json
import logging
import random
import time
import atexit

import requests
from requests.adapters import HTTPAdapter

try:
    import config_private as config
except ImportError:
    import config

from van import (
    Fan, Status, FanfouError, Timeline)

log = logging.getLogger(__name__)
sess = requests.session()
sess.mount('http://', HTTPAdapter(max_retries=5))

fan = Fan(config.FAN_APP_KEY,
          config.FAN_APP_SECRET,
          config.FAN_ACCESS_TOKEN)
state = {}
emojis = '😀😃😄😁🤣😂😅😆☺️😊😇🙂😍😌😉😘😗' \
         '😛😋😝😜🐶🐱🐭🐹🐼🐻🦊🐰🐨🐯🦁🐮🐷🐽🐸🐵'


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
                response = data['result']['intents'][0]['outputs'][0]['property']['text']
                log.info('Got response from api: %s', response)
                return response
        except (json.JSONDecodeError, KeyError) as e:
            log.exception('Parse response error')
            return None


def reply(status: Status):
    text = status.process_text(status.text, pure=True).strip()
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
        statuses = mentions.fetch_newer()
        log.info('Got %s new mentions', len(statuses))
        if not statuses:
            idle *= 1.5
        else:
            idle = 1
        for st in statuses:  # type:Status
            if st.user.id == fan.me.id:
                log.info('Ignore one mention by self')
                continue
            yield st

        state['mention_since_id'] = mentions._max_id
        save_state()
        if idle >= 60:
            idle = 60
        time.sleep(idle)


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', level=logging.INFO)
    atexit.register(save_state)

    restore_state()
    since_id = state['mention_since_id']
    for message in get_message(since_id):
        reply(message)
