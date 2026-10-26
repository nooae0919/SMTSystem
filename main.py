import os
import subprocess

# 切换到当前程序所在的目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 直接调用系统命令启动 app.py
# shell=True 允许像在 CMD 里一样执行命令
subprocess.Popen(["python", "app.py"], shell=True)
