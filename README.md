# go2-llm-planner

自然语言 → LLM 任务规划 → Unitree Go2 仿真执行的具身智能先行项目。

## 架构

```
自然语言指令（"向前走三步然后坐下"）
        │
        ▼
LLM 规划层（本地 Ollama qwen3 / 远程 vLLM Qwen3-32B，temperature=0.1）
        │  输出 JSON 技能序列，校验失败自动带错误信息重试
        ▼
技能层 skill_api.py
  · 白名单：BalanceStand / Move / StopMove / Sit / StandUp / Hello
    （与 unitree_sdk2py SportClient 接口名对齐，真机可平移）
  · 安全钳位：|vx|≤0.5, |vy|≤0.3, |vyaw|≤1.0, duration≤10s, 计划≤8步
        ▼
仿真后端 sim_backend.py（MuJoCo + Menagerie 官方 Go2 模型）
```

## 当前状态（诚实声明）

- **执行后端为演示后端**：Move 以运动学插值驱动基座，腿部保持站立关键帧，
  表现为"滑行"。刻意采用 mock-first 策略：先跑通 LLM 规划全链路。
- **下一步**：用 MuJoCo MJX（JAX，支持 RTX 50 系）训练真实步态策略替换执行器，
  上层代码零改动。

## 运行

```bash
# 0) 依赖
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/google-deepmind/mujoco_menagerie third_party/mujoco_menagerie
cd third_party/mujoco_menagerie && git sparse-checkout set unitree_go2 && cd ../..

# 1) 自检（无窗口）
python smoke_test.py

# 2) 看 Go2 站立（3D 窗口）
python view_go2.py

# 3) 无 LLM 录 demo 视频
python record_demo.py

# 4) 完整链路（先安装 Ollama 并 ollama pull qwen3:8b）
python planner.py
```

## 路线图

- [x] Day 1：MuJoCo Go2 + LLM 规划闭环（演示后端）
- [ ] Week 2：MJX 训练步态策略替换演示后端
- [ ] Week 3：接入 Qwen2.5-VL 视觉理解（仿真截图→语义反馈）
- [ ] Week 4：远程 32B 大脑 + 本地小脑的边缘-云分层架构与降级策略
