import os
import sys
import requests
import hashlib
import shutil
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('updater.log'),
        logging.StreamHandler()
    ]
)

def download_file(url, save_path):
    """带进度显示的文件下载"""
    # ... 实现下载逻辑 ...

def verify_file(file_path, expected_hash):
    """校验文件完整性"""
    # ... 实现SHA256校验 ...

def backup_files(file_list):
    """创建备份"""
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    for f in file_list:
        shutil.copy2(f, backup_dir)

def run_update():
    """执行更新流程"""
    try:
        # 1. 获取更新配置
        config = requests.get("https://github.com/mayicome/mazongzhuiban.git/update.json").json()
        
        # 2. 创建备份
        file_list = [f['path'] for f in config['files']]
        backup_files(file_list)
        
        # 3. 下载并替换文件
        for file_info in config['files']:
            temp_path = file_info['path'] + ".tmp"
            download_file(file_info['url'], temp_path)
            verify_file(temp_path, file_info['sha256'])
            os.replace(temp_path, file_info['path'])
            
        logging.info("更新成功！")
        return True
    except Exception as e:
        logging.error(f"更新失败: {e}")
        return False

if __name__ == '__main__':
    if run_update():
        # 启动主程序
        os.execl(sys.executable, sys.executable, "mytrade_zhuizhangtingban.py", *sys.argv[1:])