import os
import sys
import configparser
import requests
import json
import re
import html
import shutil
import time
import signal
import ctypes
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


def enable_windows_ansi():
    if sys.platform != 'win32':
        return
    kernel32 = ctypes.windll.kernel32
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    for handle_id in (-11, -12):
        handle = kernel32.GetStdHandle(handle_id)
        if handle == -1:
            continue
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)


class Colors:
    """终端颜色输出"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """打印标题"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")


def print_section(text):
    """打印分节"""
    print(f"\n{Colors.OKCYAN}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")


def print_success(text):
    """打印成功信息"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    """打印错误信息"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text):
    """打印警告信息"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text):
    """打印信息"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def get_base_path():
    """获取程序的基础路径，兼容打包前和打包后的情况"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def load_config():
    config = configparser.ConfigParser()
    base_path = get_base_path()
    config_path = os.path.join(base_path, 'config.ini')
    config.read(config_path, encoding='utf-8')
    return config


def get_wav_files(base_path):
    """获取指定路径下的WAV文件"""
    voices_dir = os.path.join(base_path, 'media', 'voices')
    if not os.path.exists(voices_dir):
        print_error(f"目录不存在: {voices_dir}")
        return []
    return [os.path.join(voices_dir, f) for f in os.listdir(voices_dir) if f.endswith('.wav')]


def transcribe_audio(file_path, api_url, api_key, model, retry_count=3, retry_interval=2):
    url = f"{api_url}/v1/audio/transcriptions"
    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    
    file_name = os.path.basename(file_path)
    
    for attempt in range(retry_count):
        try:
            with open(file_path, 'rb') as audio_file:
                files = {
                    'file': (file_name, audio_file, 'audio/wav')
                }
                data = {
                    'model': model
                }
                
                response = requests.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                
                result = response.json()
                text = result.get('text', '')
                
                if text:
                    return text
                else:
                    with print_lock:
                        print_warning(f"[{file_name}] 返回结果为空 (第{attempt + 1}次尝试)")
                    if attempt < retry_count - 1:
                        time.sleep(retry_interval)
        except requests.exceptions.RequestException as e:
            with print_lock:
                print_error(f"[{file_name}] 请求失败 (第{attempt + 1}次尝试)")
            if attempt < retry_count - 1:
                time.sleep(retry_interval)
        except Exception as e:
            with print_lock:
                print_error(f"[{file_name}] 处理出错 (第{attempt + 1}次尝试)")
            if attempt < retry_count - 1:
                time.sleep(retry_interval)
    
    with print_lock:
        print_error(f"[{file_name}] 重试 {retry_count} 次后失败")
    return ''


# 全局变量用于跟踪进度
interrupted = False

# 线程锁用于保护共享资源
print_lock = Lock()
result_lock = Lock()

def signal_handler(signum, frame):
    """处理中断信号"""
    global interrupted
    if not interrupted:
        interrupted = True
        print(f"\n{Colors.WARNING}\n⚠ 收到中断信号，程序即将退出{Colors.ENDC}")
        print_info("已转换的结果已自动保存到文件")
        sys.exit(0)


def register_signal_handler():
    """注册中断信号处理器"""
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception as e:
        print_warning(f"无法注册信号处理器: {e}")





def delete_wav_file(wav_path):
    """删除原始音频文件"""
    try:
        if os.path.exists(wav_path):
            os.remove(wav_path)
            return True
        return False
    except Exception as e:
        with print_lock:
            print_error(f"删除音频文件时出错: {os.path.basename(wav_path)}")
        return False


def replace_single_voice_message(html_content, wav_name, text):
    """在内存中替换单个语音消息"""
    marker = "window.WEFLOW_DATA = ["
    start_index = html_content.find(marker)
    if start_index == -1:
        return html_content, False

    array_start = start_index + len(marker)
    array_end = html_content.find("];", array_start)
    if array_end == -1:
        return html_content, False

    array_body = html_content[array_start:array_end].strip()
    if array_body:
        json_text = "[" + array_body.rstrip(",") + "]"
        try:
            items = json.loads(json_text)
        except json.JSONDecodeError as exc:
            print_error(f"HTML 数据解析失败: {exc}")
            return html_content, False
    else:
        items = []

    modified = False
    for item in items:
        body = item.get("b")
        if not isinstance(body, str):
            continue
        if "[语音消息]" not in body:
            continue
        match = re.search(r'src="([^"]+\.wav)"', body)
        if not match:
            continue
        match_wav_name = Path(match.group(1)).name
        if match_wav_name == wav_name:
            safe_text = html.escape(text, quote=True)
            new_body = body.replace("[语音消息]", f"[语音转文字-{safe_text}]")
            if new_body != body:
                item["b"] = new_body
                modified = True
                break

    if modified:
        new_array = ",\n".join(json.dumps(item, ensure_ascii=False) for item in items)
        html_content = html_content[:start_index] + marker + "\n" + new_array + "\n" + html_content[array_end:]

    return html_content, modified


def load_html_files(base_path):
    """获取HTML文件列表"""
    print_section("扫描 HTML 文件")
    
    html_files = sorted(base_path.glob("*.html"))
    if not html_files:
        print_error("当前文件夹中未找到 HTML 文件")
        return []

    print_info(f"找到 {len(html_files)} 个 HTML 文件")
    for html_file in html_files:
        print_info(f"  ✓ {html_file.name}")
    
    return html_files


def update_html_files(html_files, wav_name, text):
    """直接更新HTML文件中的语音消息（立即写入磁盘）"""
    updated_count = 0
    
    for html_path in html_files:
        try:
            # 使用锁保护文件读写，避免并发冲突
            with print_lock:
                # 读取文件
                content = html_path.read_text(encoding="utf-8")
                
                # 修改内容
                new_content, modified = replace_single_voice_message(content, wav_name, text)
                
                if modified:
                    # 立即写回文件
                    html_path.write_text(new_content, encoding="utf-8")
                    updated_count += 1
        except Exception as e:
            with print_lock:
                print_error(f"更新 {html_path.name} 失败: {e}")
    
    return updated_count


def finalize_html_files(batch_mode=False):
    """最终确认（由于已实时保存，此函数仅用于显示提示）"""
    if not batch_mode:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ 所有转换结果已实时保存到文件{Colors.ENDC}")
    return 0


def process_wav_file(wav_file, api_url, api_key, model, retry_count, retry_interval, html_files, delete_wav_after, file_index, total_files):
    """处理单个WAV文件（用于并发处理）"""
    global interrupted
    
    if interrupted:
        return None, None, 0, 0
    
    file_name = os.path.basename(wav_file)
    
    # 转写音频
    text = transcribe_audio(wav_file, api_url, api_key, model, retry_count, retry_interval)
    
    updated = 0
    deleted = 0
    
    if text:
        # 更新HTML文件（直接写入磁盘）
        updated = update_html_files(html_files, file_name, text)
        
        # 根据配置决定是否删除原始音频文件
        if delete_wav_after:
            if delete_wav_file(wav_file):
                deleted = 1
        
        # 实时输出结果（使用锁保证输出有序）
        with print_lock:
            print(f"  [{file_index}/{total_files}] {Colors.OKGREEN}✓{Colors.ENDC} {file_name} {Colors.OKCYAN}{text[:10]}{'...' if len(text) > 10 else ''}{Colors.ENDC}")
        
        return file_name, text, updated, deleted
    else:
        # 实时输出失败结果
        with print_lock:
            print(f"  [{file_index}/{total_files}] {Colors.FAIL}✗{Colors.ENDC} {file_name}")
        
        return file_name, None, 0, 0


def transcribe_and_update(config, base_path):
    """转写WAV文件并立即更新HTML文件（实时保存）"""
    global interrupted
    print_section("语音转文字（实时保存模式）")
    
    api_url = config.get('API', 'URL')
    api_key = config.get('API', 'KEY')
    model = config.get('API', 'MODEL')
    retry_count = config.getint('BASE', 'retry_count', fallback=3)
    retry_interval = config.getint('BASE', 'retry_interval', fallback=2)
    delete_wav_after = config.getboolean('BASE', 'delete_wav_after_transcribe', fallback=True)
    concurrency = config.getint('BASE', 'concurrency', fallback=3)
    
    print_info(f"API URL: {api_url}")
    print_info(f"模型: {model}")
    print_info(f"重试次数: {retry_count}")
    print_info(f"重试间隔: {retry_interval} 秒")
    print_info(f"转写后删除原音频: {'是' if delete_wav_after else '否'}")
    print_info(f"并发数: {concurrency}")
    
    # 获取HTML文件列表
    html_files = load_html_files(base_path)
    if not html_files:
        print_error("没有找到HTML文件，无法继续")
        return 0, 0, 0
    
    wav_files = get_wav_files(base_path)
    print_info(f"找到 {len(wav_files)} 个WAV文件")
    
    if not wav_files:
        print_warning("没有找到WAV文件")
        return 0, 0, 0
    
    success_count = 0
    failed_count = 0
    updated_count = 0
    deleted_count = 0
    
    total_files = len(wav_files)
    
    if concurrency > 1 and total_files > 1:
        # 并发处理模式
        print_section(f"开始并发处理")
        print_info(f"并发数: {concurrency} 线程")
        print_info(f"待处理文件: {total_files} 个")
        print(f"\n{Colors.OKCYAN}正在处理中...{Colors.ENDC}")
        print(f"{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
        
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {}
            for idx, wav_file in enumerate(wav_files, start=1):
                if interrupted:
                    break
                future = executor.submit(
                    process_wav_file,
                    wav_file, api_url, api_key, model,
                    retry_count, retry_interval, html_files,
                    delete_wav_after, idx, total_files
                )
                futures[future] = wav_file
            
            # 收集结果
            for future in as_completed(futures):
                if interrupted:
                    executor.shutdown(wait=False)
                    break
                
                try:
                    file_name, text, updated, deleted = future.result()
                    
                    with result_lock:
                        if text:
                            success_count += 1
                            updated_count += updated
                            deleted_count += deleted
                        else:
                            failed_count += 1
                except Exception as e:
                    with print_lock:
                        print_error(f"处理文件时发生异常: {e}")
                    failed_count += 1
        
        print(f"{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
    else:
        # 串行处理模式
        print_section(f"开始串行处理")
        print_info(f"待处理文件: {total_files} 个")
        print(f"\n{Colors.OKCYAN}正在处理中...{Colors.ENDC}")
        print(f"{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
        
        for idx, wav_file in enumerate(wav_files, start=1):
            # 检查是否被中断
            if interrupted:
                print_warning("检测到中断，停止处理")
                break
            
            file_name = os.path.basename(wav_file)
            
            # 转写音频
            text = transcribe_audio(wav_file, api_url, api_key, model, retry_count, retry_interval)
            
            if text:
                print(f"  [{idx}/{total_files}] {Colors.OKGREEN}✓{Colors.ENDC} {file_name} {Colors.OKCYAN}{text[:10]}{'...' if len(text) > 10 else ''}{Colors.ENDC}")
                
                # 立即更新HTML文件（直接写入磁盘）
                updated = update_html_files(html_files, file_name, text)
                if updated > 0:
                    updated_count += updated
                
                # 根据配置决定是否删除原始音频文件
                if delete_wav_after:
                    if delete_wav_file(wav_file):
                        deleted_count += 1
                
                success_count += 1
            else:
                print(f"  [{idx}/{total_files}] {Colors.FAIL}✗{Colors.ENDC} {file_name}")
                print(f"    {Colors.FAIL}→{Colors.ENDC} 转写失败")
                failed_count += 1
        
        print(f"\n{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
    
    print(f"\n{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
    print_success(f"转写完成！")
    print_info(f"成功: {success_count} 个")
    if failed_count > 0:
        print_error(f"失败: {failed_count} 个")
    print_info(f"总计: {len(wav_files)} 个文件")
    print_success(f"累计更新HTML: {updated_count} 处")
    if delete_wav_after:
        print_info(f"已删除原音频: {deleted_count} 个")
    
    return success_count, failed_count, updated_count


def process_single_directory(config, base_path, batch_mode=False):
    """处理单个目录（实时保存模式）"""
    # 转写并立即更新HTML文件（实时保存到磁盘）
    success_count, failed_count, updated_count = transcribe_and_update(config, base_path)
    
    if success_count > 0:
        # 最终确认提示
        finalize_html_files(batch_mode)
        
        print(f"\n{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
        print_success(f"处理完成！")
        print_info(f"成功转写: {success_count} 个")
        print_info(f"成功更新HTML: {updated_count} 处")
        print_info(f"所有结果已实时保存到文件")
        
        return updated_count, success_count + failed_count
    else:
        print_error("语音转写失败")
        return 0, 0


def process_batch_directories(config, root_path):
    """批量处理多个目录"""
    root_path = Path(root_path)
    
    if not root_path.exists():
        print_error(f"目录不存在: {root_path}")
        return 0, 0
    
    subdirs = [d for d in root_path.iterdir() if d.is_dir()]
    
    if not subdirs:
        print_error(f"在 {root_path} 中未找到任何子目录")
        return 0, 0
    
    print_section(f"批量处理模式")
    print_info(f"根目录: {root_path}")
    print_info(f"找到 {len(subdirs)} 个子目录")
    print(f"  - " + "\n  - ".join([d.name for d in subdirs]))
    
    print(f"\n{Colors.WARNING}{Colors.BOLD}⚠ 即将批量处理以上目录！{Colors.ENDC}")
    print(f"{Colors.WARNING}是否继续？(y/n): {Colors.ENDC}", end="")
    
    confirm = input().strip().lower()
    if confirm != 'y':
        print_warning("用户取消操作")
        return 0, 0
    
    total_updated = 0
    total_voice = 0
    success_dirs = 0
    failed_dirs = 0
    
    for idx, subdir in enumerate(subdirs, start=1):
        print_header(f"[{idx}/{len(subdirs)}] 处理目录: {subdir.name}")
        print(f"{Colors.OKCYAN}{'='*60}{Colors.ENDC}")
        
        try:
            updated, voice = process_single_directory(config, subdir, batch_mode=True)
            total_updated += updated
            total_voice += voice
            if updated > 0 or voice > 0:
                success_dirs += 1
        except Exception as e:
            print_error(f"处理目录 {subdir.name} 时出错: {e}")
            failed_dirs += 1
    
    return total_updated, total_voice, success_dirs, failed_dirs


def main():
    enable_windows_ansi()
    register_signal_handler()
    
    print_header("语音转文字与HTML替换工具（优化版）")
    
    print(f"\n{Colors.OKCYAN}请选择处理模式:{Colors.ENDC}")
    print(f"  {Colors.OKGREEN}1{Colors.ENDC}. 直接识别处理当前目录")
    print(f"  {Colors.OKGREEN}2{Colors.ENDC}. 手动填写总目录路径（批量处理）")
    print(f"\n{Colors.OKCYAN}请输入选项 (1/2): {Colors.ENDC}", end="")
    
    choice = input().strip()
    
    config = load_config()
    
    try:
        if choice == '1':
            print_header("模式: 处理当前目录")
            base_path = Path(get_base_path())
            total_updated, total_voice = process_single_directory(config, base_path, batch_mode=False)
            
            print_header("处理完成")
            print_info(f"语音文件总数: {total_voice} 个")
            print_success(f"成功替换总数: {total_updated} 条")
        
        elif choice == '2':
            print(f"\n{Colors.OKCYAN}请输入总目录路径: {Colors.ENDC}", end="")
            root_path = input().strip()
            
            if not root_path:
                print_error("路径不能为空")
                return
            
            total_updated, total_voice, success_dirs, failed_dirs = process_batch_directories(config, root_path)
            
            print_header("批量处理完成")
            print_info(f"处理目录总数: {success_dirs + failed_dirs} 个")
            print_success(f"成功处理: {success_dirs} 个")
            if failed_dirs > 0:
                print_error(f"失败: {failed_dirs} 个")
            print_info(f"语音文件总数: {total_voice} 个")
            print_success(f"成功替换总数: {total_updated} 条")
        
        else:
            print_error("无效的选项")
    
    except Exception as e:
        print_error(f"程序运行出错: {e}")
    
    print(f"\n{Colors.OKCYAN}按任意键退出...{Colors.ENDC}")
    input()


if __name__ == '__main__':
    main()