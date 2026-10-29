"""Trim an actual recording and label it; never synthesize execution frames."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

from competition.v2.runtime import execution_source_hashes

PROJECT=Path(__file__).resolve().parents[3]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--log',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--recorded-ui',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    target=out/'寒域智航_90秒实际运行录屏.mp4'
    if target.exists():raise ValueError('Do not overwrite an existing delivered recording')
    log=args.log.read_text(encoding='utf-8')
    recording=json.loads(log.split('### Result\n',1)[1].split('\n',1)[0])
    archive=json.loads(args.archive.read_text(encoding='utf-8'))
    assert recording['result_sha256']==archive['result_sha256']
    assert archive['metadata']['source_sha256']==execution_source_hashes()
    assert sha(args.recorded_ui)==sha(PROJECT/'competition/v2/presentation/live.html')
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(args.raw)]))
    started=datetime.fromisoformat(probe['format']['tags']['creation_time'].replace('Z','+00:00')).timestamp()
    trim=recording['began_unix_ms']/1000-started
    assert 0<=trim<float(probe['format']['duration'])-90
    assert next(m['wall_s'] for m in recording['marks'] if m['event']=='exported')<89
    assets=out.parent/'video-labels';assets.mkdir(exist_ok=True)
    texts={'identity':'实际运行录屏 · 20倍仿真 · 非真实飞行',
           'title':'寒域智航',
           'phase1':'先看温度\n\n同一任务\n比较预算',
           'phase2':'途中有变化\n\n加入禁入区\n重新安排',
           'phase3':'回来再核对\n\n实际到基地\n导出记录'}
    for name,text in texts.items():(assets/(name+'.txt')).write_text(text,encoding='utf-8')
    inputs=[]
    for phase in ('phase1','phase2','phase3'):
        panel=Image.new('RGBA',(1920,1080),(0,0,0,0));draw=ImageDraw.Draw(panel)
        for text,x,y,size in ((texts['identity'],260,2,18),(texts['title'],26,90,32),(texts[phase],26,200,24)):
            draw.multiline_text((x,y),text,font=ImageFont.truetype(str(args.font),size),fill='#164e44',spacing=14)
        label_path=assets/(phase+'.png');panel.save(label_path);inputs+=['-loop','1','-i',str(label_path)]
    filters=['[0:v]pad=1920:1080:240:30:color=0xf3f6f5[base]',
             "[base][1:v]overlay=enable='lt(t,11)'[one]",
             "[one][2:v]overlay=enable='between(t,11,72)'[two]",
             "[two][3:v]overlay=enable='gte(t,72)'[final]"]
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(trim),'-i',str(args.raw),*inputs,
                    '-t','90','-filter_complex',';'.join(filters),'-map','[final]','-r','25','-c:v','libx264','-crf','20',
                    '-pix_fmt','yuv420p','-movflags','+faststart','-an',str(target)],check=True)
    delivered=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(target)]))
    duration=float(delivered['format']['duration']);assert abs(duration-90)<.05
    metadata={'verified_on':'2026-10-28','identity':recording['identity'],'video':target.name,
              'duration_s':duration,'pixels':[1920,1080],'codec':'h264','pixel_format':'yuv420p',
              'simulation_speedup':20,'video_playback_rate':1,'audio':'none',
              'editing':'trim waiting before/after actual 90-second operation; pad sides and add identity/chapter labels; no trajectory or result edits',
              'source_video_sha256':sha(args.raw),'trim_start_s':trim,'video_sha256':sha(target),
              'ui_sha256':sha(args.recorded_ui),'execution_source_sha256':archive['metadata']['source_sha256'],
              'archive_sha256':sha(args.archive),'run_id':archive['state']['id'],
              'result_sha256':archive['result_sha256'],'operation_marks':recording['marks']}
    (out/'video-manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False))


if __name__=='__main__':main()
