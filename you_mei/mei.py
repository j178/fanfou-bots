# 获取 public status
# 1. 有图
# 2. owner 性别为女
# 3. 如果有生日的话，先判断一下年龄

# 提交图片到微软 face API
# 1. face_number > 0
# 2. gender = female
# 3. age < 40

# 提交图片到小冰颜值 API
# 1. score > 6

import json
import sys
import logging
import threading
import time
from collections import namedtuple
from datetime import datetime
from pathlib import Path
from queue import Queue
from base64 import b64encode

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
    Fan, Status, FanfouError
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
session = requests.Session()
session.mount('http://', HTTPAdapter(max_retries=3))
session.mount('https://', HTTPAdapter(max_retries=3))

fan = Fan(config.FAN_APP_KEY,
          config.FAN_APP_SECRET,
          config.FAN_ACCESS_TOKEN)
FaceAttributes = namedtuple('FaceAttributes', 'age gender')

DEBUG = False
DEBUG_PHOTO_FOLDER = Path('./debug/photos').absolute()
DEBUG_STAT_FOLDER = Path('./debug/stat').absolute()

MAX_AGE = 30
MIN_SCORE = 7


def now():
    return datetime.now().strftime('%Y-%m-%d_%H_%M_%S')


def face_detection(status: Status, *, face_url=None, content=None):
    api_url = 'https://eastasia.api.cognitive.microsoft.com/face/v1.0/detect'
    api_key = config.MS_FACE_API_KEY
    params = {
        'returnFaceId': 'false',
        'returnFaceLandmarks': 'false',
        'returnFaceAttributes': 'age,gender'
    }
    headers = {
        'Ocp-Apim-Subscription-Key': api_key
    }
    if face_url:
        data = {'json': {'url': face_url}}
        headers['content-type'] = 'application/json'
    elif content:
        data = {'data': content}
        headers['content-type'] = 'application/octet-stream'
    else:
        raise ValueError

    try:
        resp = session.post(api_url, params=params, headers=headers, **data)
        resp.raise_for_status()
    except Exception:
        return None
    else:
        data = resp.json()
        if 'error' in data:
            return None
        else:
            if DEBUG:
                f = DEBUG_STAT_FOLDER / (now() + '' + status.id + '.json')
                if f.is_file():
                    d = json.loads(f.read_text())
                else:
                    d = {}
                d['face_api'] = data
                f.write_text(json.dumps(d, sort_keys=True, indent=2))
            results = []
            for one in data:
                attr = one['faceAttributes']
                results.append(FaceAttributes(age=attr['age'], gender=attr['gender']))
            return results


def computer_vision(status: Status, *, face_url=None, content=None):
    api_url = 'https://eastasia.api.cognitive.microsoft.com/vision/v2.0/analyze'
    api_key = config.MS_VISION_API_KEY
    params = {
        'language': 'en',
        'visualFeatures': 'Categories,Tags,Faces',
    }
    headers = {
        'Ocp-Apim-Subscription-Key': api_key
    }
    if face_url:
        data = {'json': {'url': face_url}}
        headers['content-type'] = 'application/json'
    elif content:
        data = {'data': content}
        headers['content-type'] = 'application/octet-stream'
    else:
        raise ValueError

    try:
        resp = session.post(api_url, params=params, headers=headers, **data)
        resp.raise_for_status()
    except Exception:
        return None
    else:
        data = resp.json()
        if 'code' in data and 'message' in data:
            return None
        else:
            if DEBUG:
                f = DEBUG_STAT_FOLDER / (now() + '' + status.id + '.json')
                if f.is_file():
                    d = json.loads(f.read_text())
                else:
                    d = {}
                d['vision_api'] = data
                f.write_text(json.dumps(d, sort_keys=True, indent=2))

            return data


def face_score(status: Status, image_url):
    headers = {
        'Referer': 'https://kan.msxiaobing.com/ImageGame/Portal',
        'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36')
    }
    api_url = 'https://kan.msxiaobing.com/Api/ImageAnalyze/Process?service=beauty'
    portal_url = 'https://kan.msxiaobing.com/ImageGame/Portal'
    post_data = {'Content[imageUrl]': image_url}

    session = requests.Session()
    session.get(portal_url)
    try:
        resp = session.post(api_url, data=post_data, headers=headers)
    except Exception:
        return None

    data = resp.json()
    if isinstance(data, str) and 'quota exceeded' in data:
        log.info('XiaoBing api quota exceeded')
        return None
    try:
        if DEBUG:
            f = DEBUG_STAT_FOLDER / (now() + '' + status.id + '.json')
            if f.is_file():
                d = json.loads(f.read_text())
            else:
                d = {}
            d['xiaobing'] = data
            f.write_text(json.dumps(d, sort_keys=True, indent=2))

        faces = data['content']['metadata']['face_number']
        if faces == 1:
            score = data['content']['metadata']['score']
            return score
    except Exception:
        return None


def upload_photo_to_microsoft(image_content):
    upload_url = 'https://kan.msxiaobing.com/Api/Image/UploadBase64'
    if not isinstance(image_content, bytes):
        return None

    image = b64encode(image_content)
    try:
        data = session.post(upload_url, data=image).json()
        image_url = data['Host'] + data['Url']
    except Exception:
        return None
    return image_url


def download_photo(img_url):
    try:
        resp = session.get(img_url)
        resp.raise_for_status()
    except Exception:
        return None
    return resp.content


def filter_by_status(status: Status):
    bots = {'weather_image'}
    # 原创
    if 'repost_status' in status.dict:
        return False
    # 有图
    if 'photo' not in status.dict:
        return False
    # 过滤经常发图的机器人
    if status.user.id in bots:
        return False

    # 年轻妹子
    if status.user.gender == '男':
        return False
    elif status.user.gender == '女':
        birthday = status.user.birthday
        if birthday:
            year = datetime.now().year
            try:
                if int(birthday[:4]) < year - MAX_AGE:
                    return False
            except Exception:
                pass
    return True


def filter_by_image(status, data):
    target_categories = {'people_', 'people_portrait', 'people_young'}
    target_tags = {'woman', 'lady', 'beautiful', 'girl', 'portrait', 'face'}

    metadata = data['metadata']
    categories = data['categories']
    faces = data['faces']
    tags = data['tags']

    # 是否为人像
    categories = {c['name']: c['score'] for c in categories}
    tags = {t['name']: t['confidence'] for t in tags}
    if not target_categories.intersection(categories.keys()):
        return False
    if 'person' not in tags:
        return False
    if not target_tags.intersection(tags.keys()):
        return False

    if not faces or len(faces) > 1:
        return False
    face = faces[0]
    if face['age'] > MAX_AGE or face['gender'].lower() != 'female':
        return False

    # 如果脸的面积太小
    r = face['faceRectangle']
    face_area = r['width'] * r['height']
    image_area = metadata['width'] * metadata['height']
    if (face_area / image_area) < 0.08:
        return False

    return True


def produce(queue):
    timeline = fan.public_timeline
    idle = origin = 5
    while True:
        try:
            statuses = timeline.fetch_newer()
        except FanfouError as e:
            # Fanfou 有可能宕机了
            log.exception('Fetch new statuses error')
            time.sleep(3)
            continue

        log.info('Got %s new statuses', len(statuses))
        if not statuses:
            idle = min(idle * 1.5, 60)
        elif len(statuses) <= 3:
            idle = 10
        else:
            idle = origin

        for status in statuses:
            queue.put(status)

        time.sleep(idle)

    queue.put(None)


def consume(queue):
    while True:
        status: Status = queue.get()
        if status is None:
            log.info('[consumer] Exiting')
            break

        if not filter_by_status(status):
            log.info('Filtered one by status info')
            continue

        fanfou_url = status.photo.origin_url
        image_content = download_photo(fanfou_url)
        if DEBUG and image_content:
            f = DEBUG_PHOTO_FOLDER / (now() + '_' + status.id + '.' + fanfou_url.rsplit('.')[-1])
            f.write_bytes(image_content)

        image_url = upload_photo_to_microsoft(image_content)
        if not image_url:
            continue

        data = computer_vision(status, face_url=image_url)
        if not data or not filter_by_image(status, data):
            log.info('Filtered one by image info')
            continue

        score = face_score(status, image_url)
        if score is not None and score < MIN_SCORE:
            log.info('Filtered one by face score')
            continue

        try:
            status.repost('', repost_style_left='转', repost_style_right='')
            log.info('Forward one')
        except Exception:
            log.error('Report failed')

        time.sleep(1)


def main():
    if DEBUG:
        DEBUG_PHOTO_FOLDER.mkdir(parents=True, exist_ok=True)
        DEBUG_STAT_FOLDER.mkdir(parents=True, exist_ok=True)

    q = Queue(maxsize=100)
    producer = threading.Thread(target=produce, args=(q,), daemon=True)
    consumer = threading.Thread(target=consume, args=(q,), daemon=True)

    producer.start()
    consumer.start()
    producer.join()
    consumer.join()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        DEBUG = sys.argv[1].startswith('d')

    main()
