import configparser
import json
import os
import re
from pathlib import Path


def load_cut_size(config_path: Path, default_size: int = 4000) -> int:
	config = configparser.ConfigParser()
	config.read(config_path, encoding="utf-8")
	try:
		value = config.get("BASE", "cutmessages")
		return max(1, int(value))
	except Exception:
		return default_size


def extract_data_block(html_text: str):
	pattern = re.compile(
		r"^(?P<indent>\s*)window\.WEFLOW_DATA\s*=\s*\[(?P<data>.*?)\];",
		re.DOTALL | re.MULTILINE,
	)
	match = pattern.search(html_text)
	if not match:
		return None, None, None
	return match.group("data"), match.group("indent"), match.span()


def parse_data_list(raw_data: str):
	raw = "[" + raw_data + "]"
	return json.loads(raw)


def build_data_block(messages, indent: str) -> str:
	lines = [json.dumps(item, ensure_ascii=False, separators=(",", ": ")) for item in messages]
	joined = ",\n".join(lines)
	return f"{indent}window.WEFLOW_DATA = [\n{joined}\n{indent}];"


def update_counts(html_text: str, count: int) -> str:
	html_text = re.sub(
		r"(<span>)(\d+)\s*条消息(</span>)",
		lambda m: f"{m.group(1)}{count} 条消息{m.group(3)}",
		html_text,
		count=1,
	)
	html_text = re.sub(
		r"(id=\"resultCount\">\s*共\s*)(\d+)(\s*条)",
		lambda m: f"{m.group(1)}{count}{m.group(3)}",
		html_text,
		count=1,
	)
	return html_text


def split_messages(messages, chunk_size: int):
	for i in range(0, len(messages), chunk_size):
		yield messages[i : i + chunk_size]


def process_html_file(html_path: Path, output_dir: Path, chunk_size: int):
	html_text = html_path.read_text(encoding="utf-8")
	raw_data, indent, span = extract_data_block(html_text)
	if raw_data is None:
		return 0

	messages = parse_data_list(raw_data)
	if not messages:
		return 0

	output_dir.mkdir(parents=True, exist_ok=True)
	total_parts = (len(messages) + chunk_size - 1) // chunk_size
	base_name = html_path.stem

	for index, chunk in enumerate(split_messages(messages, chunk_size), start=1):
		updated_html = html_text
		updated_html = update_counts(updated_html, len(chunk))
		data_block = build_data_block(chunk, indent)
		updated_html = (
			updated_html[: span[0]] + data_block + updated_html[span[1] :]
		)

		suffix = f"_part{index:03d}"
		output_name = f"{base_name}{suffix}.html"
		output_path = output_dir / output_name
		output_path.write_text(updated_html, encoding="utf-8")

	return total_parts


def main():
	# 获取当前工作目录（用户运行exe的目录）
	workspace = Path(os.getcwd())
	config_path = workspace / "config.ini"
	cut_size = load_cut_size(config_path)
	output_dir = workspace / "分割结果"

	html_files = [p for p in workspace.glob("*.html") if p.is_file()]
	if not html_files:
		print(f"未找到HTML文件，当前目录: {workspace}")
		print("请确保将HTML文件放在与exe相同的目录中")
		return

	total_files = len(html_files)
	total_parts = 0

	print(f"找到 {total_files} 个HTML文件需要处理")
	print(f"分割大小: {cut_size} 条消息/文件")
	print(f"输出目录: {output_dir}")
	print("=" * 50)

	for html_path in html_files:
		print(f"处理文件: {html_path.name}")
		parts = process_html_file(html_path, output_dir, cut_size)
		total_parts += parts
		print(f"  生成 {parts} 个文件")

	print("=" * 50)
	print(f"处理完成！")
	print(f"总处理文件数: {total_files}")
	print(f"总生成文件数: {total_parts}")
	print("\n按任意键退出...")
	input()


if __name__ == "__main__":
	main()