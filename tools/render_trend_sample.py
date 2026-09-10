"""Render the reviewed iPhone trend draft locally; never enqueue or publish."""
import asyncio
import argparse
import math
import json
import os
import re
import subprocess
import socket
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

import edge_tts
import httpx
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from pythainlp import word_tokenize

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/google_trends/iphone17_preview"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _font_path(*candidates):
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    raise OSError("Thai font is not installed")


FONT = _font_path(
    "C:/Windows/Fonts/leelawad.ttf",
    "/usr/share/fonts/truetype/tlwg/Loma.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
)
BOLD = _font_path(
    "C:/Windows/Fonts/leelawdb.ttf",
    "/usr/share/fonts/truetype/tlwg/Loma-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf",
)
SOURCE_LABEL = "ข้อมูลจาก Apple • apple.com/iphone-17"
CATEGORY_LABEL = "ข่าวและกระแส"
BACKGROUND_IMAGE = None


def wrap_thai_lines(text, font, width=840):
    lines, current = [], ""
    for token in word_tokenize(text, engine="newmm"):
        candidate = current + token
        if font.getlength(candidate) > width and current:
            lines.append(current.strip())
            current = token
        else:
            current = candidate
        if font.getlength(current) > width:
            raise ValueError("Token too wide; reduce font size")
    if current.strip():
        lines.append(current.strip())
    return lines


def card(index, headline, hero, detail):
    if BACKGROUND_IMAGE is not None:
        im = ImageOps.fit(BACKGROUND_IMAGE, (1080, 1920), method=Image.Resampling.LANCZOS)
        im = ImageEnhance.Brightness(im).enhance(0.42)
    else:
        im = Image.new("RGB", (1080, 1920))
    draw = ImageDraw.Draw(im)
    if BACKGROUND_IMAGE is None:
        for y in range(1920):
            t = y / 1919
            draw.line((0, y, 1080, y), fill=(int(12+9*t), int(24+36*t), int(42+27*t)))
    draw.rounded_rectangle((74, 185, 1006, 265), radius=40, fill="#184d56")
    def text(value, y, size, color="#f5f2e9", bold=False):
        font = ImageFont.truetype(str(BOLD if bold else FONT), size)
        for line in wrap_thai_lines(value, font):
            draw.text((540, y), line, font=font, fill=color, anchor="mt")
            y += int(size*1.55)
        return y
    text(f"ป้าเข็มบอกต่อ  /  {CATEGORY_LABEL}", 200, 32)
    if text(headline, 375, 70, bold=True) > 670:
        raise ValueError("Headline exceeds card")
    draw.rounded_rectangle((85, 690, 995, 1225), radius=48, fill="#f3efe5")
    if text(hero, 770, 72, "#123b47", bold=True) > 1010:
        raise ValueError("Hero exceeds card")
    end = text(detail, 1025, 39, "#31525a")
    if end > 1215:
        raise ValueError("Detail exceeds card")
    text(SOURCE_LABEL, 1300, 30, "#a1c0c5")
    text("ความรู้ไอที เข้าใจง่าย", 1410, 39, "#81e2cc")
    for n in range(5):
        x = 355 + n*78
        draw.rounded_rectangle((x, 1565, x+58, 1575), radius=5, fill="#81e2cc" if n <= index else "#38525e")
    path = OUT / f"card_{index+1}.png"
    im.save(path)
    return path


def run(args):
    return subprocess.run([FFMPEG, "-hide_banner", "-y", *args], check=True, capture_output=True, text=True, timeout=240, cwd=OUT)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads((ROOT / "artifacts/google_trends/sample_scripts.json").read_text(encoding="utf-8"))["scripts"][0]
    scenes = [
        ("จอลื่นขึ้น ดูตรงไหน?", "จอลื่นขึ้น ดูตรงไหน?", "iPhone 17", "ทำความรู้จักจอและกล้อง"),
        ("ป้าเข็มชวนดู iPhone 17 จ้ะ Apple ระบุว่ารุ่นนี้มีจอ ProMotion ปรับอัตรารีเฟรชได้สูงสุดหนึ่งร้อยยี่สิบเฮิรตซ์", "จอ ProMotion", "สูงสุด 120Hz", "ปรับอัตรารีเฟรชได้"),
        ("คำว่าสูงสุดหมายถึงจอไม่ได้ทำงานที่ค่านี้ตลอดเวลานะจ๊ะ", "สูงสุด ไม่ใช่ตลอดเวลา", "ปรับได้", "อัตรารีเฟรชไม่ได้คงที่ที่ 120Hz"),
        ("ส่วนกล้องหน้าเป็น Center Stage", "อีกจุดคือกล้องหน้า", "Center Stage", "กล้องหน้าของ iPhone 17"),
        ("คุณสนใจจอหรือกล้องมากกว่ากัน? คอมเมนต์แล้วติดตามป้าเข็มไว้จ้ะ", "คุณสนใจอะไรมากกว่า?", "จอ / กล้อง", "คอมเมนต์และติดตามป้าเข็ม"),
    ]
    assert " ".join(s[0] for s in scenes) == source["voiceover_script"]
    timings, total = [], 0.0
    for i, (voice, headline, hero, detail) in enumerate(scenes):
        picture = card(i, headline, hero, detail)
        audio = OUT / f"voice_{i+1}.mp3"
        await edge_tts.Communicate(voice, "th-TH-PremwadeeNeural", rate="+20%", volume="+0%").save(str(audio))
        probe = run(["-i", str(audio), "-f", "null", "-"])
        match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
        if not match:
            raise RuntimeError("Cannot measure voice duration")
        duration = int(match[1])*3600 + int(match[2])*60 + float(match[3]) + .15
        clip = OUT / f"scene_{i+1}.mp4"
        run(["-loop", "1", "-framerate", "30", "-i", str(picture), "-i", str(audio),
             "-vf", "scale=1080:1920,setsar=1,format=yuv420p", "-af", "apad=pad_dur=0.3,volume=1.0",
             "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-threads", "2", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(clip)])
        timings.append({"scene": i+1, "start": round(total, 3), "duration": duration, "voice": voice})
        total += duration
        print(f"Scene {i+1}/5 rendered ({duration:.2f}s)", flush=True)
    playlist = OUT / "scenes.txt"
    playlist.write_text("\n".join(f"file 'scene_{i+1}.mp4'" for i in range(5)), encoding="utf-8")
    video = OUT / "iphone17_preview.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(playlist), "-c", "copy", "-movflags", "+faststart", str(video)])
    verify = run(["-i", str(video), "-af", "volumedetect", "-f", "null", "-"])
    (OUT / "verification.log").write_text(verify.stderr, encoding="utf-8")
    (OUT / "timings.json").write_text(json.dumps(timings, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "caption.txt").write_text(source["caption"] + "\n\n" + " ".join("#"+t for t in source["hashtags"]), encoding="utf-8")
    thumbs = Image.new("RGB", (1080, 384), "#102030")
    for i in range(5):
        frame = OUT / f"check_{i+1}.png"
        run(["-ss", str(timings[i]["start"] + timings[i]["duration"]/2), "-i", str(video), "-frames:v", "1", str(frame)])
        with Image.open(frame) as im:
            thumbs.paste(im.resize((216,384)), (i*216,0))
    thumbs.save(OUT / "contact_sheet.jpg")
    print(f"Complete: {video}", flush=True)


async def motion(source=None, output_dir=None):
    """Continuous TTS, timed captions and local frame animation."""
    global OUT, SOURCE_LABEL, CATEGORY_LABEL, BACKGROUND_IMAGE
    OUT = Path(output_dir) if output_dir else ROOT / "artifacts/google_trends/iphone17_motion"
    OUT.mkdir(parents=True, exist_ok=True)
    source = source or json.loads((ROOT / "artifacts/google_trends/sample_scripts.json").read_text(encoding="utf-8"))["scripts"][0]
    SOURCE_LABEL = source.get("source_label", "ข้อมูลจาก Apple • apple.com/iphone-17")
    CATEGORY_LABEL = source.get("category_label", "ข่าวและกระแส")
    BACKGROUND_IMAGE = None
    image_url = source.get("image_url", "")
    if image_url:
        parsed = urlparse(image_url)
        if parsed.scheme == "https" and parsed.hostname:
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
            if addresses and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                try:
                    response = httpx.get(image_url, timeout=20, follow_redirects=True,
                                         headers={"User-Agent": "Mozilla/5.0"})
                    response.raise_for_status()
                    if len(response.content) <= 8_000_000:
                        image_path = OUT / "source_image.jpg"
                        image_path.write_bytes(response.content)
                        with Image.open(image_path) as source_image:
                            if source_image.width >= 640 and source_image.height >= 360:
                                BACKGROUND_IMAGE = source_image.convert("RGB")
                except Exception:
                    BACKGROUND_IMAGE = None
    spoken = source["voiceover_script"]
    audio, word_file = OUT / "voice.mp3", OUT / "words.json"
    if not audio.exists() or not word_file.exists():
        words = []
        try:
            with audio.open("wb") as stream:
                async for chunk in edge_tts.Communicate(spoken, "th-TH-PremwadeeNeural", rate="+20%", volume="+0%", boundary="WordBoundary").stream():
                    if chunk["type"] == "audio":
                        stream.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append(chunk)
        except Exception:
            audio.unlink(missing_ok=True)
            if os.getenv("TTS_ALLOW_GOOGLE_FALLBACK", "false").lower() not in ("true", "1", "yes"):
                raise
            from gtts import gTTS
            gTTS(text=spoken, lang="th", slow=False).save(str(audio))
            probe = run(["-i", str(audio), "-f", "null", "-"])
            match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
            if not match:
                raise ValueError("Cannot measure fallback TTS")
            speech_duration = int(match[1])*3600 + int(match[2])*60 + float(match[3])
            for token in re.finditer(r"\S+", spoken):
                start = speech_duration * token.start() / max(1, len(spoken))
                end = speech_duration * token.end() / max(1, len(spoken))
                words.append({"type":"WordBoundary", "text":token.group(),
                              "offset":int(start*1e7), "duration":max(1, int((end-start)*1e7))})
        word_file.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
    words = json.loads(word_file.read_text(encoding="utf-8"))
    if not words:
        raise ValueError("TTS returned no word timings")
    cursor = 0
    for word in words:
        start = spoken.find(word["text"], cursor)
        if start < 0 or re.search(r"[\w]", spoken[cursor:start]):
            raise ValueError("Cached speech does not match script; remove cached audio and words together")
        word.update(char_start=start, char_end=start+len(word["text"]), start=word["offset"]/1e7, end=(word["offset"]+word["duration"])/1e7)
        cursor = word["char_end"]
    if re.search(r"[\w]", spoken[cursor:]):
        raise ValueError("Incomplete speech boundaries")
    probe = run(["-i", str(audio), "-f", "null", "-"])
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
    if not m:
        raise ValueError("Cannot measure audio")
    duration = int(m[1])*3600 + int(m[2])*60 + float(m[3]) + .2
    if words[-1]["end"] > duration:
        raise ValueError("Word timing exceeds audio")
    phrases = [s["voice"] for s in source["scenes"]] if source.get("scenes") else ["จอลื่นขึ้น", "ป้าเข็มชวน", "คำว่าสูงสุด", "ส่วนกล้องหน้า", "คุณสนใจ"]
    scene_offsets, offset = [], 0
    for phrase in phrases:
        position = spoken.index(phrase, offset)
        scene_offsets.append(position)
        offset = position+len(phrase)
    scene_chars = set(scene_offsets)
    groups, group = [], []
    for word in words:
        if group and (word["char_end"] - group[0]["char_start"] > 34 or word["char_start"] in scene_chars
                      or "?" in spoken[group[-1]["char_end"]:word["char_start"]]):
            groups.append(group)
            group = []
        group.append(word)
    if group:
        groups.append(group)
    def stamp(t):
        ms = round(t*1000)
        return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"
    cues = []
    for i, g in enumerate(groups):
        content = spoken[g[0]["char_start"]:g[-1]["char_end"]]
        cues.append(f"{i+1}\n{stamp(g[0]['start'])} --> {stamp(g[-1]['end'])}\n{content}\n")
    (OUT / "captions.srt").write_text("\n".join(cues), encoding="utf-8")
    headings = [
        ("จอลื่นขึ้น ดูตรงไหน?", "iPhone 17", "ทำความรู้จักจอและกล้อง"),
        ("จอ ProMotion", "สูงสุด 120Hz", "ปรับอัตรารีเฟรชได้"),
        ("สูงสุด ไม่ใช่ตลอดเวลา", "ปรับได้", "อัตรารีเฟรชไม่ได้คงที่ที่ 120Hz"),
        ("อีกจุดคือกล้องหน้า", "Center Stage", "กล้องหน้าของ iPhone 17"),
        ("คุณสนใจอะไรมากกว่า?", "จอ / กล้อง", "คอมเมนต์และติดตามป้าเข็ม"),
    ]
    if source.get("scenes"):
        headings = [(s["headline"],s["hero"],s["detail"]) for s in source["scenes"]]
    if len(headings) != 5:
        raise ValueError("Exactly five scenes required")
    starts = [next(w["start"] for w in words if w["char_start"] == pos) for pos in scene_offsets]
    if starts[1] > 2.2:
        raise ValueError("Opening hook exceeds two seconds")
    if duration > 14.5:
        raise ValueError("Voiceover exceeds 14.5-second pacing limit")
    starts[0] = 0
    cards = []
    for i, values in enumerate(headings):
        with Image.open(card(i, *values)) as im:
            cards.append(im.copy())
    font = ImageFont.truetype(str(BOLD), 46)
    # Pre-render subtitle states so Thai shaping is not repeated for every frame.
    subtitles = {}
    for g in groups:
        first = g[0]["char_start"]
        value = spoken[first:g[-1]["char_end"]]
        lines = wrap_thai_lines(value, font, 850)
        if len(lines) > 2:
            raise ValueError("Subtitle exceeds two lines")
        for active in [None, *g]:
            layer = Image.new("RGBA", (1080, 260))
            d = ImageDraw.Draw(layer)
            d.rounded_rectangle((65, 10, 1015, 225), radius=32, fill=(5, 16, 29, 245))
            consumed = 0
            for n, line in enumerate(lines):
                line_start = value.find(line, consumed)
                x, y = (1080-font.getlength(line))/2, 46+n*78
                if active:
                    pos = active["char_start"]-first-line_start
                    if 0 <= pos and pos+len(active["text"]) <= len(line):
                        lx = x+font.getlength(line[:pos])
                        rw = font.getlength(active["text"])
                        d.rounded_rectangle((lx-5,y-4,lx+rw+5,y+65), radius=8, fill="#177c76")
                d.text((x,y),line,font=font,fill="#ffffff",anchor="lt")
                consumed = line_start+len(line)
            subtitles[(first, active["char_start"] if active else -1)] = layer
    def background(index, t):
        fraction = max(0,min(1,(t-starts[index])/max(.1,(starts[index+1] if index<4 else duration)-starts[index])))
        scale = 1 + .025*fraction
        im = cards[index].resize((round(1080*scale),round(1920*scale)), Image.Resampling.BICUBIC)
        left, top = (im.width-1080)//2, (im.height-1920)//2
        return im.crop((left,top,left+1080,top+1920))
    output = OUT / "iphone17_motion.mp4"
    cmd = [FFMPEG,"-hide_banner","-y","-f","rawvideo","-pix_fmt","rgb24","-s","1080x1920","-r","30","-i","pipe:0","-i",str(audio),"-af","apad=pad_dur=0.3,volume=1.0","-t",str(duration),"-c:v","libx264","-preset","veryfast","-crf","20","-threads","2","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart",str(output)]
    with (OUT / "encode.log").open("w") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log, stdout=subprocess.DEVNULL)
        try:
            for frame in range(math.ceil(duration*30)):
                t = frame/30
                idx = max(i for i,s in enumerate(starts) if s <= t)
                im = background(idx,t)
                if idx and t-starts[idx] < .25:
                    im = Image.blend(background(idx-1,t),im,(t-starts[idx])/.25)
                for g in groups:
                    if g[0]["start"] <= t <= g[-1]["end"]:
                        active = next((w for w in g if w["start"] <= t <= w["end"]),None)
                        overlay = subtitles[(g[0]["char_start"],active["char_start"] if active else -1)]
                        im.paste(overlay,(0,1370),overlay)
                        break
                d = ImageDraw.Draw(im)
                d.rounded_rectangle((85,1675,995,1683),radius=4,fill="#38525e")
                d.rounded_rectangle((85,1675,85+910*t/duration,1683),radius=4,fill="#81e2cc")
                proc.stdin.write(im.tobytes())
                if frame%150 == 0:
                    print(f"Rendered {t:.0f}/{duration:.1f} seconds",flush=True)
            proc.stdin.close()
            if proc.wait(timeout=240):
                raise RuntimeError("FFmpeg encoding failed; see encode.log")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    result = run(["-i",str(output),"-af","volumedetect","-vf","blackdetect=d=0.3:pix_th=0.05","-f","null","-"])
    (OUT/"verification.log").write_text(result.stderr,encoding="utf-8")
    (OUT/"scene_timing.json").write_text(json.dumps({"duration":duration,"scene_starts":starts,"word_count":len(words)},indent=2),encoding="utf-8")
    (OUT/"caption.txt").write_text(source["caption"]+"\n\n"+" ".join("#"+h for h in source["hashtags"]),encoding="utf-8")
    sheet = Image.new("RGB",(1080,384))
    for i,s in enumerate(starts):
        point = s+.65
        p = OUT/f"check_{i+1}.png"
        run(["-ss",str(point),"-i",str(output),"-frames:v","1",str(p)])
        with Image.open(p) as im:
            sheet.paste(im.resize((216,384)),(216*i,0))
    sheet.save(OUT/"contact_sheet.jpg")
    print(f"Complete: {output}",flush=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--motion", action="store_true", help="Add timed subtitles, zoom and cross-dissolves")
    args = parser.parse_args()
    asyncio.run(motion() if args.motion else main())
