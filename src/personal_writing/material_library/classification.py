"""Legal literature title-based classification engine.

Configurable keyword rules for auto-categorizing legal scholarship into
Chinese legal sub-disciplines. Rules can be customized at runtime.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# ── Default Rules ──────────────────────────────────────────────────────────
# Format: {category_name: [[keyword_group_1], [keyword_group_2], ...]}
# A document matches a category if ANY keyword group matches (OR logic).
# Within a keyword group, ANY single keyword match suffices.
# Groups allow: category A matches on [keywordA, keywordB] OR [keywordC]
DEFAULT_RULES: Dict[str, List[List[str]]] = {
    "刑法": [
        ["刑法", "犯罪", "刑罚", "定罪", "量刑", "刑事",
         "刑事责任", "故意", "过失", "未遂", "共犯",
         "死刑", "扫黑除恶", "经济犯罪", "职务犯罪",
         "毒品犯罪", "网络犯罪", "恐怖主义", "黑社会",
         "腐败", "受贿", "贪污", "渎职", "正当防卫",
         "紧急避险", "自首", "立功", "累犯", "缓刑",
         "假释", "减刑", "数罪并罚", "追诉时效"],
    ],
    "民法": [
        ["民法",
         "合同编", "物权编", "侵权责任编", "婚姻家庭编",
         "合同", "侵权", "物权", "担保物权",
         "不当得利", "无因管理", "缔约过失", "违约责任",
         "所有权", "用益物权", "占有",
         "产品责任", "医疗损害",
         "格式条款", "情势变更",
         "代位权", "撤销权",
         "买卖", "租赁", "承揽", "委托", "赠与"],
    ],
    "行政法": [
        ["行政", "政府", "许可", "处罚", "复议", "行政诉讼",
         "行政行为", "行政强制", "行政赔偿", "行政协议",
         "信息公开", "行政许可", "行政处罚", "行政处分",
         "行政复议", "国家赔偿", "公务员", "行政主体",
         "行政裁量", "比例原则", "信赖保护", "行政法"],
    ],
    "宪法": [
        ["宪法", "基本法", "违宪", "基本权利", "宪制",
         "宪政", "宪法解释", "宪法监督", "宪法修改",
         "国家机构", "人民代表大会", "立法权",
         "民族区域自治", "特别行政区", "选举",
         "合宪性审查", "宪法实施"],
    ],
    "诉讼法": [
        ["诉讼", "诉讼法", "证据", "审判", "管辖", "裁判",
         "民事诉讼法", "刑事诉讼法", "行政诉讼法",
         "起诉", "上诉", "再审", "抗诉",
         "举证责任", "证明责任", "证明标准", "非法证据排除",
         "司法鉴定",
         "保全", "先予执行", "强制执行", "仲裁", "调解",
         "诉讼时效", "期间", "送达", "回避", "诉讼参加人",
         "程序法", "程序正义", "程序"],
    ],
    "商法/经济法": [
        ["公司法", "破产", "证券", "金融", "信托", "保险", "银行",
         "商事", "商法", "合伙企业", "有限责任",
         "股份", "股东", "董事会", "监事会", "独立董事",
         "上市公司", "并购", "重组", "清算", "破产重整",
         "票据", "信用证", "保理", "融资租赁", "期货", "基金",
         "宏观调控", "产业政策", "经济法",
         "价格法", "会计法", "审计法"],
    ],
    "知识产权": [
        ["知识产权", "专利", "商标", "著作权", "版权",
         "发明", "实用新型", "外观设计",
         "驰名商标", "地理标志", "商业秘密", "不正当竞争",
         "商标注册", "专利申请", "创造性", "新颖性", "实用性",
         "知识产权法"],
    ],
    "劳动法": [
        ["劳动", "工伤", "社保", "劳动合同", "劳动争议",
         "劳动法", "劳动合同法", "社会保险",
         "养老保险", "医疗保险", "失业保险", "工伤保险",
         "工资", "工时", "加班", "劳务派遣",
         "集体合同", "工会", "女职工保护", "劳动仲裁",
         "劳动关系", "劳动报酬", "劳动监察", "就业促进",
         "职业病防治"],
    ],
    "环境法": [
        ["环境", "排污", "环评", "自然资源", "环保",
         "环境保护", "环境污染", "生态",
         "碳排放", "碳中和", "碳达峰", "排污权", "环境影响评价",
         "环境公益诉讼", "矿产资源", "森林法",
         "海洋环境保护", "大气污染防治", "野生动物保护",
         "环境法"],
    ],
    "国际法": [
        ["国际法", "条约", "WTO", "国际私法", "海牙",
         "国际公法", "国际人权法", "国际人道法", "海洋法",
         "国际刑法", "国际法院", "国际仲裁", "国际投资法",
         "国际贸易法", "国际商事", "联合国",
         "主权", "国籍", "引渡", "庇护", "外交豁免",
         "冲突法", "准据法", "域外管辖",
         "区际法律冲突", "港澳基本法",
         "国际投资", "投资仲裁", "国际商事仲裁",
         "外国仲裁", "跨国"],
    ],
    "数据法/网络法": [
        ["数据", "个人信息", "隐私", "网络安全", "算法", "AI",
         "人工智能", "大数据", "区块链", "数字货币",
         "个人信息保护", "数据安全", "数据跨境", "数据产权",
         "数据治理", "算法治理", "平台经济", "平台责任",
         "电子商务", "电子签名", "电子合同",
         "网络治理", "算法规制", "被遗忘权",
         "关键信息基础设施", "数据要素"],
    ],
    "竞争法": [
        ["竞争", "反垄断", "不正当竞争",
         "垄断", "垄断协议", "滥用市场支配地位",
         "经营者集中", "相关市场", "市场支配地位",
         "反垄断法", "反不正当竞争法",
         "虚假宣传", "商业诋毁"],
    ],
    "税法": [
        ["税法", "财政", "税务", "税收",
         "所得税", "增值税", "消费税", "关税",
         "房产税", "契税",
         "税收征管", "税收优惠", "税收抵免",
         "国际税收", "转让定价", "反避税",
         "预算法", "国债", "政府采购"],
    ],
    "房地产法": [
        ["房地产", "土地", "拆迁", "征收",
         "不动产权", "土地使用权", "建设用地",
         "房屋买卖", "房屋租赁", "物业管理", "业主",
         "商品房", "经济适用房",
         "土地征收", "土地出让",
         "农村土地", "宅基地", "承包地",
         "三权分置", "城乡规划", "土地管理法"],
    ],
    "婚姻家庭法": [
        ["婚姻", "家庭", "继承", "抚养", "赡养", "离婚",
         "结婚", "夫妻", "夫妻财产", "共同财产",
         "离婚财产分割", "子女抚养", "探视权", "收养", "监护",
         "继承法", "法定继承", "遗嘱继承", "遗赠",
         "遗产", "代位继承", "转继承",
         "家庭暴力", "彩礼", "同居", "事实婚姻",
         "非婚生子女", "婚姻法", "家事"],
    ],
}

# Display order for categories in the tree
# More specific categories come first; 民法 (broad) last among specific ones.
CATEGORY_ORDER: List[str] = [
    "宪法", "行政法", "刑法",
    "劳动法", "环境法", "知识产权",
    "商法/经济法", "竞争法", "税法",
    "国际法", "数据法/网络法",
    "婚姻家庭法", "房地产法",
    "诉讼法",
    "民法",
]

OTHER_CATEGORY = "综合/未分类"


def classify_title(title: str, rules: Optional[Dict[str, List[List[str]]]] = None) -> str:
    """Return the first (primary) matching category for a title.

    Returns OTHER_CATEGORY if no rule matches.
    """
    if not title:
        return OTHER_CATEGORY

    rules = rules or DEFAULT_RULES
    for cat in CATEGORY_ORDER:
        if cat not in rules:
            continue
        for group in rules[cat]:
            if any(kw in title for kw in group):
                return cat
    return OTHER_CATEGORY


def classify_title_multi(
    title: str, rules: Optional[Dict[str, List[List[str]]]] = None
) -> List[str]:
    """Return ALL matching categories for a title (multi-label classification).

    Returns [OTHER_CATEGORY] if no match.
    """
    if not title:
        return [OTHER_CATEGORY]

    rules = rules or DEFAULT_RULES
    matched: List[str] = []
    for cat in CATEGORY_ORDER:
        if cat not in rules:
            continue
        for group in rules[cat]:
            if any(kw in title for kw in group):
                matched.append(cat)
                break
    return matched if matched else [OTHER_CATEGORY]


def build_category_tree(
    refs: List[dict],
    rules: Optional[Dict[str, List[List[str]]]] = None,
) -> List[dict]:
    """Build a category tree with document counts from a list of references.

    Each result: {"name": str, "key": str, "count": int}
    The first entry is always "全部文档" (all documents).
    """
    rules = rules or DEFAULT_RULES
    counts: Dict[str, int] = {c: 0 for c in CATEGORY_ORDER}
    counts[OTHER_CATEGORY] = 0

    for ref in refs:
        title = ref.get("title") or ref.get("original_filename", "")
        for cat in classify_title_multi(title, rules):
            if cat in counts:
                counts[cat] += 1
            else:
                counts[cat] = 1

    tree = [
        {"name": "全部文档", "key": "__all__", "count": len(refs)},
    ]
    for cat in CATEGORY_ORDER:
        if counts.get(cat, 0) > 0:
            tree.append({"name": cat, "key": cat, "count": counts[cat]})
    if counts.get(OTHER_CATEGORY, 0) > 0:
        tree.append(
            {"name": OTHER_CATEGORY, "key": OTHER_CATEGORY, "count": counts[OTHER_CATEGORY]}
        )
    return tree


def get_rules_json() -> dict:
    """Return rules in a JSON-serializable format for frontend use."""
    return {
        cat: [group for group in groups]
        for cat, groups in DEFAULT_RULES.items()
    }


def get_rules_json_for_js() -> str:
    """Return rules as a JSON string for embedding in JavaScript."""
    import json
    return json.dumps(get_rules_json(), ensure_ascii=False)


def classify_ref(
    ref: dict, rules: Optional[Dict[str, List[List[str]]]] = None
) -> str:
    """Classify a single reference dict by its title."""
    return classify_title(ref.get("title") or ref.get("original_filename", ""), rules)


def classify_refs(
    refs: List[dict], rules: Optional[Dict[str, List[List[str]]]] = None
) -> List[dict]:
    """Classify a list of reference dicts, adding a 'categories' field to each."""
    rules = rules or DEFAULT_RULES
    result = []
    for ref in refs:
        ref = dict(ref)
        ref["categories"] = classify_title_multi(ref.get("title") or ref.get("original_filename", ""), rules)
        ref["primary_category"] = ref["categories"][0]
        result.append(ref)
    return result
