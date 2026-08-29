"""LLM 大脑：把自然语言变成技能序列 JSON。

支持两种后端，接口统一：
- ollama : 本地 Ollama（POST /api/chat，format=json 强制 JSON 输出）
- openai : 任何 OpenAI 兼容服务（远程 vLLM：POST /v1/chat/completions）

温度设 0.1：规划任务要稳定，不要发散。
"""
import json

import requests

import config
from skill_api import validate_plan

SYSTEM_PROMPT = """你是四足机器人Go2的任务规划器。把用户的自然语言指令拆解为技能序列，只输出JSON。

可用技能（名称必须完全一致）：
- BalanceStand: params {} —— 原地站立保持平衡
- Move: params {"vx":前进速度m/s, "vy":左移速度m/s, "vyaw":左转角速度rad/s, "duration":持续秒}
  安全范围: |vx|<=0.5, |vy|<=0.3, |vyaw|<=1.0, duration<=10（超出会被截断，请主动遵守）
- StopMove: params {} —— 停止移动
- Sit: params {} —— 坐下
- StandUp: params {} —— 起立
- Hello: params {} —— 打个招呼

输出格式（严格遵循）：
{"plan": [{"name": "Move", "params": {"vx": 0.3, "vy": 0, "vyaw": 0, "duration": 2}}]}

示例1：
用户：向前走两步然后坐下
输出：{"plan": [{"name": "Move", "params": {"vx": 0.3, "vy": 0, "vyaw": 0, "duration": 2}}, {"name": "Sit", "params": {}}]}

示例2：
用户：左转
输出：{"plan": [{"name": "Move", "params": {"vx": 0, "vy": 0, "vyaw": 0.8, "duration": 2}}]}

只输出JSON，不要输出任何解释或markdown代码块标记。"""


class LLMBrain:
    def __init__(self, backend="ollama", model=None, base_url=None, api_key=None):
        self.backend = backend
        self.model = model or (config.OLLAMA_MODEL if backend == "ollama" else config.REMOTE_MODEL)
        self.base_url = (base_url or (config.OLLAMA_URL if backend == "ollama"
                                      else config.REMOTE_VLLM_URL)).rstrip("/")
        if backend == "openai" and not self.base_url:
            raise RuntimeError(
                "openai 后端缺少 base_url：请通过 --base-url 传入，或在 config.py 填写 REMOTE_VLLM_URL。")
        self.api_key = api_key or config.REMOTE_API_KEY
        # 多轮重试时保留对话历史，把校验错误喂回去让模型自己修
        self.history: list[dict] = []

    # ---------- 两种后端的原始调用 ----------
    def _call_ollama(self, messages) -> str:
        r = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": messages, "format": "json",
                  "stream": False, "options": {"temperature": 0.1, "num_ctx": 4096}},
            timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def _call_openai(self, messages) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {"model": self.model, "messages": messages, "temperature": 0.1,
                "response_format": {"type": "json_object"}}
        r = requests.post(f"{self.base_url}/chat/completions",
                          json=body, headers=headers, timeout=120)
        if r.status_code == 400:  # 部分服务不支持 response_format，去掉重试
            body.pop("response_format")
            r = requests.post(f"{self.base_url}/chat/completions",
                              json=body, headers=headers, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _raw_call(self, messages) -> str:
        if self.backend == "ollama":
            return self._call_ollama(messages)
        return self._call_openai(messages)

    # ---------- 带校验重试的规划入口 ----------
    def plan(self, user_cmd, max_retries=2):
        """返回 (skills, warnings, llm_raw_text)。失败抛 RuntimeError。"""
        self.history = [{"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_cmd}]
        last_raw = ""
        for attempt in range(max_retries + 1):
            raw = self._raw_call(self.history)
            last_raw = raw
            # 小模型偶尔输出 markdown 代码块围栏，预处理去掉以提高首次成功率
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                error = f"JSON解析失败: {e}"
                parsed = None
            else:
                skills, warnings, error = validate_plan(parsed)
                if error is None:
                    return skills, warnings, raw
            if attempt < max_retries:
                self.history.append({"role": "assistant", "content": raw})
                self.history.append({
                    "role": "user",
                    "content": f"你的输出有问题：{error}。请严格按照系统提示里的格式重新只输出JSON。"})
        raise RuntimeError(f"LLM 连续 {max_retries + 1} 次输出不合格，最后一次输出：{last_raw[:500]}")


def pick_backend():
    """自动探测可用后端：优先远程 vLLM，其次本地 Ollama。返回 (backend, model) 或抛错。"""
    if config.REMOTE_VLLM_URL:
        headers = ({"Authorization": f"Bearer {config.REMOTE_API_KEY}"}
                   if config.REMOTE_API_KEY else {})
        try:
            r = requests.get(f"{config.REMOTE_VLLM_URL.rstrip('/')}/models",
                             timeout=3, headers=headers)
            if r.ok:
                return "openai", config.REMOTE_MODEL
        except requests.RequestException:
            pass
    try:
        r = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2)
        if r.ok:
            return "ollama", config.OLLAMA_MODEL
    except requests.RequestException:
        pass
    raise RuntimeError(
        "没有可用的 LLM 后端。请先安装并启动 Ollama，然后执行：\n"
        f"  ollama pull {config.OLLAMA_MODEL}\n"
        "或在 config.py 里填写 REMOTE_VLLM_URL 使用远程服务器。")
