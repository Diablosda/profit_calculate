#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码版本保存脚本
用于保存Python文件的版本控制
"""

import os
import sys
import subprocess
from datetime import datetime


def run_command(cmd, cwd=None):
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, '', str(e)


def save_version(message=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    os.chdir(project_root)
    
    print("=" * 60)
    print("代码版本保存工具 (仅监测.py文件)")
    print("=" * 60)
    
    returncode, stdout, stderr = run_command('git status --porcelain *.py')
    if returncode != 0:
        print(f"错误: 无法检查Git状态\n{stderr}")
        return False
    
    py_changes = []
    for line in stdout.splitlines():
        if line.strip() and not line.endswith('.ipynb'):
            py_changes.append(line)
    
    if not py_changes:
        print("没有检测到Python文件(.py)的修改")
        return True
    
    print("\n检测到以下Python文件变更:")
    for line in py_changes:
        print(line)
    
    if not message:
        print("\n请输入本次修改描述 (直接回车使用默认):")
        try:
            user_input = input("> ").strip()
            if user_input:
                message = user_input
            else:
                message = f"update: 代码更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        except KeyboardInterrupt:
            print("\n操作已取消")
            return False
    
    print(f"\n提交信息: {message}")
    print("\n正在添加所有修改的Python文件...")
    returncode, stdout, stderr = run_command('git add *.py')
    
    print("正在提交...")
    returncode, stdout, stderr = run_command(f'git commit -m "{message}"')
    
    if returncode == 0:
        print("\n✓ 版本保存成功!")
        returncode, stdout, stderr = run_command('git log --oneline -1')
        print(f"\n最新提交: {stdout.strip()}")
        return True
    else:
        print(f"\n✗ 提交失败:\n{stderr}")
        return False


def show_history():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    os.chdir(project_root)
    
    print("=" * 60)
    print("提交历史记录")
    print("=" * 60)
    
    returncode, stdout, stderr = run_command('git log --oneline -20')
    if returncode == 0:
        print(stdout)
    else:
        print(f"错误: 无法获取历史记录\n{stderr}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "history":
            show_history()
        else:
            message = " ".join(sys.argv[1:])
            save_version(message)
    else:
        save_version()
