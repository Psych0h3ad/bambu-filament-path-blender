# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad
"""Build the Blender-installable ZIP from this checkout, using only stdlib."""
from pathlib import Path
import ast
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'makerchip_rounded_import'
info = next(node.value for node in ast.parse((PACKAGE / '__init__.py').read_text(encoding='utf-8')).body
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in node.targets))
version = '.'.join(map(str, ast.literal_eval(info)['version']))
output = ROOT / 'dist'
output.mkdir(exist_ok=True)
archive = output / f'Bambu_Rounded_Beads-{version}.zip'
files = {str(p.relative_to(ROOT)).replace('\\', '/'): p for p in PACKAGE.rglob('*.py')}
for filename in ('LICENSE', 'README.md', 'README.en.md'):
    files[f'makerchip_rounded_import/{filename}'] = ROOT / filename
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name, path in sorted(files.items()):
        info = zipfile.ZipInfo(name, date_time=(2026, 9, 14, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, path.read_bytes())
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(output / 'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
print(f'{archive.name}: {archive.stat().st_size:,} bytes; SHA256 {digest}')
