"""MuJoCo Go2 仿真后端（演示版）。

设计说明（README 同步说明，请保持一致）：
本后端为"演示后端"——Move 通过运动学方式直接插值基座位姿实现，四条腿保持
站立关键帧，因此看起来是"滑行"。这是刻意的 mock-first 设计：先让 LLM 规划
链路完整跑通，第二阶段再把执行器替换为真实 RL 步态策略（MJX / Isaac Lab），
上层 skill_api 与 planner 代码零改动。
"""
import math
import time

import mujoco
import numpy as np

import config


class Go2Sim:
    def __init__(self, headless: bool = True):
        # headless 参数保留用于兼容旧调用；是否开窗口实际由 start_viewer() 决定
        self.model = mujoco.MjModel.from_xml_path(config.GO2_SCENE)
        self.data = mujoco.MjData(self.model)
        # 'home' 关键帧 = 四腿支撑的站立姿态，是所有动作的基准；按名字取，不依赖索引顺序
        home_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_KEY, "home")
        if home_id < 0:
            raise ValueError("scene.xml 缺少名为 'home' 的关键帧")
        self._home_key = home_id
        self.home = self.model.key_qpos[home_id].copy()
        self.z_stand = float(self.home[2])
        self.z_sit = self.z_stand * 0.55
        self.base = {"x": float(self.home[0]), "y": float(self.home[1]),
                     "yaw": 0.0, "z": self.z_stand}
        self._viewer = None
        self._renderer = None
        self._cam = mujoco.MjvCamera()
        self._cam.lookat[:] = [self.base["x"], self.base["y"], 0.2]
        self._cam.distance = 2.2
        self._cam.azimuth = 135
        self._cam.elevation = -22
        self.reset()

    # ---------- 基础 ----------
    def reset(self):
        mujoco.mj_resetDataKeyframe(self.model, self.data, self._home_key)
        mujoco.mj_forward(self.model, self.data)
        self.base = {"x": float(self.home[0]), "y": float(self.home[1]),
                     "yaw": 0.0, "z": self.z_stand}

    def _write_base(self):
        q = self.data.qpos
        q[0], q[1] = self.base["x"], self.base["y"]
        q[2] = self.base["z"]
        half = self.base["yaw"] / 2.0
        q[3:7] = [math.cos(half), 0.0, 0.0, math.sin(half)]
        self.data.qvel[:] = 0
        # 运动学演示：只改基座 qpos，腿部关节（qpos[7:]）保持 home 关键帧不动。
        # 这里只调用 mj_forward、不执行 actuator，因此不写 self.data.ctrl。
        mujoco.mj_forward(self.model, self.data)

    def _follow_camera(self):
        self._cam.lookat[:] = [self.base["x"], self.base["y"], 0.2]

    # ---------- 观看 / 渲染 ----------
    def start_viewer(self):
        import mujoco.viewer
        self._viewer = mujoco.viewer.launch_passive(self.model, self.data)
        return self._viewer

    def viewer_sync(self):
        if self._viewer is not None and self._viewer.is_running():
            self._follow_camera()
            v = self._viewer.cam
            v.lookat[:] = self._cam.lookat
            v.distance, v.azimuth, v.elevation = (
                self._cam.distance, self._cam.azimuth, self._cam.elevation)
            self._viewer.sync()

    def viewer_running(self) -> bool:
        return self._viewer is not None and self._viewer.is_running()

    def _ensure_renderer(self):
        if self._renderer is None:
            # Menagerie 模型默认离屏缓冲 640px，渲染前调大到 720p
            self.model.vis.global_.offwidth = config.RENDER_WIDTH
            self.model.vis.global_.offheight = config.RENDER_HEIGHT
            self._renderer = mujoco.Renderer(
                self.model, height=config.RENDER_HEIGHT, width=config.RENDER_WIDTH)
        return self._renderer

    def render_frame(self) -> np.ndarray:
        r = self._ensure_renderer()
        self._follow_camera()
        r.update_scene(self.data, camera=self._cam)
        return r.render()

    def close(self):
        if self._viewer is not None:
            self._viewer.close()
        if self._renderer is not None:
            self._renderer.close()

    # ---------- 技能实现（演示后端）----------
    def _animate(self, duration, update, frame_cb=None, realtime=True):
        """以 1/FPS 的步长把 duration 秒的动作演出来。

        update(t01) 在每帧被调用（t01 为进度 0~1），运动学模式下每帧一次
        mj_forward 足够，不需要小步长动力学积分。
        """
        frames = max(1, int(round(duration * config.FPS)))
        frame_cb = frame_cb or (self.viewer_sync if self._viewer else None)
        for i in range(1, frames + 1):
            update(i / frames)
            self._write_base()
            if frame_cb:
                frame_cb()
            if realtime:
                time.sleep(1.0 / config.FPS)

    def _move(self, vx, vy, vyaw, duration, frame_cb=None):
        dt = 1.0 / config.FPS
        def update(t01):
            yaw = self.base["yaw"] + vyaw * dt
            self.base["yaw"] = yaw
            self.base["x"] += (vx * math.cos(yaw) - vy * math.sin(yaw)) * dt
            self.base["y"] += (vx * math.sin(yaw) + vy * math.cos(yaw)) * dt
        self._animate(duration, update, frame_cb)

    def _change_height(self, target, frame_cb=None):
        start = self.base["z"]
        def update(t01):
            self.base["z"] = start + (target - start) * t01
        self._animate(1.0, update, frame_cb)

    def execute(self, skill, frame_cb=None) -> str:
        """执行单个技能，返回给上层看的执行说明。"""
        n, p = skill.name, skill.params
        if n == "Move":
            self._move(p["vx"], p["vy"], p["vyaw"], p["duration"], frame_cb)
            return f"移动 {p['duration']}s (vx={p['vx']:.2f}, vy={p['vy']:.2f}, vyaw={p['vyaw']:.2f})"
        if n == "BalanceStand":
            self._animate(0.5, lambda t: None, frame_cb)
            return "原地站立保持平衡"
        if n == "StopMove":
            self._animate(0.3, lambda t: None, frame_cb)
            return "停止移动"
        if n == "Sit":
            self._change_height(self.z_sit, frame_cb)
            return "坐下"
        if n == "StandUp":
            self._change_height(self.z_stand, frame_cb)
            return "起立"
        if n == "Hello":
            def wiggle(t01):
                self.base["yaw"] += 0.06 * math.sin(t01 * 6 * math.pi)
            self._animate(1.5, wiggle, frame_cb)
            return "打招呼"
        return f"技能 {n} 未实现"
