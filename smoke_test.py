"""冒烟测试：不开窗口，验证 模型加载→关键帧站立→运动学移动→离屏渲染 全链路。
通过标准：脚本正常结束并输出 PASS，生成 smoke_test.png。"""
import os

import cv2

import config
from sim_backend import Go2Sim
from skill_api import Skill, validate_plan

os.chdir(config.PROJECT_ROOT)

sim = Go2Sim(headless=True)
print(f"[1] 模型加载成功: nq={sim.model.nq}, nu={sim.model.nu}, "
      f"home基座高度={sim.z_stand:.3f}m")

skills, warns, err = validate_plan(
    {"plan": [{"name": "Move", "params": {"vx": 0.4, "vy": 0, "vyaw": 0, "duration": 2.0}},
              {"name": "Sit", "params": {}}]})
assert err is None, f"校验器失败: {err}"
print(f"[2] 计划校验通过: {[str(s) for s in skills]}, warnings={warns}")

for s in skills:
    sim.execute(s, frame_cb=lambda: None)
print(f"[3] 技能执行完成，基座位移: dx={sim.base['x'] - sim.home[0]:.2f}m, "
      f"z={sim.base['z']:.3f}m（坐下降低）")

frame = sim.render_frame()
cv2.imwrite("smoke_test.png", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
print(f"[4] 离屏渲染成功: {frame.shape[1]}x{frame.shape[0]}, 已存 smoke_test.png")
sim.close()
print("PASS")
