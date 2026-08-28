# -*- coding: utf-8 -*-
"""retranslate.py — M2 翻译差标记修复: 三段式重译工作包(Translate→Reflect→Adaptation)。

用法:
  python retranslate.py --block 15-014            # 生成三段式工作包(打印+存 state/retranslate_pkg.json)
  python retranslate.py --block 15-014 --apply zh.txt   # 读 agent 终稿文件, 生成 patches 并回写 /api/patches

工作包内容: 块 + 前后各3块上下文 + 术语表(context.md 5.3) + 用户批注(来自该块 tags 的 note)
agent(harness 对话中的我)按包执行三段式, 终稿写入 zh.txt, 然后 --apply 回写。
"""
import argparse
import json
import re
import sys
import urllib.request

ROOT = r"D:\Kita-Tools\Media\agentisub"
API = "http://127.0.0.1:8720"

def load_blocks():
    blocks = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            blocks.append(json.loads(ln))
    return blocks

def load_tags():
    try:
        d = json.load(open(ROOT + r"\state\tags.json", encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []

def load_glossary():
    """从 context.md 提取 5.3 曲名对照 之后的术语文本。"""
    try:
        txt = open(ROOT + r"\context\context.md", encoding="utf-8").read()
        m = re.search(r"### 5\.3 曲名对照.*?(?=\n## )", txt, re.S)
        return m.group(0).strip() if m else ""
    except Exception:
        return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True)
    ap.add_argument("--apply")
    args = ap.parse_args()

    blocks = load_blocks()
    by_id = {b["id"]: b for b in blocks}
    b = by_id.get(args.block)
    if not b:
        print("block not found: %s" % args.block)
        sys.exit(1)

    if args.apply:
        zh = open(args.apply, encoding="utf-8").read().strip()
        patch = [{
            "id": "P-RETR-%s" % b["id"],
            "block_id": b["id"],
            "tag_id": "",
            "reply": "三段式重译(Translate→Reflect→Adaptation)完成",
            "changes": {"zh": zh},
        }]
        print(json.dumps(patch, ensure_ascii=False, indent=1))
        req = urllib.request.Request(API + "/api/patches", data=json.dumps(patch).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as r:
            print("applied: " + r.read().decode())
        return

    # 上下文: 前后各 3 块
    idx = blocks.index(b)
    ctx = blocks[max(0, idx - 3):idx + 4]

    # 用户批注: 该块 tags 的 note
    tags = load_tags()
    notes = [t.get("note", "") for t in tags if t.get("block_id") == b["id"]]

    pkg = {
        "block_id": b["id"],
        "ja": b["ja"],
        "zh_current": b["zh"],
        "context": [{"id": x["id"], "ja": x["ja"], "zh": x["zh"]} for x in ctx],
        "user_notes": notes,
        "glossary": load_glossary(),
        "stages": {
            "translate": "带上下文窗口+术语表+用户批注, 初译 ja->zh (贴合演出语境, 忠实原意)",
            "reflect": "自审初译: 挑出直译生硬/术语不一致/漏译处, 列问题清单",
            "adaptation": "按问题清单改写, 输出终稿; 用户批注为最高优先级约束",
        },
    }
    out_path = ROOT + r"\state\retranslate_pkg.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pkg, f, ensure_ascii=False, indent=1)
    print(json.dumps(pkg, ensure_ascii=False, indent=1))
    print("\nwrote %s" % out_path)

if __name__ == "__main__":
    main()
