import os
import sys
import configparser
import requests
import json
from pathlib import Path
from datetime import datetime
import shutil

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

def get_wav_files():
    base_path = get_base_path()
    voices_dir = os.path.join(base_path, 'media', 'voices')
    if not os.path.exists(voices_dir):
        print(f"目录不存在: {voices_dir}")
        return []
    return [os.path.join(voices_dir, f) for f in os.listdir(voices_dir) if f.endswith('.wav')]

def transcribe_audio(file_path, api_url, api_key, model):
    url = f"{api_url}/v1/audio/transcriptions"
    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    
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
            return result.get('text', '')
    except requests.exceptions.RequestException as e:
        print(f"请求失败 {file_path}: {e}")
        return ''
    except Exception as e:
        print(f"处理文件时出错 {file_path}: {e}")
        return ''

def save_result(file_name, text, result_file):
    try:
        with open(result_file, 'a', encoding='utf-8') as f:
            result = {
                'name': file_name,
                'result': text
            }
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
        print(f"  结果已保存: {file_name}")
    except Exception as e:
        print(f"  保存结果时出错: {e}")

def init_result_file(result_file):
    try:
        if os.path.exists(result_file) and os.path.getsize(result_file) > 0:
            backup_file = create_backup(result_file)
            print(f"已备份原始结果文件: {backup_file}")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            pass
        print(f"结果文件已初始化: {result_file}")
    except Exception as e:
        print(f"初始化结果文件时出错: {e}")

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

def main():
    config = load_config()
    
    api_url = config.get('API', 'URL')
    api_key = config.get('API', 'KEY')
    model = config.get('API', 'MODEL')
    base_path = get_base_path()
    result_file = os.path.join(base_path, config.get('BASE', 'result'))
    
    print(f"API URL: {api_url}")
    print(f"模型: {model}")
    print(f"结果文件: {result_file}")
    print("-" * 50)
    
    wav_files = get_wav_files()
    print(f"找到 {len(wav_files)} 个WAV文件")
    
    if not wav_files:
        print("没有找到WAV文件，程序退出")
        return
    
    init_result_file(result_file)
    
    success_count = 0
    
    for wav_file in wav_files:
        file_name = os.path.basename(wav_file)
        print(f"正在处理: {file_name}")
        text = transcribe_audio(wav_file, api_url, api_key, model)
        
        if text:
            save_result(file_name, text, result_file)
            print(f"  转写成功: {text[:50]}...")
            success_count += 1
        else:
            print(f"  转写失败")
    
    print("-" * 50)
    print(f"处理完成！共处理 {success_count}/{len(wav_files)} 个文件")
    print("\n按任意键退出...")
    input()

if __name__ == '__main__':
    main()