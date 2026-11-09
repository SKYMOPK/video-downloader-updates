"""Ensure delivered Python bytecode and QML match the final reviewed sources."""
import marshal
from pathlib import Path
import sys
import types
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
reader=CArchiveReader(ROOT/'dist/VideoDownloader/VideoDownloader.exe')
archive=reader.open_embedded_archive('PYZ.pyz')

def normalized(value):
    if isinstance(value,types.CodeType):
        return (value.co_code,tuple(normalized(v) for v in value.co_consts),value.co_names,value.co_varnames,value.co_freevars,
                value.co_cellvars,value.co_flags,value.co_argcount,value.co_posonlyargcount,value.co_kwonlyargcount,value.co_exceptiontable)
    if isinstance(value,tuple): return tuple(normalized(v) for v in value)
    return value

failures=[]
for path in (ROOT/'app').glob('*.py'):
    module='app' if path.stem=='__init__' else 'app.'+path.stem
    if module not in archive.toc: continue
    source=compile(path.read_bytes(),str(path),'exec',dont_inherit=True,optimize=0)
    if normalized(archive.extract(module))!=normalized(source): failures.append(path.relative_to(ROOT).as_posix())
main=compile((ROOT/'main.py').read_bytes(),str(ROOT/'main.py'),'exec',dont_inherit=True,optimize=0)
if normalized(marshal.loads(reader.extract('main')))!=normalized(main): failures.append('main.py')
for path in (ROOT/'qml').rglob('*'):
    if path.is_file() and path.read_bytes()!=(ROOT/'dist/VideoDownloader/_internal/qml'/path.relative_to(ROOT/'qml')).read_bytes(): failures.append(str(path))
assert not failures,'Frozen source mismatch: '+', '.join(failures)
print('Frozen Python and QML match final source files.')
