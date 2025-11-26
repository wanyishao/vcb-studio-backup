import requests
import os
import time
import random
from bs4 import BeautifulSoup
from requests.exceptions import RequestException, ConnectionError, Timeout
from http.client import IncompleteRead

# --- 配置参数 ---
BASE_URL = "https://vcb-s.com"
START_NAV_PAGE = 1
# 定义需要强制更新文章页的页码范围 (Page 1, 2, 3)
FORCE_UPDATE_ARCHIVES_PAGES = range(1, 4) 
MIN_DELAY = 1        # 最小延迟（秒）
MAX_DELAY = 2       # 最大延迟（秒）
MAX_RETRIES = 3      # 最大重试次数
RETRY_DELAY = 5     # 重试等待时间（秒）

# --- 文件夹设置 ---
PAGE_DIR = "page"
ARCHIVES_DIR = "archives"

# 创建文件夹
os.makedirs(PAGE_DIR, exist_ok=True)
os.makedirs(ARCHIVES_DIR, exist_ok=True)

print(f"文件夹 '{PAGE_DIR}' 和 '{ARCHIVES_DIR}' 已创建/确认存在。")

# --- 核心下载函数（无变化，但为完整性保留） ---

def safe_download(url, filename, force_update=False):
    """
    以随机延迟安全地下载网页内容并保存到文件，包含重试机制。
    force_update=True 时，会强制重新下载并覆盖文件。
    返回 tuple (HTML内容, 状态码)
    """
    
    if os.path.exists(filename) and not force_update:
        # 文件存在且不需要强制更新，跳过下载并读取本地内容
        print(f"文件已存在，跳过下载: {filename}")
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read(), 200
        except Exception:
            print(f"!!! 警告: 尝试读取本地文件失败，将进行下载: {filename}")
            pass
            
    if force_update and os.path.exists(filename):
        os.remove(filename)
        print(f"文件存在，已删除准备强制更新: {filename}")

    
    for attempt in range(MAX_RETRIES):
        delay = random.randint(MIN_DELAY, MAX_DELAY)
        print(f"\n--- 尝试 {attempt + 1}/{MAX_RETRIES} 下载: {url} | 延迟: {delay}s ---")
        time.sleep(delay)

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            }
            
            with requests.get(url, headers=headers, timeout=30, stream=True) as response:
                
                if "Cloudflare" in response.text or "Checking your browser before accessing" in response.text:
                     print(f"!!! 警告: {url} 可能被 Cloudflare 拦截，请检查 IP/User-Agent 或增大延迟。")
                     return None, response.status_code

                if response.status_code == 200:
                    with open(filename, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    print(f"成功保存到: {filename}")
                    
                    # 为了提取链接，需要返回文本内容，从已保存的文件中读取
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            return f.read(), response.status_code
                    except Exception:
                        return None, response.status_code 
                else:
                    print(f"!!! 错误: {url} 下载失败, 状态码: {response.status_code}")
                    if attempt < MAX_RETRIES - 1:
                        print(f"等待 {RETRY_DELAY}s 后重试...")
                        time.sleep(RETRY_DELAY)
                    continue
        
        except (RequestException, ConnectionError, Timeout, IncompleteRead) as e:
            print(f"!!! 致命错误: 下载 {url} 时发生网络异常: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"等待 {RETRY_DELAY}s 后重试...")
                time.sleep(RETRY_DELAY)
            continue
            
        except Exception as e:
            print(f"!!! 致命错误: 发生未知异常: {e}")
            break

    return None, 0

def extract_archive_links(html_content):
    """
    从导航页 HTML 中提取文章页链接。（无变化）
    """
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    archive_links = []
    
    article_titles = soup.find_all('div', class_='title-article')
    
    for title_div in article_titles:
        link = title_div.find('a', href=True)
        if link and "/archives/" in link['href']:
            path_segment = link['href'].split(BASE_URL)[-1] 
            full_url = BASE_URL + path_segment
            archive_links.append(full_url)
            
    return sorted(list(set(archive_links)))

# --- 主程序逻辑 ---

all_extracted_archive_urls = {} 
page_num = START_NAV_PAGE

# 记录整个脚本开始时间
script_start_time = time.time()

# =========================================================================
# 阶段一：循环强制更新所有导航页（Page）并收集链接
# =========================================================================
print("==================== [阶段一] 开始强制更新所有导航页并收集链接 ====================")
phase_one_start_time = time.time() # 记录阶段一开始时间

while True:
    nav_url = f"{BASE_URL}/page/{page_num}"
    nav_filename = os.path.join(PAGE_DIR, f"{page_num}.html")
    
    print(f"\n==================== 尝试处理导航页: {page_num} ====================")
    
    # 导航页：强制更新所有 page/NUM 文件 (force_update=True)
    page_content, status_code = safe_download(nav_url, nav_filename, force_update=True)
    
    if status_code != 200:
        print(f"导航页 {page_num} 下载失败或返回状态码 {status_code}，完成导航页探索。")
        break
        
    try:
        if page_content is None:
             # 如果下载函数返回 None 但状态码是 200 (例如解析失败)，从文件读取
             with open(nav_filename, 'r', encoding='utf-8') as f:
                page_content = f.read()

        extracted_links = extract_archive_links(page_content)
    except Exception as e:
        print(f"!!! 警告: 无法解析导航页 {page_num} 内容，跳过链接提取: {e}")
        extracted_links = []


    if not extracted_links and page_num > START_NAV_PAGE:
        print(f"导航页 {page_num} 未找到任何文章链接，完成导航页探索。")
        break

    for link in extracted_links:
        if link not in all_extracted_archive_urls:
            all_extracted_archive_urls[link] = page_num
        
    print(f"从导航页 {page_num} 提取到 {len(extracted_links)} 个文章链接。")
    print(f"当前累计提取到 {len(all_extracted_archive_urls)} 个不重复的文章链接。")
    
    page_num += 1
    
    batch_delay = random.randint(1, 2)
    print(f"等待 {batch_delay}s 后继续处理下一页...")
    time.sleep(batch_delay)

# 记录阶段一结束时间
phase_one_end_time = time.time()
phase_one_duration = phase_one_end_time - phase_one_start_time

print(f"==================== [阶段一] 完成，总计找到 {len(all_extracted_archive_urls)} 个文章链接。用时: {int(phase_one_duration // 60)} 分钟 {int(phase_one_duration % 60)} 秒 ====================\n")


# =========================================================================
# 阶段二：下载所有文章页（Archives），针对 page/1-3 强制更新
# =========================================================================
print("==================== [阶段二] 开始下载文章页 (Page 1-3 强制更新) ====================")
phase_two_start_time = time.time() # 记录阶段二开始时间

total_links = len(all_extracted_archive_urls)
current_index = 0

for archive_url, source_page in all_extracted_archive_urls.items():
    current_index += 1
    
    archive_id = archive_url.split('/')[-1] if archive_url.split('/')[-1] else archive_url.split('/')[-2]
    archive_filename = os.path.join(ARCHIVES_DIR, f"{archive_id}.html")
    
    should_force_update = (source_page in FORCE_UPDATE_ARCHIVES_PAGES)
    
    action = "强制更新" if should_force_update else "初次下载/存在则跳过"
    
    print(f"\n--- 正在处理第 {current_index} / {total_links} 个文章页 ({action}, 来自 Page {source_page}) ---")
    
    safe_download(archive_url, archive_filename, force_update=should_force_update)

# 记录阶段二结束时间
phase_two_end_time = time.time()
phase_two_duration = phase_two_end_time - phase_two_start_time

print(f"\n==================== [阶段二] 完成。用时: {int(phase_two_duration // 60)} 分钟 {int(phase_two_duration % 60)} 秒 ====================")


# --- 总结报告 ---
script_end_time = time.time()
total_duration = script_end_time - script_start_time

print("\n==================== 任务总结 ====================")
print(f"总共处理了 {page_num - 1} 页导航页。")
print(f"共尝试下载/更新了 {total_links} 个文章页。")
print(f"--------------------------------------------------")
print(f"阶段一 (导航页) 总用时: {int(phase_one_duration // 60)}m {int(phase_one_duration % 60)}s")
print(f"阶段二 (文章页) 总用时: {int(phase_two_duration // 60)}m {int(phase_two_duration % 60)}s")
print(f"脚本总运行用时: {int(total_duration // 60)}m {int(total_duration % 60)}s")
print("==================================================")
