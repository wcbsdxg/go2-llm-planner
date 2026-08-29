"""无窗口录制 demo 视频：把预定义技能序列渲染成 mp4，存到 videos/。

不依赖 LLM 和 3D 窗口，今天最先能跑通的东西；等 Ollama 就绪后可加 --llm
用真实 LLM 规划录屏（推荐用 OBS 录 planner.py 的窗口，画面信息更全）。
"""
import argparse
import os

import cv2

import config
from sim_backend import Go2Sim
from skill_api import Skill

# 键名用 ASCII：Windows 下 cv2.VideoWriter 打不开中文路径，视频文件会静默缺失
DEMO_PLANS = {
    "forward": [Skill("Move", {"vx": 0.4, "vy": 0, "vyaw": 0, "duration": 2.0})],
    "turn_left": [Skill("Move", {"vx": 0, "vy": 0, "vyaw": 0.8, "duration": 2.0})],
    "walk_and_sit": [
        Skill("Move", {"vx": 0.4, "vy": 0, "vyaw": 0, "duration": 2.5}),
        Skill("StopMove", {}),
        Skill("Sit", {}),
    ],
    "hello": [Skill("Hello", {})],
}


def record(name, skills, out_dir):
    sim = Go2Sim(headless=True)
    frames_path = os.path.join(out_dir, f"{name}.mp4")
    writer = None
    def frame_cb():
        nonlocal writer
        frame = cv2.cvtColor(sim.render_frame(), cv2.COLOR_RGB2BGR)
        if writer is None:
            writer = cv2.VideoWriter(frames_path, cv2.VideoWriter_fourcc(*"mp4v"),
                                     config.FPS, (frame.shape[1], frame.shape[0]))
        writer.write(frame)
    for s in skills:
        sim.execute(s, frame_cb=frame_cb)
    if writer is not None:
        writer.release()
    print(f"已生成 videos/{name}.mp4")
    sim.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只录某一个场景，如 --only forward")
    args = ap.parse_args()
    out_dir = os.path.join(config.PROJECT_ROOT, "videos")
    os.makedirs(out_dir, exist_ok=True)
    for name, skills in DEMO_PLANS.items():
        if args.only and name != args.only:
            continue
        record(name, skills, out_dir)


if __name__ == "__main__":
    main()
