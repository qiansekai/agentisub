# -*- coding: utf-8 -*-
"""fetch_netease_lyrics.py — 批量抓取网易云歌词入库到 state/lyrics.json。

用法:
  python fetch_netease_lyrics.py          # 用内置 id 映射批量抓取
输出:
  D:/Kita-Tools/Media/agentisub/state/lyrics.json
  { "songs": [ {"id":"05","netease_id":2033878955,"title":"...","lines":["...","..."]} ] }
"""
import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://music.163.com/", "Content-Type": "application/x-www-form-urlencoded"}

# 摸底结果：曲目 -> 网易云 song id（exact 匹配）
NETEASE_MAP = {
    "01": 2137413653,   # 描き続けた君へ (色彩)
    "02": 2137412927,   # ディメンション (色彩)
    "03": 2137412928,   # 暮れなずむ約束 (色彩)
    "04": 2610967298,   # システムズコア (单曲)
    "05": 2033878955,   # そして白に還る
    "06": 2082329207,   # ラピスのお人形
    "07": 2137413649,   # グレイスケイル (色彩)
    "08": 1907751316,   # 物語りのワルツ (創生)
    "09": 2137413650,   # 此処に棘と死を (色彩)
    "10": 1907752041,   # いろはに咲きて (創生)
    "11": 1907752045,   # ヰ世界の宝石譚 (創生)
    "12": 1907751320,   # シリウスの心臓 (創生)
    "13": 2664123870,   # 異世界転調リクヱスト (魔女ぷらす)
    "13b": 2711500027,  # ぼくらの逃避行 (魔女ぷらす2)
    "14": 2163665131,   # new world (feat. ヰ世界情緒)
    "16": 2637081794,   # アンビバレント
    "17": 2137413655,   # ANGELIC (色彩)
    "18": 2600429498,   # シェイク (内緒のピアス/星界)
    "19": 2623889384,   # 眠りゆく芽吹き
    "20": 1907751324,   # ARCADIA (創生)
    "21": 2040000970,   # かたちなきもの
    "22": 2686295178,   # みらいのかたち
    "ED": 2709724605,   # ETERNAL
    # 15 Capullo: 网易云无收录（跳过）
}

def lyric(song_id):
    # GET + lv/tv/rv 三参数: lv=原词 tv=翻译 rv=音译(罗马音), 需 Cookie 头
    url = "https://music.163.com/api/song/lyric?id=%s&lv=1&tv=1&rv=1" % song_id
    req = urllib.request.Request(url)
    req.add_header("Referer", "https://music.163.com")
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Cookie", "appver=1.0.0; os=pc")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def parse_lrc(text):
    """LRC 文本 -> 纯歌词行列表（去时间戳、去空行、去元信息）"""
    import re
    lines = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # 去时间戳标记
        ln = re.sub(r"\[\d{1,2}:\d{2}([.:]\d{1,3})?\]", "", ln).strip()
        ln = re.sub(r"<\d{1,2}:\d{2}([.:]\d{1,3})?>", "", ln).strip()
        # 去元信息行
        if not ln:
            continue
        if re.match(r"^(作词|作曲|编曲|作詞|作曲|編曲|制作人|製作|歌手|歌名|专辑|專輯)\s*[:：]", ln):
            continue
        if ln.startswith(("作词", "作曲", "编曲", "作詞", "編曲", "制作", "製作")):
            continue
        lines.append(ln)
    return lines

def parse_lrc_ts(text):
    """LRC 文本 -> [(t, text)] 带时间戳（原文/译文/罗马音共用）"""
    import re
    out = []
    for m in re.finditer(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]([^\[]*)", text or ""):
        mm, ss, ms, txt = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4).strip()
        if txt and not re.match(r"^(作词|作曲|编曲|作詞|作曲|編曲|制作|製作)", txt):
            t = mm * 60 + ss + (int(ms.ljust(3, "0")) / 1000 if ms else 0)
            out.append((t, txt))
    return out

def align_aux(ja_ts, aux_ts, tol=1.5):
    """把辅助歌词(译文/罗马音)按时间戳对齐到原文行: 返回与 ja 行数等长的列表(无则空串)"""
    res = []
    for t, _ in ja_ts:
        best = ""
        bd = tol
        for t2, txt in aux_ts:
            d = abs(t2 - t)
            if d < bd:
                bd = d
                best = txt
        res.append(best)
    return res

songs_meta = json.load(open(r"D:\Kita-Tools\Media\agentisub\state\songs.json", encoding="utf-8"))["songs"]

out = []
for s in songs_meta:
    nid = NETEASE_MAP.get(s["id"])
    if not nid:
        print("%s | %s | SKIP (无网易云收录)" % (s["id"], s["title"]))
        continue
    try:
        lr = lyric(nid)
        lrc_text = (lr.get("lrc") or {}).get("lyric") or ""
        tlyric_text = (lr.get("tlyric") or {}).get("lyric") or ""
        roma_text = (lr.get("romalrc") or {}).get("lyric") or ""
        lines = parse_lrc(lrc_text)
        ja_ts = parse_lrc_ts(lrc_text)
        lines_zh = align_aux(ja_ts, parse_lrc_ts(tlyric_text))
        lines_roma = align_aux(ja_ts, parse_lrc_ts(roma_text))
        out.append({"id": s["id"], "netease_id": nid, "title": s["title"],
                    "lines": lines, "lines_zh": lines_zh, "lines_roma": lines_roma})
        nzh = sum(1 for x in lines_zh if x)
        nroma = sum(1 for x in lines_roma if x)
        print("%s | %s | OK %d 行 (译文 %d, 罗马音 %d)" % (s["id"], s["title"], len(lines), nzh, nroma))
    except Exception as e:
        print("%s | %s | ERR %s" % (s["id"], s["title"], e))

with open(r"D:\Kita-Tools\Media\agentisub\state\lyrics.json", "w", encoding="utf-8") as f:
    json.dump({"songs": out}, f, ensure_ascii=False, indent=1)
print("wrote state/lyrics.json: %d songs" % len(out))
