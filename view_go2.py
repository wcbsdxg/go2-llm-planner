"""步骤0自检：打开3D窗口看 Go2 站立 + 原地坐下/起立循环。按 Ctrl+C 退出。"""
import time

from sim_backend import Go2Sim
from skill_api import Skill

sim = Go2Sim(headless=False)
sim.start_viewer()
print("Go2 已加载，3秒后开始坐下-起立循环，Ctrl+C 退出")
time.sleep(3)
try:
    while sim.viewer_running():
        sim.execute(Skill("Sit"))
        time.sleep(0.5)
        sim.execute(Skill("StandUp"))
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
sim.close()
