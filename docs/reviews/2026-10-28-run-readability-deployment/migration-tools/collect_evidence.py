"""只汇总发布元数据、校验结果和计数，不复制配置或业务响应。"""
import hashlib
import json
from pathlib import Path
root = Path('/home/ubuntu/pytestautoapi')
tag = '20261028-run-readability-8e11bf8'
release, backup = root/'releases'/tag, root/'backups'/tag
read = lambda path: json.loads(path.read_text())
before = read(backup/'quiesced.json')
restored = read(backup/'restored-before.json')
drill = read(backup/'restored-migrated.json')
after = read(backup/'after-compatible.json')
state = read(release/'verification/state.json')
result = {
 'tag': tag,
 'commit': read(release/'manifest.json')['commit'],
 'previous': state['previous'],
 'current': str((root/'current').resolve()),
 'phase': state['phase'],
 'image_id': read(release/'verification/build.json')['image_id'],
 'schema': (release/'verification/alembic-current.txt').read_text().strip(),
 'schema_review': read(release/'verification/migration-review-final.json'),
 'backup': str(backup),
 'backup_sha256': {line.split()[1]:line.split()[0] for line in (backup/'SHA256SUMS').read_text().splitlines()},
 'restore_original_content_equal': before['records'] == restored['records'],
 'restore_migrated_content_equal': before['records'] == drill['records'],
 'production_original_content_equal': before['records'] == after['records'],
 'numbering_matches_drill': read(backup/'production-numbers.json') == read(backup/'drill-numbers.json'),
 'run_numbers': read(backup/'production-numbers.json'),
 'counts': after['counts'],
 'worker': after['worker'],
 'image_checks': read(release/'verification/image.json'),
 'worker_smoke': read(release/'verification/worker.json'),
 'migration_tools_sha256': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'incoming'/tag/'migration-tools').iterdir() if p.suffix in {'.sh','.py'}},
}
assert all(result[key] for key in ('restore_original_content_equal','restore_migrated_content_equal','production_original_content_equal','numbering_matches_drill'))
print(json.dumps(result,ensure_ascii=False,indent=2))
