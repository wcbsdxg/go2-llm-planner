"""项目配置：路径、LLM 端点、安全限制。所有可调参数集中在这里。"""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
GO2_SCENE = os.path.join(
    PROJECT_ROOT, "third_party", "mujoco_menagerie", "unitree_go2", "scene.xml"
)

# ---- LLM 后端 ----
# 备用：本地 Ollama（你安装并 pull 模型后生效）
# 本机为 5060 8GB 显存：qwen3:8b(Q4,约5.2GB) 可全量进显存；14b 会溢出到 CPU 明显卡顿
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:8b"

# 主路线：远程 vLLM（OpenAI 兼容接口）。留空表示暂不使用。
# 填写示例："http://你的服务器IP:8000/v1"
REMOTE_VLLM_URL = ""
REMOTE_API_KEY = ""
REMOTE_MODEL = "Qwen/Qwen3-32B"

# ---- 安全钳位（超出范围的一律截断并记录日志）----
SAFETY = {
    "vx": 0.5,        # 前进/后退速度上限 m/s
    "vy": 0.3,        # 侧移速度上限 m/s
    "vyaw": 1.0,      # 转向角速度上限 rad/s
    "duration": 10.0, # 单个动作最长持续时间 s
    "max_skills": 8,  # 单次计划最多技能数，防止 LLM 输出超长序列
}

RENDER_WIDTH = 1280
RENDER_HEIGHT = 720
FPS = 30
