# AGENTS.md — 给 AI 编码 agent 的项目指南

> Agentisub 是"Agent 优先"的字幕 QC 工作台：这份文件就是给 agent 的说明书（README 是给人的）。
> 修改任何代码前先读这里，遵守约定，避免踩坑。

## 一句话定位

人看视频打标记 → agent 接标记定点修复字幕 → 三色置信度收敛到全绿 → 导出 SRT/ASS。

## 架构总览

```
server/main.go   Go stdlib http（无框架，端口 8720，-root flag 指向数据项目目录）
web-src/         Vue 3 + Vuetify 3（无 JSX；组件显式导入）
exec/            36 个 Python/PowerShell 工具脚本（agent 能力，命令行独立运行）
```

- **数据单一源**：`{root}/state/blocks.jsonl`（每行一个块 JSON）。Go 启动时全量加载到内存 store，变更写回文件，5 秒后自动 `git commit`（数据自带版本历史）。
- **媒体**：`{root}/media/video.mp4` 由 `/media/video` Range 流；路径从 `state/meta.json` 的 `media.video` 读取。
- **音频分析**：16k mono WAV（波形/频谱预计算产物 `state/*.bin`）+ 录音室参考音源（`state/dtw/*.mp3`，DTW 映射用，不入库）。

## 关键约定

### 后端（Go）
- 只用 stdlib（net/http + encoding/json + os/exec），禁止引入第三方依赖。
- 路由全部在 `main()` 注册，按资源分组注释（块/标记/补丁/歌词/DTW/媒体）。
- 块/标记变更必须：加锁 → 改内存 → `st.dirty = true` → `st.save()` → 异步 `st.commit()`（5s 防抖）。
- 所有写操作写 History 记录（`before`/`after`），支持 revert。

### 前端（Vue3 + Vuetify3）
- **Vuetify 组件必须显式导入**（`main.ts` 里 `import * as components from 'vuetify/components'`）——Vite 8 tree-shaking 会丢组件，直接 `<v-btn>` 会渲染成未注册标签。
- 时间轴用 Canvas 手绘（`TimelineCanvas.vue`），数据驱动（blocks/peaks/currentTime），watch 变更调度重绘。
- API 调用集中在 `api.ts`；类型在 `types.ts`。
- 布局约定：左主区（视频行 + 时间轴 360px），视频右侧（演出结构 + 歌词面板），右侧面板 330px（块详情 + 标记队列）。

### exec 工具（Python）
- 每个脚本一个任务、命令行独立可跑（argparse 风格）。
- 头部 `ROOT` / `WAV` / `ANIMA3` 为作者本机路径常量，fork 后按需修改。
- 依赖：faster-whisper / librosa / pykakasi / demucs（见各脚本 import，Anima3 venv 场景）。
- 修改块数据优先走 HTTP API（`POST /api/patches`、`POST /api/blocks`），不要直接改 blocks.jsonl（服务会覆盖）。

## 常见坑（血泪教训）

1. **JS `\W` 是 ASCII 语义**：会删除全部日文。日文规范化用显式标点正则。
2. **PowerShell 管道陷阱**：`Where-Object ... -in` 在本机环境偶发返回空，批量脚本用普通 foreach + `-eq`。
3. **缓存格式变更要向后兼容**：`state/lrc/*.json` 曾从数组格式改为字典格式，旧缓存导致脚本静默失败（autotime 的 create 模式曾因此输出 0）。读缓存必须兼容两种格式。
4. **CSS Grid 固定高度容器 + 大量隐式行**：行高可能被异常均分（曾出现 43 行 × 6.9px 挤扁内容）。列表场景用块流 + 容器滚动。
5. **whisper 对唱歌段不可靠**：整曲转录输出乱码（伴奏干扰）。歌词对齐走"歌词提示 ASR + difflib 字符对齐"（align_song 模式），不要用裸 ASR 重建歌词。
6. **Vuetify `v-select multiple`** 的 v-model 是数组；`title` 属性传 `v-btn` 才能作为 DOM title。
7. **`go build main.go`**（无 go.mod）或 `GO111MODULE=off`；产物需复制到项目根运行。
8. **SRT 导出必须 UTF-8 BOM**（Windows 播放器兼容）。
9. **音频接口**：网易云歌词 GET 需 `lv=1&tv=1&rv=1` + `Cookie: appver=1.0.0; os=pc`（POST + kv 参数拿不到罗马音）；VIP 音频需登录态 player/url。
10. **DTW 映射方向**：`np.interp(studio_t, studio_arr, live_arr)`；映射单调性保证 live 时间递增。

## 修改指南（改 X 要动哪些）

| 想改 | 涉及文件 |
|---|---|
| 块/标记/补丁 API | `server/main.go` + `web-src/api.ts` + 对应组件 |
| 时间轴绘制 | `web-src/components/TimelineCanvas.vue`（Canvas 手绘逻辑全在这） |
| 歌词面板 | `web-src/components/LiveLyrics.vue` + `exec/align_lyrics_live.py`（数据生成） |
| 打轴/重对齐 | `exec/autotime.py`（LRC+DTW）、`exec/retime.py`（ASR 对齐） |
| DTW 映射 | `exec/dtw_align.py` / `dtw_anchor.py` |
| 数据诊断/修复 | `exec/diagnose_blocks.py` / `fix_damaged.py` |
| 构建/部署 | `exec/build.ps1`（npm build → copy dist → go build 单二进制） |

## 验证方式（无测试框架）

1. 后端：`Invoke-RestMethod http://127.0.0.1:8720/api/...` 直测（GET 读 / POST 写 / 检查 total 变化）。
2. 前端：`npm run build`（vue-tsc 类型检查 + vite 构建）通过后浏览器刷新验证；交互用 CDP 或手工。
3. 数据脚本：先在预览模式跑（无 --apply），核对输出再写入。
4. 时间轴质量：`exec/check_block_times.py`（歌词行 vs 块时间偏差）+ `dtw_verify.py`（LRC 基准体检）。

## 数据与版权

仓库只含代码框架。字幕/歌词/媒体数据属各内容方版权，勿提交到公开仓库（`state/`、`media/` 已 gitignore）。
