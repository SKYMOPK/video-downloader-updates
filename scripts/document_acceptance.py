"""Real QML, subprocess queue and output acceptance against synthetic fixtures."""
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['VD_DATA_DIR']=str(ROOT/'evidence/document-acceptance-data')
from PySide6.QtCore import QTimer, QUrl, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
import pypdfium2 as pdfium
from app.controller import Controller
from app.storage import atomic_json
from app.release import VERSION

app=QApplication([]); QQuickStyle.setStyle('Basic')
messages=[]; qInstallMessageHandler(lambda mode,context,message:messages.append(message))
backend=Controller(); docs=backend.documents
docs._folder=str(ROOT/'evidence/document-results')
engine=QQmlApplicationEngine(); engine.rootContext().setContextProperty('backend',backend)
engine.load(QUrl.fromLocalFile(str(ROOT/'qml/Main.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0]; window.setProperty('currentTool','documents')
fixtures=ROOT/'evidence/document-fixtures'
sources=['中文報告.docx','試算表.xlsx','簡報.pptx','中文文字.txt','透明圖片.png','可選取文字.pdf','掃描文件.pdf','Big5文字.txt']
docs.model.beginResetModel(); docs.model.items=[]; docs.model.endResetModel()
docs.addFiles([QUrl.fromLocalFile(str(fixtures/name)).toString() for name in sources])
assert docs.count==len(sources),(docs.count,docs.error)
for task in docs.model.items:
    task['output']='txt' if task['name']=='可選取文字.pdf' else 'png' if task['name']=='掃描文件.pdf' else 'pdf'
docs.refresh()
def pump(seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline: app.processEvents(); time.sleep(.01)
pump(1); window.grabWindow().save(str(ROOT/'evidence/document-ready.png'))
started=time.monotonic(); docs.start()
pump(.3); assert not backend.requestClose(),'Active document conversion must block unconfirmed close'
window.grabWindow().save(str(ROOT/'evidence/document-converting.png'))
while docs.activeCount and time.monotonic()-started<240: pump(.1)
assert docs.activeCount==0,'Document queue did not finish'
assert all(t['state']=='completed' for t in docs.model.items),docs.model.items
for task in docs.model.items:
    if task['output']=='pdf':
        with pdfium.PdfDocument(task['path']) as pdf:
            page=pdf[0]; bitmap=page.render(scale=1)
            bitmap.to_pil().save(ROOT/'evidence'/f"converted-{Path(task['sources'][0]).stem}.png")
            bitmap.close(); page.close()
            if task['name'] in ('中文報告.docx','簡報.pptx'): assert len(pdf)==2
pump(.5); window.grabWindow().save(str(ROOT/'evidence/document-completed.png'))
# Small-window layout and empty state are separately captured for visual inspection.
window.setWidth(900); window.setHeight(640); pump(.3)
window.grabWindow().save(str(ROOT/'evidence/document-small.png'))
report={'version':VERSION,'seconds':round(time.monotonic()-started,2),'tasks':[
    {key:t[key] for key in ('name','format','output','state','path','directory')} for t in docs.model.items], 'qml_messages':messages}
atomic_json(ROOT/'evidence/document-acceptance.json',report)
print(json.dumps(report,ensure_ascii=True),flush=True)
backend.shutdown(); pump(.3)
