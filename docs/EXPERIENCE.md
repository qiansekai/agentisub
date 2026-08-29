# Agentisub Agentisub 开发经验沉淀库

> 每次踩坑/修复 bug 后**立即追加**到本文档（格式：现象 → 根因 → 解法）。
> 开源仓库 AGENTS.md 的"血泪坑"章节从本文档摘取；本文档是唯一源头。
> 建立时间：2026-08-29（回溯沉淀 08-28~08-29 两天的全部经验）。

## 前端

### 1. JS `\W` 是 ASCII 语义，会删光日文
- **现象**：文本规范化函数用 `/\W/g` 后，日文全部消失（块匹配全失败）。
- **根因**：`\W` 匹配"非 ASCII 单词字符"，日文汉字/假名全算非单词字符。
- **解法**：显式标点正则（`/[\s\u3000・、。，．！？!?「」…]/g`）。凡是涉及日文文本的规范化，禁用 `\W`。

### 2. Vuetify 3.13 + Vite 8 tree-shaking 丢组件
- **现象**：`.v-btn` 元素数为 0，`<v-dialog>` 渲染成未知小写标签。
- **根因**：Vite 8 的 tree-shaking 把"未显式导入"的 Vuetify 组件摇掉了。
- **解法**：`main.ts` 里 `import * as components from 'vuetify/components'` + `import * as directives from 'vuetify/directives'`，全部注册。改完清 `.vite` 缓存。

### 3. CSS Grid 固定高度容器 + 大量隐式行 → 行高被异常均分
- **现象**：演出结构 43 项在 339px 高的 grid 里，每行被压成 6.9px（内容挤扁看不见）。
- **根因**：grid 容器 `height:100%` + `flex:1` 双约束下，隐式行未按 auto 内容高度计算，被均分填满容器。
- **解法**：列表场景放弃 grid，用**块流布局 + 容器 `overflow-y:auto`**（`display:block`，容器滚动）。不要在受限高度 grid 里放大量自动行。

### 4. flex 嵌套溢出：缺 `min-height:0`
- **现象**：LiveLyrics 撑到 1810px 高，一屏溢出。
- **根因**：flex 子项默认 `min-height:auto`，内容高时撑破父容器；纵向 flex 链上每层都要 `min-height:0` 才允许收缩。
- **解法**：纵向滚动区的 flex 链（容器→组件根→滚动区）每一层都加 `min-height:0`，最外层容器 `overflow:hidden` 兜底。

### 5. 隐藏滚动条
- **解法**：`scrollbar-width: none`（Firefox）+ `::-webkit-scrollbar { display: none }`（Chrome），滚轮/触控板滚动保留。

### 6. 原生 confirm() 在 CDP 自动化下会卡死点击链
- **现象**：CDP 模拟点击删除按钮 → confirm 弹窗 → accept 后删除没执行。
- **根因**：`confirm()` 同步阻塞页面 JS，CDP 连接在此期间的时序不可靠。
- **解法**：真实用户环境无此问题；自动化验证时直接测 API（DELETE 接口）而非走 UI confirm 链路。

## 后端（Go）

### 7. 无 go.mod 时的构建
- **现象**：`go build` 报 module 错误。
- **解法**：`go build main.go`（文件级编译）或 `GO111MODULE=off`。产物是 `main.exe`/指定名，**必须复制到项目根目录**（工作目录约定）再重启。

### 8. 服务重启模式
- **解法**：`Get-NetTCPConnection -LocalPort 8720` 找 PID → `Stop-Process` → 换 exe → `Start-Process -WorkingDirectory <项目根> -WindowStyle Hidden`。

### 9. 数据自动 commit 有 5 秒延迟
- **现象**：API 写入后立刻查 git 状态看不到提交。
- **根因**：服务端设计——变更 5 秒后防抖 commit（数据自带版本历史）。
- **解法**：脚本/验证里 API 写入后 `Start-Sleep 6` 再查 git；批量操作完等 6 秒再手动 commit 总结。

### 10. 媒体路径从 meta.json 读
- **设计**：`/media/video` 读 `state/meta.json` 的 `media.video` 字段（轻量代理切换只改配置），缺省 `media/proxy.mp4`。加媒体接口时沿用此模式。

## Python 工具链

### 11. pykakasi 的 hepburn 字段带空格
- **现象**：罗马音比较时"watashihanemurushiro" vs "watashihanemuru shiro" 判不等（表记差异被误判为冲突）。
- **解法**：比较前 `.replace(" ", "")`。另注意 pykakasi 局限：助词"は"输出 ha 而非 wa；歌词刻意读法（水無月→rokugatsu）词典查不对——**这类必须用人工整理罗马音（联网抓取），算法只能兜底**。

### 12. whisper 对唱歌段不可靠
- **现象**：整曲转录输出乱码（"勇気的な生活未満の手たらくな体…"），07/08 曲几乎不可用。
- **根因**：BGM/混响干扰，ASR 对唱词识别差。
- **解法**：歌词对齐走 **align_song prompt 模式**（歌词做 initial_prompt + difflib 字符对齐，07 曲 33 行实证）；不要用裸 ASR 重建歌词块。ASR 只适合 MC 说话段。

### 13. 缓存格式升级要向后兼容
- **现象**：`state/lrc/*.json` 从数组 `[[t,txt],…]` 升级为字典 `{lrc,tlyric,romalrc}` 后，autotime 读旧缓存 `for t,txt in lrc` 直接 ValueError → create 模式静默失败（批量输出 0 创建，实际该建 193 块）。
- **解法**：读缓存必须判断 `isinstance(data, dict)` 双分支兼容；**升级缓存格式的脚本要负责让所有消费者兼容**，或清缓存重抓。

### 14. np.interp 要求 x 升序
- **现象**：DTW 路径乱序时 `np.interp` 报错/结果错。
- **解法**：`np.argsort(x)` 重排后再 interp；DTW 映射 studio→live 方向记牢：`np.interp(studio_t, studio_arr, live_arr)`。

### 15. 重复副歌块与 LRC 时间戳
- **现象**：autotime 给重复副歌块分配同一歌词行时间 → 新造压缩。
- **解法**：LRC 保留重复行的时间戳列表（`lrc_all[norm] = [t1, t2,…]`），块按 live 时间排序后**按出现次序依次消费**；块数超出时用最后一次时间。

### 16. 批量任务先预览再 apply
- **解法**：工具脚本统一 `[--apply]` 参数——无 apply 时输出预览清单（含相似度/新旧时间），核对后再写入。所有改数据脚本遵守此约定。

## PowerShell 环境

### 17. Where-Object … -in 偶发返回空
- **现象**：`$list | Where-Object { $_.id -in $ids }` 在本机间歇性空结果（批量脚本丢数据）。
- **解法**：批量场景用普通 `foreach` + `-eq` 条件；`-contains` 数组判断也避免管道。

### 18. 字符串插值 `$sid:` 语法错误
- **现象**：`"$sid: 结果"` 报 "Variable reference is not valid"。
- **解法**：用 `${sid}`。

### 19. JSON 数组下标访问
- **现象**：`ConvertFrom-Json` 后 `$lrc | ForEach { $_.PSObject.Properties['0'] }` 拿到空。
- **解法**：`$lrc[$i][0]`（嵌套数组直接下标）。

### 20. pwsh 捕获 Python 输出
- **解法**：`$env:PYTHONIOENCODING='utf-8'` 先设（防中文乱码）；`& python script 2>&1 | Out-String` 捕获后 `-match` 提取统计。

## 网易云接口

### 21. 歌词接口参数决定返回字段
- **现象**：POST + `lv/kv/tv` 参数拿不到 romalrc（罗马音全空，误判"网易云没有"）。
- **解法**：`GET /api/song/lyric?id=xx&lv=1&tv=1&rv=1` + `Cookie: appver=1.0.0; os=pc` 头——`rv=1` 才返回罗马音。tlyric=译文、lrc=原文。

### 22. VIP 音频获取（零凭据泄露方案）
- **解法**：CDP 连接用户已登录的网易云页面 → **页面内 fetch** `player/url`（Cookie 自动附带，token 不出浏览器）→ 拿 CDN URL 后主机下载。`fee:1` 的曲目此路可通，320kbps。比让用户交 token 更安全。

### 23. free 接口的假象
- **现象**：`outer/url` 对部分曲返回 106884 字节 JSON 错误（非音频）。
- **根因**：fee=0 但地区/风控限制的曲走不了 free 接口。
- **解法**：probe 后用 ffprobe 验时长（dur=0 即 BAD），BAD 的曲转 CDP 方案（#22）。

## 数据与版权

### 24. 公开报道口径 vs 实际演出
- **教训**：context/公开报道说"01-04 是待机 BGM"，实际 BD 里开场就唱了 01（用户观察实锤，转写确认）。**数据错误率最高的来源是"想当然的结构假设"**——以实际演出/音频为准，用户反馈优先于外部口径。

### 25. 版权红线
- 字幕/歌词/媒体数据不进公开仓库；开源仓库只推代码（`state/`、`media/`、构建产物全 gitignore）。歌词版权（网易云）+ 演唱会内容版权。

## 开源

### 26. 开源仓库与工作仓库分离
- **结构**：`agentisub`（工作，含数据与历史）/ `agentisub-open`（开源，仅代码，干净历史）。同步 = 拷贝变更 + commit + push，数据绝不互通。
- 文档三件套：README（人）/ AGENTS.md（agent）/ LICENSE。**名字巧思**：Agentis（拉丁语 agēns/agentis 行动者）+ Agent is + 谐音希腊语 Aegis（αἰγίς 神盾）+ sub。

## 自主修正轮次（08-29 夜间）

### 27. 重叠修复：顺延 vs 中点切分
- **现象**：顺延式修平（后块 start = 前块 end）把 676 个重叠块连锁顺延，01 曲尾块被推出 +96s（超唱段、撞 MC）。
- **教训**：**修重叠必须用中点切分**（两侧各让半，`A.end = B.start = mid`），顺延会连锁放大尾部错误。批量时序类修复后必须验证"尾部出界 + 与相邻环节块冲突"两项。
- **回滚点选择**：checkout 时选错 commit（d9e1a96 已含污染）——**批量 apply 前先记下"操作前最后一个手动 commit hash"**（服务端 5s 自动 checkpoint 会让污染混进历史）。

### 28. 重复副歌块 vs 校验统计假象
- **现象**：check_block_times 的"大偏差块"计数修完不降（134 个）。
- **根因**：校验脚本 `{norm: block}` dict 去重，同一歌词行的重复副歌块只留一个——副歌第 2 遍的块与第 1 遍歌词时间比天然"大偏差"。
- **解法**：**用序列单调性验证轴健康**（相邻块倒序/重叠/同 start 计数），不要只看"块 vs 歌词行时间差"。两个指标配合。

### 29. whisper 幻觉块
- **现象**：MC 尾部空白段（掌声/无人声）转写出歌词文本（U-009"大事な約束の彼方"误听进 12029 段）。
- **解法**：补块后交叉验证——转写块文本与相邻曲目歌词比对，命中歌词行但时间远离该曲段的即幻觉，删除。VAD 过滤不能完全防幻觉。

### 30. Qwen3-ASR 依赖死结
- **现象**：qwen-asr 0.0.6 与 transformers 无兼容版本——4.57.6（声明依赖）缺 `tokenizer.audio_token`；主分支 5.16.0.dev0 改 `check_model_inputs()` 装饰器 API 致 modeling 代码崩溃。
- **结论**：上游打包问题（0.0.6 对应某特定 transformers commit）。**测试脚本已备好（qwen_asr_test.py），上游修复后一键可跑**。Qwen3-ASR 支持 2026-06 已合入 transformers 主分支，待正式发布。
- **教训**：装主分支/降级依赖前先确认核心工具链影响（faster-whisper 不依赖 transformers，安全）；改完必须回归验证 import。

### 31. 歌曲段空白 ≠ 缺字幕
- **现象**：find_blanks 报大量歌曲段内空白（07 曲 37s 等），疑似唱段遗漏。
- **验证**：probe 转写 → 全无语音（间奏/前奏纯音乐）。
- **解法**：**只有 MC 环节空白才转写补块**；歌曲段空白是删段/间奏，不补（给纯间奏加块是错误）。

### 32. rap 段超短块
- **现象**：13 曲同 start 的 16 对块全是 0.2-0.3s 的 rap 行（"Q & A""U & Me""Clap Your Hands"）。
- **结论**：rap 拆块过碎（0.3s 字幕不可读），但自动合并会错拼不同 rap 行——**保持现状打标，人工听判重新切块**。rap/快嘴段是自动切块的天敌。
- **后续实测修正**：用户标记"挤在一起刷过去"→ 实际合并可行——同 start 对唱对用"／"join、连续碎块按 1.2s 组并（89 块→33 块），坏块 end<start 交换。**对唱 rap 的"同 start 两个块"是正常现象（对唱重叠）不是损坏**，合并时保留双方文本。

## ASR 模型部署（08-29 白天）

### 33. torch 必须 CUDA 版才能用 GPU（且要 cu128）
- **现象**：`device_map="cuda"` 报 "Torch not compiled with CUDA enabled"；cu126 报 "no kernel image is available"。
- **根因**：①最初装 demucs 用了 CPU 源 ②RTX 5060 Ti（Blackwell **sm_120**）需要 **CUDA 12.8+**（cu126 内核不支持 sm_120）。
- **解法**：`pip install torch --index-url https://download.pytorch.org/whl/cu128 --force-reinstall`（同版本号 pip 不重装，必须 --force-reinstall）；pip 依赖 nvidia 包（cudnn 9.x 的 zlibwapi 问题：torch cu128 wheel 自带 cudnn 但缺依赖时补 `nvidia-cudnn-cu12`）。

### 34. ctranslate2 与 torch CUDA 冲突 → 双 venv 分家
- **现象**：装了 torch cu126 后，`import ctranslate2` 报 WinError 127（torch 的 cudnn DLL 从 ct2 目录找到错误依赖）。
- **根因**：ctranslate2 `__init__` 先 `add_dll_directory` 自己目录（捆绑 CUDA DLL），torch 在其后 import 时 DLL 搜索路径被污染。
- **解法**：**faster-whisper 不需要 torch CUDA**（ct2 自带）——分家：
  - 原 venv：torch **CPU** 版 + faster-whisper（GPU 正常）
  - 新 venv（qwen-env）：torch cu128 + transformers（Qwen 用）
  - 两套工具各自用自己的 python 跑，互不干扰。

### 35. pip 下载撑爆 C 盘
- **现象**：torch 2.75GB wheel 下载中断 "No space left on device"（C 盘 3.6GB）。
- **解法**：`$env:TMP/TEMP = "D:\Temp"` + `pip --cache-dir "D:\Temp\pipcache"`（每个 pwsh 会话都要设，后台任务不继承）；事后清 `%LOCALAPPDATA%\Temp\pip-*` 残留。

### 36. Qwen3-ASR 的正确用法（transformers ≥5.13 原生）
- 模型卡：`Qwen/Qwen3-ASR-{0.6B,1.7B}-hf`、`Qwen/Qwen3-ForcedAligner-0.6B-hf`
- ASR：`AutoProcessor.apply_transcription_request(audio=ndarray, language="ja")` + `AutoModelForMultimodalLM` + **`model.generate(**inputs)` 展开传参**（直接传 BatchFeature 报 AttributeError）
- **必须传 language**：不传自动语言识别会把日语歌判成英文（输出英文幻觉）
- ForcedAligner：`prepare_forced_aligner_inputs(audio, transcript, language)` + `AutoModelForTokenClassification` + `decode_forced_alignment(...)`；输出字段是 `text/start_time/end_time`（不是 word/start/end）
- 旧 SDK qwen-asr 包（锁 transformers==4.57.6）与任何版本都不兼容，**别用**

### 37. DTW 映射的 t0/t1 依赖
- **现象**：03 曲整曲块落在 credit 卡期间（5710-5775），实际唱在 5560-5650——DTW 映射把块排到了错误区间。
- **根因**：songs.json 的 t0/t1 当初凭早期粗略转写定（把 credit 卡当唱段），DTW 在错误区间对齐 → 整曲错位。
- **教训**：**t0/t1 必须转写证据锚定**（每首歌唱段起止用 whisper 词级时间确认）；改 t0/t1 后必须重跑 dtw_align + autotime。开场曲的开头漂移（01/02 曲 -6s）同源：live 前奏比 studio 短，DTW 开头对齐漂移——用"第一句起唱时间"三方证据（whisper/Qwen/FA）锚定修正。
