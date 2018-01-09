# 1. 每个一段时间爬取所有人的信息
#   对于已经保存了的信息要不要更新？
#   用API还是爬网页？ API方便但是有次数限制，用多个API token。 用网页可以没有限制，但是解析麻烦。
# 2. 每小时选择一个当天生日的人发出祝福
#    祝福写什么？
# 3. 允许手动加入？
#    以私信的形式加入

from collections import deque

from fanfou_sdk.van import Fan, User, Config

Fan.setup(cfg=Config())

entry_point = 'wangxing'
seen_users = {entry_point}
users_todo = deque()
users_todo.append(entry_point)

f = open('users.txt', 'w', encoding='utf8')

while True:
    try:
        curr = users_todo.popleft()
    except IndexError:
        break
    f.write(curr + '\n')

    user = User(id=curr, fill=False)

    friends = set(user.friends_id)

    not_seen = friends.difference(seen_users)
    users_todo.extend(not_seen)
    seen_users.update(friends)

f.flush()
f.close()

with open('seen_users.txt', 'w', encoding='utf8') as f:
    f.writelines(seen_users)
