# go2-llm-planner 项目上下文（导入 DSH 用）

> 从 ZCode 对话中提取的关键上下文：项目全貌、决策记录、当前状态、后续计划。
> 导入 DSH 后，DSH 应能基于此上下文继续协助项目开发。

## 项目目标
高二学生谢昊汐申请宇树科技"天才少年"无偿赞助计划（1~2万元，过程导向评审）。
主申请项目：LeRobot SO-101 主从臂 + 模仿学习 → SmolVLA 微调，具身智能全流程闭环。
先行项目（本仓库）：自然语言→LLM 规划→Go2 仿真执行，作为申请书第四节"先行工作"实证。

## 技术架构
```
自然语言指令 → LLM 规划(qwen3:8b, Ollama, temperature=0.1)
  → JSON 技能序列 → skill_api 校验(白名单+NaN/Inf+钳位)
  → sim_backend MuJoCo Go2 执行(演示后端=运动学滑行，第二周换 Playground 预训练策略)
  → 全程 jsonl 会话日志
```

## 文件地图
- config.py: 路径、LLM 端点、安全阈值
- skill_api.py: 6 技能白名单(BalanceStand/Move/StopMove/Sit/StandUp/Hello)、_coerce_num 有限性校验、validate_plan 三层校验
- llm_brain.py: SYSTEM_PROMPT(2 few-shot)、LLMBrain.plan(重试循环+JSON围栏预处理)、pick_backend(远程→本地自动降级)
- sim_backend.py: MuJoCo Menagerie go2 scene.xml、mj_name2id 按名取 home 关键帧、运动学 _write_base/_animate/_move
- planner.py: run_once(规划→执行→日志)、--force-local 降级演示、启动预热
- acceptance_test.py: 5 条验收指令(含模糊指令 A5)
- docs/CODE_GUIDE.md: 代码讲解 + 6 个决策叙事
- demos: videos/go2_llm_demo.mp4(无声字幕版)、videos/go2_llm_demo_final.mp4(带环境音)

## 关键决策记录
1. mock-first 演示后端(运动学滑行)：先跑通 LLM 链路，再换执行器
2. 三层安全防线：白名单→有限性校验(isfinite)→钳位
3. 双后端自动降级：Ollama 本地优先，vLLM 远程可选
4. JSON 围栏预处理：小模型偶尔输出 markdown 代码块
5. 关键帧按名加载：mj_name2id 防顺序变化
6. 全程 jsonl 日志：过程导向评审的核心证据

## 审查与修复历史
- 一轮(DSH): 13 个问题(NaN穿透、中文路径、模型名不一致等)，修复 12 项
- 二轮(DSH): 6 个新问题(pick_backend 报错信息、日志目录、sim.reset 脏状态等)，修复 9 项含 JSON 围栏预处理
- 行为级攻击测试：NaN/Inf/duration≤0/params=[] 全部拦截，无误伤
- 路线审查：Week2 从零训练 MJX→改用 MuJoCo Playground 预训练策略推理

## 硬件环境
- 本地: RTX 5060 8GB + 32GB 内存，Windows
- 远程: 5090×2 暂时不可用
- Ollama: 数据迁至 G:\Ollama，OLLAMA_MODELS=G:\Ollama\models(用户级+setx)
- 模型: qwen3:8b(Q4_K_M, 5.2GB)，本地推理
- 云端: 仙工云 5090 容器租赁，余额约 7 元(2~3 元/时)，用于 UnifoLM-VLA-0 QLoRA 或 Playground 训练

## 当前状态
- [x] 全部代码完成，两轮审查修复，12 commits
- [x] qwen3:8b 已 pull，落 G 盘
- [x] 验收 5/5 PASS(A5 人工确认通过)
- [x] demo 视频制作(无声字幕版，2:27，含过程留痕收尾)
- [x] 仓库公开: github.com/wcbsdxg/go2-llm-planner
- [x] 申请书终稿(本地 docs/application.md，含真实姓名，不入库)
- [ ] 提交申请到 Genius@unitree.com
- [ ] Week2: MuJoCo Playground 预训练 Go2 策略推理部署
- [ ] Week3(可选): Qwen2.5-VL 3B 视觉集成
- [ ] Week4: ARCHITECTURE.md + 降级演示收尾

## 后续计划
- 发送申请书后，等待宇树回复
- Week2: 独立 Python 3.12 venv(因 JAX 不支持 3.14)，安装 MuJoCo Playground，
  加载 Go2 预训练策略，替换 sim_backend._move 内运动学为 policy(obs) 推理
- 若 Playground 无 Go2 checkpoint，降级为 a1/go1 迁移或社区 ONNX sim2sim
- 若 Playground 也走不通，保留演示后端 + 架构文档说明 mock-first 设计
- 云端 5090: 建议用于 UnifoLM-VLA-0 QLoRA(申请书 B 线)，脚本先在本地写好再开机

## 常见问题
- run.bat 双击即可启动；系统 python 是 Store 占位程序(静默退出)，run.bat 已封装 venv 路径
- 首次启动会预热模型(20~60s)，之后秒回
- MuJoCo 3D 窗口可能被其他窗口挡住，查任务栏
- Go2 滑行是正常表现(演示后端)，地面滚动=运动，第二周换真实步态
- JSON 偶尔被围栏包围：预处理已自动剥离，不影响执行