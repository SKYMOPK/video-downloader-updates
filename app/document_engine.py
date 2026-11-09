"""Conversion subprocess. Files are staged; the GUI publishes only verified results."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import warnings
import hashlib
import uuid
import zipfile

from .document_formats import identify, outputs, read_text, DocumentError, IMAGES, SHEETS, SLIDES
from .storage import ROOT, DATA, atomic_json, read_json


def office_executable():
    candidate = ROOT / 'tools/office/program/soffice.com'
    if candidate.is_file(): return candidate
    manifest = read_json(ROOT / 'tools/office-manifest.json', {})
    digest = manifest.get('runtime_sha256','')
    if len(digest) != 64: return None
    candidate = DATA / 'office-runtime' / digest[:20] / 'program/soffice.com'
    return candidate if candidate.is_file() else None


def office_available():
    return bool(office_executable() or (ROOT / 'tools/office-runtime.zip').is_file())


def prepare_private_runtime(executable):
    # Administrative MSI extraction places the redistributable beside program/.
    # Put the matching x64 DLLs next to the engine, avoiding any system install.
    runtime=executable.parent.parent/'System64'
    if runtime.is_dir():
        for source in runtime.glob('*.dll'):
            target=executable.parent/source.name
            if not target.exists(): shutil.copyfile(source,target)
    return executable


def ensure_office():
    executable = office_executable()
    manifest = read_json(ROOT/'tools/office-manifest.json', {})
    if executable:
        with executable.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest() == manifest.get('soffice_sha256'): return prepare_private_runtime(executable)
        raise DocumentError('文件轉換元件驗證失敗，請重新安裝 App')
    archive_path = ROOT/'tools/office-runtime.zip'
    if not archive_path.is_file(): return None
    stage('首次使用，正在準備文件轉換引擎；完成後不需再次準備')
    with archive_path.open('rb') as stream:
        digest = hashlib.file_digest(stream,'sha256').hexdigest()
    if digest != manifest.get('runtime_sha256'): raise DocumentError('文件轉換元件驗證失敗，請重新安裝 App')
    cache = DATA/'office-runtime'; cache.mkdir(parents=True,exist_ok=True)
    # A forcibly cancelled first preparation cannot run finally; reclaim only
    # our marked, abandoned directories before the next serial Office job.
    for child in cache.iterdir():
        if re.fullmatch(r'preparing-[a-f0-9]{32}',child.name) and child.is_dir() and not child.is_symlink() and not child.is_junction():
            marker=read_json(child/'.owner.json',{})
            if marker.get('app')=='VideoDownloaderOffice': shutil.rmtree(child,ignore_errors=True)
    destination=cache/digest[:20]
    temporary=cache/('preparing-'+uuid.uuid4().hex); temporary.mkdir()
    atomic_json(temporary/'.owner.json',{'app':'VideoDownloaderOffice'})
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries=archive.infolist()
            expanded=sum(e.file_size for e in entries)
            if len(entries)>25000 or expanded>2*1024**3: raise DocumentError('文件元件大小驗證失敗')
            if shutil.disk_usage(cache).free < expanded+200*1024**2: raise DocumentError('準備文件轉換引擎需要約 1.8 GB 可用空間，請釋放空間後再試')
            for entry in entries:
                relative=Path(entry.filename)
                if relative.is_absolute() or '..' in relative.parts or ':' in entry.filename or '\\' in entry.filename: raise DocumentError('文件元件路徑驗證失敗')
                target=temporary/relative
                if entry.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(entry) as source,target.open('xb') as output: shutil.copyfileobj(source,output)
        candidate=temporary/'program/soffice.com'
        with candidate.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=manifest.get('soffice_sha256'): raise DocumentError('文件元件驗證失敗')
        temporary.rename(destination)
        return prepare_private_runtime(destination/'program/soffice.com')
    finally:
        if temporary.exists() and temporary.parent==cache and temporary.name.startswith('preparing-'):
            shutil.rmtree(temporary,ignore_errors=True)


_work = None


def stage(text):
    value = {'stage': text}
    if _work: atomic_json(_work/'status.json',value)
    if sys.stdout is not None: print(json.dumps(value, ensure_ascii=True), flush=True)


def text_to_docx(source, destination):
    from docx import Document
    from docx.shared import Pt, Cm
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    text = read_text(source)
    if not text.strip(): raise DocumentError('文件中沒有可轉換的文字')
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2.2)
    style = document.styles['Normal']
    style.font.name, style.font.size = 'Microsoft JhengHei', Pt(11)
    fonts = style.element.get_or_add_rPr().find(qn('w:rFonts'))
    fonts.set(qn('w:eastAsia'), 'Microsoft JhengHei')
    style.paragraph_format.space_after = Pt(5)
    style.paragraph_format.line_spacing = 1.25
    for line in text.replace('\r\n','\n').replace('\r','\n').split('\n'):
        document.add_paragraph(line)
    document.save(destination)


def office_convert(source, output, work, source_kind):
    stage('正在轉換文件，複雜版面可能需要一些時間')
    executable = ensure_office()
    if not executable: raise DocumentError('文件轉換元件遺失，請重新安裝完整版本 App')
    profile = work / 'office-profile'
    profile.mkdir()
    (profile / 'user').mkdir()
    (profile / 'user/registrymodifications.xcu').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item><item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="AllowLinkUpdate" oor:op="fuse"><value>false</value></prop></item></oor:items>''', encoding='utf-8')
    filters = {'pdf': 'pdf:' + ('calc_pdf_Export' if source_kind in SHEETS else 'impress_pdf_Export' if source_kind in SLIDES else 'writer_pdf_Export'),
               'txt':'txt:Text (encoded):UTF8', 'docx':'docx:Office Open XML Text', 'odt':'odt:writer8', 'rtf':'rtf:Rich Text Format'}
    result = subprocess.run([str(executable), '-env:UserInstallation=' + profile.as_uri(), '--headless', '--norestore', '--nodefault', '--nolockcheck',
                             '--convert-to', filters[output], '--outdir', str(work / 'outputs'), str(source)],
                            capture_output=True, timeout=150, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    target = work / 'outputs' / (source.stem + '.' + output)
    if result.returncode or not target.is_file() or target.stat().st_size == 0:
        raise DocumentError('文件轉換未成功。請確認檔案可正常開啟、未加密，或先移除不支援的內容。')
    return target


def image_frames(paths):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    total = 0
    for path in paths:
        with Image.open(path) as source:
            frames = getattr(source, 'n_frames', 1)
            if frames > 1 and source.format != 'TIFF': raise DocumentError('目前只支援靜態圖片，請先將動畫另存為靜態圖片')
            for i in range(frames):
                total += 1
                if total > 200: raise DocumentError('一次最多處理 200 張圖片或頁面')
                source.seek(i)
                if source.width * source.height > 40_000_000: raise DocumentError('圖片尺寸超過 4,000 萬像素，請先縮小圖片')
                image = ImageOps.exif_transpose(source).convert('RGBA')
                yield image


def white_rgb(image):
    from PIL import Image
    background = Image.new('RGB', image.size, 'white')
    background.paste(image, mask=image.getchannel('A'))
    return background


def convert_images(paths, output, work):
    from PIL import Image
    folder = work / 'outputs'
    if output == 'pdf':
        # Each image is a separate A4 page. Encode/combine one page at a time.
        import pypdfium2 as pdfium
        result = pdfium.PdfDocument.new()
        try:
            for number, image in enumerate(image_frames(paths)):
                stage(f'正在整理第 {number + 1} 張圖片')
                rgb = white_rgb(image)
                page_w, page_h = (841.89, 595.28) if image.width > image.height else (595.28, 841.89)
                scale = min((page_w-48)/image.width, (page_h-48)/image.height)
                width, height = image.width*scale, image.height*scale
                page = result.new_page(page_w, page_h)
                bitmap = pdfium.PdfBitmap.from_pil(rgb)
                obj = pdfium.PdfImage.new(result)
                obj.set_bitmap(bitmap)
                obj.set_matrix(pdfium.PdfMatrix(width,0,0,height,(page_w-width)/2,(page_h-height)/2))
                page.insert_obj(obj)
                page.gen_content()
                page.close()
                bitmap.close()
                rgb.close(); image.close()
            target = folder / 'document.pdf'
            result.save(target)
        finally: result.close()
        return [target]
    targets = []
    for i, image in enumerate(image_frames(paths)):
        target = folder / f'page-{i+1:03d}.{output}'
        if output == 'jpg':
            converted = white_rgb(image)
            converted.save(target, 'JPEG', quality=92, subsampling=0)
            converted.close()
        elif output == 'webp': image.save(target, 'WEBP', lossless=True)
        else: image.save(target, 'PNG')
        image.close(); targets.append(target)
    return targets


def convert_pdf(source, output, work):
    import pypdfium2 as pdfium
    try: document = pdfium.PdfDocument(source)
    except pdfium.PdfiumError: raise DocumentError('PDF 已損壞或受到密碼保護，請先解除保護後再試') from None
    targets, texts = [], []
    try:
        if not 1 <= len(document) <= 200: raise DocumentError('PDF 一次最多處理 200 頁')
        for i in range(len(document)):
            stage(f'正在處理 PDF 第 {i+1}／{len(document)} 頁')
            page = document[i]
            try:
                if output == 'txt':
                    text_page = page.get_textpage()
                    try: texts.append(text_page.get_text_range())
                    finally: text_page.close()
                else:
                    width, height = page.get_size()
                    if width*height*(150/72)**2 > 40_000_000: raise DocumentError('PDF 頁面尺寸過大，請先縮小頁面')
                    bitmap = page.render(scale=150/72, fill_color=(255,255,255,255))
                    try:
                        image = bitmap.to_pil().convert('RGB')
                        target = work / 'outputs' / f'page-{i+1:03d}.{output}'
                        image.save(target, 'JPEG' if output == 'jpg' else 'PNG', **({'quality':92} if output == 'jpg' else {}))
                        image.close(); targets.append(target)
                    finally: bitmap.close()
            finally: page.close()
        if output == 'txt':
            text = '\n\n'.join(texts)
            if not text.strip(): raise DocumentError('這份 PDF 沒有可擷取的文字，可能是掃描文件。本版未提供 OCR，可改為轉成圖片。')
            target = work / 'outputs/document.txt'
            target.write_text(text, encoding='utf-8-sig'); targets = [target]
        return targets
    finally: document.close()


def verify_results(paths, output):
    if not paths or any(not p.is_file() or not p.stat().st_size for p in paths): raise DocumentError('輸出檔案不完整，未標記為完成')
    if output == 'pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(paths[0]) as document:
            if not 1 <= len(document) <= 200: raise DocumentError('PDF 超過 200 頁上限或內容無效')
            page = document[0]
            try:
                bitmap = page.render(scale=0.2)
                bitmap.close()
            finally: page.close()
    elif output in ('png','jpg','webp'):
        from PIL import Image
        for path in paths:
            with Image.open(path) as image: image.verify()
    elif output == 'docx':
        from docx import Document
        Document(paths[0])
    elif output == 'odt':
        if identify(paths[0])['format'] != 'odt': raise DocumentError('輸出文件格式驗證失敗')
    elif output == 'txt' and not read_text(paths[0]).strip(): raise DocumentError('輸出文字為空，未標記為完成')
    elif output == 'rtf' and not paths[0].read_bytes().lstrip().startswith(b'{\\rtf'): raise DocumentError('RTF 輸出驗證失敗')


def run_job(job_path):
    global _work
    job_path = Path(job_path).resolve()
    work = job_path.parent
    _work = work
    job = json.loads(job_path.read_text(encoding='utf-8'))
    try:
        sources = [Path(p) for p in job['sources']]
        metadata = [identify(p) for p in sources]
        output = job['output']
        if not sources or len(sources) > 100 or any(output not in outputs(m['format'], office_available()) for m in metadata):
            raise DocumentError('此來源不支援所選輸出格式')
        if len(sources) > 1 and (output != 'pdf' or any(m['format'] not in IMAGES for m in metadata)):
            raise DocumentError('目前只支援將多張圖片合併為 PDF')
        stage('正在讀取並準備文件')
        (work / 'outputs').mkdir()
        copied = []
        for i, (source, meta) in enumerate(zip(sources, metadata)):
            target = work / f'source-{i}.{meta["format"]}'
            shutil.copyfile(source, target); copied.append(target)
        kind = metadata[0]['format']
        if kind in IMAGES: paths = convert_images(copied, output, work)
        elif kind == 'pdf': paths = convert_pdf(copied[0], output, work)
        elif kind == 'txt':
            intermediate = work / 'source-text.docx'
            text_to_docx(copied[0], intermediate)
            paths = [intermediate] if output == 'docx' else [office_convert(intermediate, output, work, 'docx')]
        else: paths = [office_convert(copied[0], output, work, kind)]
        if output == 'docx' and kind == 'txt':
            moved = work / 'outputs/document.docx'; paths[0].rename(moved); paths = [moved]
        stage('正在驗證輸出檔案')
        verify_results(paths, output)
        atomic_json(work / 'result.json', {'ok':True, 'files':[p.relative_to(work / 'outputs').as_posix() for p in paths],
                                          'directory': kind == 'pdf' and output in ('png','jpg') or len(paths)>1})
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, DocumentError) else '轉換未完成，檔案可能已損壞、內容過大，或元件無法讀取。'
        if isinstance(exc,OSError) and exc.errno==28: message='磁碟空間不足，請釋放空間或選擇其他儲存位置後再試'
        elif isinstance(exc,PermissionError): message='檔案或儲存位置無法存取，請確認權限、關閉占用檔案的程式後再試'
        atomic_json(work / 'result.json', {'ok':False, 'error':message})
        return 1


if __name__ == '__main__': raise SystemExit(run_job(sys.argv[1]))
