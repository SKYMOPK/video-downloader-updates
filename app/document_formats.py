"""Bounded content-based identification and supported conversion choices."""
from pathlib import Path
import zipfile

MAX_FILE = 100 * 1024 ** 2
IMAGES = {"png", "jpg", "webp", "bmp", "tiff", "gif"}
WRITER = {"docx", "doc", "odt", "rtf"}
SHEETS = {"xlsx", "xls", "ods"}
SLIDES = {"pptx", "ppt", "odp"}
OFFICE = WRITER | SHEETS | SLIDES
NAMES = {"docx": "Word", "doc": "舊版 Word", "xlsx": "Excel", "xls": "舊版 Excel", "pptx": "PowerPoint", "ppt": "舊版 PowerPoint",
         "txt": "純文字", "odt": "ODT 文件", "ods": "ODS 試算表", "odp": "ODP 簡報", "rtf": "RTF 文件", "pdf": "PDF",
         "png": "PNG 圖片", "jpg": "JPG 圖片", "webp": "WebP 圖片", "bmp": "BMP 圖片", "tiff": "TIFF 圖片", "gif": "GIF 圖片"}
LABELS = {"pdf": "PDF 文件", "docx": "Word 文件", "odt": "ODT 文件", "rtf": "RTF 文件", "txt": "純文字 TXT", "png": "PNG 圖片", "jpg": "JPG 圖片", "webp": "WebP 圖片"}


class DocumentError(Exception): pass


def read_text(path):
    if Path(path).stat().st_size > 10 * 1024 ** 2: raise DocumentError("純文字檔案上限為 10 MB")
    data = Path(path).read_bytes()
    if len(data) > 10 * 1024 ** 2: raise DocumentError("純文字檔案上限為 10 MB")
    encodings = ["utf-8-sig", "utf-16", "big5", "cp950"] if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ["utf-8-sig", "big5", "cp950"]
    for encoding in encodings:
        try:
            text = data.decode(encoding)
            if "\x00" not in text and not any(ord(c) < 32 and c not in '\t\n\r\f' for c in text): return text
        except UnicodeError: pass
    raise DocumentError("無法辨識文字編碼，請先將文件另存為 UTF-8 或 Big5")


def identify(path):
    path = Path(path)
    if not path.is_file(): raise DocumentError("找不到檔案，或這不是一般檔案")
    size = path.stat().st_size
    if not size: raise DocumentError("檔案是空的，請選擇有內容的文件")
    if size > MAX_FILE: raise DocumentError("單一檔案上限為 100 MB")
    with path.open('rb') as stream: head = stream.read(4096)
    if head.startswith(b'%PDF-'): kind = 'pdf'
    elif head.startswith(b'PK'):
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(e.file_size for e in entries) > 300 * 1024 ** 2:
                    raise DocumentError("文件內容過大，無法安全處理")
                if any(e.flag_bits & 1 for e in entries): raise DocumentError("不支援加密文件，請先解除密碼保護")
                names = set(archive.namelist())
                if any(n.lower().endswith('vbaproject.bin') or n.lower().startswith(('basic/','scripts/')) for n in names): raise DocumentError("目前不處理含巨集的 Office 文件，請另存為不含巨集的版本")
                kind = next((k for name, k in [('word/document.xml','docx'), ('xl/workbook.xml','xlsx'), ('ppt/presentation.xml','pptx')] if name in names), '')
                if not kind and 'mimetype' in names:
                    with archive.open('mimetype') as stream: mime = stream.read(128).decode('ascii', errors='replace')
                    kind = {'application/vnd.oasis.opendocument.text':'odt', 'application/vnd.oasis.opendocument.spreadsheet':'ods', 'application/vnd.oasis.opendocument.presentation':'odp'}.get(mime, '')
                if not kind: raise DocumentError("這是壓縮檔，或不是支援的 Office 文件")
        except (zipfile.BadZipFile, KeyError): raise DocumentError("Office 文件已損壞，無法讀取") from None
    elif head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        import olefile
        try:
            with olefile.OleFileIO(path) as document:
                if document.exists('EncryptedPackage'): raise DocumentError("不支援加密文件，請先解除密碼保護")
                if any('vba' in '/'.join(parts).lower() for parts in document.listdir()): raise DocumentError("目前不處理含巨集的 Office 文件，請另存為不含巨集的版本")
                kind = 'doc' if document.exists('WordDocument') else 'xls' if document.exists('Workbook') or document.exists('Book') else 'ppt' if document.exists('PowerPoint Document') else ''
                if not kind: raise DocumentError("無法辨識這個舊版 Office 文件")
        except OSError: raise DocumentError("舊版 Office 文件已損壞") from None
    elif head.lstrip().startswith(b'{\\rtf'): kind = 'rtf'
    else:
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(path) as image:
                if image.width*image.height>40_000_000: raise DocumentError('圖片尺寸超過 4,000 萬像素，請先縮小圖片')
                if getattr(image,'n_frames',1)>1 and image.format!='TIFF': raise DocumentError('目前只支援靜態圖片，請先將動畫另存為靜態圖片')
                kind = {'JPEG':'jpg','PNG':'png','WEBP':'webp','BMP':'bmp','TIFF':'tiff','GIF':'gif'}.get(image.format, '')
            if not kind: raise DocumentError("尚未支援這種圖片格式")
        except Image.DecompressionBombError: raise DocumentError('圖片尺寸過大，請先縮小圖片') from None
        except (UnidentifiedImageError, OSError):
            if path.suffix.lower() not in ('.txt', '.text'): raise DocumentError("無法辨識檔案內容，請選擇支援的文件或圖片") from None
            read_text(path)
            kind = 'txt'
    return {"format": kind, "formatLabel": NAMES[kind], "size": size, "name": path.name, "source": str(path.resolve())}


def outputs(kind, office_available=True):
    if kind in OFFICE and not office_available: return []
    if kind in WRITER: values = ['pdf','txt','docx','odt','rtf']
    elif kind in SHEETS | SLIDES: values = ['pdf']
    elif kind == 'txt': values = ['pdf','docx'] if office_available else ['docx']
    elif kind == 'pdf': values = ['png','jpg','txt']
    elif kind in IMAGES: values = ['pdf','png','jpg','webp']
    else: values = []
    return [value for value in values if value != kind]


def warning(kind, output):
    if output == 'txt': return "只保留文字，不保留排版、圖片或表格樣式；掃描 PDF 需要 OCR，本版未提供文字辨識。"
    if output == 'jpg': return "JPG 使用有損壓縮；透明區域會填成白色。多頁 PDF 會輸出為圖片資料夾。"
    if kind == 'pdf': return "每一頁會分別輸出為圖片，保存在同一個資料夾。"
    if kind in SHEETS: return "依來源的列印範圍與分頁設定輸出；請先在試算表中確認版面。"
    if kind in SLIDES: return "每張投影片輸出為一頁 PDF，動畫與影片不會保留。"
    if kind in WRITER: return "盡量保留版面；特殊字型、複雜表格或特殊效果可能有差異。"
    return "在本機轉換，原始檔案會保留。"
