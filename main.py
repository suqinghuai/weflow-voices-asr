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
from pathlib import Path
from datetime import datetime


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
    
    for attempt in range(retry_count):
        try:
            with open(file_path, 'rb') as audio_file:
                files = {
                    'file': (os.path.basename(file_path), audio_file, 'audio/wav')
                }
                data = {
                    'model': model
                }
                
                response = requests.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                
                result = response.json()
                text = result.get('text', '')
                
                if text:
                    if attempt > 0:
                        print_success(f"重试成功 (第{attempt + 1}次尝试)")
                    return text
                else:
                    print_warning(f"返回结果为空 (第{attempt + 1}次尝试)")
                    if attempt < retry_count - 1:
                        print_info(f"等待 {retry_interval} 秒后重试...")
                        time.sleep(retry_interval)
        except requests.exceptions.RequestException as e:
            print_error(f"请求失败 (第{attempt + 1}次尝试): {e}")
            if attempt < retry_count - 1:
                print_info(f"等待 {retry_interval} 秒后重试...")
                time.sleep(retry_interval)
        except Exception as e:
            print_error(f"处理文件时出错 (第{attempt + 1}次尝试): {e}")
            if attempt < retry_count - 1:
                print_info(f"等待 {retry_interval} 秒后重试...")
                time.sleep(retry_interval)
    
    print_error(f"重试 {retry_count} 次后仍然失败")
    return ''


# 全局变量用于跟踪进度和保存状态
interrupted = False
html_contents = {}  # 内存中缓存的HTML内容

def signal_handler(signum, frame):
    """处理中断信号"""
    global interrupted
    if not interrupted:
        interrupted = True
        print(f"\n{Colors.WARNING}\n⚠ 收到中断信号，正在保存进度...{Colors.ENDC}")
        save_all_html_contents()
        print_success("进度已保存，程序即将退出")
        sys.exit(0)


def register_signal_handler():
    """注册中断信号处理器"""
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception as e:
        print_warning(f"无法注册信号处理器: {e}")


def save_all_html_contents():
    """保存所有内存中的HTML内容到硬盘"""
    global html_contents
    for html_path, content in html_contents.items():
        try:
            html_path.write_text(content, encoding="utf-8")
            print_info(f"已保存进度: {html_path.name}")
        except Exception as e:
            print_error(f"保存 {html_path.name} 时出错: {e}")


def delete_wav_file(wav_path):
    """删除原始音频文件"""
    try:
        if os.path.exists(wav_path):
            os.remove(wav_path)
            print_success(f"已删除原始音频: {os.path.basename(wav_path)}")
            return True
        return False
    except Exception as e:
        print_error(f"删除音频文件时出错: {e}")
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
    """加载HTML文件到内存"""
    global html_contents
    print_section("加载 HTML 文件到内存")
    
    html_files = sorted(base_path.glob("*.html"))
    if not html_files:
        print_error("当前文件夹中未找到 HTML 文件")
        return []

    print_info(f"找到 {len(html_files)} 个 HTML 文件")
    
    for html_file in html_files:
        try:
            content = html_file.read_text(encoding="utf-8")
            html_contents[html_file] = content
            print_info(f"  ✓ {html_file.name}")
        except Exception as e:
            print_error(f"  ✗ 加载 {html_file.name} 失败: {e}")
    
    return list(html_contents.keys())


def update_html_in_memory(wav_name, text):
    """在内存中更新所有HTML文件中的语音消息"""
    global html_contents
    updated_count = 0
    
    for html_path, content in html_contents.items():
        new_content, modified = replace_single_voice_message(content, wav_name, text)
        if modified:
            html_contents[html_path] = new_content
            updated_count += 1
            print_info(f"  更新了 {html_path.name}")
    
    return updated_count


def finalize_html_files(batch_mode=False):
    """将内存中的HTML内容写入硬盘"""
    global html_contents
    
    if not html_contents:
        return 0
    
    if not batch_mode:
        print(f"\n{Colors.WARNING}{Colors.BOLD}⚠ 警告: 即将保存HTML文件！{Colors.ENDC}")
        print(f"{Colors.WARNING}建议在保存前备份HTML文件{Colors.ENDC}")
        print(f"\n{Colors.OKCYAN}是否继续保存HTML文件？(y/n): {Colors.ENDC}", end="")
        
        confirm = input().strip().lower()
        if confirm != 'y':
            print_warning("用户取消操作，跳过HTML保存")
            return 0
    else:
        print_info(f"{Colors.OKGREEN}批量处理模式: 自动跳过确认{Colors.ENDC}")

    saved_count = 0
    for html_path, content in html_contents.items():
        try:
            html_path.write_text(content, encoding="utf-8")
            print_success(f"  ✓ 已保存: {html_path.name}")
            saved_count += 1
        except Exception as e:
            print_error(f"  ✗ 保存 {html_path.name} 失败: {e}")
    
    return saved_count


def transcribe_and_update(config, base_path):
    """转写WAV文件并立即更新HTML（优化后的流程）"""
    global interrupted
    print_section("语音转文字（优化模式）")
    
    api_url = config.get('API', 'URL')
    api_key = config.get('API', 'KEY')
    model = config.get('API', 'MODEL')
    retry_count = config.getint('BASE', 'retry_count', fallback=3)
    retry_interval = config.getint('BASE', 'retry_interval', fallback=2)
    delete_wav_after = config.getboolean('BASE', 'delete_wav_after_transcribe', fallback=True)
    
    print_info(f"API URL: {api_url}")
    print_info(f"模型: {model}")
    print_info(f"重试次数: {retry_count}")
    print_info(f"重试间隔: {retry_interval} 秒")
    print_info(f"转写后删除原音频: {'是' if delete_wav_after else '否'}")
    
    # 加载HTML文件到内存
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
    
    for idx, wav_file in enumerate(wav_files, start=1):
        # 检查是否被中断
        if interrupted:
            print_warning("检测到中断，停止处理")
            break
        
        file_name = os.path.basename(wav_file)
        print(f"\n[{idx}/{len(wav_files)}] 正在处理: {file_name}")
        
        # 转写音频
        text = transcribe_audio(wav_file, api_url, api_key, model, retry_count, retry_interval)
        
        if text:
            print_success(f"转写成功: {text[:50]}...")
            
            # 立即在内存中更新HTML
            updated = update_html_in_memory(file_name, text)
            if updated > 0:
                updated_count += updated
            
            # 根据配置决定是否删除原始音频文件
            if delete_wav_after:
                if delete_wav_file(wav_file):
                    deleted_count += 1
            else:
                print_info(f"保留原始音频: {file_name}")
            
            success_count += 1
        else:
            print_error(f"转写失败，保留原始文件")
            failed_count += 1
    
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
    """处理单个目录（优化后）"""
    global html_contents
    
    # 重置内存中的HTML内容
    html_contents = {}
    
    # 转写并立即更新内存中的HTML
    success_count, failed_count, updated_count = transcribe_and_update(config, base_path)
    
    if success_count > 0:
        # 最终保存HTML文件到硬盘
        saved_count = finalize_html_files(batch_mode)
        
        print(f"\n{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
        print_success(f"处理完成！")
        print_info(f"成功转写: {success_count} 个")
        print_info(f"成功更新HTML: {updated_count} 处")
        print_info(f"成功保存文件: {saved_count} 个")
        
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
    # 注册中断信号处理器
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