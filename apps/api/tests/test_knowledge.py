# 文件用途：验证解析边界、token 分块覆盖、PDF/OCR 错误及中英文检索分词一致性。
import io
from types import SimpleNamespace

import pytest
from devflow.errors import DomainError
from devflow.knowledge import lexical_terms, parse_document, split_chunks
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


class CharacterTokenizer:
    def encode(self, text, **kwargs):
        return SimpleNamespace(
            ids=list(range(len(text))), offsets=[(i, i + 1) for i in range(len(text))]
        )


def test_chunking_preserves_entire_long_paragraph_and_overlap():
    content = "# 标题\n\n" + "长文本边界" * 300 + "\n\n## 最后\n尾部必须被保留"
    chunks = split_chunks(content, CharacterTokenizer())
    assert all(0 < c["token_count"] <= 384 for c in chunks)
    assert chunks[-1]["content"].endswith("尾部必须被保留")
    assert all(
        chunks[i]["content"][-48:] == chunks[i + 1]["content"][:48] for i in range(len(chunks) - 1)
    )
    assert chunks[0]["start_line"] == 1 and chunks[-1]["end_line"] == 6


def test_markdown_utf8_and_invalid_documents():
    assert parse_document("notes.md", b"\xef\xbb\xbf# title\r\ntext")[0] == "# title\ntext"
    for filename, raw, code in [
        ("a.txt", b"\xff", "document_encoding"),
        ("a.md", b"a\x00b", "document_binary"),
        ("a.txt", b" ", "document_empty"),
        ("a.exe", b"text", "document_type"),
        ("a.pdf", b"broken", "pdf_parse_failed"),
    ]:
        with pytest.raises(DomainError) as error:
            parse_document(filename, raw)
        assert error.value.code == code


def pdf_bytes(*, blank=False, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if not blank:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 250 Td (Owner isolation policy) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("password")
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def test_pdf_text_page_mapping_scans_and_encryption():
    text, pages = parse_document("design.pdf", pdf_bytes())
    assert "Owner isolation policy" in text and pages == [{"page": 1, "start_line": 1}]
    for raw, code in [
        (pdf_bytes(blank=True), "pdf_ocr_required"),
        (pdf_bytes(encrypted=True), "pdf_encrypted"),
    ]:
        with pytest.raises(DomainError) as error:
            parse_document("scan.pdf", raw)
        assert error.value.code == code


def test_lexical_rules_cover_chinese_and_code_identifiers():
    terms = lexical_terms("所有者隔离 owner_id getTaskOwner")
    assert {"owner_id", "owner", "id", "gettaskowner", "get", "task"} <= set(terms)
    assert lexical_terms("所有者隔离") == lexical_terms("所有者隔离")
