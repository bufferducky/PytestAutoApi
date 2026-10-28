"""本次0001→0002迁移的只读API盘点；仅排除明确新增的展示字段。"""
import hashlib
import json
import sys
from inventory import collect, get


def compatible_get(path):
    value = get(path)
    if path.startswith('runs?'):
        for item in value['items']:
            item.pop('name', None)
            item.pop('run_number', None)
    elif path.startswith('runs/'):
        value.pop('name', None)
        value.pop('run_number', None)
    return value


if '--numbers' in sys.argv:
    offset, items = 0, []
    while True:
        page = get(f'runs?limit=100&offset={offset}')
        items.extend(page['items'])
        if len(items) >= page['total']:
            break
        if not page['items']:
            raise ValueError('incomplete run pagination')
        offset = len(items)
    numbers = [item['run_number'] for item in items]
    assert all(isinstance(number, str) and number.isdecimal() and int(number) > 0 for number in numbers)
    assert len(set(numbers)) == len(numbers)
    assert all(get('runs/' + item['run_id'])['run_number'] == item['run_number'] for item in items)
    print(json.dumps({'passed': True, 'total': len(items), 'unique_numbers': len(set(numbers)),
        'min': min(map(int, numbers), default=None), 'max': max(map(int, numbers), default=None),
        'mapping_sha256': hashlib.sha256(json.dumps(sorted((item['run_id'], item['run_number']) for item in items)).encode()).hexdigest()}))
else:
    print(json.dumps(collect(fetch=compatible_get), sort_keys=True))
