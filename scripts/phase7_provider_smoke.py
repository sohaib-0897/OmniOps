"""One image, one short audio request; report metadata only, never provider payloads."""
import asyncio, hashlib, json, sys, wave
from pathlib import Path
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.llm.multimodal import configured_gemini_multimodal
from app.llm.base import ProviderError
from app.ingestion.vision_parser import analyze_image_file
from app.ingestion.audio_parser import transcribe_audio_recording
async def main():
    out=ROOT/'phase7-evidence'; media=out/'test-media'; media.mkdir(exist_ok=True)
    image=Image.new('RGB',(640,320),'white'); draw=ImageDraw.Draw(image); draw.text((30,30),'PHASE 7 AUTHORED TEST IMAGE. Revenue: 10',fill='black'); draw.rectangle((50,100,150,270),fill='black'); image.save(media/'vision.png')
    audio=media/'speech.wav'
    if not audio.exists():
        with wave.open(str(audio),'wb') as wav: wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b'\x00\x00'*8000)
    results={'gemini_credential_present':bool(settings.GEMINI_API_KEY),'embedding_credential_present':bool(settings.OPENAI_API_KEY),'audio_fixture':'Authored TTS if supplied; otherwise 0.5-second silence, no speaker accuracy claim','calls':[]}
    if settings.GEMINI_API_KEY:
        for modality,fn,path in [('vision',analyze_image_file,media/'vision.png'),('audio',transcribe_audio_recording,audio)]:
            try:
                result=await fn(str(path))
                meta=result.get('metadata',{})
                results['calls'].append({'modality':modality,'status':result.get('status'),'chunks':len(result.get('chunks',[])),'provider':meta.get('provider'),'model':meta.get('model'),'error_code':meta.get('error_code'),'metadata_keys':sorted(meta),'provider_request_id_present':bool(meta.get('provider_request_id')),'payload_sha256':hashlib.sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest()})
            except Exception as exc:
                results['calls'].append({'modality':modality,'status':'FAILED','exception_type':type(exc).__name__,'code':getattr(exc,'code',None)})
    (out/'provider-smoke.json').write_text(json.dumps(results,indent=2),encoding='utf-8'); print(json.dumps(results,indent=2))
if __name__=='__main__':asyncio.run(main())
