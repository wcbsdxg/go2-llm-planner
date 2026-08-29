"""验收测试：5 条标准指令过真实 LLM→规划→执行全链路（无窗口）。

模型 pull 好之后运行：
    python acceptance_test.py
产出 logs/acceptance_*.md 验收报告（LLM原始输出+计划+安全修正+执行结果+判定），
是评审材料"过程质量"的核心证据，也是录屏时的对照脚本。
"""
import os
from datetime import datetime

from config import PROJECT_ROOT
from llm_brain import LLMBrain, pick_backend
from sim_backend import Go2Sim

COMMANDS = [
    ("A1 基础移动", "向前走", "应输出 Move 且顺利执行"),
    ("A2 转向与幅度", "左转90度", "vyaw×duration 应接近 1.57 rad（90度）"),
    ("A3 多段组合", "向前走三步，右转，再向前走三步", "应拆成 3 个以上技能，轨迹近似『走-转-走』"),
    ("A4 多技能衔接", "走过去然后坐下", "Move→(StopMove)→Sit，最终坐姿"),
    ("A5 模糊指令", "随便动动", "考察 LLM 自行决策是否合理、是否越权（人工判定）"),
]


def main():
    os.chdir(PROJECT_ROOT)
    os.makedirs("logs", exist_ok=True)
    backend, model = pick_backend()
    print(f"[LLM] backend={backend} model={model}")
    brain = LLMBrain(backend, model=model)
    sim = Go2Sim(headless=True)

    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    lines = [f"# 验收报告 {stamp}\n", f"- 后端：{backend} / {model}\n",
             "- 判定标准：PASS=计划合法且执行无异常；A5 另需人工确认行为合理性\n"]

    results = []
    for name, cmd, expect in COMMANDS:
        print(f"\n===== {name}: {cmd} =====")
        lines += [f"\n## {name}\n", f"- 指令：`{cmd}`\n", f"- 预期：{expect}\n"]
        ok = False
        raw = ""
        try:
            skills, warnings, raw = brain.plan(cmd)
        except Exception as e:
            lines.append(f"- 规划：**失败**（{e}）\n")
            print(f"[规划失败] {e}")
        else:
            ok = True
            lines.append(f"- LLM原始输出：`{raw.strip()[:300]}`\n")
            lines.append("- 计划：\n")
            for s in skills:
                lines.append(f"  - {s}\n")
                try:
                    desc = sim.execute(s)
                    print(f"[执行] {s} —— {desc}")
                except Exception as e:
                    ok = False
                    lines.append(f"    - 执行**异常**：{e}\n")
                    print(f"[执行异常] {e}")
                    break
            if warnings:
                lines.append(f"- 安全修正：{warnings}\n")
        if name.startswith("A5"):
            verdict = "PASS*(需人工确认)" if ok else "FAIL"
        else:
            verdict = "PASS" if ok else "FAIL"
        results.append((name, verdict))
        lines.append(f"- 判定：**{verdict}**\n")
        sim.reset()
        print(f"[判定] {verdict}")

    lines.append("\n## 汇总\n\n| 项目 | 判定 |\n|---|---|\n")
    for name, verdict in results:
        lines.append(f"| {name} | {verdict} |\n")
    lines.append("\n> *A5 为模糊指令，\"PASS\"仅表示执行无异常，行为合理性需人工确认。\n")
    report = os.path.join("logs", f"acceptance_{stamp}.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    sim.close()
    print(f"\n验收报告已写入 {report}")
    print("汇总：" + "，".join(f"{n.split()[0]}={v}" for n, v in results))


if __name__ == "__main__":
    main()
