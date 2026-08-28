# Agentisub

**人机协作的字幕质量控制工作台**（human + agent subtitle QC workbench）。

把 AI 产出的字幕（含置信度）可视化，让**人实时看视频挑问题、打标记**，标记回流给 agent 定点修复（重对齐、重译、听写、文本核对），人看 diff 与置信度变化，逐步收敛到"全绿"。取名致敬打轴神器 Aegisub（Agent + Aegisub）。

![stack](https://img.shields.io/badge/Go-stdlib%20http-00ADD8) ![frontend](https://img.shields.io/badge/Vue3-Vuetify3-42b883) ![agent](https://img.shields.io/badge/agent-Python%20whisper%20%2B%20librosa-3776AB)

## 核心工作流

```
人看视频/时间轴 → 发现"轴不准/翻译差/需重听…" → 打标记（可多类型、可二次编辑）
        ↓
agent 接标记 → 定点修复（重对齐 / 重译 / 听写 / 文本核对）→ 回写块
        ↓
人看 diff（可逐条回滚）→ 置信度变化（绿/黄/红）→ 收敛到全绿 → 导出 SRT/ASS
```

## 特性

- **三色置信度**：绿（已确认）/ 黄（待校对）/ 红（听写稿），一眼定位问题区
- **标记生命周期**：待处理 / 已完成 / 已驳回三态队列，类型多选、二次编辑、reply 记录
- **自主打轴**：官方歌词 LRC 时间戳 + DTW 映射（live↔studio 对齐）自动修正/生成块时间轴
- **DTW 曲线图层**：时间轴叠加 live↔studio 映射线（台阶 = live 删段/插段），播放头金点跟随
- **三语歌词面板**：原文 / 罗马音 / 译文，跟随播放聚焦滚动，点击行跳转
- **演出结构导航**：环节列表（歌曲/MC/幕间/安可）带时间段，一键跳段
- **字幕加删改**：＋块 / 删除（可撤销）/ 拖边改轴 / 拆合块 / 平移，全程历史可回滚
- **字幕叠加播放**：视频上实时显示当前块双语，A-B 循环、0.5-2x 变速、边界试听
- **导出**：SRT / ASS（双语样式），可选仅绿块

## 架构

```
server/main.go        Go stdlib http 服务（端口 8720）：块/标记/补丁/歌词/DTW/媒体 Range 流
web/src/              Vue3 + Vuetify3 前端：时间轴 Canvas、块面板、歌词面板、标记队列
exec/                 Python 工具链（agent 侧能力，独立命令行）：
  retime.py           曲级歌词提示 ASR 重对齐 → patches
  relisten.py         多 pass ASR 交叉重听
  retranslate.py      三段式重译（Translate→Reflect→Adaptation）
  autotime.py         自主打轴：LRC + DTW 映射批量修正/补块
  dtw_align.py        chroma + DTW 映射（live ↔ 录音室参考音源）
  dtw_anchor.py       锚点分段 DTW（live 大改编曲目）
  align_lyrics_live.py 歌词行对齐 live 时间轴
  diagnose_blocks.py  块数据质量诊断（重复/时间压缩）
  …（其余脚本见 exec/）
```

数据目录（`-root` 参数指向的项目目录）：

```
state/blocks.jsonl   字幕块（单一数据源，服务端 5s 自动 git 提交）
state/tags.json      标记队列
state/songs.json     曲目
state/lyrics.json    歌词（原文/译文/罗马音）
state/lyrics_live.json  歌词 live 时间轴对齐版
state/dtw/*.json     DTW 映射（媒体文件不入库）
media/video.mp4      视频（Range 流，支持轻量代理）
```

## 快速开始

```bash
# 1. 构建前端
cd web-src && npm install && npm run build
# 2. 构建服务（单二进制，内嵌 dist）
cd ../server && go build -o agentisub.exe main.go
# 3. 运行（-root 指向数据项目目录）
./agentisub.exe -root /path/to/your/project
# 打开 http://127.0.0.1:8720/
```

## 注意事项

- **数据版权**：仓库只含代码框架；字幕/歌词/媒体数据属各内容方版权，请自行准备，勿上传到公开仓库。
- **exec 工具路径**：工具脚本顶部含作者本机路径常量（`ROOT` / `WAV` 等，形如 `D:\Kita-Tools\...`），fork 后按需修改。
- **代理视频**：打轴用 720p 低码率代理可显著降低磁盘 IO（`ffmpeg -c:v h264_nvenc -b:v 2500k -vf scale=-2:720`）。
- **AI 依赖**：exec 工具链需 faster-whisper / librosa / pykakasi 等（见各脚本 import）。

## License

MIT
