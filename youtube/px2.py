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


def drive_overview(tok):
    """Alle Dateien im Hauptordner und in den Unterordnern auflisten (zur Kontrolle)."""
    root = os.environ["DRIVE_FOLDER_ID"]
    lines = []
    for f in px.drive_list(tok, root):
        lines.append(f"/{f['name']} ({f['mimeType']}, {round(int(f.get('size', 0) or 0) / 1e6, 1)} MB)")
        if f["mimeType"] == "application/vnd.google-apps.folder":
            for g in px.drive_list(tok, f["id"]):
                lines.append(f"/{f['name']}/{g['name']} ({g['mimeType']}, "
                             f"{round(int(g.get('size', 0) or 0) / 1e6, 1)} MB)")
    for l in lines:
        px.log("Drive: " + l)
    return lines


def sichtung():
    tok = px.token()
    drive_overview(tok)
    sub = {f["name"].lower(): f["id"] for f in px.drive_list(tok, os.environ["DRIVE_FOLDER_ID"])
           if f["mimeType"] == "application/vnd.google-apps.folder"}
    OUT.mkdir(parents=True, exist_ok=True)
    old = {}
    if (OUT / "index.json").exists():  # schon gesichtete Clips nicht erneut laden
        prev = json.loads((OUT / "index.json").read_text())
        old = {c["id"]: c for c in prev.get("clips", [])}
        old.update({"music:" + m["name"]: m for m in prev.get("music", [])})
    idx = {"date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M"),
           "clips": [], "music": []}
    for c in sorted(px.drive_list(tok, sub["clips"]), key=lambda f: f["name"].lower()):
        if not (c["name"].lower().endswith(px.VIDEO_EXT) or c.get("mimeType", "").startswith("video/")):
            continue
        if c["id"] in old and (OUT / old[c["id"]]["sheet"]).exists():
            idx["clips"].append(old[c["id"]])
            continue
        src = "clip" + (pathlib.Path(c["name"]).suffix.lower() if c["name"].lower().endswith(px.VIDEO_EXT) else ".mp4")
        px.drive_download(tok, c["id"], src)
        info = probe(src)
        sheet = OUT / f"{safe(c['name'])}.jpg"
        n = 6 if info["seconds"] <= 20 else min(12, int(info["seconds"] // 3))
        info["frames_at"] = contact_sheet(src, info["seconds"], sheet, n)
        info.update({"name": c["name"], "id": c["id"], "sheet": sheet.name,
                     "mb": round(int(c.get("size", 0)) / 1e6, 1)})
        idx["clips"].append(info)
        px.log(f"Clip: {c['name']} {info['seconds']} s {info['width']}x{info['height']} GPS={info['gps']}")
        os.remove(src)
    for m in px.drive_list(tok, sub.get("musik", "")) if "musik" in sub else []:
        if not m["name"].lower().endswith(px.AUDIO_EXT):
            continue
        if "music:" + m["name"] in old:
            idx["music"].append(old["music:" + m["name"]])
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
    if seg.get("sharpen"):
        f += ",unsharp=5:5:0.8:5:5:0.0"
    if seg.get("card"):  # grosse Story-Texttafel oben, fuer die Dauer der Einstellung
        f += "," + ",".join(overlay_text(seg["card"], 0.15, dur - 0.15))
    label = seg.get("label")
    if label:
        label = re.sub(r"[^\u0000-\uFFFF]|[\u2600-\u27BF\uFE0F]", "", label).strip()
        pathlib.Path(f"lab{i}.txt").write_text(label, encoding="utf-8")
        f += (f",drawtext=fontfile={FONT}:textfile=lab{i}.txt:fontcolor=white:fontsize=44:"
              "x=(w-text_w)/2:y=h*0.64:shadowcolor=black@0.7:shadowx=2:shadowy=2:"
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
            hits = [k for k in clips if name.lower() in k.lower()]
            if not hits:
                sys.exit(f"Clip nicht gefunden: {name}")
            seg["clip"] = name = hits[0]
        if name not in files:
            fn = f"in{len(files)}" + (pathlib.Path(name).suffix.lower() if name.lower().endswith(px.VIDEO_EXT) else ".mp4")
            px.drive_download(tok, clips[name]["id"], fn)
            files[name], srcdur[name] = fn, px.probe_duration(fn)
    music = None
    if job.get("music") and job["music"] in songs:
        music = "music" + pathlib.Path(job["music"]).suffix.lower()
        px.drive_download(tok, songs[job["music"]]["id"], music)
    elif job.get("music") and (MUSIK / job["music"]).exists():
        music = str(MUSIK / job["music"])
        lic = json.loads((MUSIK / "lizenzen.json").read_text()).get(job["music"], {})
        if lic.get("attribution") and lic["attribution"] not in job.get("description", ""):
            job["description"] = job.get("description", "") + "\n\n🎵 Music:\n" + lic["attribution"]
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
    # Ort und Aufnahmedatum: aus dem Auftrag oder automatisch aus den GPS-Daten der Clips
    loc, rec = job.get("location"), job.get("recorded")
    try:
        idx = json.loads((OUT / "index.json").read_text())
        meta = {c["name"]: c for c in idx.get("clips", [])}
        for seg in plan:
            m = meta.get(seg["clip"], {})
            if not loc and m.get("gps"):
                loc = px.parse_iso6709(m["gps"])
            if not rec and m.get("created"):
                rec = m["created"]
    except Exception:
        pass
    if isinstance(loc, dict):
        loc = (loc["lat"], loc["lng"])
    tok = px.token()
    title = job["title"]
    # Titel: 1-2 Hashtags am Ende (Land + #shorts), Beschreibung: 3-6 passende, wichtigste zuerst
    for h in job.get("title_hashtags", []):
        if h.lower() not in title.lower() and len(title) + len(h) + 1 <= 100:
            title = title.replace(" #shorts", "") + f" {h}" + (" #shorts" if "#shorts" in title else "")
    v = px.upload(tok, "short.mp4", title[:100], job.get("description", ""),
                  job.get("tags", []), os.environ.get("PRIVACY", "private"), loc, rec, job.get("place"))
    url = f"https://youtu.be/{v['id']}"
    px.log(f"Hochgeladen: {url} (Status: {v['status']['privacyStatus']}, Ort: {loc})")
    for pl in job.get("playlists", []):
        px.add_to_playlist(tok, v["id"], pl)
    return {"ok": True, "mode": "montage", "url": url, "title": job["title"],
            "seconds": round(total, 1), "privacy": v["status"]["privacyStatus"]}


def yt_get(tok, path, params):
    import requests
    r = requests.get(f"https://www.googleapis.com/youtube/v3/{path}", params=params,
                     headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    r.raise_for_status()
    return r.json()


def stats():
    """Alle Videos des Kanals mit Aufrufen, Likes, Kommentaren; dazu Analytics (Wiedergabedauer)."""
    import requests
    tok = px.token()
    ch = yt_get(tok, "channels", {"part": "snippet,statistics,contentDetails", "mine": "true"})["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while True:
        p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if page:
            p["pageToken"] = page
        j = yt_get(tok, "playlistItems", p)
        ids += [it["contentDetails"]["videoId"] for it in j.get("items", [])]
        page = j.get("nextPageToken")
        if not page:
            break
    vids = []
    for k in range(0, len(ids), 50):
        j = yt_get(tok, "videos", {"part": "snippet,statistics,contentDetails,status",
                                   "id": ",".join(ids[k:k + 50])})
        for v in j.get("items", []):
            st = v.get("statistics", {})
            vids.append({"id": v["id"], "title": v["snippet"]["title"],
                         "published": v["snippet"].get("publishedAt", ""),
                         "duration": v["contentDetails"].get("duration", ""),
                         "privacy": v["status"].get("privacyStatus", ""),
                         "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                         "comments": int(st.get("commentCount", 0))})
    # Analytics: Wiedergabedauer je Video (Daten kommen mit 1-2 Tagen Verzoegerung)
    ana = {}
    try:
        end = datetime.date.today().isoformat()
        r = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", params={
            "ids": "channel==MINE", "startDate": "2020-01-01", "endDate": end,
            "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained",
            "dimensions": "video", "sort": "-views", "maxResults": 200},
            headers={"Authorization": f"Bearer {tok}"}, timeout=60)
        r.raise_for_status()
        j = r.json()
        cols = [h["name"] for h in j.get("columnHeaders", [])]
        for row in j.get("rows", []) or []:
            d = dict(zip(cols, row))
            ana[d["video"]] = d
    except Exception as e:
        px.log(f"Hinweis: Analytics nicht verfuegbar ({e})")
    for v in vids:
        a = ana.get(v["id"])
        if a:
            v.update({"avg_view_seconds": a.get("averageViewDuration"),
                      "avg_view_percent": round(float(a.get("averageViewPercentage", 0)), 1),
                      "minutes_watched": a.get("estimatedMinutesWatched"),
                      "subs_gained": a.get("subscribersGained")})
    out = {"time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "channel": {"title": ch["snippet"]["title"],
                       "subscribers": int(ch["statistics"].get("subscriberCount", 0)),
                       "views": int(ch["statistics"].get("viewCount", 0)),
                       "videos": int(ch["statistics"].get("videoCount", 0))},
           "videos": sorted(vids, key=lambda v: v["published"], reverse=True)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    (OUT.parent / "stats.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for v in out["videos"]:
        px.log(f"{v['published'][:10]} {v['views']:>6} Aufrufe {v['likes']:>3} Likes "
               f"{v.get('avg_view_percent', '-')}% | {v['title'][:60]} ({v['privacy']})")
    return {"ok": True, "mode": "stats", "channel": out["channel"]}


MUSIK = pathlib.Path(os.environ.get("MUSIK_DIR", "../youtube/musik"))
ATTRIB = ('"{title}" Kevin MacLeod (incompetech.com)\n'
          "Licensed under Creative Commons: By Attribution 4.0 License\n"
          "http://creativecommons.org/licenses/by/4.0/")


def musik(job):
    """Laedt passende CC-BY-Titel von incompetech.com ins Repo (youtube/musik) und misst das Tempo."""
    import requests
    base = "https://incompetech.com/music/royalty-free/"
    MUSIK.mkdir(parents=True, exist_ok=True)
    r = requests.get(base + "pieces.json", timeout=60, headers={"User-Agent": "px-media/1.0"})
    r.raise_for_status()
    pieces = r.json()
    if isinstance(pieces, dict):
        pieces = next((v for v in pieces.values() if isinstance(v, list)), [])
    keys = sorted({k for p in pieces[:50] for k in p})
    px.log(f"Katalog: {len(pieces)} Titel, Felder: {keys}")
    want = [w.lower() for w in job.get("want", ["epic", "cinematic", "action", "intense", "driving",
                                                  "dramatic", "bright", "uplifting", "suspense"])]
    def txt(p):
        return " ".join(str(p.get(k, "")) for k in p if any(x in k.lower() for x in
                        ("genre", "feel", "instrument", "description", "title"))).lower()
    def fname(p):
        return next((p[k] for k in p if "file" in k.lower() and str(p[k]).lower().endswith(".mp3")), None)
    scored = []
    for p in pieces:
        f = fname(p)
        if not f:
            continue
        t = txt(p)
        score = sum(t.count(w) for w in want)
        if score:
            scored.append((score, p, f))
    scored.sort(key=lambda x: -x[0])
    titles = [t.lower() for t in job.get("titles", [])]
    if titles:  # gezielte Auswahl nach Titel
        scored = [x for x in scored if any(t in str(x[1].get("title", x[2])).lower() for t in titles)] or scored
    lic = json.loads((MUSIK / "lizenzen.json").read_text()) if (MUSIK / "lizenzen.json").exists() else {}
    got = 0
    for score, p, f in scored:
        if got >= int(job.get("count", 15)):
            break
        if f in lic:
            continue
        rr = requests.get(base + "mp3-royaltyfree/" + requests.utils.quote(f), timeout=120,
                          headers={"User-Agent": "px-media/1.0"})
        if rr.status_code != 200 or len(rr.content) < 100000:
            px.log(f"Uebersprungen: {f} ({rr.status_code})")
            continue
        (MUSIK / f).write_bytes(rr.content)
        title = p.get("title") or pathlib.Path(f).stem
        info = {"title": title, "file": f, "seconds": round(px.probe_duration(str(MUSIK / f)), 1),
                "bpm": tempo(str(MUSIK / f)), "score": score,
                "tags": {k: p[k] for k in p if any(x in k.lower() for x in ("genre", "feel"))},
                "attribution": ATTRIB.format(title=title)}
        lic[f] = info
        got += 1
        px.log(f"Musik geladen: {title} ({info['seconds']:.0f} s, ca. {info['bpm']} BPM) {info['tags']}")
    (MUSIK / "lizenzen.json").write_text(json.dumps(lic, indent=1, ensure_ascii=False))
    return {"ok": True, "mode": "musik", "neu": got, "gesamt": len(lic)}


def passthrough(job):
    """Clip 1:1 hochladen. Hochformat: Originaldatei unveraendert. Querformat: nur auf 9:16
    zuschneiden (Mitte), Ton unveraendert uebernehmen."""
    tok = px.token()
    sub = {f["name"].lower(): f["id"] for f in px.drive_list(tok, os.environ["DRIVE_FOLDER_ID"])
           if f["mimeType"] == "application/vnd.google-apps.folder"}
    clips = {c["name"]: c for c in px.drive_list(tok, sub["clips"])}
    name = job["clip"]
    if name not in clips:
        hits = [k for k in clips if name.lower() in k.lower()]
        if not hits:
            sys.exit(f"Clip nicht gefunden: {name}")
        name = hits[0]
    src = "src" + (pathlib.Path(name).suffix.lower() or ".mp4")
    px.drive_download(tok, clips[name]["id"], src)
    info = probe(src)
    out = src
    if info["width"] > info["height"]:
        out = "short.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf",
                        "crop=ih*9/16:ih,scale=1080:1920,setsar=1", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "18", "-c:a", "copy", "-movflags", "+faststart", out], check=True)
        px.log(f"Querformat {info['width']}x{info['height']} -> 9:16 zugeschnitten (Ton unveraendert)")
    else:
        px.log(f"Hochformat {info['width']}x{info['height']}: Originaldatei unveraendert")
    tok = px.token()
    v = px.upload(tok, out, job["title"], job.get("description", ""), job.get("tags", []),
                  os.environ.get("PRIVACY", job.get("privacy", "private")),
                  synthetic=job.get("synthetic", False), category=job.get("category", "19"),
                  publish_at=job.get("publish_at"))
    url = f"https://youtu.be/{v['id']}"
    st = v["status"]
    px.log(f"Hochgeladen: {url} (Status: {st['privacyStatus']}, geplant: {st.get('publishAt', '-')}, "
           f"KI: {st.get('containsSyntheticMedia')})")
    for pl in job.get("playlists", []):
        px.add_to_playlist(tok, v["id"], pl)
    return {"ok": True, "mode": "passthrough", "url": url, "title": job["title"],
            "privacy": st["privacyStatus"], "publishAt": st.get("publishAt")}


def update(job):
    """Titel/Beschreibung/Tags eines vorhandenen Videos aendern."""
    import requests
    tok = px.token()
    v = yt_get(tok, "videos", {"part": "snippet", "id": job["video"]})["items"][0]
    sn = v["snippet"]
    body = {"id": job["video"], "snippet": {
        "title": job.get("title", sn["title"])[:100],
        "description": job.get("description", sn.get("description", ""))[:4900],
        "tags": job.get("tags", sn.get("tags", [])),
        "categoryId": job.get("category", sn.get("categoryId", "19"))}}
    r = requests.put("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet"},
                     headers={"Authorization": f"Bearer {tok}"}, json=body, timeout=60)
    if r.status_code != 200:
        sys.exit(f"Aenderung fehlgeschlagen ({r.status_code}): {r.text[:300]}")
    px.log(f"Geaendert: {job['video']} -> {body['snippet']['title']}")
    return {"ok": True, "mode": "update", "video": job["video"], "title": body["snippet"]["title"]}


def main():
    job = json.loads(pathlib.Path(os.environ.get("RUN_FILE", "../youtube/run.json")).read_text())
    mode = job.get("mode")
    if mode == "sichtung":
        res = sichtung()
    elif mode == "stats":
        res = stats()
    elif mode == "musik":
        res = musik(job)
    elif mode == "passthrough":
        res = passthrough(job)
    elif mode == "update":
        res = update(job)
    else:
        res = montage(job)
    res["time"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    rf = os.environ.get("RESULT_FILE")
    if rf:
        pathlib.Path(rf).write_text(json.dumps(res, indent=1, ensure_ascii=False))
    px.log(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
