import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from personal_writing.core import pipeline
from personal_writing.db import schema
from personal_writing.db.repository import (
    DocumentChunkRepo,
    LibraryDocumentRepo,
    MaterialFolderRepo,
    MaterialLibraryRepo,
)
from personal_writing.material_library.chunker import chunk_document
from personal_writing.material_library.context_builder import build_evidence_pack
from personal_writing.material_library import storage
from personal_writing.material_library.extractors import extract, extract_text
from personal_writing.material_library.indexing import build_library_index_summary, build_source_guide
from personal_writing.web.app import create_app
from personal_writing.zotero_library import (
    build_reference_pack,
    build_writing_snippet,
    export_bibtex,
    export_csl_json,
    format_citation,
    import_pdf_bytes,
    import_references,
    parse_bibtex,
    parse_csl_json,
    parse_ris,
    search_references,
)


class TempDbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_dir = schema.DB_DIR
        self.old_db_path = schema.DB_PATH
        schema.DB_DIR = self.tmp.name
        schema.DB_PATH = os.path.join(self.tmp.name, "test.db")
        pipeline.init()

    def tearDown(self):
        schema.DB_DIR = self.old_db_dir
        schema.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def import_text(self):
        lib_id = MaterialLibraryRepo.create("算法治理论文库", topic="算法治理")
        doc_id = LibraryDocumentRepo.create(
            lib_id,
            title="平台治理笔记",
            original_filename="note.txt",
            file_path="",
            source_type="txt",
            sha256="demo",
        )
        extracted = extract_text(
            "平台治理笔记",
            "算法治理要求平台承担透明度义务。\n\n自动化决策需要解释机制和申诉渠道。",
        )
        chunks = chunk_document(extracted, max_chars=40, overlap_chars=0)
        DocumentChunkRepo.replace_for_document(doc_id, lib_id, chunks)
        LibraryDocumentRepo.update_parse_result(
            doc_id,
            "ready",
            page_count=1,
            word_count=len(extracted.text),
            text_preview=extracted.text,
        )
        return lib_id, doc_id

    def import_text_in_folder(self):
        lib_id = MaterialLibraryRepo.create("算法治理论文库", topic="算法治理")
        folder_id = MaterialFolderRepo.create(lib_id, "规范材料", description="法条和监管文本")
        doc_id = LibraryDocumentRepo.create(
            lib_id,
            title="平台治理规范",
            original_filename="rules.txt",
            file_path="",
            source_type="txt",
            sha256="folder-demo",
            folder_id=folder_id,
            tags=["规范依据"],
        )
        extracted = extract_text(
            "平台治理规范",
            "平台治理规范要求自动化决策提供解释渠道。\n\n平台应当保存审核记录。",
        )
        chunks = chunk_document(extracted, max_chars=50, overlap_chars=0)
        DocumentChunkRepo.replace_for_document(doc_id, lib_id, chunks)
        LibraryDocumentRepo.update_parse_result(
            doc_id,
            "ready",
            page_count=1,
            word_count=len(extracted.text),
            text_preview=extracted.text,
        )
        return lib_id, folder_id, doc_id


def _minimal_pdf_bytes(title="Platform Governance PDF Title", body="Transparency evidence for platforms"):
    stream = f"BT /F1 18 Tf 72 720 Td ({title}) Tj 0 -30 Td ({body}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref_at = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += (
        b"trailer\n"
        + f"<< /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    return pdf


class MaterialLibrarySchemaTests(TempDbTestCase):
    def test_schema_initializes_material_library_tables(self):
        conn = sqlite3.connect(schema.DB_PATH)
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            )
        }
        self.assertIn("material_libraries", names)
        self.assertIn("library_documents", names)
        self.assertIn("material_library_folders", names)
        self.assertIn("document_chunks", names)
        self.assertIn("generation_retrieval_snapshots", names)
        self.assertIn("article_citations", names)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(library_documents)")
        }
        conn.close()
        self.assertIn("folder_id", columns)
        self.assertIn("tags", columns)


class MaterialLibraryFlowTests(TempDbTestCase):
    def test_create_import_chunk_search_and_evidence_pack(self):
        lib_id, doc_id = self.import_text()
        chunks = DocumentChunkRepo.list_by_document(doc_id)
        self.assertGreaterEqual(len(chunks), 1)
        results = DocumentChunkRepo.search([lib_id], "算法治理", limit=5)
        self.assertGreaterEqual(len(results), 1)

        evidence = build_evidence_pack([lib_id], "算法治理", mode="strict", top_k=3)
        self.assertIn("## 素材库证据包", evidence["pack"])
        self.assertIn("[S1]", evidence["pack"])
        self.assertIn("需补证", evidence["pack"])
        self.assertEqual(evidence["results"][0]["label"], "S1")

    def test_create_folder_save_document_and_filter_by_folder(self):
        lib_id, folder_id, doc_id = self.import_text_in_folder()
        folders = MaterialFolderRepo.list_by_library(lib_id)
        self.assertEqual(folders[0]["name"], "规范材料")
        self.assertEqual(folders[0]["document_count"], 1)

        doc = LibraryDocumentRepo.get(doc_id)
        self.assertEqual(doc["folder_id"], folder_id)
        self.assertEqual(doc["folder_name"], "规范材料")

        filtered_docs = LibraryDocumentRepo.list_by_library(lib_id, folder_id=folder_id)
        self.assertEqual([d["id"] for d in filtered_docs], [doc_id])

        results = DocumentChunkRepo.search([lib_id], "解释渠道", limit=5, folder_id=folder_id)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["folder_name"], "规范材料")

        evidence = build_evidence_pack([lib_id], "解释渠道", folder_id=folder_id, folder_name="规范材料")
        self.assertIn("检索范围：规范材料", evidence["pack"])
        self.assertEqual(evidence["results"][0]["folder_name"], "规范材料")
        self.assertIn("document_id", evidence["results"][0])
        self.assertIn("chunk_id", evidence["results"][0])
        self.assertIn("excerpt", evidence["results"][0])

    def test_old_documents_without_folder_stay_uncategorized(self):
        lib_id, doc_id = self.import_text()
        doc = LibraryDocumentRepo.get(doc_id)
        self.assertIsNone(doc["folder_id"])

        uncategorized = LibraryDocumentRepo.list_by_library(lib_id, folder_id="uncategorized")
        self.assertEqual([d["id"] for d in uncategorized], [doc_id])

        results = DocumentChunkRepo.search([lib_id], "自动化决策", limit=5, folder_id="uncategorized")
        self.assertGreaterEqual(len(results), 1)

    def test_source_guide_and_library_index_summary(self):
        lib_id, folder_id, doc_id = self.import_text_in_folder()
        doc = LibraryDocumentRepo.get(doc_id)
        chunks = DocumentChunkRepo.list_by_document(doc_id)

        guide = build_source_guide(doc, chunks)
        self.assertEqual(guide["document_id"], doc_id)
        self.assertEqual(guide["folder_name"], "规范材料")
        self.assertEqual(guide["parse_status"], "ready")
        self.assertGreaterEqual(guide["chunk_count"], 1)
        self.assertIn("平台治理", guide["summary"])
        self.assertGreaterEqual(len(guide["keywords"]), 1)
        self.assertGreaterEqual(len(guide["suggested_questions"]), 3)

        summary = build_library_index_summary(lib_id)
        self.assertEqual(summary["document_count"], 1)
        self.assertGreaterEqual(summary["chunk_count"], 1)
        self.assertEqual(summary["folder_count"], 1)
        self.assertEqual(summary["searchable_document_count"], 1)
        self.assertEqual(summary["folder_breakdown"][0]["folder_id"], folder_id)
        self.assertGreaterEqual(summary["folder_breakdown"][0]["chunk_count"], 1)

    def test_library_and_document_pages_render_index_cards(self):
        lib_id, _, doc_id = self.import_text_in_folder()
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        detail = client.get(f"/libraries/{lib_id}")
        self.assertEqual(detail.status_code, 200)
        # New workbench layout: stat badges instead of index overview
        self.assertIn("可检索".encode("utf-8"), detail.data)
        self.assertIn("文档".encode("utf-8"), detail.data)

        document = client.get(f"/libraries/{lib_id}/documents/{doc_id}")
        self.assertEqual(document.status_code, 200)
        self.assertIn("文档索引卡".encode("utf-8"), document.data)
        self.assertIn("建议追问".encode("utf-8"), document.data)

    def test_ordinary_pdf_upload_still_indexes_and_searches(self):
        lib_id = MaterialLibraryRepo.create("普通 PDF 素材库", topic="平台治理")
        saved = storage.save_bytes(lib_id, "ordinary-paper.pdf", _minimal_pdf_bytes())
        doc_id = LibraryDocumentRepo.create(
            lib_id,
            title="ordinary-paper.pdf",
            original_filename="ordinary-paper.pdf",
            file_path=saved["path"],
            source_type="pdf",
            mime_type="application/pdf",
            sha256=saved["sha256"],
        )
        try:
            extracted = extract(saved["path"], "pdf")
        except RuntimeError as e:
            self.assertIn("缺少 PDF 解析依赖", str(e))
            return
        chunks = chunk_document(extracted, max_chars=500, overlap_chars=0)
        DocumentChunkRepo.replace_for_document(doc_id, lib_id, chunks)
        LibraryDocumentRepo.update_parse_result(
            doc_id,
            "ready",
            page_count=len(extracted.pages or []),
            word_count=len(extracted.text or ""),
            text_preview=extracted.text,
        )

        results = DocumentChunkRepo.search([lib_id], "Transparency", limit=5)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["source_type"], "pdf")


class PipelineRetrievalHookTests(TempDbTestCase):
    def test_pipeline_injects_evidence_pack_when_library_ids_are_given(self):
        lib_id, _ = self.import_text()
        captured = {}

        def fake_call(prompt):
            captured.setdefault("prompt", prompt)
            return "# 算法治理的透明度义务\n正文引用素材库证据。[S1]"

        with patch("personal_writing.core.pipeline.claude_client.is_available", return_value=True), \
             patch("personal_writing.core.pipeline.claude_client.call", side_effect=fake_call), \
             patch("personal_writing.core.pipeline.save_local_file", return_value=""):
            result = pipeline.write(
                "请写一段算法治理论文片段",
                ["zheng_ge_academic"],
                library_ids=[lib_id],
                retrieval_query="算法治理",
                library_mode="strict",
            )

        self.assertIn("素材库证据包", captured["prompt"])
        self.assertIn("[S1]", captured["prompt"])
        self.assertIn("需补证", captured["prompt"])
        self.assertGreater(result["retrieval_snapshot_id"], 0)
        self.assertEqual(result["articles"][0]["retrieval_snapshot_id"], result["retrieval_snapshot_id"])

    def test_pipeline_without_library_keeps_plain_writing_flow(self):
        captured = {}

        def fake_call(prompt):
            captured["prompt"] = prompt
            return "# 普通写作\n正文不需要素材库证据。"

        with patch("personal_writing.core.pipeline.claude_client.is_available", return_value=True), \
             patch("personal_writing.core.pipeline.claude_client.call", side_effect=fake_call), \
             patch("personal_writing.core.pipeline.save_local_file", return_value=""):
            result = pipeline.write(
                "请写一段普通文章",
                ["short_science"],
                library_ids=[],
            )

        self.assertNotIn("素材库证据包", captured["prompt"])
        self.assertEqual(result["retrieval_snapshot_id"], 0)
        self.assertEqual(len(result["articles"]), 1)


class ZoteroLibraryAdapterTests(TempDbTestCase):
    def test_parse_import_search_and_snippet_from_bibtex(self):
        bibtex = """
@article{smith2024platform,
  title = {Platform Governance and Algorithmic Accountability},
  author = {Smith, Alice and Wang, Bo},
  year = {2024},
  journal = {Journal of Digital Governance},
  doi = {10.1234/demo.2024.01},
  url = {https://example.org/platform-governance},
  abstract = {This article studies transparency duties for automated decision systems.},
  keywords = {algorithmic governance; transparency; platform},
  note = {Useful for explaining audit duties.},
  file = {/tmp/platform-governance.pdf}
}
"""
        refs = parse_bibtex(bibtex)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["title"], "Platform Governance and Algorithmic Accountability")
        self.assertEqual(refs[0]["authors"], ["Alice Smith", "Bo Wang"])
        self.assertEqual(refs[0]["year"], "2024")
        self.assertIn("transparency", refs[0]["tags"])

        lib_id = MaterialLibraryRepo.create("Zotero 文献库", topic="算法治理")
        imported = import_references(lib_id, refs)
        self.assertEqual(len(imported), 1)
        document_id = imported[0]["document_id"]

        by_author = search_references(lib_id, author="Smith")
        self.assertEqual([r["document_id"] for r in by_author], [document_id])
        by_year_tag_journal = search_references(
            lib_id,
            year="2024",
            tag="platform",
            journal="Digital Governance",
        )
        self.assertEqual([r["document_id"] for r in by_year_tag_journal], [document_id])

        evidence = build_evidence_pack([lib_id], "transparency duties", top_k=3)
        self.assertIn("Platform Governance", evidence["pack"])
        self.assertIn("[S1]", evidence["pack"])

        snippet = build_writing_snippet(document_id)
        self.assertIn("可复制引用素材", snippet)
        self.assertIn("Alice Smith等（2024）", snippet)
        self.assertIn("10.1234/demo.2024.01", snippet)

    def test_parse_import_search_from_csl_json(self):
        csl = [
            {
                "id": "doe2023",
                "type": "article-journal",
                "title": "Explainable AI in Public Administration",
                "author": [{"given": "Jane", "family": "Doe"}],
                "issued": {"date-parts": [[2023]]},
                "container-title": "Public Law Review",
                "DOI": "10.5555/plr.2023.7",
                "URL": "https://example.org/xai",
                "abstract": "A study of explanation and appeal channels.",
                "keyword": "行政法, explainability",
                "note": "Connects directly to due process arguments.",
            }
        ]
        refs = parse_csl_json(json.dumps(csl))
        self.assertEqual(refs[0]["authors"], ["Jane Doe"])
        self.assertEqual(refs[0]["publicationTitle"], "Public Law Review")

        lib_id = MaterialLibraryRepo.create("CSL 文献库", topic="可解释 AI")
        imported = import_references(lib_id, refs)
        self.assertEqual(len(imported), 1)
        results = search_references(lib_id, query="appeal", tag="行政法")
        self.assertEqual(results[0]["title"], "Explainable AI in Public Administration")

    def test_parse_ris_import_export_and_reference_pack(self):
        ris = """TY  - JOUR
ID  - zhang2025risk
TI  - Risk Regulation for Generative AI
AU  - Zhang, Wei
AU  - Chen, Li
PY  - 2025
JO  - Chinese Journal of Law and Technology
DO  - 10.9999/cjlt.2025.3
UR  - https://example.org/risk-regulation
AB  - This article discusses platform risk regulation and evidence duties.
KW  - generative AI
KW  - risk regulation
N1  - Strong background for risk-classification arguments.
ER  -
"""
        refs = parse_ris(ris)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["title"], "Risk Regulation for Generative AI")
        self.assertEqual(refs[0]["authors"], ["Wei Zhang", "Li Chen"])
        self.assertEqual(refs[0]["publicationTitle"], "Chinese Journal of Law and Technology")

        lib_id = MaterialLibraryRepo.create("RIS 文献库", topic="AI 风险治理")
        imported = import_references(lib_id, refs)
        document_id = imported[0]["document_id"]

        pack = build_reference_pack([lib_id], "risk evidence duties", top_k=3, citation_style="apa")
        self.assertIn("## 参考文献包", pack["pack"])
        self.assertIn("Zhang, W.", pack["pack"])
        self.assertIn(f"document_id={document_id}", pack["pack"])
        self.assertIn("关键片段", pack["pack"])

        evidence = build_evidence_pack([lib_id], "risk evidence duties", top_k=3)
        self.assertIn("## 文献引用卡", evidence["pack"])
        self.assertIn("Risk Regulation for Generative AI", evidence["pack"])
        self.assertGreaterEqual(len(evidence["reference_pack"]["cards"]), 1)

        csl_json = export_csl_json(search_references(lib_id))
        self.assertIn("Risk Regulation for Generative AI", csl_json)
        bibtex = export_bibtex(search_references(lib_id))
        self.assertIn("@article", bibtex)
        self.assertIn("10.9999/cjlt.2025.3", bibtex)
        self.assertIn("Zhang, W.", format_citation(search_references(lib_id)[0], style="apa"))

    def test_import_pdf_as_zotero_reference_indexes_text_and_snippet(self):
        lib_id = MaterialLibraryRepo.create("PDF 文献库", topic="平台治理")
        try:
            imported = import_pdf_bytes(lib_id, "platform-governance-paper.pdf", _minimal_pdf_bytes())
        except RuntimeError as e:
            self.assertIn("PDF 解析失败", str(e))
            return

        doc = LibraryDocumentRepo.get(imported["document_id"])
        self.assertEqual(doc["source_type"], "zotero")
        self.assertEqual(doc["mime_type"], "application/pdf")
        self.assertTrue(doc["file_path"].endswith(".pdf"))
        self.assertEqual(doc["attachment_path"], doc["file_path"])
        self.assertEqual(imported["title"], "Platform Governance PDF Title")
        self.assertGreaterEqual(imported["chunk_count"], 1)

        refs = search_references(lib_id, query="Transparency")
        self.assertEqual([r["document_id"] for r in refs], [imported["document_id"]])
        evidence = build_evidence_pack([lib_id], "Transparency", top_k=3)
        self.assertIn("Transparency evidence", evidence["pack"])
        snippet = build_writing_snippet(imported["document_id"])
        self.assertIn("PDF：", snippet)
        self.assertIn("Platform Governance PDF Title", snippet)

    def test_zotero_import_and_filter_render_in_web_ui(self):
        lib_id = MaterialLibraryRepo.create("页面文献库", topic="平台治理")
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.post(
            f"/libraries/{lib_id}",
            data={
                "action": "zotero_import",
                "zotero_format": "csl-json",
                "zotero_text": json.dumps([
                    {
                        "id": "liu2022",
                        "title": "Platform Due Process",
                        "author": [{"given": "Lin", "family": "Liu"}],
                        "issued": {"date-parts": [[2022]]},
                        "container-title": "Law and Technology",
                        "abstract": "Due process for platform moderation.",
                        "keyword": "平台治理",
                    }
                ]),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("已导入 1 条 Zotero-style 文献".encode("utf-8"), response.data)

        filtered = client.post(
            f"/libraries/{lib_id}",
            data={"action": "zotero_search", "zotero_author": "Liu"},
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertIn("Platform Due Process".encode("utf-8"), filtered.data)
        # New workbench layout: center ref-list, no "Zotero 文献列表" heading
        self.assertIn("筛选文献".encode("utf-8"), filtered.data)
        self.assertIn("Liu".encode("utf-8"), filtered.data)

        export_response = client.get(f"/libraries/{lib_id}/zotero/export.bib")
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("Platform Due Process".encode("utf-8"), export_response.data)

        pack_response = client.get(f"/api/v1/libraries/{lib_id}/zotero/reference-pack?q=platform")
        self.assertEqual(pack_response.status_code, 200)
        self.assertGreaterEqual(len(pack_response.get_json()["cards"]), 1)

    def test_zotero_pdf_import_render_in_web_ui(self):
        lib_id = MaterialLibraryRepo.create("页面 PDF 文献库", topic="平台治理")
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.post(
            f"/libraries/{lib_id}",
            data={
                "action": "zotero_pdf_import",
                "zotero_pdf_file": (io.BytesIO(_minimal_pdf_bytes()), "platform-governance-ui.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        if "PDF 解析失败".encode("utf-8") in response.data:
            self.assertIn("缺少 PDF 解析依赖".encode("utf-8"), response.data)
            return
        self.assertIn("已导入 PDF 文献".encode("utf-8"), response.data)
        filtered = client.post(
            f"/libraries/{lib_id}",
            data={"action": "zotero_search", "zotero_query": "Transparency"},
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertIn("Platform Governance PDF Title".encode("utf-8"), filtered.data)


if __name__ == "__main__":
    unittest.main()
