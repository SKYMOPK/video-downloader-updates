import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile

import pytest
from PIL import Image
import pypdfium2 as pdfium
from docx import Document
from PySide6.QtCore import QUrl

from app.document_formats import DocumentError, identify, outputs, read_text
from app.document_engine import run_job, office_executable
from app.storage import atomic_json, read_json
from app import documents as module


def convert(tmp_path,sources,output):
    work=tmp_path/'job'; work.mkdir()
    atomic_json(work/'job.json',{'sources':[str(p) for p in sources],'output':output})
    code=run_job(work/'job.json')
    result=read_json(work/'result.json',{})
    return code,result,work/'outputs'


def test_content_detection_does_not_trust_extension(tmp_path):
    source=tmp_path/'renamed.pdf'; Image.new('RGB',(20,10),'red').save(source,'PNG')
    assert identify(source)['format']=='png'
    assert 'docx' not in outputs('pdf')
    assert 'png' not in outputs('png')
    assert outputs('xlsx')==['pdf']


@pytest.mark.parametrize('encoding',['utf-8-sig','utf-16','big5'])
def test_text_encodings(tmp_path,encoding):
    source=tmp_path/'中文.txt'; source.write_text('繁體中文測試',encoding=encoding)
    assert read_text(source)=='繁體中文測試'
    assert identify(source)['format']=='txt'


def test_corrupt_and_macro_documents_rejected(tmp_path):
    source=tmp_path/'bad.docx'; source.write_bytes(b'PKgarbage')
    with pytest.raises(DocumentError): identify(source)
    with zipfile.ZipFile(source,'w') as archive:
        archive.writestr('word/document.xml','document'); archive.writestr('word/vbaProject.bin','macro')
    with pytest.raises(DocumentError,match='巨集'): identify(source)
    with zipfile.ZipFile(source,'w') as archive:
        archive.writestr('mimetype','application/vnd.oasis.opendocument.text')
        archive.writestr('Basic/Standard/Module1.xba','macro')
    with pytest.raises(DocumentError,match='巨集'): identify(source)


def test_empty_and_binary_text_rejected(tmp_path):
    source=tmp_path/'empty.txt'; source.write_bytes(b'')
    with pytest.raises(DocumentError): identify(source)
    source.write_bytes(b'\x00binary')
    with pytest.raises(DocumentError): identify(source)


def test_text_to_word_preserves_chinese_and_lines(tmp_path):
    source=tmp_path/'原始.txt'; source.write_text('中文第一行\n第二行',encoding='utf-8')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    code,result,folder=convert(tmp_path,[source],'docx')
    assert code==0, result
    doc=Document(folder/result['files'][0])
    assert [p.text for p in doc.paragraphs]==['中文第一行','第二行']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest


def test_image_pdf_orientation_and_transparency(tmp_path):
    source=tmp_path/'image.png'; image=Image.new('RGBA',(200,100),(0,0,0,0))
    for x in range(100):
        for y in range(50): image.putpixel((x,y),(255,0,0,255))
    image.save(source)
    code,result,folder=convert(tmp_path,[source],'pdf'); assert code==0,result
    with pdfium.PdfDocument(folder/result['files'][0]) as document:
        assert len(document)==1
        page=document[0]; assert page.get_width()>page.get_height()
        bitmap=page.render(scale=1); rendered=bitmap.to_pil().convert('RGB')
        assert rendered.getpixel((100,150))[0]>220
        assert rendered.getpixel((100,150))[1]<30
        assert rendered.getpixel((700,400))==(255,255,255)
        rendered.close(); bitmap.close(); page.close()


def test_tiff_page_count_and_animation_rejection(tmp_path):
    source=tmp_path/'pages.tiff'; Image.new('RGB',(40,60),'red').save(source,save_all=True,append_images=[Image.new('RGB',(60,40),'blue')])
    code,result,folder=convert(tmp_path,[source],'png'); assert code==0,result
    assert result['directory'] and len(result['files'])==2
    other=tmp_path/'animated'; other.mkdir()
    gif=tmp_path/'animation.gif'; Image.new('RGB',(10,10),'red').save(gif,save_all=True,append_images=[Image.new('RGB',(10,10),'blue')],duration=100)
    code,result,_=convert(other,[gif],'pdf'); assert code==1 and '靜態圖片' in result['error']


def test_pdf_image_and_text_and_scan_rejection(tmp_path):
    source=tmp_path/'scan.pdf'; image=tmp_path/'scan.png'; Image.new('RGB',(60,40),'blue').save(image)
    code,result,folder=convert(tmp_path,[image],'pdf'); assert code==0,result
    shutil.copyfile(folder/result['files'][0],source)
    other=tmp_path/'text'; other.mkdir()
    code,result,_=convert(other,[source],'txt'); assert code==1 and 'OCR' in result['error']
    other=tmp_path/'render'; other.mkdir()
    code,result,folder=convert(other,[source],'jpg'); assert code==0,result
    assert result['directory'] and Image.open(folder/result['files'][0]).format=='JPEG'


@pytest.mark.skipif(not office_executable(),reason='Bundled Office engine required')
@pytest.mark.parametrize('target',['pdf','txt','odt','rtf'])
def test_real_writer_conversions(tmp_path,target):
    source=tmp_path/'中文來源.docx'; doc=Document(); doc.add_paragraph('繁體中文與 English 123'); doc.save(source)
    code,result,folder=convert(tmp_path,[source],target); assert code==0,result
    assert all((folder/p).stat().st_size>0 for p in result['files'])
    if target=='txt': assert '繁體中文' in read_text(folder/result['files'][0])
    if target=='pdf':
        with pdfium.PdfDocument(folder/result['files'][0]) as pdf:
            page=pdf[0]; text=page.get_textpage()
            assert '繁體中文' in text.get_text_range(); text.close(); page.close()


def wait(qt, predicate, timeout=30):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end: qt.processEvents(); time.sleep(.01)
    assert predicate(),'Timed out waiting for document process'


def queue(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'DATA',tmp_path/'data')
    docs=module.Documents(); docs._folder=str(tmp_path/'out')
    return docs


def test_queue_continues_after_failure_and_preserves_existing(qt,tmp_path,monkeypatch):
    docs=queue(tmp_path,monkeypatch)
    broken=tmp_path/'bad.pdf'; broken.write_bytes(b'%PDF-1.7\nBROKEN')
    text=tmp_path/'中文.txt'; text.write_text('保留來源',encoding='utf-8')
    output=tmp_path/'out'; output.mkdir(); (output/'中文.docx').write_bytes(b'existing')
    docs.addFiles([QUrl.fromLocalFile(str(p)).toString() for p in (broken,text)])
    docs.model.items[1]['output']='docx'; docs.start()
    wait(qt,lambda: docs.activeCount==0)
    assert [t['state'] for t in docs.model.items]==['failed','completed']
    assert Path(docs.model.items[1]['path']).name=='中文 (1).docx'
    assert (output/'中文.docx').read_bytes()==b'existing'
    assert text.read_text(encoding='utf-8')=='保留來源'
    assert not (output/'.video-downloader-documents').exists()


def test_cancel_queue_and_restore_without_autostart(qt,tmp_path,monkeypatch):
    docs=queue(tmp_path,monkeypatch)
    text=tmp_path/'file.txt'; text.write_text('cancel',encoding='utf-8')
    docs.addFiles([QUrl.fromLocalFile(str(text)).toString()]); docs.start(); docs.cancelAll()
    wait(qt,lambda: docs.worker is None)
    assert docs.model.items[0]['state']=='cancelled'
    assert not list((tmp_path/'out').glob('*.pdf'))
    assert not (tmp_path/'out'/'.video-downloader-documents').exists()
    docs.model.items[0]['state']='converting'; docs.persist()
    restored=module.Documents(); assert restored.model.items[0]['state']=='draft' and restored.worker is None


def test_merge_order_and_reordering(qt,tmp_path,monkeypatch):
    docs=queue(tmp_path,monkeypatch)
    for i,color in enumerate(('red','blue')):
        path=tmp_path/f'{i}.png'; Image.new('RGB',(40,60),color).save(path); docs.addFiles([QUrl.fromLocalFile(str(path)).toString()])
    assert docs.canMerge
    docs.move(docs.model.items[1]['id'],-1); docs.setMerge(True); docs.start()
    wait(qt,lambda: docs.activeCount==0)
    assert docs.count==1 and docs.model.items[0]['state']=='completed',docs.model.items
    with pdfium.PdfDocument(docs.model.items[0]['path']) as pdf:
        assert len(pdf)==2; page=pdf[0]; bitmap=page.render(scale=.2); image=bitmap.to_pil()
        assert image.getpixel((50,50))[2]>220
        image.close(); bitmap.close(); page.close()


def test_update_waits_for_documents_and_blocks_new_work(qt,tmp_path,monkeypatch):
    import app.controller as controller
    import app.app_updates as updates
    monkeypatch.setattr(controller,'DATA',tmp_path/'data')
    monkeypatch.setattr(module,'DATA',tmp_path/'data')
    monkeypatch.setattr(updates,'DATA',tmp_path/'data')
    monkeypatch.setattr(controller.Controller,'check_dependencies',lambda self:None)
    owner=controller.Controller()
    owner.app_update_timer.stop()
    task={'state':'queued'}
    owner.documents.model.items.append(task)
    owner.app_updates._state='ready'; owner.app_updates._pending=True
    calls=[]; monkeypatch.setattr(owner.app_updates,'launch_install',lambda:calls.append(True))
    owner._try_app_install()
    assert not calls and not owner.requestClose()
    # Avoid constructing an invalid persisted fixture outside the waiting check.
    owner.documents.model.items.clear()
    owner._try_app_install()
    assert calls==[True]
    owner.documents.closing=True
    owner.closing=True
    owner.app_update_timer.stop()


def test_managed_cancel_terminates_descendants(qt,tmp_path):
    import sys
    import psutil
    from app.process import ManagedProcess
    script=tmp_path/'child.py'
    script.write_text('import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\nprint(p.pid,flush=True)\ntime.sleep(60)\n',encoding='utf-8')
    process=ManagedProcess(sys.executable,[str(script)],memory_limit=256*1024**2)
    children=[]; ended=[]
    process.line.connect(lambda line:children.append(int(line)))
    process.done.connect(lambda *args:ended.append(args))
    process.start(); wait(qt,lambda:bool(children))
    assert psutil.pid_exists(children[0])
    process.cancel(); wait(qt,lambda:bool(ended))
    wait(qt,lambda:not psutil.pid_exists(children[0]))


def test_managed_timeout_stops_child(qt,tmp_path):
    import sys
    from app.process import ManagedProcess
    result=[]
    process=ManagedProcess(sys.executable,['-c','import time;time.sleep(60)'],timeout=100)
    process.done.connect(lambda code,output:result.append((code,output)))
    process.start(); wait(qt,lambda:bool(result))
    assert result[0][0]!=0 and '逾時' in result[0][1]


def test_recovered_image_merge_only_offers_pdf(tmp_path,monkeypatch):
    docs=queue(tmp_path,monkeypatch)
    for i in range(2):
        source=tmp_path/f'{i}.png'; Image.new('RGB',(10,10),'red').save(source)
        docs.addFiles([QUrl.fromLocalFile(str(source)).toString()])
    task=docs.model.items[0]
    task['sources'].append(docs.model.items[1]['sources'][0]); task['state']='cancelled'; task['output']='pdf'
    docs.model.items=docs.model.items[:1]; docs.persist()
    restored=module.Documents()
    assert restored.model.items[0]['options']==['pdf']


def test_corrupted_history_cannot_prevent_startup(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'DATA',tmp_path)
    atomic_json(tmp_path/'document-settings.json',{'folder':False})
    atomic_json(tmp_path/'document-tasks.json',[{'id':1,'sources':[],'name':'bad','format':[], 'formatLabel':'bad','size':0,'output':[], 'state':[], 'detail':'','path':''}])
    docs=module.Documents()
    assert docs.count==0 and docs.folder.endswith('文件轉換')


def test_cleanup_preserves_unrelated_siblings(qt,tmp_path,monkeypatch):
    docs=queue(tmp_path,monkeypatch)
    parent=tmp_path/'out'/'.video-downloader-documents'; parent.mkdir(parents=True)
    keep=parent/'user-file.txt'; keep.write_text('keep me',encoding='utf-8')
    source=tmp_path/'file.txt'; source.write_text('文件內容',encoding='utf-8')
    docs.addFiles([QUrl.fromLocalFile(str(source)).toString()])
    docs.model.items[0]['output']='docx'; docs.start()
    wait(qt,lambda: docs.activeCount==0)
    assert docs.model.items[0]['state']=='completed'
    assert keep.read_text(encoding='utf-8')=='keep me'
    assert list(parent.iterdir())==[keep]


def test_pages_are_files_and_workspaces_removed(qt,tmp_path,monkeypatch):
    docs=queue(tmp_path,monkeypatch)
    source=tmp_path/'多頁.tiff'
    Image.new('RGB',(20,20),'red').save(source,save_all=True,append_images=[Image.new('RGB',(20,20),'blue')])
    docs.addFiles([QUrl.fromLocalFile(str(source)).toString()])
    docs.model.items[0]['output']='png'; docs.start()
    assert not (tmp_path/'out'/'.video-downloader-documents').exists()
    wait(qt,lambda: docs.activeCount==0)
    assert docs.model.items[0]['state']=='completed', docs.model.items
    assert sorted(p.name for p in (tmp_path/'out').iterdir())==['多頁（第 1 頁）.png','多頁（第 2 頁）.png']
    assert not (tmp_path/'data'/'document-workspaces').exists()


def test_stale_workspace_recovery_preserves_unmarked_and_live(tmp_path):
    import os
    import psutil
    root=tmp_path/'document-workspaces'
    stale=root/'stale'; live=root/'live'; other=root/'other'
    for item in (stale,live,other): item.mkdir(parents=True)
    atomic_json(stale/'.owner.json',{'app':'VideoDownloader','task':'stale','pid':os.getpid(),'created':0})
    atomic_json(live/'.owner.json',{'app':'VideoDownloader','task':'live','pid':os.getpid(),'created':psutil.Process().create_time()})
    (other/'personal.txt').write_text('keep')
    assert module.clean_document_workspaces(root)
    assert not stale.exists() and live.exists() and (other/'personal.txt').exists()


def test_cleanup_failure_is_reported(tmp_path,monkeypatch):
    import os
    root=tmp_path/'document-workspaces'; stale=root/'stale'; stale.mkdir(parents=True)
    atomic_json(stale/'.owner.json',{'app':'VideoDownloader','task':'stale','pid':os.getpid(),'created':0})
    def blocked(path): raise PermissionError('locked')
    monkeypatch.setattr(module.shutil,'rmtree',blocked)
    assert not module.clean_document_workspaces(root)
    assert stale.exists()
