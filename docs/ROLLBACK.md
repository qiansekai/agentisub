# 回滚指南（2026-08-29 睡前自主修正任务）

## Checkpoint 基线

- **Commit**: `b2ad784`（full: `b2ad784c9d7f4df80f89d9e6a8350651b9dadeac`）
- **时间**: 2026-08-29 睡觉前
- **状态**: 1349 块 / 24 曲 / 三色 760-535-54 / 块级 history 全链 / 打轴三层记录完整
- **服务**: 8720 运行中（PID 9340）

## 怎么回滚

**回滚数据**（所有自主修正的改动）：
```powershell
# 停服务
$p = Get-NetTCPConnection -State Listen -LocalPort 8720 | Select-Object -First 1 -ExpandProperty OwningProcess
Stop-Process -Id $p -Force
# 恢复 state/ 到 checkpoint
git -C "D:\Kita-Tools\Media\agentisub" checkout b2ad784 -- state/
# 重启服务
Start-Process -FilePath "D:\Kita-Tools\Media\agentisub\agentisub.exe" -WorkingDirectory "D:\Kita-Tools\Media\agentisub" -WindowStyle Hidden
```

**回滚代码**（exec 脚本改动）：
```powershell
git -C "D:\Kita-Tools\Media\agentisub" checkout b2ad784 -- exec/ server/ web/
```

**完全回滚**（危险，回到基线 commit 本身）：
```powershell
git -C "D:\Kita-Tools\Media\agentisub" reset --hard b2ad784
```

## 自主修正任务清单（睡觉期间 agent 执行）

1. 缺失歌词：04 罗马音再搜人工源；Capullo 无官方源（诚实收尾）
2. 缺失字幕：MC 段空白补块（whisper 转写）
3. 未对齐字幕：损坏曲残留修复（13/07/12/04/18，aligned difflib 流程）
4. Qwen ASR vs whisper 转写对比测试
5. 每轮验证 + 独立 commit（可逐轮回滚）

## 约束

- Capullo 无官方音源/歌词：不伪造，维持 ⚠️ 听写稿
- 所有改动走 API/脚本 → 块级 history + git 自动 checkpoint
- 每个修复轮次独立 commit 带说明
- 用户机器 CPU 可用于 whisper（用户已睡），合理并行不超过 2 个重任务
