# 代码导览 —— 理解并讲清这个项目的完整指南

> 写给项目作者本人：这份文档帮你把 9 个源文件真正变成"自己的东西"。
> 每一节都按"它是什么 → 关键代码 → 评审可能怎么问 → 你怎么答"组织。

---

## 一、一图流：一条指令的完整旅程

以输入 **"向前走三步然后坐下"** 为例：

```
你在终端输入指令
   │
   ▼ planner.py: run_once() 接收，写入会话日志 (logs/sessions/*.jsonl)
   │
   ▼ llm_brain.py: LLMBrain.plan()
   │   ① 组装消息：SYSTEM_PROMPT（技能表+输出格式+2个示例）+ 用户指令
   │   ② POST http://localhost:11434/api/chat（Ollama, format=json, temperature=0.1）
   │   ③ 得到原始文本 → json.loads → dict
   │   ④ 交给 skill_api.validate_plan() 校验
   │      ├─ 通过 → 返回 [Skill, Skill, ...]
   │      └─ 失败 → 把错误信息追加进对话历史 → 重试（最多2次）
   │
   ▼ skill_api.py: validate_plan() 的三道关
   │   ① 白名单：技能名必须 ∈ {BalanceStand, Move, StopMove, Sit, StandUp, Hello}
   │   ② 数值：float 可转换 + math.isfinite（拒绝 NaN/Inf）+ duration > 0
   │   ③ 钳位：|vx|≤0.5, |vy|≤0.3, |vyaw|≤1.0, duration≤10, 计划≤8个技能
   │      （每次截断/修正都生成 warning，写入日志）
   │
   ▼ sim_backend.py: Go2Sim.execute() 逐技能执行
   │   Move → _move()：按 30fps 逐帧积分位姿（vx·cosθ·dt 前进，vyaw·dt 转向）
   │   Sit  → _change_height()：基座 z 从 0.270m 平滑降到 0.149m
   │   每帧：_write_base() 把基座 x/y/z/yaw 写进 qpos → mj_forward() 刷新渲染
   │
   ▼ 终端打印每步结果，jsonl 日志落盘，[完成] [OK]
```

---

## 二、分文件讲解

### config.py —— 唯一的参数来源（20 行）

**它是什么**：路径、LLM 端点、安全限制、渲染参数全部集中在这一个文件。
**为什么这样设计**：改任何阈值只动一处；`SAFETY` 字典被 `skill_api` 读取，
`OLLAMA_MODEL` 被 `llm_brain` 和错误提示引用——单一事实来源，改模型名不会出现
三处不一致（二轮审查修的就是这种问题）。

### skill_api.py —— 整个项目安全性的核心

**它是什么**：LLM 和机器人之间的一堵墙。LLM 只能"点菜"（白名单里选），
不能"进厨房"（直接给控制量）。

**关键代码**：

| 成员 | 作用 |
|---|---|
| `SKILL_SCHEMA` | 6 个技能 → 参数类型表的映射，白名单+类型一张表定死 |
| `Skill` (dataclass) | 一个技能实例：`name` + `params`，`__str__` 打印成 `Move(vx=0.30, ...)` |
| `_coerce_num()` | 把 `"0.3"`、`0`、`0.0` 统一转 float；**`math.isfinite` 拒绝 NaN/Inf** |
| `validate_plan()` | 主校验：格式 → 数量截断 → 逐技能：白名单 → params 必须是 dict → 逐参数转换 → duration>0 → 钳位 → 多余参数丢弃。任何硬错误返回 error 让 LLM 重试 |

**评审会问**："LLM 输出 `vx: NaN` 会怎样？"
**你的答**：`float("nan")` 能正常转换，而钳位条件 `abs(v) > limit` 对 NaN 恒为
False——NaN 会直接穿透钳位，污染基座位姿、写出非法 JSON 日志、甚至让
`int(round(NaN))` 抛异常打崩程序。这就是 `_coerce_num` 里 `math.isfinite` 存在的
原因。这个故事是"攻击→发现→修复→回归测试"的完整闭环，过程质量的绝佳素材。

### llm_brain.py —— 大模型翻译官

**它是什么**：把自然语言变成合法 JSON 的封装，支持 Ollama/OpenAI 两种后端。

**关键设计**（每个都能讲出一套理由）：

| 设计 | 理由 |
|---|---|
| `SYSTEM_PROMPT` 里给 2 个 few-shot 示例 | 小模型对格式示例的遵从远高于纯描述 |
| `temperature=0.1` | 规划任务要稳定复现，不要发散 |
| `format:"json"`（Ollama）/ `response_format`（vLLM） | 语法级强制 JSON，比提示词约束硬 |
| `plan()` 的重试循环 | 校验失败时把**具体错误**追加进对话历史让模型自己改——self-correction，最多 2 次 |
| JSON 围栏预处理（二轮新增） | 小模型偶尔无视"不要 markdown"的指令输出 ` ```json ` 围栏，先剥掉再解析，省一次重试 |
| `pick_backend()` 探测顺序 远程→本地 | 云端强模型优先，自动降级到本地；探测请求带鉴权头 |

### sim_backend.py —— 仿真世界（"演示后端"是刻意设计）

**它是什么**：MuJoCo 物理引擎 + DeepMind Menagerie 维护的宇树 Go2 官方模型。

**关键代码**：

| 成员 | 作用 |
|---|---|
| `__init__` | `mj_name2id(..., "home")` **按名字**取站立关键帧（不依赖索引顺序），id<0 直接报错 |
| `_write_base()` | 运动学写基座 x/y/z/四元数到 `qpos[0:7]`，腿部保持 home 姿态；只调 `mj_forward` 不调 `mj_step`（运动学模式不需要动力学积分） |
| `_animate(duration, update)` | 以 1/30s 步长驱动动作，每帧回调（给 viewer 同步或录屏用） |
| `_move()` | 基座坐标系下积分：yaw 先转，x/y 沿新朝向推进——所以"左转90度"会走出圆弧 |
| `execute()` | 技能分发器：6 个技能各对应一个运动学实现 |

**必须能讲清的一句话**：当前 Move 是"滑行"（运动学拖动基座，腿保持站姿），
这是 **mock-first 刻意设计**——先把 LLM→规划→执行的全链路风险清零，再换执行器。
换执行器时上层代码零改动，因为技能接口与 `unitree_sdk2py.SportClient` 命名对齐。

### planner.py —— 把一切串起来的主循环

**关键代码**：`run_once()` = 规划（异常→日志+返回）→ 打印计划+安全修正 →
逐技能执行（**单个异常→`sim.reset()` 复位防脏状态→日志→继续下一条指令**）→
全程 jsonl 留痕。`--force-local` 强制走本地后端，用于演示"远程不可用时的降级"。

### 其余四个文件（自检工具，各 30 行以内）

| 文件 | 用途 |
|---|---|
| `smoke_test.py` | 无窗口全链路自检：加载→校验→执行→离屏渲染，输出 PASS |
| `view_go2.py` | 开 3D 窗口看 Go2 站立/坐下循环，人工确认渲染正常 |
| `record_demo.py` | 无 LLM 录 4 段预定义技能视频（ASCII 文件名，Windows 中文路径坑） |
| `acceptance_test.py` | 5 条验收指令过真实 LLM，产出 markdown 验收报告；A5 模糊指令标注"需人工确认" |

---

## 三、六个"决策叙事"（评审材料的黄金素材）

每个都按 **为什么这样做 → 替代方案 → 为什么没选** 的结构写：

1. **mock-first 演示后端**：先清零链路风险再换执行器。替代：直接从 RL 步态开始——
   被否，因为 RL 调参是以周为单位的高风险工作，会阻塞所有下游验证。
2. **三层安全防御**（白名单→有限性校验→钳位）。替代：信任 LLM 输出——被否，
   NaN 事件证明小模型输出不可信，防线必须在代码层而不是提示词层。
3. **双后端自动探测与降级**。替代：写死本地 Ollama——被否，`pick_backend()`
   让"远程 32B 大脑 ↔ 本地 8B"切换对上层透明，`--force-local` 一键演示降级。
4. **带错误反馈的重试 + 围栏预处理**。替代：解析失败直接报错——被否，
   把校验错误喂回对话让模型自修，实测是提升小模型首次成功率 cheapest 的手段。
5. **关键帧按名加载**。替代：`key_qpos[0]` 索引——被否，模型文件更新顺序变化会
   静默拿错姿态，`mj_name2id` + 显式报错把失败提前到启动时。
6. **会话日志全程 jsonl 留痕**。替代：只在最后写总结——被否，过程导向评审看的
   是过程，失败和修正同样要留痕。

---

## 四、评审 Q&A 速答

- **为什么不用 Isaac Gym 训练？** 旧版 Isaac Gym 不支持 RTX 50 系（Blackwell
  sm_120 架构）；Week2 步态改用 DeepMind MuJoCo Playground（MJX+JAX，支持新卡）。
- **为什么 temperature 0.1？** 规划要可复现；发散会让同一指令得到不同技能序列，
  没法做验收基线。
- **为什么 LLM 不能直接输出关节角？** 12 维连续控制量超出小模型数值能力，
  且越权绕过所有安全层。LLM 只做"语义→离散技能+有界参数"的翻译。
- **演示后端怎么换成真步态？** `sim_backend._move` 内部替换为 `policy(obs)` 推理，
  `execute()` 签名不变——这就是接口对齐的价值。
- **为什么所有下载/数据都不放 C 盘？** Ollama 通过 `OLLAMA_MODELS` 环境变量迁移
  到 `G:\Ollama`（注册表+setx 双保险），C 盘只剩几百字节的密钥（Ollama 固定从
  用户主目录读取，无法迁移，无害）。
