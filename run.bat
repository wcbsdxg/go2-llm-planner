@echo off
rem 启动器：双击或命令行运行，自动使用项目 venv 的 python（系统 python 是 Store 占位程序，静默无输出）
cd /d %~dp0
.venv\Scripts\python.exe planner.py %*
