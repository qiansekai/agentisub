# Agentisub · 字幕人机协作工作台 · 规划文档

> 项目曾用名 subqc（subtitle+QC），2026-08-28 改名 **Agentisub**。名字巧思：**Agentis**（拉丁语 agēns/agentis"行动者/代理人"，英语 agent 的词源）+ Agent is（agent 就是校对者）+ 谐音希腊语 **Aegis**（αἰγίς 神盾，与致敬对象 Aegisub 同源）+ sub（字幕）。
> 项目目录：`D:\Kita-Tools\Media\agentisub\`（旧目录 subqc 已冻结，会话结束后删除）。
> **经验沉淀机制**：技术踩坑/修复经验一律追加到 `docs/EXPERIENCE.md`，每次会话收尾时检查是否漏记。开源仓库 AGENTS.md 从 EXPERIENCE.md 摘取摘要。

## 理念与未来技术展望（2026-08-29 定稿）

**核心理念（与框架无关，任何技术换代都保留）**：
1. **人机协作闭环**：人打标 → agent 修 → 三色（绿/黄/红）收敛到全绿
2. **数据分层**：官方歌词=权威文本、ASR=时间辅助、人耳=终审
3. **一切可回滚、可 diff、可追溯**

**痛点 → 未来技术映射**（详见 EXPERIENCE.md 对应条目）：

| 痛点 | 未来技术 | 评估 |
|---|---|---|
| 唱歌段转写乱码 | 唱歌专用 ASR（Qwen3-ASR 已含唱歌能力，日语数据扩展中） | 1-2 年可期 |
| 词级对齐 | 端到端歌词对齐 / ForcedAligner 唱歌支持（官方路线图） | 1-2 年可期 |
| 快嘴 rap | 上述组合仅边际改善——**物理极限，长期靠人耳** | 无质变预期 |
| 无歌词曲（Capullo） | 音频理解 LLM（Qwen3-Omni 系） | 1-3 年 |
| ~~舞台屏幕 OCR~~ | ~~视频 LLM 读现场歌词屏~~ | **❌ 已放弃：神椿 zanlive 演出无字幕（舞台无歌词屏），此路线无效** |

**架构策略**：不推翻框架，做 **Provider 抽象层**（`exec/providers.py`：transcribe/align 接口 + whisper/Qwen 实现）——未来新技术落地 = 新增一个 Provider 实现，工具链/UI/数据格式不动。

## 〇、实施进度（v3.1，2026-08-29 DTW 复活+自主打轴+数据补全+界面重构）

### 本轮新增（08-29）

**自主打轴 ✅（核心新能力）**：
- `exec/autotime.py`：LRC 官方时间戳 + DTW 映射 → 自动计算 live 时间轴，批量修正 **632 块** + 补 **193 个缺失块**（有官方歌词但无字幕块的行，标黄待校对——live 可能删段/改词需听判）
- 重复副歌按出现次序依次分配 LRC 时间戳（避免重复块挤同一时间）
- `exec/diagnose_blocks.py`：全量诊断出 9 首"时间压缩"损坏曲（迁移 bug：多块挤同一 start，13 曲 68 块最重）；autotime 修复后压缩残留从 130+ 降至 ~45（live 结构差异尾巴）
- `exec/dtw_verify.py` 时间轴体检 + `exec/check_block_times.py` 行级校验

**字幕加删改 ✅**：
- 后端 `POST /api/blocks`（新建，自动分配 id）+ `DELETE /api/blocks/{id}`（删除，可撤销）
- 前端顶栏 **＋块** 按钮（对话框：时间/类型/曲目/双语）+ 块面板 🗑 删除按钮（confirm）+ 撤销栈支持恢复删除

**标记增强 ✅**：
- 类型**多选**（v-select multiple + chips，块×类型双重循环创建）
- **二次编辑**（PUT /api/tags/{id} + 队列铅笔按钮，类型/备注可改）

**开场曲 01-04 补全 ✅（重大事实修正）**：
- 用户打标记 → 转写发现 **演出从 5002s 就开场演唱 01"描き続けた君へ"**——推翻"01-04 是待机 BGM"的公开报道口径（以实际演出为准）
- 4 首 VIP 音频 CDP 登录态获取（320kbps）→ DTW → autotime create 生成 **150 个歌词块**（双语）+ 开场 MC 口播 2 块（转写"ありがとう！…最後まで盛り上がっていきましょう"等）
- segments 修正：真待机 [0-5002] + 开场唱 01-04（每曲间有 MC 介绍）→ 43 个演出环节全部带时间段显示

**三语歌词 ✅**：
- 接口修正：`GET /api/song/lyric?id=xx&lv=1&tv=1&rv=1` + `Cookie: appver=1.0.0; os=pc` 头才能拿到 romalrc（POST+lv/kv/tv 参数不对，之前罗马音全空）
- 24 首罗马音 100% 覆盖：14 首官方完整 + 6 首官方大部分 + **3 首联网抓人工版**（06 UtaTime / 11 Genius / 20 Genius，验证了"歌词刻意读法算法猜不对、人工整理版才是正解"，如 水無月→rokugatsu）+ 04 及零星行 pykakasi 算法版（网上无公开人工源）
- `exec/align_lyrics_live.py`：歌词行对齐 live 轴（LRC→DTW 映射），`state/lyrics_live.json` 供歌词面板
- **歌词面板**（视频右侧）：三语行（原文/罗马音/译文）+ 当前播放行高亮 + 平滑聚焦居中 + 点击跳转 + 宽容窗口（歌曲前后 ±15s 不断档）

**视频低占用 ✅**：NVENC GPU 硬编（RTX 5060 Ti）转 720p 2.7Mbps 轻量代理（13GB→4.6GB，14x 速度），Go 从 meta.json 读视频路径可切换。

**界面重构 ✅**：
- 演出结构 + 歌词移入**视频右侧**（演出 290px 单列滚动 + 歌词占大头 684px），右侧面板专注块详情+标记队列
- 顶栏按钮全部靠左；三色统计移至标记面板（chip+tooltip）；演出/歌词窗格隐藏原生滚动条
- 演出窗格 grid 行异常均分（43 行×6.9px 挤扁）改块流布局修复

**M1 真人打标闭环 ✅**：用户真实打标（范围 4987-5004，多类型 retime+relisten）→ agent 转写识别开场环节 → done+reply → 触发 01-04 补全。

### ASR 模型逐个验证（08-29 白天，含环境大改造）

**环境改造 ✅**：
- 发现 torch 一直是 **CPU 版**（装 demucs 时选 CPU 源）——GPU 从未被 torch 用过
- RTX 5060 Ti（Blackwell sm_120）需 **CUDA 12.8+**：torch cu128（2.11.0）才支持
- ctranslate2 与 torch CUDA 库冲突（ct2 自带 CUDA DLL 干扰 torch cudnn 加载）→ **双 venv 分家**：
  - `Anima3 venv`：torch CPU + faster-whisper（GPU 靠 ct2 自带 CUDA）——whisper 工具链
  - `qwen-env`（`D:\Kita-Tools\Media\qwen-env`）：torch 2.11+cu128 + transformers——Qwen 全家桶
- C 盘空间危机 → 临时目录/缓存全挪 D 盘（D:\Temp、D:\huggingface）

**验证 ① whisper 切 GPU ✅**：8 个脚本 `device="cuda", compute_type="int8_float16"`，**16 倍提速**（19.0s→1.2s，文本质量与 CPU int8 完全一致）；GPU 下 faster-whisper 的 `vad_filter` 失效（返回 0 段），已关掉靠空文本跳过。

**验证 ② Qwen3-ASR-1.7B ✅**：部署成功（transformers ≥5.13 原生，`generate(**inputs)` 展开传参）。三模型对比：
| 段 | whisper | Qwen 0.6B | Qwen 1.7B |
|---|---|---|---|
| MC 说话 | **1 错（最佳）** | 3 错 | 2 错 |
| 唱歌段 | 2-3 错 | 4+ 错 | **2 错（"鳥も鳴かず風も吹かず"精确命中）** |
| 快嘴/rap | 乱码 | 乱码 | 乱码 |
**组合方案：whisper（MC）+ Qwen 1.7B（唱歌）+ 歌词对齐（权威）**。

**验证 ③ Qwen3-ForcedAligner ✅**：**支持日语**（11 语言含 Japanese），词级对齐成功（"託さ"5002.00 与转写证据吻合），时间戳稀疏（部分词零长度可插值）；`prepare_forced_aligner_inputs` + `decode_forced_alignment` 用法见 `exec/fa_test.py`。可与 DTW 行级锚点结合做词级精确对齐（卡拉 OK 基础）。

**Capullo 重听 ✅**：Qwen 1.7B 整段转写（255s/26s）作第二参考版本；**双 ASR 交叉验证 10 块升绿**（两独立模型共识），41 块保持红（两版本对照待听判）。

**50 待处理标记清零 ✅**：
- 13 曲 rap 段 **89 个 0.2-0.3s 碎块 → 33 个可读合并块**（对唱行"／"分隔，含 1 个 end<start 坏块修复）
- "没听出来"段重听确认 = U-002 MC 块已覆盖
- 开场段确认 = credit 卡画面文字（无口播），01 曲块已存在

**开场 4 曲开头漂移修复 ✅**（用户反馈"01 曲最前面没对上"触发）：
- 01 曲前 5 块 -6s（三方证据 5002 起唱）
- 02 曲前 4 块 -6s（5308.4 起唱）
- **03 曲整曲错位**：块在 5710-5775（credit 卡期间），实际唱在 5560-5650 → songs t0/t1 修正 + DTW 重跑 + 27 块重排
- 04 曲 37 块重排（5800-5933 唱段）
- **根因**：DTW 映射依赖 songs.json t0/t1，t0/t1 当初凭粗略转写定错 → 映射错 → 整曲错位。教训：**t0/t1 必须转写证据锚定**。

### 已完成（v3.0，主线缺口清零）

**M1 验收闭环 ✅**：代打 10 标记（Capullo 需重听×4/文本可疑×5/翻译差×1）→ agent 修复 10 个：whisper 局部重听交叉 + 网易云歌词核对修正 07-019（合并行拆分）与 05-017（カラー）→ Capullo 官方无音源诚实收尾（done+reply+⚠️徽标）。tags_open 10→0，diff 面板可查可回滚。

**M2 agent 修复能力 ✅**：
- `exec/retime.py`：曲级别歌词提示 ASR 重对齐（复用 Anima3 align_song prompt 模式）→ patches。**实测修复 07 曲 33 块时间轴**（历史迁移 bug：前 49 块被压缩在 0.9s 内，现已散开到正确位置 6699-6831s）
- `exec/relisten.py`：多 pass ASR 交叉（3 组 beam/prompt 组合输出候选）
- `exec/retranslate.py`：三段式重译工作包（Translate→Reflect→Adaptation + 上下文 + 术语表 + 用户批注）
- 拆/合句：后端 `POST /api/blocks/{id}/split`（按字数分配时间、子 id 继承 a/b/c）+ `POST /api/blocks/merge`，实测 07-019 拆两块无缝衔接（gap=0）
- 文本核对：网易云歌词比对（19 首入库）+ 块面板对照高亮
- 标签生命周期 UI：三态 tab（待处理/已完成/已驳回）+ reply 展示 + 驳回/重开

**工程化 ✅**：
- SRT 导出 UTF-8 BOM（Windows 播放器兼容）
- 防目录穿越：http.FileServer(http.Dir) 内置防护，已验证
- 全局撤销栈：Ctrl+Z / 顶栏撤销按钮（retime/shift 操作可逆）
- **go:embed 单二进制**：`exec/build.ps1` 一键构建，13.5MB agentisub.exe 内嵌 dist，实测移走 web/dist 后服务正常

**M3 余项 ✅**：
- A/V 偏移旋钮：波形/频谱整体平移 ±0.1s（视频音轨与 16k 波形对不齐时微调）
- 频谱交互：悬停显示时间+频率 Hz
- 多项目管理：-root flag 参数化（一个项目一个目录）

### M4 归档（维持可选，不排期）

| 模块 | 归档理由 |
|---|---|
| ~~DTW 曲线图层~~ | **已实现**（08-29：网易云录音室音源补全后复活，见下） |
| 卡拉OK 逐字预览 | 需 Qwen3-ForcedAligner-0.6B + torch（~2.5GB），重依赖，无实际需求驱动 |
| 双人校对模式 | 单人+agent 协作已覆盖需求，无第二校对者场景 |

### 已知数据问题（记录在案）

- **黄色待校对块**：193 个 autotime 补块（官方歌词文本但 live 可能删段/改词）+ Capullo 52 红块（无官方音源，听写稿维持）——人工听判后批量转绿是收敛主线。
- **压缩损坏残留**：autotime 修复后 ~45 个压缩块（13 曲 15 / 20 曲 8 / 19 曲 7 等）为 live/studio 结构差异尾巴，需听判。
- **07 曲 23 块**：已打"轴不准"标记待人工（live 段落重排）。
- **13 曲 rap 段**：16 对同 start 超短块（0.2-0.3s rap 行"Q & A""U & Me"等），自动合并会错拼，需人工听判重新切块。
- **04 システムズコア 罗马音**：算法版（pykakasi），已联网搜索 5 轮（Genius/UtaTime/kashinavi/lyricstranslate/巴哈姆特）确认无公开人工罗马音源；如日后找到可替换 `exec/web_romaji.json` + 重跑 `align_web_romaji.py`。
- **Qwen3-ASR 对比 ✅（已跑通，08-29 白天重试成功）**：正确路径是 **transformers ≥5.13 原生支持**（非旧 SDK qwen-asr 包）：`AutoProcessor.apply_transcription_request(audio=ndarray)` + `AutoModelForMultimodalLM` + **`model.generate(**inputs)` 展开传参**（直接传 BatchFeature 会报 AttributeError，5.13/5.16 均需展开）。四段对比结论：**MC 说话段 whisper 略优（1 错 vs 3 错："拳を上げて"被 Qwen 听成"戦局で覚えていて"）；唱歌段两者皆乱码（whisper 稍好）——whisper large-v3-turbo 为当前日语场景最佳选择**，Qwen3-ASR-0.6B 无优势（1.7B 版未测，CPU 更慢）。对比脚本 `exec/asr_compare.py`，结果 `state/dtw/asr_compare.json`。
- **12/18 曲 DTW 锚点**：12 曲曾疑 LRC 版本问题（实为压缩损坏，已随 autotime 修复）；18 曲锚点错位（重复副歌文本误导），曲级待听判。
- **工具链**：`exec/fix_damaged.py`（align_song 对齐+重建）、`exec/rebuild_live.py`（ASR segment，唱歌段不可靠弃用）备用。

### 自主修正记录（08-29 夜间，基线 b2ad784 可回滚）

- **R1 时间轴修复**：残留块插值 37（fix_residual）+ 重叠中点切分 676→2（fix_overlap，弃顺延方案——会连锁推出曲界）+ 01 曲尾块 6 个按转写证据修正（MC 重叠清零）。验证：全曲零倒序、零尾部出界、歌词 vs MC 重叠 0。
- **R2 MC 空白补块**：find_blanks 扫出 19 段 MC 空白 → whisper 转写创建 13 块（含片尾"異世界情緒でした。また会おうね"、开场 4 曲连唱 MC），黄色待校对；歌曲段空白转写验证为间奏/前奏（不补）。
- **R3 Qwen ASR 对比**：上游依赖不兼容，诚实收尾 + 删 whisper 幻觉块 U-009。
- **R4 文档沉淀**：EXPERIENCE.md + PLANNING.md 自主修正记录。

### 白天后续（08-29 白天）

- **标记处理**：50 待处理标记清零（13 曲 rap 段 89 碎块→33 可读合并块、2 段重听确认）+ 开场欢迎 MC 补块 U-016（双 ASR 重听"みなさーん！アニマⅢへようこそ！"）。
- **开场 4 曲开头漂移修复**（用户反馈触发）：01/02 曲开头 -6s、03 曲整曲重排（唱段 5560-5650，songs t0/t1 修正 + DTW 重跑）、04 曲重排——根因 DTW 依赖 songs t0/t1。
- **ASR 逐个验证 + 环境改造**：torch 发现为 CPU 版→装 cu128（sm_120 需 CUDA 12.8+）；ct2 与 torch CUDA 冲突→双 venv 分家（Anima3 venv: whisper GPU / qwen-env: Qwen）；whisper 切 GPU 16 倍提速；Qwen3-ASR-1.7B GPU 部署；ForcedAligner 日语词级对齐验证。
- **Capullo 重听**：Qwen 1.7B 整段转写 + 双 ASR 交叉验证 10 块升绿。
- **实时刷新**：SSE 推送（/api/events + 前端 EventSource 防抖 refreshAll）+ 静态 no-cache 头 + openTags 改 computed（修复标记队列不消失）。
- **代码审查修复**：双路审查（自审+子代理）修复 10 项（meta 竞态/split 越界/commit 竞态/路径穿越/tag ID 撞号/坏时间校验/ASS 注入/dtw 契约/资源泄漏）。
- **模型调研**：联网+HuggingFace 模型库搜索，下载实测 neosophie JA 微调版（键映射转换成功，MC 段"拳"优于原版但唱歌互有胜负）与 jaykwok Anime-hf 版（chat 报错待查）；结论维持现有组合。新候选记录：Voxtral-Mini-4B（需 vLLM）、pyannote 说话人分离（多人 MC 潜在能力）。
- **数据现状**：total 1277 块、绿 753 / 黄 480 / 红 44、tags_open 0。

### M4 DTW 复活（用网易云正常版音乐补录音室音源）

- **音源**：**23/24 首**录音室音频到手（19 首 free/VIP 混合 + 01-04 开场曲经 CDP 登录态 player/url 获取，均为 320kbps），存 `state/dtw/`（gitignore）。Capullo(15) 无网易云收录。
- **映射**：chroma+DTW 全局（23 首）+ 锚点分段（8 首改编曲：13b/19/20 中位偏差降到 <1s、16 接近、08 改善 40%）。`state/dtw/{song}.map.json` / `.anchored.json`。
- **前端图层**：`/api/dtw/{song}` + 时间轴标尺下紫色映射线（台阶=live 删段/插段）+ 播放头金点 + 顶栏 DTW 开关（歌曲段内启用）。
- **人声分离（demucs）**：已验证技术可行（htdemucs 分离 + 人声 DTW），但对 live 段落重排/数据损坏类问题无改善（问题在结构不在特征），归档。
- **时间轴体检**：dtw_verify.py 用 LRC 官方时间戳做基准，批量发现"健康曲/改编曲/损坏曲"三类。

---

> 以下为定稿 v1.0 原始设计（2026-08-28 定稿，保留作历史记录；实施中偏离处以"实施进度"章节为准）。
> 状态：**已定稿**，待用户发令开工（从 M1 启动）。实施中若发现本方案问题，先更新本文档再改代码。
> 定位：把"AI 产出的字幕"（含置信度）可视化，让人**实时调整 + 打标记**，标记回流给 agent 定点修复，形成闭环。
> 首个应用场景：Anima Ⅲ 双语字幕（1003 条，数据在 `../Anima3/`）。

## 一、目标

- 人只做两件事：**看颜色挑问题、打标记**；其余（重对齐、重译、听写、文本核对）全由 agent 接。
- 每一轮 agent 修复后，人看到 diff 与置信度变化，逐步收敛到"全绿"。
- 全程不改原始视频；SRT/ASS 只在导出时生成。

## 二、核心工作流

```
加载项目(JSON 状态) → 时间轴+波形+三色置信度 → 播放/拖动/框选
    → 打标记(类型+备注) → 导出 tags → agent 定点处理
    → 回写 JSON(带 diff 与历史) → 界面刷新(红→绿) → 人复审 → 导出 SRT/ASS
```

## 三、数据模型（草案）

```json
{
  "project": "anima3",
  "media": { "video": "...", "audio_16k": "...", "duration": 14571.3 },
  "blocks": [
    {
      "id": "b-000123",              // 稳定 id（不变）
      "start": 6152.18, "end": 6162.90,
      "kind": "lyric" | "talk",
      "song": "05",                   // 歌词所属曲目，MC 为 null
      "ja": "…", "zh": "…",
      "confidence": "green|yellow|red|gray",
      "tags": [ {"type": "retime", "note": "…", "ts": "…", "author": "user"} ],
      "history": [ {"start":..., "end":..., "zh":..., "ts":..., "actor": "agent"} ]
    }
  ],
  "songs": [ {"id":"05","t0":…,"t1":…,"title":…,"has_studio":true,"lrc":true} ],
  "dtw":  [ {"song":"05","path":[[live_t, studio_t],…],"quality":0.9} ]
}
```

设计原则：
- **块 id 稳定**，不因排序/插入变化（教训 8）。
- 所有编辑走 history，agent 修改与人手修改互不覆盖、可回滚。
- tags 是队列：`tags.json` 导出 → agent 消费 → 处理结果以 history 形式回写。

## 四、标记分类 → agent 动作映射

| 标记 | agent 动作 | 产出 |
|---|---|---|
| 🕐 轴不准 | 该段重跑提示词 ASR / DTW 重映射（有录音室参考时） | 候选时间轴+置信度 |
| 👂 需重听 | 多 pass ASR（不同 beam/prompt）交叉 | 2-3 个候选文本 |
| 🌐 翻译差 | 子代理带上下文+用户批注重译 | 新译文+理由 |
| 🎵 缺歌词 | 听写管线（无官方词的曲） | 听写稿(※标注) |
| 📝 文本可疑 | 检索官方歌词来源核对 | 来源+修正 |
| ✂️ 拆/合 | 字数规则断句/合并 | 新块结构 |
| ✅ 已确认 | 锁定，agent 跳过 | 状态置绿 |

## 五、界面组件（MVP → 迭代）

1. **主时间轴**：预生成波形（wavesurfer/peaks.js）+ 字幕块矩形，块色=置信度；拖动边缘改轴；框选范围。
2. **播放器**：本地 HTTP Range 服务播 MKV（备选：720p 代理 MP4）；A-B 循环；0.25x-2x 变速。
3. **DTW 曲线图层**：录音室↔live 映射线，改编段呈台阶状，点击跳转（依赖 DTW 数据）。
4. **对照面板**：ja / zh / ASR 原文 / 官方歌词 四栏，点击跳时间。
5. **标记面板**：快速打标按钮 + 备注输入 + 批量提交。
6. **diff 视图**：agent 改动的块高亮，显示 改前→改后，单条回滚。
7. **统计条**：红/黄/绿计数、标记队列长度、收敛进度。

## 六、技术选型（草案）

- 后端：Python FastAPI（本地 localhost，静态页 + JSON API + MKV Range 服务）；agent 通过读写 JSON 文件/HTTP 接口交互。
- 前端：原生 HTML/JS（轻依赖）+ wavesurfer.js；不引重框架。
- 视频：直接 Range 服务原 MKV（Chrome/Edge 对 H264/AAC MKV 兼容性较好）；失败则一次性转 720p 代理。
- agent 接口：`POST /jobs`（tags 队列）或约定目录文件协议；结果写回 JSON + diff 事件。

## 七、里程碑（草案）

- **M1 基础闭环**：JSON 状态导入（迁移 Anima3 现有 1003 条）→ 时间轴+波形+三色 → 拖动改轴 → 打标导出 → agent 处理一个样例标记 → diff 回显。验收：你标 10 个问题，我修 10 个，全程不碰代码。
- **M2 智能修复**：接入 DTW 重对齐（轴不准）、多 pass 重听（需重听）、子代理重译（翻译差）。
- **M3 体验**：A-B 循环、变速、快捷键、批量标记、历史回滚完善。
- **M4 扩展**：卡拉OK 逐字预览、双人校对模式、多项目管理。

## 八、风险与备选

- 浏览器播 MKV 失败 → 720p 代理文件（gyan ffmpeg 可编 libx264）。
- agent 回环延迟（分钟级）→ 批处理模式 + 状态轮询，接受非实时。
- 置信度分层不准 → DTW 与 ASR 两法交叉验证，取一致才绿。

## 九、已敲定决策（v0.2，2026-08-28）

1. **核心原则：Agent 友好 / Agent 优先**。工具不是孤立编辑器，而是"人 + agent（deepseek harness 中的我）"协作的界面：所有操作既有人用 UI，也有 agent 用的文件协议/HTTP 接口，两套入口读写同一份状态。
2. **agent 编排中心 = deepseek harness 会话**。用户在工具里打标 → 导出/同步 tags → 回到 harness 对话告诉我 → 我定点处理（联网检索、重译、重听写、重对齐）→ 结果以 patch 形式回写工具 → 用户刷新看 diff。工具内不内嵌 LLM，不自己拉模型。
3. **WebUI 形态**：本地网页（localhost），确认。
4. **视频本地处理（v0.4 修正）**：浏览器对 MKV 容器兼容性不可靠（Jellyfin 等有失败先例）→ 改为**无损 remux 出 MP4 代理**（`ffmpeg -c copy -movflags +faststart`，H.264/AAC 换容器不重编码，12GB 仅需几分钟），工具播代理文件；原 MKV 永不动。
5. **目标一步到位、执行分步走**：功能规划按完整版设计，交付按 M1→M2→M3 里程碑推进（双语面板、DTW 等都在规划内，不砍，只排序）。
6. **置信度初版规则**：ASR 锚点行=绿、插值行=黄、Capullo 听写行=红、MC 两遍交叉=绿。确认。
7. **标记粒度**：行级点击 + 时间范围框选 都做。确认。
8. **深色主题 + 中文界面**：确认。
9. **块 id（稳定编号）**：导入现有 1003 条时，每条分配永久 id（曲目+行号生成），之后无论排序/插入/删改，id 不变——保证人的手工修改与 agent 的修改不会互相覆盖、可以各自回滚。已确认采纳。
10. **DTW（录音室↔live 音频对齐）**：暂缓为可选模块（用户不熟悉，不阻塞主线）；规划中保留接口，M3 之后视需要引入。
11. **新增：项目上下文模块**。开工前先建"背景档案"：角色/世界观/wiki 链接/术语表/曲目表/歌词来源等；agent 启动字幕或翻译流程时，先读档案 + 联网检索补充背景，使翻译与听写更准确。用户可提供 wiki 网址等材料，也可由 agent 自动调研后请用户确认。

## 十、已敲定决策（续，v0.3）

- **项目上下文模块 = agent 联网调研模式**：不要求用户手工填表。开工时由 agent（我）用联网工具尽可能搜集背景（角色/世界观/wiki/术语/曲目/歌词来源/嘉宾/演出信息），整理成档案存入项目 `context/` 目录，请用户过目确认后作为后续翻译与听写的依据。
- **agent 接口 = 文件协议为主**（tags/patches JSON），HTTP API 可选加分。确认。
- **M1 验收标准**："标 10 个问题 → agent 修 10 个 → 工具内可看 diff、可回滚、红变绿，用户全程不碰代码"。确认。
- **波形**（时间轴下方声音起伏图，用于精确对位）：**预计算**——用现有 16k 音轨提前生成波形数据文件，工具打开秒加载。确认。
- **技术栈（讨论中）**：用户倾向 Go。分析见下，待最终确认。

## 十一、技术栈分析（Go vs Python）

- 工具实际由两部分组成：
  - **服务层**：静态网页、MKV Range 视频服务、状态 JSON API、任务队列（轻量、IO 型）
  - **执行层**：重对齐/重听写/重翻译/DTW 等重活（今天的全流程已验证在 Python venv 里）
- **执行层必须 Python**：faster-whisper、librosa/DTW、demucs、翻译编排脚本全在 Python 生态；Go 侧无等价物，重写不现实。
- **服务层两种方案**：
  - 方案 A（契合用户偏好）：**Go 写服务层**（单二进制、无运行时依赖、Range 服务与 JSON API 都很干净），Python 脚本做执行层，两者用**文件协议解耦**（与上一条决策天然一致）。
  - 方案 B：**纯 Python（FastAPI）**——开发最快、与服务层复用同一 venv，但产物是"python 脚本 + 依赖"，部署略重。
- 前端 HTML/JS 两种方案完全相同。
- 结论：**已敲定 混合架构（方案 A）：Go 服务层 + Python 执行层**，文件协议解耦。前端 HTML/JS 相同。

## 十一·B、git 状态管理（已敲定）

- `agentisub/` 根目录即 **git 仓库**（`media/` 进 .gitignore；state/context/web/exec/server 全部纳入）。
- 状态文件用 **JSONL（每块一行）**：git diff 可读、行级合并基本不冲突、单块回滚的天然载体。
- **提交纪律**：UI 端走"保存点"（显式保存/定时/退出时），autosave 日志兜底；agent 端每批任务一提交，提交信息带标记批次号。
- **分支用于大改动**：agent 批量操作（全量重译、DTW 重对齐等）在独立分支执行，用户 review 后合并或丢弃。
- 回滚分层：块内 `history[]`（局部快）+ git（全局安全网）。
- diff 视图直接消费 `git diff`，不重复造轮子。

## 十二、里程碑（定稿版）

**M1 基础闭环（目标：验证"标记→agent 修复→回显"全链路）**
- 项目初始化：agent 联网调研生成 `context/` 背景档案（用户确认）
- 数据迁移：现有 1003 条 → JSON 状态（稳定块 id、置信度三色、kind/song 归属）
- Go 服务层：静态 UI + MKV Range 视频服务 + 状态 JSON API
- 前端 v1：波形（预计算）+ 时间轴三色块 + 拖动改轴 + 行级/框选标记 + 标记导出
- agent 回环：tags.json → harness 对话 → patches.json 回写 → diff 高亮 + 单条回滚
- **验收**：标 10 个问题 → agent 修 10 个 → 可看 diff、可回滚、红变绿，用户全程不碰代码

**M2 智能修复模块**
- 重对齐（提示词 ASR 局部重跑；DTW 作为可选增强后置）
- 多 pass 重听写（需重听标记）
- **子代理重译（翻译差标记）——采用 VideoLingo 三段式翻译链**（见十五节）：
  1. **Translate**：带上下文窗口（前后各 3-5 块）+ 术语表 + 用户批注做初译
  2. **Reflect**：同一子代理自审——挑出直译生硬、术语不一致、漏译处，列出问题清单
  3. **Adaptation**：按问题清单改写，输出终稿 + 简短改译理由
  - 用户批注（"这里想要 xx 感觉"）作为最高优先级约束贯穿三步
- 文本核对（联网检索歌词来源）
- 自动拆/合句
- 双语面板（ja/zh 对照 + 翻译标记流程）
- **标签生命周期（借鉴 Label Studio 回环语义）**：
  - 状态机：`open（待处理）→ processing（agent 进行中）→ done（已修）→ rejected（无法自动修，需人工）`
  - 每条标签带 `reply` 字段：agent 完成后必须写"改了什么/为什么不能修/给了什么候选"，工具在标记旁展示，用户可"接受"或"驳回重试"
  - 批量提交：用户攒一批 open 标签 → 一次导出 → agent 按类型分组处理 → 逐条回填
  - 驳回（rejected）的标签进入"红色清单"，只能人工消——防止 agent 反复空转

**M3 体验完善**
- A-B 循环试听、0.25x-2x 变速、快捷键、批量标记、历史回滚完善、多项目管理

**M4 扩展（可选）**
- DTW 曲线图层（若引入录音室对齐）
- 卡拉OK 逐字预览、双人校对模式

## 十三、项目结构（草案）

```
agentisub/
├── server/            # Go 服务层（静态 UI、MP4 Range、状态 API、jobs）
├── web/               # 前端（HTML/JS/CSS，深色中文）
├── exec/              # Python 执行层（复用 ../Anima3/ 的 venv 与脚本）
│   ├── retime.py      # 局部重对齐
│   ├── relisten.py    # 多 pass 重听写
│   ├── retranslate.py # 子代理重译编排
│   └── verify_text.py # 歌词来源核对
├── state/             # 项目状态（blocks.json 唯一真源；tags/patches 队列）
├── media/             # MP4 无损 remux 代理
└── context/           # 背景档案（agent 联网调研产出）
```

## 十四、缺口补充（2026-08-28 自审 + 联网调研）

**重要修正：**
1. 视频用无损 remux MP4（见决策 4），规避 MKV 浏览器兼容风险。
2. **频谱视图**：Aegisub 打轴的核心利器（频谱比波形更能看出人声起止，尤其 live 噪音大）——预计算步骤同时生成波形+频谱数据，前端提供切换（M1 纳入预计算，M3 做交互打磨）。

**交互能力补全（对照 Aegisub 打轴工作流）：**
3. 边界试听快捷键：播放"行前 500ms / 行末 500ms / 当前行 / 选区"——打轴效率的关键（M3）。
4. 整段平移（shift 时间）：发现系统性偏移时一键平移（M1，简单且刚需）。
5. 关键帧吸附、卡拉OK 逐字模式：M3/M4 可选。

**工程健壮性补丁：**
6. 状态文件**原子写**（tmp+rename），防 agent 与用户并发写坏。
7. `schema_version` 字段 + 迁移函数（多项目/未来演进）。
8. 标签生命周期：`open → processing → done/rejected`，且 agent 每条回复都带 `reply` 字段（用户能看见"这行我做了什么/为什么没修"）。
9. 置信度带**证据字段**（来源方法+数值），UI 可解释"为什么红"。
10. 用户编辑 autosave 日志 + 全局撤销栈（超单条回滚）。
11. A/V 偏移旋钮（视频音轨与 16k 波形间允许全局偏移微调）。
12. 拆句/合句的 id 继承规则（拆句产生子 id 链，合句保留主 id + 历史）。
13. 服务仅绑定 127.0.0.1；静态服务防目录穿越。
14. 导出约定：编码（UTF-8/BOM）、命名（.ass/.srt/.chs.ass/.chs.srt）、仅绿块/全部可选。

**DTW 路线获学术背书**：chroma + DTW 正是"live 演出歌词同步"的经典方案（IEEE SPM 2016 现场歌词显示系统、ISMIR 2021 参考演出对齐、librosa 官方示例）；已知弱点"全局变速差异"用锚点分段缓解。维持 M4 可选模块定位不变。

## 十五、现有方案调研（2026-08-28 联网核实）

**结论：单个零件均有现成，但"本地的字幕时间轴工作台 + 置信度三色 + 行/段标记 + 对话 agent 回环 + git 状态 + live 歌词领域"的组合是空白。维持自建，但交互细节全部参考成熟先例。**

| 现有工具 | 与我们重叠 | 借鉴点 |
|---|---|---|
| Aegisub | 时间轴编辑教科书 | 波形/频谱视图、打轴快捷键流（s/d/f/g、边界前后 500ms 试听）、卡拉OK逐字模式、吸附/平移 |
| Label Studio | 打标+回环骨架（最接近的通用方案） | 标签生命周期 + "模型回传预测"语义（我们把模型后端替换成 harness 对话中的 agent）；注意其领域模型不匹配，不采用其本体 |
| VideoLingo / pyvideotrans | AI 字幕生产流水线（与我们今天的管线同款） | **三段式翻译链 Translate→Reflect→Adaptation**、术语体系管理、WhisperX 词级识别思路 |
| Subtitle Edit | 波形编辑 + 内置 ASR | 转写就地修改的交互习惯 |
| MediaCAT / Phrase Studio | "AI 质检标记 + 人工修复"概念（商业云） | 校验规则可配置、段级审批语义（MCP 接 agent 的方向与我们一致，但闭源云不适用） |
| 剪映等 | 自动字幕 + 文稿匹配 | 文稿匹配（文本↔音频自动对齐）的思路，已被我们的提示词对齐覆盖 |
| 学术（MIREX/IEEE/ISMIR） | 歌词对齐与现场歌词同步 | DTW 路线成熟，M4 直接引用 librosa 实现 |

**不采用 Label Studio 本体的理由**（重要）：其标注界面是表单式的，与"字幕块时间轴"领域模型冲突；ML 后端是固定模型 API 服务器，无法承载"对话里的 agent 按标记语义定点修复"；SRT/ASS 导出、曲目/歌词分组、置信度证据链都需要自建。用它等于为其改造大半，不如 Go+原生 JS 按需实现。

## 十六、技术选型明细（v1.0）

### Go 服务层
- Go 1.22+（仅标准库：`net/http` 新版路由 + `http.ServeContent` 内置 Range/206 处理；零第三方依赖）
- 静态资源 `go:embed` 打包 → 交付单二进制 exe
- 只绑 `127.0.0.1:8720`，无鉴权
- 状态写入：tmp+`os.Rename` 原子替换；不引入数据库，文件即真源
- 职责边界：只做"界面服务 + 状态 API + 视频/音频/波形文件服务 + git diff 接口"；**不执行 AI 任务**（AI 由 harness 对话中的 agent 调用 exec 脚本完成，天然解耦）

### 前端
- **Vue 3 + TypeScript + Vite + Vuetify 3**（✅ 用户拍板：喜欢 Vuetify；深色主题内置；构建由便携 Node 完成，交付单 exe）
- 界面 chrome（工具栏/面板/标记对话框/diff 对话框/统计）用 Vuetify 组件；**时间轴、波形、频谱为自绘 canvas 组件**（Vuetify 无此领域组件）
- 波形：**wavesurfer.js v7**（canvas 渲染、region 插件、支持自定义 peaks 数据）
- 频谱：自绘 canvas（数据由 Python 预计算 STFT 幅度 → state/spectrum.bin，uint8）
- 视频：原生 `<video>` + 自绘控制条（与时间轴双向同步 seek），不引 video.js
- diff 视图：直接渲染 Go 端 `git diff` 输出（左右对照），不引 JS diff 库

### Python 执行层（agent 操作，不在 Go 服务内）
- 复用 `../Anima3/.venv`（faster-whisper/ctranslate2/srt/numpy 已就绪）
- **ASR 模型策略（2026-08 调研定稿）**：
  - 主力：faster-whisper **large-v3-turbo**（已实测：4h 直播档 RTF≈0.02，词级时间戳，环境已调通）
  - 精度后备：whisper **large-v3**（需重听段落换跑/交叉验证）
  - **第二意见（M2 引入）**：**Qwen3-ASR-1.7B**（日语 CER 优于 whisper；支持带 BGM 唱歌转写；专名更准，可用日语微调版 neosophie/Qwen3-ASR-1.7B-JA）——用于"需重听/轴不准"标记的交叉验证；需装 torch（~2.5GB）
  - 唱歌段固定走"歌词提示对齐"，不用 ASR 直接听唱
  - 卡拉OK 逐字（M4）：Qwen3-ForcedAligner-0.6B（11 语言词级对齐，含日语），备选 whisperX/wav2vec2
- M4 再补 librosa（DTW）；人声分离若需要才装 torch+demucs
- 脚本接口约定：每个动作一个脚本，入参 JSON、出参 patches JSON

### 数据与接口
- `state/blocks.jsonl` 字段（完整版）：`id, start, end, kind(lyric/talk), song, ja, zh, style, confidence(green/yellow/red/gray), evidence{method,detail}, tags[], history[], locked`
- 队列文件：`state/tags.json`（open/processing/done/rejected + reply）、`state/patches.json`（agent 回写，带唯一 patch id，幂等可重放）
- REST API：`GET/PUT /api/blocks`、`GET /api/tags`、`POST /api/tags`、`POST /api/patches`、`GET /api/git/diff?from=..&to=..`、`GET /media/video|audio|peaks|spectrum`
- git 规范：仓库根 = agentisub/；提交前缀 `[ui]` / `[agent:tags#N]`；大改动走 `agent/xxx` 分支，用户 review 后合并

### 预计算产物（一次性，Python 生成）
- `media/peaks.json`：16k WAV 按像素桶 min/max 抽取（numpy）
- `media/spectrum.json`：STFT 幅度按时间桶降采样（numpy）
- `media/proxy.mp4`：ffmpeg（imageio-ffmpeg 7.1）`-c copy -movflags +faststart` 无损 remux

### 运行方式
- 开发：`vite dev`（前端热更）+ `go run ./server`；交付：`vite build` + `go build` → `agentisub.exe` 双击即用
- agent（我）通过 pwsh 直接调 exec 脚本 + 读写 state 文件；与 UI 无耦合

### 待确认项
- 前端框架：Vue 3 + TS（推荐，生态好、适合后续扩展）vs 零构建原生 JS（无 Node 依赖，但复杂交互手写成本高）——请用户拍板。
