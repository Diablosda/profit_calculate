#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码回滚脚本
用于回滚Python文件到之前的版本
"""

import os
import sys
import subprocess


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


def show_history():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    os.chdir(project_root)
    
    print("=" * 60)
    print("提交历史记录 (最近20条)")
    print("=" * 60)
    
    returncode, stdout, stderr = run_command('git log --oneline -20')
    if returncode == 0:
        print(stdout)
    else:
        print(f"错误: 无法获取历史记录\n{stderr}")


def rollback_to_commit(commit_hash, hard=False):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    os.chdir(project_root)
    
    print(f"\n正在回滚到提交: {commit_hash}")
    
    if hard:
        confirm = input("警告: 硬回滚会丢失所有未提交的修改! 确认继续? (y/N): ")
        if confirm.lower() != 'y':
            print("操作已取消")
            return False
        
        returncode, stdout, stderr = run_command(f'git reset --hard {commit_hash}')
    else:
        returncode, stdout, stderr = run_command(f'git reset --soft {commit_hash}')
    
    if returncode == 0:
        print("\n✓ 回滚成功!")
        return True
    else:
        print(f"\n✗ 回滚失败:\n{stderr}")
        return False


def show_file_diff(commit1, commit2=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    os.chdir(project_root)
    
    if commit2:
        cmd = f'git diff {commit1} {commit2} -- *.py'
    else:
        cmd = f'git diff {commit1} -- *.py'
    
    returncode, stdout, stderr = run_command(cmd)
    if returncode == 0:
        print("=" * 60)
        print("Python文件差异")
        print("=" * 60)
        print(stdout)
    else:
        print(f"错误: 无法获取差异\n{stderr}")


def restore_file(file_path, commit_hash):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    os.chdir(project_root)
    
    print(f"正在恢复文件 '{file_path}' 到提交 {commit_hash}")
    returncode, stdout, stderr = run_command(f'git checkout {commit_hash} -- {file_path}')
    
    if returncode == 0:
        print(f"\n✓ 文件 '{file_path}' 已恢复!")
        return True
    else:
        print(f"\n✗ 恢复失败:\n{stderr}")
        return False


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("=" * 60)
        print("代码回滚工具")
        print("=" * 60)
        print("\n使用方法:")
        print("  python scripts/rollback.py history              # 查看历史记录")
        print("  python scripts/rollback.py diff <commit>        # 查看与某提交的差异")
        print("  python scripts/rollback.py file <file> <commit> # 恢复单个文件")
        print("  python scripts/rollback.py soft <commit>        # 软回滚")
        print("  python scripts/rollback.py hard <commit>        # 硬回滚")
        print("\n示例:")
        print("  python scripts/rollback.py history")
        print("  python scripts/rollback.py diff HEAD~1")
        print("  python scripts/rollback.py file matching_tools_new.py HEAD~1")
        print("\n")
        show_history()
    elif sys.argv[1] == "history":
        show_history()
    elif sys.argv[1] == "diff" and len(sys.argv) >= 3:
        commit = sys.argv[2]
        commit2 = sys.argv[3] if len(sys.argv) >= 4 else None
        show_file_diff(commit, commit2)
    elif sys.argv[1] == "file" and len(sys.argv) >= 4:
        file_path = sys.argv[2]
        commit_hash = sys.argv[3]
        restore_file(file_path, commit_hash)
    elif sys.argv[1] == "soft" and len(sys.argv) >= 3:
        rollback_to_commit(sys.argv[2], hard=False)
    elif sys.argv[1] == "hard" and len(sys.argv) >= 3:
        rollback_to_commit(sys.argv[2], hard=True)
    else:
        print("错误: 参数不正确")
        print("\n使用方法:")
        print("  python scripts/rollback.py history")
        print("  python scripts/rollback.py diff <commit>")
        print("  python scripts/rollback.py file <file> <commit>")
        print("  python scripts/rollback.py soft <commit>")
        print("  python scripts/rollback.py hard <commit>")
