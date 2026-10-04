"""Caption a real UI recording without changing its route, values or playback rate."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path):
    return json.loads(subprocess.check_output([shutil.which('ffprobe'), '-v', 'error', '-show_entries',
        'format=duration:stream=width,height,r_frame_rate', '-of', 'json', str(path)], text=True))


def strip(path, text, font, height):
    im = Image.new('RGB', (1280, height), '#244A3D')
    draw = ImageDraw.Draw(im)
    draw.text((16, 4), text, font=ImageFont.truetype(str(font), 21 if height > 32 else 19), fill='white')
    im.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--run-export', type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    work = root / 'output/4C/.build/media/cold-caption'; work.mkdir(parents=True, exist_ok=True)
    font = root / 'output/4C/.build/fonts/SourceHanSansSC-Regular.otf'
    exported = json.loads(args.run_export.read_text())
    assert exported['state']['status'] == 'COMPLETED' and exported['summary']['visited_count'] == 1 and exported['summary']['returned']
    assert [a['action'] for a in exported['execution_audit']['records']] == ['create']
    strip(work/'identity.png', '实际软件录屏 · 自动化操作 · LOCAL_2D_SIM · 20倍仿真 · 非实飞', font, 32)
    sections = [(0,25,'同一任务：0℃完成3点，−20℃完成1点；两者均返回（完整软件预演）'),
        (25,42,'运行 −20℃案例：仿真位置、耗能与巡检点数均由后端推进'),
        (42,53,'完成第1点后：下一点与返程预算不足，系统自动转为返程'),
        (53,73,'确实到达基地后：查看完成1/3、已返回与结束原因'),
        (73,90,'复查决策、操作记录，并导出原始档案；未使用人工取消模拟返航')]
    for i,(_,_,text) in enumerate(sections): strip(work/f'section-{i}.png',text,font,40)
    inputs = ['-ss','1','-i',str(args.raw),'-loop','1','-i',str(work/'identity.png')]
    for i in range(len(sections)): inputs += ['-loop','1','-i',str(work/f'section-{i}.png')]
    filters = ['[0:v]scale=1152:648,pad=1280:720:64:32:color=0xF7F9F7[v0]', '[v0][1:v]overlay=0:0[v1]']
    for i,(start,end,_) in enumerate(sections):
        filters.append(f"[v{i+1}][{i+2}:v]overlay=0:680:enable='gte(t,{start})*lt(t,{end})'[v{i+2}]")
    final = root / 'output/4C/media/寒域智航_90秒_实际运行备用录屏.mp4'
    subprocess.run([shutil.which('ffmpeg'),'-hide_banner','-loglevel','error','-y',*inputs,'-filter_complex',';'.join(filters),
        '-map',f'[v{len(sections)+1}]','-an','-t','90','-r','25','-c:v','libx264','-preset','veryfast','-crf','20',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(final)],check=True)
    actual_duration=float(probe(final)['format']['duration']);assert abs(actual_duration-90)<.1
    dist=root/'learn/competition/web/dist'
    provenance={'identity':'actual local software UI recording; automated browser operation', 'date':'2026-10-04',
        'core_version':exported['metadata']['core_version'],'data_source':'LOCAL_2D_SIM','run_id':exported['state']['id'],
        'run_export_path':str(args.run_export.relative_to(root)),'run_export_sha256':sha(args.run_export),
        'raw_recording_private_path':str(args.raw.relative_to(root)),'raw_recording_sha256':sha(args.raw),
        'raw_duration_s':float(probe(args.raw)['format']['duration']),
        'editing':{'trim_start_s':1,'duration_s':90,'playback_rate':1,'simulation_speedup':20,'source_video_pixels':[1440,810],
            'delivered_video_pixels':[1280,720],'ui_scale_pixels':[1152,648],
            'ui_padding_pixels':[64,32],'caption_padding':'Separate top/bottom bands; no UI values or routes are covered or redrawn',
            'sections':[{'start_s':a,'end_s':b,'caption':c} for a,b,c in sections],'no_generated_motion':True},
        'delivered_video':final.name,'delivered_video_sha256':sha(final),'duration_s':actual_duration,
        'summary':exported['summary'],'web_bundle_hashes':{str(p.relative_to(dist)):sha(p) for p in sorted(dist.rglob('*')) if p.is_file()},
        'not_a_human_rehearsal':True,'not_real_drone_flight':True,'cancellation_used':False}
    (root/'output/4C/media/recording-provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2))
    print(json.dumps({'video':str(final),'duration_s':actual_duration,'run_id':provenance['run_id']}))


if __name__ == '__main__': main()
