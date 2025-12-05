import os
import re
import json
import logging
import gc
from datetime import datetime
import requests
import warnings
import urllib3
import time
import random 
from concurrent.futures import ThreadPoolExecutor

# 忽略 SSL 警告
warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)

# ================= 配置区域 =================
BATCH_SIZE = 100
TIMEOUT = 8
MAX_WORKERS = 8  # [修改] 根据您的要求设置为 8 线程
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_FILE = os.path.join(BASE_DIR, 'source.m3u')
VALID_FILE = os.path.join(BASE_DIR, 'valid.m3u')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

HEADERS = {"User-Agent": "okhttp/5.2.0"}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = {"auto_check": True, "interval_hours": 12, "sources": {}}
config = {}

def load_config():
    global config
    env_config = os.environ.get("IPTV_CONFIG")
    if env_config:
        try:
            config = json.loads(env_config)
            if "sources" not in config:
                config["sources"] = {}
            logger.info("Configuration loaded from environment variable IPTV_CONFIG.")
            return
        except Exception as e:
            logger.error(f"Failed to parse IPTV_CONFIG from env: {e}")

    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if "sources" not in config:
                    config["sources"] = {}
        else:
            if not config:
                config = DEFAULT_TEMPLATE.copy()
    except Exception as e:
        logger.error(f"Failed to load config {CONFIG_FILE}: {e}")
        config = DEFAULT_TEMPLATE.copy()

load_config()

class IPTVChecker:
    
    def download_and_merge(self):
        """
        第一阶段：下载并立即生成 source.m3u
        """
        sources = config.get("sources", {})
        if not sources:
            logger.warning("No sources found in config.")
            return False
        logger.info(f"Starting download of {len(sources)} sources...")

        # [关键] 立即写入 source.m3u，无需等待后续检测
        with open(SOURCE_FILE, 'w', encoding='utf-8') as f_out:
            f_out.write("#EXTM3U\n")
            session = requests.Session()
            
            for category, url in sources.items():
                if not url.startswith("http"):
                    continue
                try:
                    logger.info(f"Downloading: {category}")
                    response = session.get(url, timeout=30, headers=HEADERS, verify=False)
                    
                    if response.status_code == 200:
                        f_out.write(f"\n#------ {category} ------\n\n")
                        text = response.text
                        for line in text.splitlines():
                            line = line.strip()
                            if not line or line.startswith("#EXTM3U"):
                                continue
                            
                            if line.startswith("#EXTINF"):
                                match = re.search(r',(.*)$', line)
                                name = match.group(1).strip() if match else "Unknown"
                                f_out.write(f'#EXTINF:-1 group-title="{category}",{name}\n')
                            elif "," in line and not line.startswith("#"):
                                p = line.split(",", 1)
                                if len(p) == 2 and p[1].strip().startswith("http"):
                                    f_out.write(f'#EXTINF:-1 group-title="{category}",{p[0].strip()}\n')
                                    f_out.write(f'{p[1].strip()}\n')
                            elif not line.startswith("#"):
                                f_out.write(f'{line}\n')
                        
                        # 强制刷新缓冲区，确保文件写入磁盘
                        f_out.flush() 
                except Exception as e:
                    logger.error(f"Failed to download source [{category}]: {e}")
        
        logger.info(f"✅ Source file generated successfully: {SOURCE_FILE}")
        return True

    def check_url(self, session, item):
        try:
            r = session.head(item['url'], timeout=TIMEOUT, headers=HEADERS, verify=False, allow_redirects=True)
            if r.status_code >= 400 and r.status_code != 405:
                return None
            
            r_get = session.get(item['url'], timeout=TIMEOUT, headers=HEADERS, verify=False, stream=True, allow_redirects=True)
            
            if r_get.status_code != 200:
                r_get.close()
                return None
            
            chunk = r_get.raw.read(1024)
            r_get.close()
            
            if not chunk or b'<!doctype html' in chunk.lower():
                return None

            item['url'] = r_get.url
            
            return item
        except Exception:
            return None

    def _parse_source_file_blocking(self):
        with open(SOURCE_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        playlist = []
        curr_g, curr_n = "Unknown", "Unknown"
        
        # 顺序计数器
        order_index = 0
        
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                g = re.search(r'group-title="(.*?)"', line)
                if g:
                    curr_g = g.group(1)
                n = re.search(r',(.*)$', line)
                if n:
                    curr_n = n.group(1).strip()
            elif line and not line.startswith("#"):
                playlist.append({
                    "_uid": order_index, 
                    "name": curr_n, 
                    "url": line, 
                    "group": curr_g
                })
                order_index += 1
        return playlist

    def run_task(self, trigger="manual"):
        load_config()
            
        # 1. 下载并生成 source.m3u
        if not self.download_and_merge():
            return

        logger.info("Parsing source file for checking...")
        
        try:
            playlist = self._parse_source_file_blocking()
        except Exception as e:
            logger.error(f"Failed to parse file: {e}")
            return

        # 2. 乱序检测（防封）
        random.shuffle(playlist)

        total_items = len(playlist)
        logger.info(f"Total channels: {total_items}. Starting check (Shuffle + {MAX_WORKERS} Threads)...")
        
        valid_items = []
        session = requests.Session()
        
        # [修改] 使用 MAX_WORKERS (8)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for i in range(0, total_items, BATCH_SIZE):
                batch = playlist[i : i + BATCH_SIZE]
                
                results_iterator = executor.map(lambda item: self.check_url(session, item), batch)
                results = list(results_iterator)
                
                for res in results:
                    if res:
                        valid_items.append(res)
                
                checked_count = i + len(batch)
                progress = int((checked_count / total_items) * 100)
                logger.info(f"Progress: {progress}% ({len(valid_items)} valid / {checked_count} checked)")

                del results
                gc.collect()

        # 3. 生成 valid.m3u（按原始顺序还原）
        logger.info("Generating valid playlist...")
        with open(VALID_FILE, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            
            valid_items.sort(key=lambda x: x["_uid"])
            
            for item in valid_items:
                f.write(f'#EXTINF:-1 group-title="{item["group"]}",{item["name"]}\n{item["url"]}\n')

        logger.info(f"Task finished. Valid sources: {len(valid_items)}. Saved to {VALID_FILE}")

checker = IPTVChecker()

if __name__ == '__main__':
    logger.info("Script launched via CLI. Starting task...")
    checker.run_task(trigger="manual_cli")
