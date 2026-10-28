"""拒绝任何超出本次新增编号表/0002迁移的结构变化。"""
import ast
import hashlib
import json
import sys
from pathlib import Path

old, new = map(Path, sys.argv[1:])
rel = 'platform/backend/src/pyta_platform_backend/db/schema.py'
a, b = ast.parse((old / rel).read_text()), ast.parse((new / rel).read_text())
added = [node for node in b.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'run_numbers' for t in node.targets)]
assert len(added) == 1
expected = ast.parse('''run_numbers = table("run_numbers", Column("number", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True), ident("run_id", nullable=False, unique=True), sqlite_autoincrement=True)''').body[0]
assert ast.dump(added[0]) == ast.dump(expected), 'unexpected numbering table'
b.body.remove(added[0])
for node in b.body:
    if isinstance(node, ast.ImportFrom) and node.module == 'sqlalchemy':
        node.names = [name for name in node.names if name.name != 'BigInteger']
assert ast.dump(a) == ast.dump(b), 'existing schema changed'
base = 'platform/backend/alembic'
files = lambda root: {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/base).rglob('*.py') if not p.name.startswith('._')}
x, y = files(old), files(new)
assert all(y.get(key) == value for key, value in x.items()), 'existing migration changed'
assert set(y) - set(x) == {base+'/versions/0002_run_numbers.py'}, 'unexpected migration'
print(json.dumps({'passed':True, 'from':'0001_mysql', 'to':'0002_run_numbers', 'existing_tables_unchanged':True, 'new_table':'run_numbers', 'migration_sha256':y[base+'/versions/0002_run_numbers.py']}))
