import os
import sys
import configparser
import requests
import json
import re
import html
import shutil
import time
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


def save_result(file_name, text, result_file):
    try:
        with open(result_file, 'a', encoding='utf-8') as f:
            result = {
                'name': file_name,
                'result': text
            }
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
        print_success(f"结果已保存: {file_name}")
    except Exception as e:
        print_error(f"保存结果时出错: {e}")


def init_result_file(result_file):
    try:
        if os.path.exists(result_file) and os.path.getsize(result_file) > 0:
            backup_file = create_backup(result_file)
            print_info(f"已备份原始结果文件: {backup_file}")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            pass
        print_info(f"结果文件已初始化: {result_file}")
    except Exception as e:
        print_error(f"初始化结果文件时出错: {e}")


def create_backup(file_path):
    """为文件创建备份，添加时间戳"""
    file_dir = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    name, ext = os.path.splitext(file_name)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"{name}_backup_{timestamp}{ext}"
    backup_path = os.path.join(file_dir, backup_name)
    
    shutil.copy2(file_path, backup_path)
    return backup_path


def delete_result_file(result_file):
    """删除语音转文字结果文件"""
    try:
        if os.path.exists(result_file):
            os.remove(result_file)
            print_success(f"已删除结果文件: {os.path.basename(result_file)}")
            return True
        return False
    except Exception as e:
        print_error(f"删除结果文件时出错: {e}")
        return False


def load_results(result_path):
    """加载语音转文字结果"""
    print_section(f"加载语音转文字结果文件: {result_path.name}")
    results = {}
    line_count = 0
    success_count = 0
    error_count = 0
    
    with result_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            line_count += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                print_error(f"第 {line_no} 行 JSON 解析失败: {exc}")
                error_count += 1
                continue
            name = record.get("name")
            result_text = record.get("result")
            if not name or result_text is None:
                continue
            results[name] = str(result_text).strip()
            success_count += 1
    
    print_info(f"总行数: {line_count}")
    print_success(f"成功解析: {success_count} 条")
    print_error(f"解析失败: {error_count} 条")
    print_info(f"有效结果: {len(results)} 个")
    return results


def replace_voice_messages(content, results):
    """替换HTML中的语音消息"""
    marker = "window.WEFLOW_DATA = ["
    start_index = content.find(marker)
    if start_index == -1:
        return content, 0, 0

    array_start = start_index + len(marker)
    array_end = content.find("];", array_start)
    if array_end == -1:
        return content, 0, 0

    array_body = content[array_start:array_end].strip()
    if array_body:
        json_text = "[" + array_body.rstrip(",") + "]"
        try:
            items = json.loads(json_text)
        except json.JSONDecodeError as exc:
            print_error(f"HTML 数据解析失败: {exc}")
            return content, 0, 0
    else:
        items = []

    total_voice = 0
    updated = 0
    no_match_count = 0
    no_result_count = 0
    
    for item in items:
        body = item.get("b")
        if not isinstance(body, str):
            continue
        if "[语音消息]" not in body:
            continue
        total_voice += 1
        match = re.search(r'src="([^"]+\.wav)"', body)
        if not match:
            no_match_count += 1
            continue
        wav_name = Path(match.group(1)).name
        result_text = results.get(wav_name)
        if not result_text:
            no_result_count += 1
            continue
        safe_text = html.escape(result_text, quote=True)
        new_body = body.replace("[语音消息]", f"[语音转文字-{safe_text}]")
        if new_body != body:
            item["b"] = new_body
            updated += 1

    print_info(f"总消息数: {len(items)} 条")
    print_info(f"语音消息: {total_voice} 条")
    print_success(f"成功替换: {updated} 条")
    print_warning(f"未匹配wav: {no_match_count} 条")
    print_warning(f"无转写结果: {no_result_count} 条")

    new_array = ",\n".join(json.dumps(item, ensure_ascii=False) for item in items)
    new_content = content[:start_index] + marker + "\n" + new_array + "\n" + content[array_end:]
    return new_content, updated, total_voice


def process_html_files(base_path, results, batch_mode=False):
    """处理HTML文件"""
    print_section("处理 HTML 文件")
    
    html_files = sorted(base_path.glob("*.html"))
    if not html_files:
        print_error("当前文件夹中未找到 HTML 文件")
        return 0, 0

    print_info(f"找到 {len(html_files)} 个 HTML 文件")
    
    for html_file in html_files:
        print(f"  - {html_file.name}")
    
    if not batch_mode:
        print(f"\n{Colors.WARNING}{Colors.BOLD}⚠ 警告: 即将修改HTML文件！{Colors.ENDC}")
        print(f"{Colors.WARNING}建议在修改前备份HTML文件{Colors.ENDC}")
        print(f"\n{Colors.OKCYAN}是否继续处理HTML文件？(y/n): {Colors.ENDC}", end="")
        
        confirm = input().strip().lower()
        if confirm != 'y':
            print_warning("用户取消操作，跳过HTML文件处理")
            return 0, 0
    else:
        print_info(f"{Colors.OKGREEN}批量处理模式: 自动跳过确认{Colors.ENDC}")

    total_updated = 0
    total_voice = 0
    
    for idx, html_path in enumerate(html_files, start=1):
        print(f"\n[{idx}/{len(html_files)}] 处理文件: {html_path.name}")
        print(f"{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
        
        original = html_path.read_text(encoding="utf-8")
        updated_content, updated, total = replace_voice_messages(original, results)
        
        if updated_content != original:
            html_path.write_text(updated_content, encoding="utf-8")
            print_success(f"文件已更新")
        else:
            print_info(f"文件无需更新")
        
        total_updated += updated
        total_voice += total

    return total_updated, total_voice


def transcribe_wav_files(config, base_path, result_file):
    """转写WAV文件"""
    print_section("语音转文字")
    
    api_url = config.get('API', 'URL')
    api_key = config.get('API', 'KEY')
    model = config.get('API', 'MODEL')
    retry_count = config.getint('BASE', 'retry_count', fallback=3)
    retry_interval = config.getint('BASE', 'retry_interval', fallback=2)
    
    print_info(f"API URL: {api_url}")
    print_info(f"模型: {model}")
    print_info(f"结果文件: {result_file}")
    print_info(f"重试次数: {retry_count}")
    print_info(f"重试间隔: {retry_interval} 秒")
    
    wav_files = get_wav_files(base_path)
    print_info(f"找到 {len(wav_files)} 个WAV文件")
    
    if not wav_files:
        print_warning("没有找到WAV文件")
        return False
    
    init_result_file(result_file)
    
    success_count = 0
    failed_count = 0
    
    for idx, wav_file in enumerate(wav_files, start=1):
        file_name = os.path.basename(wav_file)
        print(f"\n[{idx}/{len(wav_files)}] 正在处理: {file_name}")
        text = transcribe_audio(wav_file, api_url, api_key, model, retry_count, retry_interval)
        
        if text:
            save_result(file_name, text, result_file)
            print_success(f"转写成功: {text[:50]}...")
            success_count += 1
        else:
            print_error(f"转写失败")
            failed_count += 1
    
    print(f"\n{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
    print_success(f"转写完成！")
    print_info(f"成功: {success_count} 个")
    if failed_count > 0:
        print_error(f"失败: {failed_count} 个")
    print_info(f"总计: {len(wav_files)} 个文件")
    
    return success_count > 0


def process_single_directory(config, base_path, batch_mode=False):
    """处理单个目录"""
    result_file = base_path / config.get('BASE', 'result')
    
    success = transcribe_wav_files(config, base_path, result_file)
    
    if success:
        results = load_results(result_file)
        
        if results:
            total_updated, total_voice = process_html_files(base_path, results, batch_mode)
            
            print(f"\n{Colors.OKCYAN}{'-'*60}{Colors.ENDC}")
            delete_result_file(result_file)
            
            return total_updated, total_voice
        else:
            print_error("未找到语音转文字结果")
            delete_result_file(result_file)
            return 0, 0
    else:
        print_error("语音转写失败，跳过HTML替换")
        delete_result_file(result_file)
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
    print_header("语音转文字与HTML替换工具")
    
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
            print_info(f"语音消息总数: {total_voice} 条")
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
            print_info(f"语音消息总数: {total_voice} 条")
            print_success(f"成功替换总数: {total_updated} 条")
        
        else:
            print_error("无效的选项")
    
    except Exception as e:
        print_error(f"程序运行出错: {e}")
    
    print(f"\n{Colors.OKCYAN}按任意键退出...{Colors.ENDC}")
    input()


if __name__ == '__main__':
    main()