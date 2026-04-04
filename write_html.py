import configparser
import html
import json
import os
import re
import sys
from pathlib import Path


def load_results(result_path: Path) -> dict:
	print(f"\n{'='*60}")
	print(f"正在加载语音转文字结果文件: {result_path.name}")
	print(f"{'='*60}")
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
				print(f"  [错误] 第 {line_no} 行 JSON 解析失败: {exc}")
				error_count += 1
				continue
			name = record.get("name")
			result_text = record.get("result")
			if not name or result_text is None:
				continue
			results[name] = str(result_text).strip()
			success_count += 1
	print(f"  - 总行数: {line_count}")
	print(f"  - 成功解析: {success_count} 条")
	print(f"  - 解析失败: {error_count} 条")
	print(f"  - 有效结果: {len(results)} 个")
	return results


def replace_voice_messages(content: str, results: dict) -> tuple[str, int, int]:
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
			print(f"  [错误] HTML 数据解析失败: {exc}")
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

	print(f"  - 总消息数: {len(items)} 条")
	print(f"  - 语音消息: {total_voice} 条")
	print(f"  - 成功替换: {updated} 条")
	print(f"  - 未匹配wav: {no_match_count} 条")
	print(f"  - 无转写结果: {no_result_count} 条")

	new_array = ",\n".join(json.dumps(item, ensure_ascii=False) for item in items)
	new_content = content[:start_index] + marker + "\n" + new_array + "\n" + content[array_end:]
	return new_content, updated, total_voice


def main() -> None:
	print(f"\n{'='*60}")
	print(f"语音转文字 HTML 替换工具")
	print(f"{'='*60}")

	if getattr(sys, 'frozen', False):
		base_dir = Path(sys.executable).parent
	else:
		base_dir = Path(os.path.dirname(os.path.abspath(__file__)))

	config_path = base_dir / "config.ini"
	config = configparser.ConfigParser()
	if config_path.exists():
		config.read(config_path, encoding="utf-8")

	result_name = config.get("BASE", "result", fallback="语音转文字结果.jsonl")
	result_path = base_dir / result_name
	if not result_path.exists():
		print(f"\n[错误] 结果文件不存在: {result_path}")
		return

	results = load_results(result_path)
	if not results:
		print(f"\n[错误] 未找到语音转文字结果")
		return

	html_files = sorted(base_dir.glob("*.html"))
	if not html_files:
		print(f"\n[错误] 当前文件夹中未找到 HTML 文件")
		return

	print(f"\n{'='*60}")
	print(f"找到 {len(html_files)} 个 HTML 文件")
	print(f"{'='*60}")

	total_updated = 0
	total_voice = 0
	for idx, html_path in enumerate(html_files, start=1):
		print(f"\n[{idx}/{len(html_files)}] 处理文件: {html_path.name}")
		print(f"{'-'*60}")
		original = html_path.read_text(encoding="utf-8")
		updated_content, updated, total = replace_voice_messages(original, results)
		if updated_content != original:
			html_path.write_text(updated_content, encoding="utf-8")
			print(f"  [成功] 文件已更新")
		else:
			print(f"  [提示] 文件无需更新")
		total_updated += updated
		total_voice += total

	print(f"\n{'='*60}")
	print(f"处理完成")
	print(f"{'='*60}")
	print(f"- 处理文件数: {len(html_files)} 个")
	print(f"- 语音消息总数: {total_voice} 条")
	print(f"- 成功替换总数: {total_updated} 条")
	print(f"{'='*60}\n")


def wait_for_exit():
	print("\n按任意键退出...")
	if os.name == 'nt':
		os.system('pause >nul 2>&1')
	else:
		input()


if __name__ == "__main__":
	main()
	wait_for_exit()