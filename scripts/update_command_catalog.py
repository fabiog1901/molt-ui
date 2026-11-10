from pathlib import Path
import pprint
import re
import subprocess

commands = []
common = {'source', 'target', 'schema', 'url', 'out', 'direct-copy', 'bucket-path', 'table-filter', 'schema-filter', 'table-handling', 'mode', 'non-interactive'}
for command, label in [('fetch','Fetch data'), ('verify','Verify data'), ('convert postgres','Convert PostgreSQL schema'), ('convert mysql','Convert MySQL schema'), ('convert oracle','Convert Oracle schema')]:
    help_text = subprocess.run(['./molt/molt', *command.split(), '--help'], capture_output=True, text=True, check=True).stdout
    options = []
    current = None
    for line in help_text.splitlines():
        match = re.match(r'^ {2,6}(?:-\w, )?--([\w-]+)\s+(.*)$', line)
        if match:
            name, tail = match.groups()
            if name == 'help':
                current = None
                continue
            parts = re.split(r'\s{2,}', tail, maxsplit=1)
            kind = 'string' if len(parts) == 2 else 'bool'
            if kind == 'string' and parts[0] == 'int':
                kind = 'int'
            if name == 'use-copy':
                kind = 'bool'
            current = {'name': name, 'kind': kind, 'description': parts[-1], 'advanced': name not in common, 'secret': name in {'source', 'target', 'source-cdb', 'url'}}
            options.append(current)
        elif current and line.startswith(' ' * 20):
            current['description'] += ' ' + line.strip()
        else:
            current = None
    options.sort(key=lambda opt: (opt['advanced'], ['source','target','schema','url','out'].index(opt['name']) if opt['name'] in ['source','target','schema','url','out'] else 10))
    commands.append({'id': command.replace(' ', '-'), 'label': label, 'arguments': command.split(), 'options': options})
Path('src/molt_ui/core/catalog.py').write_text('"""Command metadata captured from the bundled molt binary help.\n\nRegenerate deliberately when upgrading molt; both UIs consume this catalog.\n"""\n\nCOMMANDS = ' + pprint.pformat(commands, width=100, sort_dicts=False) + '\n')
print([(c['id'], len(c['options'])) for c in commands])
