"""主程序：自然语言 → LLM 规划 → 仿真执行，全程写会话日志。

用法：
  python planner.py                     # 自动探测后端，开 3D 窗口
  python planner.py --headless          # 无窗口（只看控制台）
  python planner.py --model qwen3:8b    # 换本地模型
  python planner.py --backend openai --base-url http://IP:8000/v1 --model Qwen/Qwen3-32B
"""
import argparse
import json
import os
import time
from datetime import datetime

from config import PROJECT_ROOT
from llm_brain import LLMBrain, pick_backend
from sim_backend import Go2Sim
from skill_api import validate_plan

SESSION_DIR = os.path.join(PROJECT_ROOT, "logs", "sessions")


def new_session_log():
    os.makedirs(SESSION_DIR, exist_ok=True)
    path = os.path.join(SESSION_DIR, f"session_{datetime.now():%Y%m%d_%H%M%S_%f}.jsonl")
    return open(path, "a", encoding="utf-8")


def log_event(f, **event):
    event["t"] = f"{datetime.now():%H:%M:%S}"
    f.write(json.dumps(event, ensure_ascii=False) + "\n")
    f.flush()


def run_once(brain: LLMBrain, sim: Go2Sim, user_cmd: str, logf) -> bool:
    """执行一条指令的完整链路。返回是否成功。"""
    print(f"\n[指令] {user_cmd}")
    log_event(logf, type="user", text=user_cmd)
    try:
        skills, warnings, raw = brain.plan(user_cmd)
    except Exception as e:
        print(f"[规划失败] {e}")
        log_event(logf, type="error", stage="plan", msg=str(e))
        return False

    print("[LLM原始输出] " + raw.replace("\n", " ")[:200])
    for i, s in enumerate(skills, 1):
        print(f"  {i}. {s}")
    for w in warnings:
        print(f"  [安全修正] {w}")
    log_event(logf, type="plan", llm_raw=raw,
              skills=[{"name": s.name, "params": s.params} for s in skills],
              warnings=warnings)

    for i, s in enumerate(skills, 1):
        try:
            desc = sim.execute(s)
        except Exception as e:
            print(f"[执行失败 {i}/{len(skills)}] {s} —— {e}")
            log_event(logf, type="error", stage="exec", skill=s.name,
                      params=s.params, msg=str(e))
            sim.reset()  # 执行中断后复位，避免脏状态影响后续命令
            return False
        print(f"[执行 {i}/{len(skills)}] {s} —— {desc}")
        log_event(logf, type="exec", skill=s.name, params=s.params, desc=desc)
    print("[完成] [OK]")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["auto", "ollama", "openai"], default="auto")
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--headless", action="store_true", help="不开3D窗口")
    ap.add_argument("--force-local", action="store_true", help="强制使用本地 Ollama（等价于 --backend ollama，用于降级演示）")
    args = ap.parse_args()

    if args.force_local:
        args.backend = "ollama"
    if args.backend == "auto":
        backend, detected_model = pick_backend()
        model = args.model or detected_model
    else:
        backend, model = args.backend, args.model
    print(f"[LLM] backend={backend} model={model}")
    brain = LLMBrain(backend, model=model, base_url=args.base_url)
    print("[预热] 正在将模型载入显存（首次约 20~60 秒，之后秒回）...")
    try:
        brain.warmup()
        print("[预热] 完成，模型已就绪")
    except Exception as e:
        print(f"[预热] 失败（不影响启动，首条指令会较慢）: {e}")

    sim = Go2Sim(headless=args.headless)
    if not args.headless:
        sim.start_viewer()
        time.sleep(0.5)

    os.makedirs(SESSION_DIR, exist_ok=True)
    with new_session_log() as logf:
        log_event(logf, type="session_start", backend=backend, model=model)
        print("\n输入自然语言指令控制 Go2（quit 退出，reset 复位）")
        print("试试：向前走三步然后坐下 / 左转 / 打个招呼")
        while True:
            try:
                cmd = input("\n指令> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not cmd:
                continue
            if cmd.lower() in ("quit", "exit", "q"):
                break
            if cmd.lower() == "reset":
                sim.reset()
                sim.viewer_sync()
                print("[已复位]")
                continue
            run_once(brain, sim, cmd, logf)

    sim.close()
    print("已退出，会话日志在 logs/sessions/")


if __name__ == "__main__":
    main()
