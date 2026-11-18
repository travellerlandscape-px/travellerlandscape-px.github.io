#!/usr/bin/env python3
"""P-X Travel, Teil 2: Sichtung und Montage.

MODE=sichtung: laedt alle Clips und Musiktitel aus Drive, zieht Standbilder je Clip
  (Uebersichtsblatt) und misst Laenge, Aufloesung, GPS und Musik-Tempo.
  Ergebnis: youtube/sichtung/index.json und youtube/sichtung/*.jpg
MODE=montage: schneidet einen Short aus mehreren Clips nach Plan in run.json
  und laedt ihn hoch.
"""
import json, os, pathlib, re, subprocess, sys, datetime
import numpy as np
import px  # Funktionen aus px.py (Anmeldung, Drive, Upload)

OUT = pathlib.Path(os.environ.get("SICHTUNG_DIR", "../youtube/sichtung"))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", pathlib.Path(name).stem)[:60]


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                          "-show_streams", path], capture_output=True, text=True).stdout
    j = json.loads(out or "{}")
    fmt = j.get("format", {})
    tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    w, h = v.get("width", 0), v.get("height", 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    fr = v.get("avg_frame_rate", "0/1").split("/")
    fps = round(float(fr[0]) / float(fr[1]), 2) if len(fr) == 2 and float(fr[1]) else 0
    gps = tags.get("com.apple.quicktime.location.iso6709") or tags.get("location") or ""
    return {"seconds": round(float(fmt.get("duration", 0) or 0), 2), "width": w, "height": h,
            "fps": fps, "gps": gps, "created": tags.get("creation_time", ""),
            "device": tags.get("com.apple.quicktime.model", "") or tags.get("encoder", "")}


def contact_sheet(path, dur, dest, n=6):
    times = [dur * (i + 0.5) / n for i in range(n)]
    frames = []
    for i, t in enumerate(times):
        f = f"f{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path,
                        "-frames:v", "1", "-vf",
                        f"scale=-2:360,drawtext=fontfile={FONT}:text='{t:.1f}s':x=8:y=8:"
                        "fontsize=26:fontcolor=white:box=1:boxcolor=black@0.6", f], check=False)
        if os.path.exists(f):
            frames.append(f)
    if not frames:
        return []
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for f in frames:
        cmd += ["-i", f]
    if len(frames) > 1:
        fc = "".join(f"[{i}:v]" for i in range(len(frames))) + f"hstack=inputs={len(frames)}"
    else:
        fc = "[0:v]null"
    cmd += ["-filter_complex", fc, "-q:v", "5", str(dest)]
    subprocess.run(cmd, check=True)
    for f in frames:
        os.remove(f)
    return [round(t, 1) for t in times]


def tempo(path):
    """Grobe Tempo-Schaetzung (BPM) ueber die Energie-Huellkurve."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-t", "90", "-ac", "1",
                          "-ar", "11025", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if len(x) < 11025 * 5:
        return None
    hop = 256
    frames = len(x) // hop
    env = np.sqrt(np.mean(x[:frames * hop].reshape(frames, hop) ** 2, axis=1))
    onset = np.maximum(0, np.diff(env))
    onset -= onset.mean()
    ac = np.correlate(onset, onset, mode="full")[len(onset) - 1:]
    fps = 11025 / hop
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 70)  # 70-180 BPM
    lag = lo + int(np.argmax(ac[lo:hi]))
    return round(60 * fps / lag, 1)


def sichtung():
    tok = px.token()
    sub = {f["name"].lower(): f["id"] for f in px.drive_list(tok, os.environ["DRIVE_FOLDER_ID"])
           if f["mimeType"] == "application/vnd.google-apps.folder"}
    OUT.mkdir(parents=True, exist_ok=True)
    idx = {"date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M"),
           "clips": [], "music": []}
    for c in sorted(px.drive_list(tok, sub["clips"]), key=lambda f: f["name"].lower()):
        if not c["name"].lower().endswith(px.VIDEO_EXT):
            continue
        src = "clip" + pathlib.Path(c["name"]).suffix.lower()
        px.drive_download(tok, c["id"], src)
        info = probe(src)
        sheet = OUT / f"{safe(c['name'])}.jpg"
        info["frames_at"] = contact_sheet(src, info["seconds"], sheet)
        info.update({"name": c["name"], "id": c["id"], "sheet": sheet.name,
                     "mb": round(int(c.get("size", 0)) / 1e6, 1)})
        idx["clips"].append(info)
        px.log(f"Clip: {c['name']} {info['seconds']} s {info['width']}x{info['height']} GPS={info['gps']}")
        os.remove(src)
    for m in px.drive_list(tok, sub.get("musik", "")) if "musik" in sub else []:
        if not m["name"].lower().endswith(px.AUDIO_EXT):
            continue
        src = "music" + pathlib.Path(m["name"]).suffix.lower()
        px.drive_download(tok, m["id"], src)
        info = {"name": m["name"], "seconds": px.probe_duration(src), "bpm": tempo(src)}
        idx["music"].append(info)
        px.log(f"Musik: {m['name']} {info['seconds']:.0f} s, ca. {info['bpm']} BPM")
        os.remove(src)
    (OUT / "index.json").write_text(json.dumps(idx, indent=1, ensure_ascii=False))
    return {"ok": True, "mode": "sichtung", "clips": len(idx["clips"]), "music": len(idx["music"])}


def segment_filter(i, seg, src_seconds):
    start = max(0.0, min(float(seg.get("start", 0)), max(0.0, src_seconds - 0.5)))
    dur = float(seg["dur"])
    speed = float(seg.get("speed", 1.0))
    take = min(dur * speed, src_seconds - start)
    speed = take / dur
    z0, z1 = seg.get("zoom", [1.0, 1.1] if i % 2 == 0 else [1.15, 1.03])
    z = f"({z0}+({z1}-{z0})*t/{dur:.2f})"
    f = (f"[{i}:v]trim={start:.3f}:{start + take:.3f},setpts=(PTS-STARTPTS)/{speed:.4f},"
         "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
         f"scale=w='1080*{z}':h='1920*{z}':eval=frame,crop=1080:1920,fps=30,"
         "eq=contrast=1.1:saturation=1.25:brightness=0.01,vignette=PI/5,"
         f"trim=0:{dur:.3f},setpts=PTS-STARTPTS")
    label = seg.get("label")
    if label:
        pathlib.Path(f"lab{i}.txt").write_text(label, encoding="utf-8")
        f += (f",drawtext=fontfile={FONT}:textfile=lab{i}.txt:fontcolor=white:fontsize=44:"
              "x=(w-text_w)/2:y=h*0.80:shadowcolor=black@0.7:shadowx=2:shadowy=2:"
              f"alpha='min(1,t/0.3)*min(1,({dur:.2f}-t)/0.3)'")
    return f + f",format=yuv420p[s{i}]"


def overlay_text(text, t0, t1, y=300):
    lines = px.wrap(re.sub(r"[^\u0000-￿]|[☀-➿️]", "", text).strip()).split("\n")
    out, lh = [], 86
    out.append(f"drawbox=x=60:y={y - 30}:w=960:h={len(lines) * lh + 40}:color=black@0.35:t=fill:"
               f"enable='between(t,{t0:.2f},{t1:.2f})'")
    for j, line in enumerate(lines):
        fn = f"ov{abs(hash((text, j)))}.txt"
        pathlib.Path(fn).write_text(line, encoding="utf-8")
        out.append(f"drawtext=fontfile={FONT}:textfile={fn}:fontcolor=white:fontsize=60:"
                   f"x=(w-text_w)/2:y={y + j * lh}:shadowcolor=black@0.6:shadowx=2:shadowy=2:"
                   f"enable='between(t,{t0:.2f},{t1:.2f})'")
    return out


def montage(job):
    tok = px.token()
    sub = {f["name"].lower(): f["id"] for f in px.drive_list(tok, os.environ["DRIVE_FOLDER_ID"])
           if f["mimeType"] == "application/vnd.google-apps.folder"}
    clips = {c["name"]: c for c in px.drive_list(tok, sub["clips"])}
    songs = {m["name"]: m for m in px.drive_list(tok, sub["musik"])} if "musik" in sub else {}
    plan = job["plan"]
    files, srcdur = {}, {}
    for seg in plan:
        name = seg["clip"]
        if name not in clips:
            sys.exit(f"Clip nicht gefunden: {name}")
        if name not in files:
            fn = f"in{len(files)}" + pathlib.Path(name).suffix.lower()
            px.drive_download(tok, clips[name]["id"], fn)
            files[name], srcdur[name] = fn, px.probe_duration(fn)
    music = None
    if job.get("music") and job["music"] in songs:
        music = "music" + pathlib.Path(job["music"]).suffix.lower()
        px.drive_download(tok, songs[job["music"]]["id"], music)
    xd = float(job.get("transition", 0.3))
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for seg in plan:
        cmd += ["-i", files[seg["clip"]]]
    if music:
        cmd += ["-ss", str(job.get("music_start", 0)), "-i", music]
    parts = [segment_filter(i, s, srcdur[s["clip"]]) for i, s in enumerate(plan)]
    last, t = "s0", float(plan[0]["dur"])
    trans = job.get("transitions", ["fade", "smoothleft", "zoomin", "slideup", "circleopen", "fadeblack"])
    for i in range(1, len(plan)):
        parts.append(f"[{last}][s{i}]xfade=transition={trans[i % len(trans)]}:duration={xd}:"
                     f"offset={t - xd:.3f}[x{i}]")
        last, t = f"x{i}", t + float(plan[i]["dur"]) - xd
    total = t
    ov = []
    if job.get("hook"):
        ov += overlay_text(job["hook"], 0.2, min(3.0, total))
    if job.get("cta"):
        ov += overlay_text(job["cta"], max(0, total - 3.0), total - 0.1)
    graph = ";".join(parts)
    if ov:
        graph += f";[{last}]" + ",".join(ov) + "[vout]"
        last = "vout"
    cmd += ["-filter_complex", graph, "-map", f"[{last}]", "-t", f"{total:.2f}"]
    if music:
        cmd += ["-map", f"{len(plan)}:a:0", "-af",
                f"afade=t=in:d=0.4,afade=t=out:st={total - 1.8:.2f}:d=1.8",
                "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-movflags", "+faststart", "short.mp4"]
    subprocess.run(cmd, check=True)
    px.log(f"Montage gerendert: {total:.1f} s, {os.path.getsize('short.mp4') / 1e6:.1f} MB")
    tok = px.token()
    v = px.upload(tok, "short.mp4", job["title"][:100], job.get("description", ""),
                  job.get("tags", []), os.environ.get("PRIVACY", "private"))
    url = f"https://youtu.be/{v['id']}"
    px.log(f"Hochgeladen: {url} (Status: {v['status']['privacyStatus']})")
    return {"ok": True, "mode": "montage", "url": url, "title": job["title"],
            "seconds": round(total, 1), "privacy": v["status"]["privacyStatus"]}


def main():
    job = json.loads(pathlib.Path(os.environ.get("RUN_FILE", "../youtube/run.json")).read_text())
    mode = job.get("mode")
    res = sichtung() if mode == "sichtung" else montage(job)
    res["time"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    rf = os.environ.get("RESULT_FILE")
    if rf:
        pathlib.Path(rf).write_text(json.dumps(res, indent=1, ensure_ascii=False))
    px.log(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
