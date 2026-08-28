# -*- coding: utf-8 -*-
"""gen_segments.py — 生成演出环节结构 state/segments.json。

输入: state/blocks.jsonl + state/songs.json + 硬编码的演出事实(context.md 3.x)
输出: state/segments.json
  {"segments":[{"type":"intro|mc|song|interval|ed","t0":..,"t1":..,"label":..,
                "song_id":..,"green":..,"yellow":..,"red":..,"outfit":..,"guest":..,"encore":bool}]}
"""
import json

ROOT = r"D:\Kita-Tools\Media\agentisub"

blocks = []
for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
    ln = ln.strip()
    if ln:
        blocks.append(json.loads(ln))

songs = json.load(open(ROOT + r"\state\songs.json", encoding="utf-8"))["songs"]

# ---- 衣装/嘉宾/安可 标注（context.md 3.2/3.3/3.4）----
SONG_META = {
    "05":  {"outfit": "开场白"},
    "09":  {"outfit": "黑礼服"},
    "13":  {"outfit": "白黄 Margaret Sol", "guest": "VALIS"},
    "13b": {"outfit": "白黄 Margaret Sol", "guest": "VALIS"},
    "14":  {"guest": "Aiobahn"},
    "15":  {"outfit": "黑 Margaret Luna", "no_official": True},
    "16":  {"outfit": "黑 Margaret Luna"},
    "17":  {"outfit": "Edelweiss 白裙"},
    "18":  {"guest": "星界"},
    "21":  {"outfit": "Sunflower 安可", "encore": True},
    "22":  {"outfit": "Sunflower 安可", "encore": True},
    "ED":  {"outfit": "片尾"},
}

# ---- 歌曲段 ----
segments = []
for s in songs:
    seg = {"type": "song", "t0": s["t0"], "t1": s["t1"], "song_id": s["id"],
           "title": s["title"], "green": s["green"], "yellow": s["yellow"], "red": s["red"]}
    m = SONG_META.get(s["id"], {})
    if m.get("outfit"):
        seg["outfit"] = m["outfit"]
    if m.get("guest"):
        seg["guest"] = m["guest"]
    if m.get("encore"):
        seg["encore"] = True
    if m.get("no_official"):
        seg["no_official"] = True
    segments.append(seg)

# ---- MC 段：talk 块按 90s 间隔聚类 ----
talks = sorted([b for b in blocks if b["kind"] == "talk"], key=lambda b: b["start"])
mc_segments = []
cur = [talks[0]]
for i in range(1, len(talks)):
    if talks[i]["start"] - talks[i - 1]["end"] > 90:
        mc_segments.append(cur)
        cur = []
    cur.append(talks[i])
mc_segments.append(cur)

for mc in mc_segments:
    t0 = mc[0]["start"]
    t1 = mc[-1]["end"]
    g = sum(1 for b in mc if b["confidence"] == "green")
    y = sum(1 for b in mc if b["confidence"] == "yellow")
    r = sum(1 for b in mc if b["confidence"] == "red")
    segments.append({"type": "mc", "t0": t0, "t1": t1, "label": "MC 环节",
                     "blocks": len(mc), "green": g, "yellow": y, "red": r})

# ---- 开场前（真·待机: 等待入场, 5002s 起开场演唱 01 描き続けた君へ）----
segments.append({"type": "intro", "t0": 0, "t1": 5002.0, "label": "开场前（等待入场）"})

# ---- 幕间影像：>120s 的空档 ----
covered = sorted(segments, key=lambda x: x["t0"])
gaps = []
for i in range(1, len(covered)):
    gap0 = covered[i - 1]["t1"]
    gap1 = covered[i]["t0"]
    if gap1 - gap0 > 120:
        gaps.append((gap0, gap1))
for g0, g1 in gaps:
    # 9800-9933 是幕间影像（context: 16/17 之间）；11779-12015 是安可前影像
    if 9700 < g0 < 10000:
        label = "幕间影像（衣装切换）"
    elif 11500 < g0 < 12000:
        label = "幕间影像（安可前）"
    else:
        label = "幕间影像"
    segments.append({"type": "interval", "t0": g0, "t1": g1, "label": label})

segments.sort(key=lambda x: x["t0"])
# 四舍五入
for s in segments:
    s["t0"] = round(s["t0"], 1)
    s["t1"] = round(s["t1"], 1)

with open(ROOT + r"\state\segments.json", "w", encoding="utf-8") as f:
    json.dump({"segments": segments}, f, ensure_ascii=False, indent=1)

print("segments: %d" % len(segments))
for s in segments:
    icon = {"intro": "⏸", "mc": "🎤", "song": "🎵", "interval": "🎬", "ed": "🔚"}.get(s["type"], "•")
    extra = ""
    if s.get("outfit"):
        extra += " 👗" + s["outfit"]
    if s.get("guest"):
        extra += " 🤝" + s["guest"]
    if s.get("encore"):
        extra += " 🎉安可"
    name = s.get("title") or s.get("label") or s["type"]
    print("  %s %s [%s-%s]%s" % (icon, name, s["t0"], s["t1"], extra))
