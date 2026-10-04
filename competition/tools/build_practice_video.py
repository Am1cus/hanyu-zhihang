"""Create an explicitly synthetic narration practice video from final slide PNGs.

Requires macOS say (Tingting), ffmpeg/ffprobe and Pillow. This is a practice aid,
never evidence of human rehearsal or an official student defence recording.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def run(args):
    subprocess.run([str(x) for x in args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(ffprobe, path):
    return float(subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True))


def caption(path, text, font):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGBA", (1280, 32), (36, 74, 61, 240))
    draw = ImageDraw.Draw(im)
    draw.text((18, 4), text, font=ImageFont.truetype(str(font), 23), fill="white")
    im.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--demo", type=Path, required=True, help="Actual 90-second UI recording")
    parser.add_argument("--audio-only", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    presentation = root / "output/4C/presentation"
    work = root / "output/4C/.build/media/voice-150"
    output = root / "output/4C/media"
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    talk_path = presentation / "talk.json"
    talk = json.loads(talk_path.read_text(encoding="utf-8"))
    assert len(talk["slides"]) == 12 and sum(s["seconds"] for s in talk["slides"]) == 540
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe or not shutil.which("say"):
        raise RuntimeError("Need macOS say plus ffmpeg and ffprobe")
    font = root / "output/4C/.build/fonts/SourceHanSansSC-Regular.otf"
    caption(work / "practice-label.png", "合成旁白练习版 · LOCAL_2D_SIM · 不代表学生真人演练", font)
    metrics = []
    for i, slide in enumerate(talk["slides"], 1):
        prefix = work / f"slide-{i:02d}"
        text = prefix.with_suffix(".txt")
        aiff = prefix.with_suffix(".aiff")
        previous = text.read_text(encoding="utf-8") if text.exists() else None
        text.write_text(slide["script"], encoding="utf-8")
        if previous != slide["script"] or not aiff.exists():
            run(["say", "-v", "Tingting", "-r", "150", "-f", text, "-o", aiff])
        raw_seconds = duration(ffprobe, aiff)
        # Fit within assigned slide time; explicitly report any audio speed change.
        speed = max(1.0, raw_seconds / (slide["seconds"] - 1))
        if speed > 2:
            raise ValueError("Script is too long for the assigned slide")
        wav = prefix.with_suffix(".wav")
        run([ffmpeg, "-hide_banner", "-y", "-i", aiff, "-af", f"atempo={speed},apad", "-t", slide["seconds"], "-ar", "48000", "-ac", "2", wav])
        metrics.append({"slide": i, "title": slide["title"], "assigned_seconds": slide["seconds"],
                        "raw_synthetic_speech_seconds": raw_seconds, "audio_speed_factor": speed})
        if args.audio_only:
            continue
        segment = prefix.with_suffix(".mp4")
        if i == 7:
            visual = ["-stream_loop", "-1", "-i", args.demo]
        else:
            visual = ["-loop", "1", "-framerate", "24", "-i", presentation / "slides" / f"slide-{i:02d}.png"]
        run([ffmpeg, "-hide_banner", "-y", *visual, "-i", wav, "-loop", "1", "-i", work / "practice-label.png",
             "-filter_complex", "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=white[v];[v][2:v]overlay=0:0[out]",
             "-map", "[out]", "-map", "1:a", "-t", slide["seconds"], "-r", "24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", segment])
        print(f"Rendered practice slide {i}/12", flush=True)
    report = {"type": "synthetic_narration_practice_only", "voice": "macOS Tingting", "voice_rate": 150, "duration_seconds": 540,
              "talk_sha256": hashlib.sha256(talk_path.read_bytes()).hexdigest(), "slides": metrics,
              "demo_path": str(args.demo), "demo_sha256": hashlib.sha256(args.demo.read_bytes()).hexdigest(),
              "slide_png_sha256": {f"slide-{i:02d}.png": hashlib.sha256((presentation / "slides" / f"slide-{i:02d}.png").read_bytes()).hexdigest() for i in range(1, 13)}}
    if not args.audio_only:
        listing = work / "concat.txt"
        listing.write_text("\n".join(f"file '{(work / f'slide-{i:02d}.mp4').as_posix()}'" for i in range(1, 13)), encoding="utf-8")
        final = output / "寒域智航_9分钟_合成旁白练习版.mp4"
        run([ffmpeg, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", "-movflags", "+faststart", final])
        report["file"] = final.name
        report["video_sha256"] = hashlib.sha256(final.read_bytes()).hexdigest()
        report["actual_duration_seconds"] = duration(ffprobe, final)
        assert abs(report["actual_duration_seconds"] - 540) < .2
    (output / "practice-video-provenance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "slides"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
