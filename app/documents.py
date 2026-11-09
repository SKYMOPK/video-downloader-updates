"""Document queue and atomic publication, independent from video downloads."""
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Property, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from .document_formats import identify, outputs, warning, LABELS, NAMES, IMAGES, DocumentError
from .document_engine import office_available
from .process import ManagedProcess
from .storage import DATA, ROOT, atomic_json, read_json, publish, safe_filename, trim_utf16

STATES = {'draft':'待轉換', 'queued':'等待中', 'converting':'轉換中', 'cancelling':'停止中',
          'completed':'已完成', 'failed':'未完成', 'cancelled':'已取消'}
ACTIVE = {'queued', 'converting', 'cancelling'}


class DocumentModel(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.items = []

    def roleNames(self): return {Qt.UserRole + 1: b'item'}
    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.items)
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.items): return None
        task = self.items[index.row()]
        return task | {'stateLabel':STATES[task['state']], 'active':task['state'] in ACTIVE,
                       'editable':task['state'] not in ACTIVE and task['state'] != 'completed',
                       'outputLabel':LABELS[task['output']], 'warning':warning(task['format'],task['output']),
                       'sizeText':f"{task['size']/1024**2:.1f} MB" if task['size'] >= 1024**2 else f"{task['size']/1024:.0f} KB"}

    def refresh(self):
        if self.items: self.dataChanged.emit(self.index(0), self.index(len(self.items)-1), [Qt.UserRole+1])


def publish_directory(source, folder, title):
    budget = min(100, 220-len(str(folder.resolve()).encode('utf-16-le'))//2)
    if budget < 12: raise OSError('儲存位置路徑太長，請選擇較短的資料夾')
    base = trim_utf16(safe_filename(title), budget)
    for i in range(10000):
        target = folder / (base + (f' ({i})' if i else ''))
        try:
            # Windows rename fails for an existing directory, including an empty one.
            if os.name != 'nt' and target.exists(): continue
            source.rename(target)
            return str(target)
        except FileExistsError: continue
    raise OSError('同名資料夾過多，請選擇其他位置')


class Documents(QObject):
    changed = Signal()
    message = Signal(str)
    idle = Signal()

    def __init__(self, parent=None, allowed=lambda: True):
        super().__init__(parent)
        self.allowed, self.closing = allowed, False
        self.model = DocumentModel(self)
        self.worker = None
        self._error = ''
        config = read_json(DATA/'document-settings.json', {})
        self._folder = config.get('folder', str(Path.home()/'Downloads'/'文件轉換')) if isinstance(config,dict) else str(Path.home()/'Downloads'/'文件轉換')
        if not isinstance(self._folder,str) or not self._folder.strip(): self._folder=str(Path.home()/'Downloads'/'文件轉換')
        self._merge = False
        stored = read_json(DATA/'document-tasks.json', [])
        for task in stored[:100] if isinstance(stored,list) else []:
            if not isinstance(task,dict) or not all(k in task for k in ('id','sources','name','format','formatLabel','size','output','state','detail','path')): continue
            if not isinstance(task['state'],str) or not isinstance(task['output'],str) or task['state'] not in STATES or task['output'] not in LABELS: continue
            if not isinstance(task['format'],str) or task['format'] not in NAMES: continue
            if not isinstance(task['sources'],list) or not task['sources'] or not all(isinstance(p,str) and p for p in task['sources']): continue
            if not isinstance(task['size'],(int,float)) or task['size']<0: continue
            if task['state'] in ACTIVE: task.update(state='draft', detail='上次未完成，請確認後重新轉換')
            task['options'] = ['pdf'] if len(task['sources'])>1 and task['format'] in IMAGES else outputs(task['format'], office_available())
            task['optionLabels'] = [LABELS[k] for k in task['options']]
            self.model.items.append(task)

    @Property(QObject, constant=True)
    def tasks(self): return self.model
    @Property(str, notify=changed)
    def folder(self): return self._folder
    @Property(str, notify=changed)
    def error(self): return self._error
    @Property(int, notify=changed)
    def count(self): return len(self.model.items)
    @Property(int, notify=changed)
    def activeCount(self): return sum(t['state'] in ACTIVE for t in self.model.items)
    @Property(int, notify=changed)
    def readyCount(self): return sum(t['state']=='draft' for t in self.model.items)
    @Property(bool, notify=changed)
    def mergeImages(self): return self._merge
    @Property(bool, notify=changed)
    def canMerge(self):
        drafts = [t for t in self.model.items if t['state']=='draft']
        return len(drafts)>1 and all(t['format'] in IMAGES and len(t['sources'])==1 for t in drafts)
    @Property('QVariantList', notify=changed)
    def commonOptions(self): return [LABELS[k] for k in self.common_keys()]

    def common_keys(self):
        rows = [t for t in self.model.items if t['state']=='draft']
        return [k for k in LABELS if rows and all(k in t['options'] for t in rows)]

    def persist(self):
        try:
            atomic_json(DATA/'document-tasks.json', self.model.items[-100:])
            atomic_json(DATA/'document-settings.json', {'folder':self._folder})
        except OSError: self.message.emit('無法保存文件任務，請確認磁碟空間與權限')

    def refresh(self):
        if not self.canMerge: self._merge = False
        self.model.refresh(); self.changed.emit(); self.persist()

    @Slot()
    def chooseFiles(self):
        files, _ = QFileDialog.getOpenFileNames(None, '加入要轉換的文件', '',
            '支援的文件 (*.doc *.docx *.odt *.rtf *.xls *.xlsx *.ods *.ppt *.pptx *.odp *.txt *.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif);;所有檔案 (*)')
        self.addFiles([QUrl.fromLocalFile(p).toString() for p in files])

    @Slot('QVariantList')
    def addFiles(self, urls):
        if self.closing or not self.allowed(): self.message.emit('請先完成或取消 App 更新'); return
        errors = []
        existing = {p for t in self.model.items if t['state']!='completed' for p in t['sources']}
        pending = []
        for value in urls:
            if len(self.model.items)+len(pending)>=100: errors.append('清單最多保留 100 個任務，請先清除已結束的任務'); break
            url = value if isinstance(value,QUrl) else QUrl(str(value))
            if not url.isLocalFile(): errors.append('只接受電腦中的檔案'); continue
            path = url.toLocalFile()
            try:
                meta = identify(path)
                if meta['source'] in existing: continue
                choices = outputs(meta['format'], office_available())
                if not choices: raise DocumentError('文件轉換元件遺失，請重新安裝完整版本 App')
                pending.append(meta | {'id':uuid.uuid4().hex, 'sources':[meta['source']], 'output':choices[0],
                    'options':choices, 'optionLabels':[LABELS[k] for k in choices], 'state':'draft', 'detail':'', 'path':'', 'directory':False})
                existing.add(meta['source'])
            except (DocumentError,OSError,ValueError) as exc: errors.append(f'{Path(path).name}：{exc}')
        if pending:
            self.model.beginInsertRows(QModelIndex(), len(self.model.items),len(self.model.items)+len(pending)-1)
            self.model.items.extend(pending); self.model.endInsertRows()
        self._error = '\n'.join(errors[:5]) + (f'\n另有 {len(errors)-5} 個檔案無法加入' if len(errors)>5 else '')
        self.refresh()

    @Slot()
    def dismissError(self): self._error=''; self.changed.emit()
    @Slot()
    def chooseFolder(self):
        path = QFileDialog.getExistingDirectory(None, '選擇文件輸出資料夾', self._folder)
        if path: self._folder=path; self.refresh()
    @Slot(bool)
    def setMerge(self, value): self._merge = bool(value) and self.canMerge; self.changed.emit()
    @Slot(int)
    def setCommonOutput(self, index):
        keys = self.common_keys()
        if 0<=index<len(keys):
            for task in self.model.items:
                if task['state']=='draft': task['output']=keys[index]
            self.refresh()
    @Slot(str,int)
    def setOutput(self, task_id, index):
        task = self.find(task_id)
        if task and task['state'] not in ACTIVE and task['state']!='completed' and 0<=index<len(task['options']):
            task['output']=task['options'][index]; self.refresh()
    def find(self, task_id): return next((t for t in self.model.items if t['id']==task_id), None)
    @Slot(str,int)
    def move(self, task_id, direction):
        task = self.find(task_id)
        if not task or task['state']!='draft': return
        i=self.model.items.index(task); j=i+direction
        if not 0<=j<len(self.model.items) or self.model.items[j]['state']!='draft': return
        self.model.beginMoveRows(QModelIndex(),i,i,QModelIndex(),j if j<i else j+1)
        self.model.items.insert(j,self.model.items.pop(i)); self.model.endMoveRows(); self.refresh()
    @Slot(str)
    def remove(self, task_id):
        task=self.find(task_id)
        if task and task['state'] not in ACTIVE:
            i=self.model.items.index(task); self.model.beginRemoveRows(QModelIndex(),i,i)
            self.model.items.pop(i); self.model.endRemoveRows(); self.refresh()
    @Slot()
    def clearFinished(self):
        for task in list(self.model.items):
            if task['state'] in ('completed','failed','cancelled'): self.remove(task['id'])
    @Slot(str)
    def retry(self, task_id):
        task=self.find(task_id)
        if task and task['state'] in ('failed','cancelled'):
            task.update(state='draft', detail=''); self.refresh()
    @Slot()
    def start(self):
        if self.closing or not self.allowed(): self.message.emit('請先完成或取消 App 更新'); return
        drafts=[t for t in self.model.items if t['state']=='draft']
        if not drafts: return
        if self._merge and self.canMerge:
            first=drafts[0]
            first.update(sources=[t['sources'][0] for t in drafts],name=f"{Path(first['name']).stem} 等 {len(drafts)} 張圖片",output='pdf',size=sum(t['size'] for t in drafts))
            first['options']=['pdf']; first['optionLabels']=[LABELS['pdf']]
            for task in drafts[1:]: self.remove(task['id'])
            drafts=[first]
        for task in drafts: task.update(state='queued',detail='等待轉換',folder=self._folder)
        self.refresh(); self.schedule()

    def schedule(self):
        if self.worker or self.closing: return
        task=next((t for t in self.model.items if t['state']=='queued'),None)
        if not task: self.idle.emit(); return
        try:
            folder=Path(task['folder']); folder.mkdir(parents=True,exist_ok=True)
            # Work on the destination volume so final publication is atomic.
            work=folder/'.video-downloader-documents'/uuid.uuid4().hex
            work.mkdir(parents=True)
            atomic_json(work/'.owner.json', {'app':'VideoDownloader','task':task['id']})
            atomic_json(work/'job.json', {'sources':task['sources'],'output':task['output']})
        except OSError:
            task.update(state='failed',detail='輸出位置無法寫入，請選擇其他資料夾再試'); self.refresh(); QTimer.singleShot(0,self.schedule); return
        task.update(state='converting',detail='正在準備轉換')
        args=[] if getattr(sys,'frozen',False) else [str(ROOT/'main.py')]
        worker=ManagedProcess(sys.executable,args+['--convert-job',str(work/'job.json')],self,timeout=240000,memory_limit=2*1024**3)
        self.worker=worker
        status_timer=QTimer(worker)
        status_timer.setInterval(300)
        def line(value):
            try:
                status=json.loads(value).get('stage')
                if isinstance(status,str) and task['state']=='converting': task['detail']=status; self.model.refresh()
            except (ValueError,AttributeError): pass
        def done(code, output):
            status_timer.stop()
            result=read_json(work/'result.json',{})
            if not isinstance(result,dict): result={}
            cancelled=task['state']=='cancelling' or self.closing
            try:
                if cancelled: task.update(state='cancelled',detail='已停止轉換，原始檔案保留')
                elif code==0 and result.get('ok'):
                    files=result.get('files',[]); output_root=(work/'outputs').resolve()
                    if not files: raise OSError('輸出檔案不完整')
                    paths=[(output_root/p).resolve() for p in files]
                    if any(not p.is_relative_to(output_root) or not p.is_file() or p.is_symlink() for p in paths): raise OSError('輸出檔案驗證失敗')
                    title=Path(task['sources'][0]).stem
                    if len(task['sources'])>1: title+='（合併）'
                    directory=bool(result.get('directory'))
                    target=publish_directory(output_root,folder,title+'（'+task['output'].upper()+'）') if directory else publish(paths[0],folder,title,'文件')
                    task.update(state='completed',detail='已驗證並儲存至輸出位置',path=target,directory=directory)
                else:
                    error=result.get('error') if isinstance(result,dict) else None
                    task.update(state='failed',detail=error or ('轉換超過時間上限，已安全停止' if '逾時' in output else '轉換程序未完成，請檢查檔案與可用記憶體後重試'))
            except OSError as exc: task.update(state='failed',detail=f'無法儲存結果：{exc}')
            finally:
                # Delete only this freshly-created, marked workspace inside its expected parent.
                if work.parent==folder/'.video-downloader-documents' and read_json(work/'.owner.json',{}).get('task')==task['id']:
                    try:
                        shutil.rmtree(work)
                        # Remove only an empty parent; preserve unrelated files.
                        work.parent.rmdir()
                    except OSError: pass
                self.worker=None; worker.deleteLater(); self.refresh(); self.idle.emit(); QTimer.singleShot(0,self.schedule)
        worker.line.connect(line); worker.done.connect(done)
        status_timer.timeout.connect(lambda: line(json.dumps(read_json(work/'status.json',{}))))
        status_timer.start()
        self.refresh(); worker.start()

    @Slot(str)
    def cancel(self, task_id):
        task=self.find(task_id)
        if not task: return
        if task['state']=='queued': task.update(state='cancelled',detail='已取消尚未開始的轉換')
        elif task['state']=='converting' and self.worker: task.update(state='cancelling',detail='正在停止'); self.worker.cancel()
        self.refresh()
    @Slot()
    def cancelAll(self):
        for task in list(self.model.items):
            if task['state'] in ACTIVE: self.cancel(task['id'])
    @Slot(str)
    def openResult(self, task_id):
        task=self.find(task_id)
        if task and task['path'] and Path(task['path']).exists(): QDesktopServices.openUrl(QUrl.fromLocalFile(task['path']))
        else: self.message.emit('結果已被移動或刪除，請確認輸出資料夾')
    @Slot()
    def openFolder(self):
        if Path(self._folder).is_dir(): QDesktopServices.openUrl(QUrl.fromLocalFile(self._folder))
        else: self.message.emit('轉換後會自動建立輸出資料夾')
    def shutdown(self):
        self.closing=True; self.cancelAll(); self.persist()
