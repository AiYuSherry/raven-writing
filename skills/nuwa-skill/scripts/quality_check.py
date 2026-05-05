#!/usr/bin/env python3
"""
自动检查生成的SKILL.md是否通过Phase 4质量标准。
对照通过标准表格逐项检查，输出通过/不通过和具体原因。

用法:
    python3 quality_check.py <SKILL.md路径或skill目录>

示例:
    python3 quality_check.py .claude/skills/elon-musk-perspective/SKILL.md
    python3 quality_check.py .claude/skills/elon-musk-perspective
"""

import sys
import re
from pathlib import Path


def check_mental_models(content: str) -> tuple[bool, str]:
    """检查心智模型数量（3-7个）"""
    # 匹配 ### 模型N: 或 ### N. 等模式
    models = re.findall(r'^###\s+(?:模型|Model|心智模型)\s*\d', content, re.MULTILINE)
    if not models:
        # fallback: 数「### 」开头的行在心智模型section中
        in_section = False
        count = 0
        for line in content.split('\n'):
            if re.match(r'^##\s+.*心智模型|Mental Model', line, re.IGNORECASE):
                in_section = True
                continue
            if in_section and re.match(r'^##\s+', line) and '心智模型' not in line:
                break
            if in_section and re.match(r'^###\s+', line):
                count += 1
        if count > 0:
            passed = 3 <= count <= 7
            return passed, f"{count}个心智模型 {'✅' if passed else '❌ (应为3-7个)'}"

    count = len(models)
    if count == 0:
        return False, "未检测到心智模型section"
    passed = 3 <= count <= 7
    return passed, f"{count}个心智模型 {'✅' if passed else '❌ (应为3-7个)'}"


def check_limitations(content: str) -> tuple[bool, str]:
    """检查每个模型是否有局限性"""
    has_limitation = bool(re.search(r'局限|失效|不适用|盲区|limitation|blind spot', content, re.IGNORECASE))
    return has_limitation, "有局限性标注 ✅" if has_limitation else "❌ 未找到局限性描述"


def check_expression_dna(content: str) -> tuple[bool, str]:
    """检查表达DNA辨识度"""
    dna_section = bool(re.search(r'表达DNA|Expression DNA|表达风格', content, re.IGNORECASE))
    if not dna_section:
        return False, "❌ 未找到表达DNA section"

    # 检查是否有具体的风格描述（句式、词汇等）
    style_markers = len(re.findall(r'句式|词汇|语气|幽默|节奏|确定性|引用|口头禅', content))
    passed = style_markers >= 3
    return passed, f"表达DNA特征: {style_markers}项 {'✅' if passed else '❌ (应≥3项)'}"


def check_honest_boundary(content: str) -> tuple[bool, str]:
    """检查诚实边界（至少3条）"""
    # 找诚实边界section
    boundary_match = re.search(r'(?:##\s+.*诚实边界|## Honest Boundary)(.*?)(?=\n##\s|\Z)', content, re.DOTALL | re.IGNORECASE)
    if not boundary_match:
        return False, "❌ 未找到诚实边界section"

    boundary_text = boundary_match.group(1)
    # 计算列表项
    items = re.findall(r'^[-*]\s+', boundary_text, re.MULTILINE)
    count = len(items)
    passed = count >= 3
    return passed, f"诚实边界: {count}条 {'✅' if passed else '❌ (应≥3条)'}"


def check_tensions(content: str) -> tuple[bool, str]:
    """检查内在张力（至少2对）"""
    tension_markers = len(re.findall(r'张力|矛盾|tension|paradox|一方面.*另一方面|既.*又', content, re.IGNORECASE))
    passed = tension_markers >= 2
    return passed, f"内在张力: {tension_markers}处 {'✅' if passed else '❌ (应≥2处)'}"


def check_primary_sources(content: str) -> tuple[bool, str]:
    """检查一手来源占比"""
    # 找调研来源section
    source_section = re.search(r'(?:##\s+.*来源|## Source|## Reference)(.*?)(?=\n##\s|\Z)', content, re.DOTALL | re.IGNORECASE)
    if not source_section:
        return True, "未找到来源section（跳过检查）"

    source_text = source_section.group(1)
    primary = len(re.findall(r'一手|primary|本人著作|原始', source_text, re.IGNORECASE))
    secondary = len(re.findall(r'二手|secondary|转述|评论', source_text, re.IGNORECASE))
    total = primary + secondary
    if total == 0:
        return True, "未标记来源类型（跳过检查）"

    ratio = primary / total
    passed = ratio > 0.5
    return passed, f"一手来源占比: {primary}/{total} ({ratio:.0%}) {'✅' if passed else '❌ (应>50%)'}"


def is_nuwa_generator_skill(content: str) -> bool:
    """判断是否为女娲这类 academic author 生成器 skill。"""
    markers = [
        "女娲",
        "学术作者路径",
        "生成 academic author skill",
        "Phase A0.75",
        "academic-author-template.md",
        "academic-author-distillation.md",
    ]
    return sum(1 for marker in markers if marker in content) >= 4


def is_academic_author_skill(content: str) -> bool:
    """判断是否为学术作者写作模型。"""
    markers = [
        "学术作者写作模型",
        "论文作者蒸馏",
        "论文写作模板",
        "问题意识",
        "概念词库",
        "论证框架",
    ]
    return sum(1 for marker in markers if marker in content) >= 3


def check_nuwa_academic_author_inheritance(content: str) -> tuple[bool, str]:
    """检查女娲是否默认把 academic author 强约束写入生成路径。"""
    required_markers = [
        "Phase A0.75",
        "样本文笔对照",
        "样本文笔对照笔记",
        "前置产物",
        "暂停完整成文",
        "一手样本文本",
        "已抽取的一手样本研究文件",
        "失败产出反例",
        "个人信息同意撤回权",
        "quality gate",
        "低相似度警报",
        "样本缺失暂停规则",
    ]
    hits = [item for item in required_markers if item in content]
    passed = len(hits) >= 10
    return passed, f"学术作者继承机制: {len(hits)}/{len(required_markers)} {'✅' if passed else '❌'}"


def check_nuwa_template_links(content: str) -> tuple[bool, str]:
    """检查女娲是否要求读取 academic author 模板和蒸馏细则。"""
    markers = [
        "references/academic-author-distillation.md",
        "references/academic-author-template.md",
        "references/research/",
        "style-comparison-notes.md",
        "object-research-dossier.md",
    ]
    hits = [item for item in markers if item in content]
    passed = len(hits) >= 4
    return passed, f"模板/研究文件链接: {len(hits)}/{len(markers)} {'✅' if passed else '❌'}"


def check_academic_boundaries(content: str) -> tuple[bool, str]:
    """检查学术作者 skill 是否明确非冒充边界。"""
    required = ["不代表", "不得冒充", "不署", "不编造"]
    hits = [item for item in required if item in content]
    passed = len(hits) >= 3
    return passed, f"边界声明: {len(hits)}/4 {'✅' if passed else '❌ (需明确非本人观点/不冒充/不署名/不编造)'}"


def check_academic_corpus(content: str) -> tuple[bool, str]:
    """检查语料分层。"""
    markers = ["一手", "语境材料", "context", "source", "references/research", "调研来源"]
    hits = [item for item in markers if item in content]
    passed = len(hits) >= 3
    return passed, f"语料分层: {len(hits)}项 {'✅' if passed else '❌ (需区分一手样本与语境材料)'}"


def check_academic_problem_consciousness(content: str) -> tuple[bool, str]:
    """检查问题意识密度。"""
    section = bool(re.search(r'##\s+.*问题意识', content))
    entries = len(re.findall(r'^###\s+', content, re.MULTILINE))
    markers = len(re.findall(r'遮蔽|流行|分类|框架|问题|批判|重建|解释', content))
    passed = section and entries >= 3 and markers >= 12
    return passed, f"问题意识: section={section}, 条目={entries}, 标记={markers} {'✅' if passed else '❌'}"


def check_academic_argument_system(content: str) -> tuple[bool, str]:
    """检查概念、谱系、论证和论文模板。"""
    required_sections = ["思想谱系", "概念词库", "论证框架", "论文写作模板", "表达 DNA", "反模式"]
    hits = [section for section in required_sections if section in content]
    passed = len(hits) == len(required_sections)
    return passed, f"学术写作系统: {len(hits)}/{len(required_sections)} {'✅' if passed else '❌'}"


def check_academic_object_research(content: str) -> tuple[bool, str]:
    """检查写作对象研究流程。"""
    required_markers = [
        "对象研究",
        "网络检索",
        "本地核验",
        "来源优先级",
        "object-research-dossier",
    ]
    alternate_markers = [
        "官方文档",
        "CLI",
        "GitHub",
        "法律法规",
        "监管文件",
        "司法案例",
    ]
    hits = [item for item in required_markers if item in content]
    alternates = [item for item in alternate_markers if item in content]
    passed = len(hits) >= 4 and len(alternates) >= 3
    return passed, f"对象研究: 核心{len(hits)}/5, 来源{len(alternates)}/6 {'✅' if passed else '❌'}"


def check_academic_literature_research(content: str) -> tuple[bool, str]:
    """检查网络检索、私有知识库检索、文献观点阅读与作者模型转化流程。"""
    required_markers = [
        "网络检索",
        "ima",
        "知识库",
        "学术文献",
        "文献观点",
        "作者模型",
    ]
    workflow_markers = [
        "数字法学研究",
        "论文检索",
        "摘要",
        "高亮",
        "片段",
        "三层材料",
        "事实层",
        "文献层",
    ]
    boundary_markers = [
        "不得直接",
        "不能替代",
        "不能只凭",
        "没有完成",
    ]
    hits = [item for item in required_markers if item in content]
    workflow_hits = [item for item in workflow_markers if item in content]
    boundary_hits = [item for item in boundary_markers if item in content]
    passed = len(hits) >= 5 and len(workflow_hits) >= 5 and len(boundary_hits) >= 2
    return passed, f"学术文献检索: 核心{len(hits)}/6, 流程{len(workflow_hits)}/8, 边界{len(boundary_hits)}/4 {'✅' if passed else '❌'}"


def check_academic_risk_spectrum(content: str) -> tuple[bool, str]:
    """检查法律风险谱系。"""
    risk_markers = [
        "数据",
        "个人信息",
        "权限",
        "身份",
        "memory",
        "skills",
        "plugins",
        "日志",
        "证据",
        "著作权",
        "网络安全",
        "专业责任",
        "组织授权",
    ]
    hits = [item for item in risk_markers if item in content]
    passed = len(hits) >= 8
    return passed, f"风险谱系: {len(hits)}/13 {'✅' if passed else '❌'}"


def check_academic_fact_model_separation(content: str) -> tuple[bool, str]:
    """检查事实层与作者模型层分离。"""
    markers = [
        "事实来自",
        "文献观点来自",
        "论证方式来自",
        "作者模型",
        "事实层",
        "文献层",
        "风险层",
        "三层材料",
        "不能用作者",
    ]
    hits = [item for item in markers if item in content]
    passed = len(hits) >= 6
    return passed, f"事实/文献/模型分离: {len(hits)}/9 {'✅' if passed else '❌'}"


def check_academic_style_comparison(content: str) -> tuple[bool, str]:
    """检查学术作者 skill 是否有样本文笔对照层和低相似度退回规则。"""
    required_markers = [
        "样本文笔对照",
        "一手写作样本",
        "句法",
        "段落节奏",
        "概念链",
        "相似度硬约束",
        "低相似度警报",
        "重写",
    ]
    failure_markers = [
        "只检索",
        "只做对象研究",
        "只套",
        "只提高概念密度",
        "不能只迁移",
        "问题意识像",
    ]
    boundary_markers = [
        "context_only",
        "语境材料",
        "不得作为",
        "不得复制",
        "不得冒充",
    ]
    prerequisite_markers = [
        "前置产物",
        "暂停完整成文",
        "一手样本文本",
        "已抽取的一手样本研究文件",
        "未完成样本文笔对照",
    ]
    failure_example_markers = [
        "个人信息同意撤回权",
        "概念密度高但作者文笔不像",
        "quality gate",
        "失败反例",
    ]
    hits = [item for item in required_markers if item in content]
    failure_hits = [item for item in failure_markers if item in content]
    boundary_hits = [item for item in boundary_markers if item in content]
    prerequisite_hits = [item for item in prerequisite_markers if item in content]
    failure_example_hits = [item for item in failure_example_markers if item in content]
    passed = (
        len(hits) >= 6
        and len(failure_hits) >= 3
        and len(boundary_hits) >= 3
        and len(prerequisite_hits) >= 3
        and len(failure_example_hits) >= 2
    )
    return passed, (
        f"样本文笔对照: 核心{len(hits)}/8, "
        f"失败模式{len(failure_hits)}/6, 边界{len(boundary_hits)}/5, "
        f"前置/暂停{len(prerequisite_hits)}/5, 反例{len(failure_example_hits)}/4 "
        f"{'✅' if passed else '❌'}"
    )


def check_no_placeholders(content: str) -> tuple[bool, str]:
    """检查占位符，忽略禁止占位符的规则说明本身。"""
    placeholder_re = re.compile(r'TODO|TBD|xxx|待补充|\[人名\]|\[来源|\[概念\]|\[动作\]', re.IGNORECASE)
    count = 0
    for line in content.splitlines():
        if "不留下" in line and "占位符" in line:
            continue
        count += len(placeholder_re.findall(line))
    passed = count == 0
    return passed, f"占位符: {count}处 {'✅' if passed else '❌'}"


def main():
    if len(sys.argv) < 2:
        print("用法: python3 quality_check.py <SKILL.md路径>")
        sys.exit(1)

    skill_path = Path(sys.argv[1])
    if skill_path.is_dir():
        skill_path = skill_path / "SKILL.md"
    if not skill_path.exists():
        print(f"❌ 文件不存在: {skill_path}")
        sys.exit(1)

    content = skill_path.read_text(encoding='utf-8')

    if is_nuwa_generator_skill(content):
        checks = [
            ("学术作者继承", check_nuwa_academic_author_inheritance),
            ("模板链接", check_nuwa_template_links),
            ("占位符", check_no_placeholders),
        ]
    elif is_academic_author_skill(content):
        checks = [
            ("非冒充边界", check_academic_boundaries),
            ("语料分层", check_academic_corpus),
            ("对象研究", check_academic_object_research),
            ("学术文献检索", check_academic_literature_research),
            ("风险谱系", check_academic_risk_spectrum),
            ("事实模型分离", check_academic_fact_model_separation),
            ("样本文笔对照", check_academic_style_comparison),
            ("问题意识", check_academic_problem_consciousness),
            ("写作系统", check_academic_argument_system),
            ("表达DNA", check_expression_dna),
            ("占位符", check_no_placeholders),
        ]
    else:
        checks = [
            ("心智模型数量", check_mental_models),
            ("模型局限性", check_limitations),
            ("表达DNA辨识度", check_expression_dna),
            ("诚实边界", check_honest_boundary),
            ("内在张力", check_tensions),
            ("一手来源占比", check_primary_sources),
        ]

    print(f"质量检查: {skill_path.name}")
    print("=" * 50)

    passed_count = 0
    total = len(checks)

    for name, check_fn in checks:
        passed, detail = check_fn(content)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name:<12} {status}  {detail}")
        if passed:
            passed_count += 1

    print("=" * 50)
    print(f"结果: {passed_count}/{total} 通过")

    if passed_count == total:
        print("🎉 全部通过，可以交付")
    elif passed_count >= total - 1:
        print("⚠️ 基本通过，建议修复不通过项后交付")
    else:
        print("❌ 多项不通过，建议回到Phase 2迭代")

    sys.exit(0 if passed_count == total else 1)


if __name__ == '__main__':
    main()
