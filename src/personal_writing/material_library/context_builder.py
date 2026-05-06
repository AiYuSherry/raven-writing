"""Build prompt-ready evidence packs from retrieved material chunks."""

from .retrieval import search
from ..zotero_library import build_reference_pack


def build_evidence_pack(library_ids, query, mode="material_first", top_k=8, folder_id=None, folder_name=""):
    """Return an evidence dict with text suitable for model prompts."""
    results = search(library_ids, query or "", top_k=top_k, folder_id=folder_id)
    strict = mode == "strict"
    rule = (
        "只能使用以下证据支持事实判断；证据不足时必须写“需补证”。"
        if strict
        else "优先使用以下证据支持事实判断；证据之外的具体文献、页码、案例和数据不得编造。"
    )
    lines = [
        "## 素材库证据包",
        f"检索问题：{query or '未填写'}",
        f"检索范围：{folder_name or ('文件夹 #' + str(folder_id) if folder_id else '整个素材库')}",
        f"生成规则：{rule}",
    ]
    reference_pack = build_reference_pack(library_ids, query or "", top_k=min(top_k, 5), folder_id=folder_id)
    if reference_pack["cards"]:
        lines.extend([
            "",
            "## 文献引用卡（优先用于论文参考）",
            "以下卡片把文献元数据、摘要/笔记和命中的 PDF/正文片段合并，写作时优先以它们确定参考文献和来源。",
        ])
        for card in reference_pack["cards"]:
            ref = card["reference"]
            lines.extend([
                "",
                f"[{card['label']}] {card['citation']}",
                f"document_id={card['document_id']}",
                f"题名：{ref.get('title', '')}",
                f"作者年份：{ref.get('year') or 'n.d.'}；出处：{ref.get('publicationTitle') or '未填'}",
            ])
            if ref.get("abstract"):
                lines.append(f"摘要：{ref['abstract'][:420]}")
            if ref.get("notes"):
                lines.append(f"笔记：{ref['notes'][:260]}")
            for snippet in card["snippets"]:
                lines.append(
                    f"关键片段 [{snippet['source_label']}] chunk_id={snippet['chunk_id']} "
                    f"{snippet['locator']}: {snippet['text']}"
                )
    if not results:
        lines.extend([
            "",
            "未检索到可用证据。",
            "如果当前任务需要事实、文献、法条、案例或数据支撑，请写“需补证”。",
        ])
    for item in results:
        lines.extend([
            "",
            item["citation_label"],
            f"素材库：{item['library_name'] or item['library_id']}",
            f"文件夹：{item.get('folder_name') or '未分类'}",
            f"原文片段：{item['snippet']}",
            "使用要求：事实性陈述如使用该片段，句末标注 "
            f"[{item['label']}]；不要改变原文含义。",
        ])

    return {
        "library_ids": [int(x) for x in library_ids or []],
        "query": query or "",
        "mode": mode,
        "folder_id": folder_id,
        "folder_name": folder_name or "",
        "results": results,
        "reference_pack": reference_pack,
        "pack": "\n".join(lines).strip(),
    }
