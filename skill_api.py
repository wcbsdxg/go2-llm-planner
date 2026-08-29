"""技能层：白名单 + 安全钳位 + 校验。

技能名与 unitree_sdk2py 的 SportClient 对齐（Move/BalanceStand/Sit/StandUp/
StopMove/Hello），这样今天写在 MuJoCo 演示后端上的上层代码，将来换到真机或
RL 策略后端时一行不用改——只换执行器实现。
"""
import math
from dataclasses import dataclass, field

from config import SAFETY

# 技能白名单：name -> 参数类型表
SKILL_SCHEMA = {
    "BalanceStand": {},
    "Move": {"vx": float, "vy": float, "vyaw": float, "duration": float},
    "StopMove": {},
    "Sit": {},
    "StandUp": {},
    "Hello": {},
}


@dataclass
class Skill:
    name: str
    params: dict = field(default_factory=dict)

    def __str__(self):
        if self.params:
            inner = ", ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
                              for k, v in self.params.items())
            return f"{self.name}({inner})"
        return f"{self.name}()"


def _coerce_num(value):
    """把 LLM 可能输出的数字变体（int/float/数字字符串）统一转 float，失败返回 None。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # 拒绝 NaN/Inf：钳位比较对 NaN 恒为 False 会失效，进而污染基座位姿与会话日志
    return v if math.isfinite(v) else None


def validate_plan(raw) -> tuple[list[Skill], list[str], str | None]:
    """校验并修正 LLM 输出的计划。

    返回 (skills, warnings, error)：error 非 None 表示计划不可用，需要让 LLM 重试。
    warnings 是被钳位/被修正的记录，全部写入日志——过程质量的素材。
    """
    warnings: list[str] = []
    if not isinstance(raw, dict) or not isinstance(raw.get("plan"), list):
        return [], warnings, "输出必须是 {\"plan\": [...]} 格式"

    plan = raw["plan"]
    if not plan:
        return [], warnings, "plan 为空，至少需要一个技能"
    if len(plan) > SAFETY["max_skills"]:
        warnings.append(f"计划含 {len(plan)} 个技能，超过上限 {SAFETY['max_skills']}，已截断")
        plan = plan[: SAFETY["max_skills"]]

    skills: list[Skill] = []
    for i, item in enumerate(plan):
        if not isinstance(item, dict) or "name" not in item:
            return [], warnings, f"第 {i + 1} 项缺少 name 字段"
        name = str(item["name"])
        if name not in SKILL_SCHEMA:
            return [], warnings, f"未知技能 '{name}'，只能使用 {list(SKILL_SCHEMA)}"
        params_in = item.get("params")
        if params_in is None:
            params_in = {}
        if not isinstance(params_in, dict):
            return [], warnings, f"技能 {name} 的 params 必须是对象"

        fixed: dict = {}
        for pname, ptype in SKILL_SCHEMA[name].items():
            missing = pname not in params_in
            raw_v = params_in.get(pname, 0.0 if ptype is float else None)
            if ptype is float:
                v = _coerce_num(raw_v)
                if v is None:
                    return [], warnings, f"技能 {name} 参数 {pname} 不是数字: {raw_v!r}"
                if pname == "duration" and v <= 0:
                    return [], warnings, f"技能 {name} 参数 duration 必须为正数，收到 {raw_v!r}"
                if missing:
                    warnings.append(f"{name}.{pname} 未提供，已默认 0.0")
                limit = SAFETY.get(pname)
                if limit is not None and abs(v) > limit:
                    clamped = max(-limit, min(limit, v))
                    warnings.append(
                        f"{name}.{pname}={v:.2f} 超出安全范围 ±{limit}，已钳位为 {clamped:.2f}")
                    v = clamped
                fixed[pname] = v
        # LLM 多给的参数直接丢弃并记录
        extra = set(params_in) - set(SKILL_SCHEMA[name])
        if extra:
            warnings.append(f"{name} 的多余参数已丢弃: {sorted(extra)}")
        skills.append(Skill(name, fixed))
    return skills, warnings, None
