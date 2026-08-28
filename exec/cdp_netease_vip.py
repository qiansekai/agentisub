# -*- coding: utf-8 -*-
"""cdp_netease_vip.py — 通过 CDP 在已登录的网易云页面内调 player/url API 拿 VIP 歌曲 URL。

用法: python cdp_netease_vip.py [输出json路径]
流程: 9222 列出标签页 -> 找 music.163.com 页面 -> websocket 连接 -> 页面内 fetch(自动带Cookie) -> 拿 URL
"""
import json
import sys
import urllib.request
import websocket

TARGETS = [
    ("01", 2137413653, "描き続けた君へ"),
    ("02", 2137412927, "ディメンション"),
    ("03", 2137412928, "暮れなずむ約束"),
    ("04", 2610967298, "システムズコア"),
]

def list_tabs():
    with urllib.request.urlopen("http://localhost:9222/json/list", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else None

    tabs = list_tabs()
    target = None
    for t in tabs:
        if t.get("type") == "page" and "music.163.com" in t.get("url", ""):
            target = t
            break
    if not target:
        print("no music.163.com page found")
        sys.exit(1)
    print("target tab: %s | %s" % (target["id"][:12], target["title"]))

    ws = websocket.create_connection(
        "ws://localhost:9222/devtools/page/%s" % target["id"],
        suppress_origin=True,
        timeout=30,
    )

    ids = [t[1] for t in TARGETS]
    expr = """
    (async () => {
      const ids = %s;
      const out = [];
      for (const id of ids) {
        try {
          const r = await fetch('/api/song/enhance/player/url', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'ids=[' + id + ']&br=320000',
            credentials: 'same-origin'
          });
          const j = await r.json();
          const d = (j.data || [])[0] || {};
          out.push({id: id, code: d.code, fee: d.fee, br: d.br, size: d.size, url: d.url || null});
        } catch (e) {
          out.push({id: id, error: String(e)});
        }
      }
      return JSON.stringify(out);
    })()
    """ % json.dumps(ids)

    ws.send(json.dumps({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {"expression": expr, "returnByValue": True, "awaitPromise": True},
    }))
    # 收消息直到拿到 id=1 的响应
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == 1:
            break
    ws.close()

    result = resp.get("result", {}).get("result", {})
    value = result.get("value")
    if not value:
        print("evaluate failed: %s" % json.dumps(resp, ensure_ascii=False)[:500])
        sys.exit(1)

    songs = json.loads(value)
    out_map = {}
    for s, meta in zip(songs, TARGETS):
        sid = meta[0]
        print("%s %s | code=%s fee=%s | %s" % (sid, meta[2], s.get("code"), s.get("fee"),
                                               (s.get("url") or "NO URL")[:80] if s.get("url") else "NO URL"))
        if s.get("url"):
            out_map[sid] = s["url"]

    if out_map and out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_map, f, ensure_ascii=False, indent=1)
        print("urls saved -> %s" % out_path)

if __name__ == "__main__":
    main()
