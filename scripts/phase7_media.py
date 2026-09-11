"""Authored bounded malformed/boundary media, using real parser implementations."""
import asyncio,io,json,os,sys,zipfile,wave,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
os.environ['GEMINI_API_KEY']='';os.environ['OPENAI_API_KEY']=''
from app.core.config import settings
from app.ingestion.pdf_parser import extract_pdf_document
from app.ingestion.vision_parser import parse_image_file,analyze_image_file
from app.ingestion.audio_parser import transcribe_audio_recording
from app.ingestion.file_guard import process_and_save_upload,validate_magic_bytes
from fastapi import UploadFile,HTTPException
from PIL import Image,ImageDraw,ImageFont
import fitz
OUT=ROOT/'phase7-evidence';MEDIA=OUT/'test-media';MEDIA.mkdir(exist_ok=True)
async def main():
    results={'fixtures':'Authored validation inputs; no business metrics or live semantic provider calls','pdf':{},'image':{},'audio':{},'guard':{}}
    image=Image.new('RGB',(1000,250),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',42) if sys.platform=='win32' else ImageFont.load_default(size=42)
    draw.text((20,75),'AUTHORED AUDIT REVENUE TEN',font=font,fill='black');image.save(MEDIA/'ocr.png');image.save(MEDIA/'valid.jpg')
    def pdf(name,kinds):
        doc=fitz.open()
        for kind in kinds:
            page=doc.new_page()
            if kind=='native':page.insert_text((50,70),'AUTHORED audit native text. Revenue was ten dollars for the test fixture.')
            elif kind=='scan':page.insert_image(fitz.Rect(40,40,540,165),filename=str(MEDIA/'ocr.png'))
        doc.save(MEDIA/name);doc.close()
    for name,kinds in [('native.pdf',['native']),('scanned.pdf',['scan']),('mixed.pdf',['native','scan']),('empty.pdf',['empty']),('image-heavy.pdf',['scan']*3),('pages-501.pdf',['native']*501)]:pdf(name,kinds)
    (MEDIA/'malformed.pdf').write_bytes(b'%PDF-1.7 malformed')
    for name in ['native.pdf','scanned.pdf','mixed.pdf','empty.pdf','image-heavy.pdf','pages-501.pdf','malformed.pdf']:
        result=extract_pdf_document(str(MEDIA/name));results['pdf'][name]={'status':result.status.value,'records':len(result.records),'methods':sorted(set(r.extraction_method.value for r in result.records)),'error_code':result.error_code,'pages_processed':result.metadata.get('pages_processed')}
    (MEDIA/'invalid.png').write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
    large=Image.new('1',(5000,4001));large.save(MEDIA/'pixels-over.png');del large
    exact=Image.new('1',(5000,4000));exact.save(MEDIA/'pixels-exact.png');del exact
    for name in ['ocr.png','valid.jpg','invalid.png','pixels-over.png','pixels-exact.png']:
        parsed=parse_image_file(str(MEDIA/name));results['image'][name]={'status':parsed['status'],'error':parsed['metadata'].get('error_code'),'width':parsed['metadata'].get('width'),'height':parsed['metadata'].get('height')}
    results['image']['spoofed_extension_rejected']=not validate_magic_bytes((MEDIA/'valid.jpg').read_bytes()[:1024],'.png')
    ocr=await analyze_image_file(str(MEDIA/'ocr.png'));results['image']['real_ocr']={'status':ocr['status'],'chunks':len(ocr['chunks']),'methods':[c.get('extraction_method') for c in ocr['chunks']]}
    (MEDIA/'spoof.wav').write_bytes(b'RIFF'+b'0'*100);(MEDIA/'truncated.wav').write_bytes((MEDIA/'speech-tts.wav').read_bytes()[:30])
    # Oversized declared duration is rejected before provider work; no giant allocation.
    frames=16000*(settings.MAX_AUDIO_DURATION_SECONDS+1);header=b'RIFF'+struct.pack('<I',36+frames*2)+b'WAVEfmt '+struct.pack('<IHHIIHH',16,1,1,16000,32000,2,16)+b'data'+struct.pack('<I',frames*2)
    (MEDIA/'duration-over.wav').write_bytes(header+b'\0\0')
    for name in ['speech-tts.wav','spoof.wav','truncated.wav','duration-over.wav']:
        parsed=await transcribe_audio_recording(str(MEDIA/name));results['audio'][name]={'status':parsed['status'],'chunks':len(parsed['chunks']),'error':parsed.get('metadata',{}).get('error_code')}
    settings.UPLOAD_DIR=ROOT/'.ui-qa/phase7-file-guard';settings.UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
    async def guard(name,data):
        try:
            saved=await process_and_save_upload(UploadFile(filename=name,file=io.BytesIO(data)),'phase7-boundary');return {'accepted':True,'clean_name':saved[0],'bytes':saved[2]}
        except HTTPException as exc:return {'accepted':False,'http':exc.status_code,'detail':exc.detail}
        except Exception as exc:return {'accepted':False,'exception_type':type(exc).__name__,'http':'UNHANDLED'}
    results['guard']['traversal']=await guard('../../outside.txt',b'Authored path traversal test')
    results['guard']['archive']=await guard('archive.zip',b'PK\x03\x04')
    for name,member in [('macros','word/vbaProject.bin'),('zip_path','../outside.xml')]:
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr(member,b'AUDIT')
        results['guard'][name]=await guard(name+'.docx',data.getvalue())
    results['guard']['byte_limit_plus_one']=await guard('too-large.txt',b'A'*(settings.MAX_FILE_SIZE_BYTES+1))
    (OUT/'media.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
if __name__=='__main__':asyncio.run(main())
