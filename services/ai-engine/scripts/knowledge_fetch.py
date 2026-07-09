import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DEFAULT_MANIFEST = ROOT_DIR / "data" / "sources" / "pediatric_authority_sources.json"
DEFAULT_RAW_DIR = ROOT_DIR / "data" / "raw"
DEFAULT_INDEX = DEFAULT_RAW_DIR / "_source_index.json"
USER_AGENT = "pediatric-ai-knowledge-fetcher/1.0"


@dataclass(frozen=True)
class SourceItem:
    id: str
    title: str
    authority: str
    region: str
    category: str
    ingestion_mode: str
    landing_url: str
    direct_url: str
    format: str
    copyright_status: str
    notes: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceItem":
        return cls(
            id=str(raw["id"]),
            title=str(raw["title"]),
            authority=str(raw["authority"]),
            region=str(raw["region"]),
            category=str(raw["category"]),
            ingestion_mode=str(raw["ingestionMode"]),
            landing_url=str(raw.get("landingUrl", "")),
            direct_url=str(raw.get("directUrl", "")),
            format=str(raw.get("format", "")),
            copyright_status=str(raw.get("copyrightStatus", "")),
            notes=str(raw.get("notes", "")),
        )


def load_sources(manifest_path: Path) -> list[SourceItem]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("manifest must be a JSON array")
    return [SourceItem.from_dict(item) for item in payload]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "source"


def guess_extension(source: SourceItem) -> str:
    parsed = urlparse(source.direct_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".pdf", ".txt"}:
        return suffix
    if suffix in {".doc", ".docx"}:
        return ".txt"
    if suffix in {".html", ".htm"}:
        return ".txt"
    if source.format == "pdf":
        return ".pdf"
    if source.format in {"doc", "docx", "word"}:
        return ".txt"
    if "html" in source.format:
        return ".txt"
    return ".bin"


def build_target_path(source: SourceItem, raw_dir: Path) -> Path:
    authority_dir = slugify(source.authority)
    filename = f"{slugify(source.id)}{guess_extension(source)}"
    return raw_dir / authority_dir / filename


def is_html_source(source: SourceItem) -> bool:
    suffix = Path(urlparse(source.direct_url).path).suffix.lower()
    return suffix in {".html", ".htm"} or "html" in source.format.lower()


def is_word_source(source: SourceItem) -> bool:
    suffix = Path(urlparse(source.direct_url).path).suffix.lower()
    return suffix in {".doc", ".docx"} or source.format.lower() in {"doc", "docx", "word"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_text_from_html(raw_html: str) -> str:
    main_match = re.search(
        r'<div[^>]+class="[^"]*(?:trs_editor_view|TRS_UEDITOR|trs_paper_default|trs_web)[^"]*"[^>]*>(.*?)</div>',
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html_source = main_match.group(1) if main_match else raw_html

    if not main_match:
        title_match = re.search(r"<title>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL)
        if title_match:
            page_title = html.unescape(title_match.group(1)).split("_")[0].strip()
            body_title_idx = raw_html.find(page_title, 5000)
            if body_title_idx != -1:
                end_candidates = [
                    raw_html.find(marker, body_title_idx)
                    for marker in (
                        '<div class="share-title"',
                        '<div class="pages_print"',
                        '<div class="editor"',
                        '<div class="footer_wrap"',
                    )
                ]
                end_candidates = [index for index in end_candidates if index != -1]
                if end_candidates:
                    html_source = raw_html[body_title_idx:min(end_candidates)]

        paragraph_blocks = re.findall(
            r'((?:<p\b[^>]*>.*?</p>\s*){8,})',
            html_source,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if paragraph_blocks:
            candidates = [
                block for block in paragraph_blocks
                if any(marker in block for marker in ("信息公开形式", "附件", "通知", "方案", "指南"))
            ]
            ranked_blocks = candidates or paragraph_blocks
            html_source = max(ranked_blocks, key=len)

    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", " ", html_source, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style\b[^>]*>.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</p\s*>", "\n\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</div\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("\r", "\n").replace("\xa0", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_text_from_word_bytes(source: SourceItem, content: bytes) -> str:
    suffix = Path(urlparse(source.direct_url).path).suffix.lower() or ".doc"
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / f"source{suffix}"
        output_path = Path(tmpdir) / "source.txt"
        input_path.write_bytes(content)
        subprocess.run(
            [
                "/usr/bin/textutil",
                "-convert",
                "txt",
                "-stdout",
                str(input_path),
            ],
            check=True,
            stdout=output_path.open("wb"),
            stderr=subprocess.DEVNULL,
        )
        return output_path.read_text(encoding="utf-8", errors="ignore").strip()


def read_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {"generatedAt": None, "items": []}
    return json.loads(index_path.read_text(encoding="utf-8"))


def write_index(index_path: Path, items: list[dict[str, Any]]) -> None:
    ensure_parent(index_path)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_index_item(index_items: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
    retained = [existing for existing in index_items if existing.get("id") != item["id"]]
    retained.append(item)
    retained.sort(key=lambda entry: str(entry.get("id", "")))
    return retained


def download_to_file(source: SourceItem, target_path: Path, timeout_seconds: int) -> None:
    ensure_parent(target_path)
    request = Request(source.direct_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout_seconds) as response:
        content = response.read()
        content_type = response.headers.get_content_type()

    if target_path.suffix.lower() == ".txt" and (content_type.startswith("text/html") or is_html_source(source)):
        charset = "utf-8"
        try:
            charset = response.headers.get_content_charset() or "utf-8"
        except Exception:
            charset = "utf-8"
        raw_html = content.decode(charset, errors="ignore")
        extracted_text = extract_text_from_html(raw_html)
        target_path.write_text(extracted_text, encoding="utf-8")
        return

    if target_path.suffix.lower() == ".txt" and is_word_source(source):
        extracted_text = extract_text_from_word_bytes(source, content)
        target_path.write_text(extracted_text, encoding="utf-8")
        return

    target_path.write_bytes(content)


def fetch_sources(
    sources: list[SourceItem],
    raw_dir: Path,
    index_path: Path,
    source_ids: set[str] | None,
    timeout_seconds: int,
) -> int:
    raw_dir.mkdir(parents=True, exist_ok=True)
    current_index = read_index(index_path)
    index_items = list(current_index.get("items", []))
    selected = [
        source for source in sources
        if (source_ids is None or source.id in source_ids)
    ]

    if not selected:
        print("未匹配到任何来源。")
        return 1

    auto_sources = [source for source in selected if source.ingestion_mode == "auto" and source.direct_url]
    skipped_sources = [source for source in selected if source not in auto_sources]

    for source in skipped_sources:
        print(f"⏭ 跳过 {source.id}: ingestionMode={source.ingestion_mode}")

    success_count = 0
    for source in auto_sources:
        target_path = build_target_path(source, raw_dir)
        try:
            print(f"⬇️  下载 {source.id} -> {target_path.relative_to(raw_dir)}")
            download_to_file(source, target_path, timeout_seconds)
            stat = target_path.stat()
            index_items = upsert_index_item(
                index_items,
                {
                    "id": source.id,
                    "title": source.title,
                    "authority": source.authority,
                    "region": source.region,
                    "category": source.category,
                    "ingestionMode": source.ingestion_mode,
                    "landingUrl": source.landing_url,
                    "directUrl": source.direct_url,
                    "localPath": str(target_path.relative_to(raw_dir)),
                    "fileSize": stat.st_size,
                    "sha256": sha256_file(target_path),
                    "downloadedAt": datetime.now(timezone.utc).isoformat(),
                    "copyrightStatus": source.copyright_status,
                    "notes": source.notes,
                },
            )
            success_count += 1
        except HTTPError as exc:
            print(f"❌ 下载失败 {source.id}: HTTP {exc.code}")
        except URLError as exc:
            print(f"❌ 下载失败 {source.id}: {exc.reason}")
        except Exception as exc:
            print(f"❌ 下载失败 {source.id}: {exc}")

    write_index(index_path, index_items)
    print(f"✅ 完成，成功下载 {success_count}/{len(auto_sources)} 个可自动获取来源。")
    if skipped_sources:
        print("ℹ️ 其余来源需人工审核 URL、授权或登录后再导入。")
    return 0 if success_count == len(auto_sources) else 1


def list_sources(sources: list[SourceItem]) -> int:
    print("知识来源清单：")
    for source in sources:
        print(
            f"- {source.id} [{source.region}/{source.category}] "
            f"{source.title} | mode={source.ingestion_mode}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="权威儿科资料来源清单与下载工具")
    parser.add_argument("command", choices=["list", "fetch"], help="执行命令")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="来源清单 JSON 路径",
    )
    parser.add_argument(
        "--dir",
        default=str(DEFAULT_RAW_DIR),
        help="原始资料保存目录，默认 services/ai-engine/data/raw",
    )
    parser.add_argument(
        "--index",
        default=str(DEFAULT_INDEX),
        help="本地下载索引 JSON 路径",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="仅处理指定来源 id，可重复传入",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="单文件下载超时秒数，默认 60",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    raw_dir = Path(args.dir).resolve()
    index_path = Path(args.index).resolve()

    if not manifest_path.exists():
        raise RuntimeError(f"manifest not found: {manifest_path}")

    sources = load_sources(manifest_path)
    source_ids = set(args.source) if args.source else None

    if args.command == "list":
        return list_sources(sources)
    if args.command == "fetch":
        return fetch_sources(sources, raw_dir, index_path, source_ids, args.timeout)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
