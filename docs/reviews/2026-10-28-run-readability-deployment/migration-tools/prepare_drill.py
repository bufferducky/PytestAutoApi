"""从受保护的现有Compose配置创建无公网端口的恢复演练配置，绝不输出环境值。"""
import json
import os
import sys
from pathlib import Path
source, destination, project, mysql_volume, state_volume = sys.argv[1:]
source, destination = Path(source), Path(destination)
config = json.load(sys.stdin)
config['name'] = project
config['services'] = {key: value for key,value in config['services'].items() if key in {'mysql','backend'}}
for service in config['services'].values():
    service.pop('build',None)
    service.pop('ports',None)
    service.pop('container_name',None)
    service['restart'] = 'no'
config['volumes'] = {'mysql-data':{'external':True,'name':mysql_volume}, 'platform-data':{'external':True,'name':state_volume}}
config['networks'] = {'default':{'name':project+'_isolated'}}
fd = os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as output:
    json.dump(config,output)
print('恢复演练配置已生成：独立网络与卷，无公开端口。')
