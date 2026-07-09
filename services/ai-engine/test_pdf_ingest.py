import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

from init_knowledge import build_insert_rows, discover_source_files


class PdfIngestTests(unittest.TestCase):
    def test_discover_source_files_recurses_pdf_and_txt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "guide.txt").write_text("txt", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "report.pdf").write_bytes(b"%PDF-1.4")
            (nested / "ignore.md").write_text("x", encoding="utf-8")

            files = discover_source_files(root)

            self.assertEqual([path.name for path in files], ["guide.txt", "report.pdf"])

    def test_build_insert_rows_preserves_pdf_page_and_source_metadata(self) -> None:
        chunks = [
            Document(page_content="第一页", metadata={"source": "/tmp/a.pdf", "page": 0}),
            Document(page_content="正文片段", metadata={"source": "/tmp/b.txt"}),
        ]
        vectors = [[0.1, 0.2], [0.3, 0.4]]

        rows = build_insert_rows(chunks, vectors)

        self.assertEqual(rows[0]["source_title"], "a.pdf")
        self.assertEqual(rows[0]["source_chapter"], "Page 1")
        self.assertEqual(rows[1]["source_title"], "b.txt")
        self.assertEqual(rows[1]["source_chapter"], "正文片段")


if __name__ == "__main__":
    unittest.main()
