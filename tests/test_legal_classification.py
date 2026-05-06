"""Tests for the legal literature title-based classification engine."""

import unittest
import json

from personal_writing.material_library.classification import (
    classify_title,
    classify_title_multi,
    build_category_tree,
    classify_refs,
    get_rules_json,
    DEFAULT_RULES,
    CATEGORY_ORDER,
    OTHER_CATEGORY,
)


class ClassificationTests(unittest.TestCase):
    """Basic keyword-based title classification accuracy."""

    def test_刑法(self):
        self.assertEqual(classify_title("论刑法的谦抑性原则"), "刑法")
        self.assertEqual(classify_title("刑事证据排除规则研究"), "刑法")
        self.assertEqual(classify_title("正当防卫的界限与判定"), "刑法")
        self.assertEqual(classify_title("受贿罪认定中的若干问题"), "刑法")

    def test_民法(self):
        self.assertEqual(classify_title("民法典合同编违约责任研究"), "民法")
        self.assertEqual(classify_title("物权法中的占有制度"), "民法")
        self.assertEqual(classify_title("格式条款的规制路径"), "民法")

    def test_行政法(self):
        self.assertEqual(classify_title("行政诉讼中的举证责任分配"), "行政法")
        self.assertEqual(classify_title("比例原则在行政法中的适用"), "行政法")
        self.assertEqual(classify_title("政府信息公开的边界"), "行政法")

    def test_宪法(self):
        self.assertEqual(classify_title("违宪审查制度的比较研究"), "宪法")
        self.assertEqual(classify_title("基本权利的限制及其正当化"), "宪法")

    def test_诉讼法(self):
        self.assertEqual(classify_title("民事诉讼法中的证据规则"), "诉讼法")
        self.assertEqual(classify_title("证明责任分配的一般原则"), "诉讼法")

    def test_商法经济法(self):
        self.assertEqual(classify_title("公司破产重整中的债权人保护"), "商法/经济法")
        self.assertEqual(classify_title("上市公司董事信义义务研究"), "商法/经济法")

    def test_知识产权(self):
        self.assertEqual(classify_title("专利侵权损害赔偿研究"), "知识产权")
        self.assertEqual(classify_title("著作权法中的合理使用制度"), "知识产权")
        self.assertEqual(classify_title("商标混淆可能性的判断"), "知识产权")

    def test_劳动法(self):
        self.assertEqual(classify_title("劳动争议仲裁程序研究"), "劳动法")
        self.assertEqual(classify_title("劳动合同法中的经济补偿制度"), "劳动法")

    def test_环境法(self):
        self.assertEqual(classify_title("碳排放权交易的法律规制"), "环境法")
        self.assertEqual(classify_title("环境公益诉讼原告资格研究"), "环境法")

    def test_国际法(self):
        self.assertEqual(classify_title("WTO争端解决机制研究"), "国际法")
        self.assertEqual(classify_title("国际投资仲裁中的管辖权问题"), "国际法")

    def test_数据法网络法(self):
        self.assertEqual(classify_title("个人信息保护法的域外效力"), "数据法/网络法")
        self.assertEqual(classify_title("人工智能伦理问题研究"), "数据法/网络法")
        self.assertEqual(classify_title("算法歧视的法律规制"), "数据法/网络法")

    def test_竞争法(self):
        self.assertEqual(classify_title("反垄断法中的相关市场界定"), "竞争法")
        self.assertEqual(classify_title("滥用市场支配地位的认定标准"), "竞争法")

    def test_税法(self):
        self.assertEqual(classify_title("增值税改革的税法问题"), "税法")
        self.assertEqual(classify_title("国际税收协定中的受益所有人认定"), "税法")

    def test_房地产法(self):
        self.assertEqual(classify_title("农村土地征收补偿制度研究"), "房地产法")
        self.assertEqual(classify_title("宅基地三权分置的法律构造"), "房地产法")

    def test_婚姻家庭法(self):
        self.assertEqual(classify_title("离婚财产分割中的夫妻共同债务认定"), "婚姻家庭法")
        self.assertEqual(classify_title("未成年人监护制度研究"), "婚姻家庭法")

    def test_其他(self):
        self.assertEqual(classify_title("法律解释方法研究"), OTHER_CATEGORY)
        self.assertEqual(classify_title(""), OTHER_CATEGORY)
        self.assertEqual(classify_title("Some English title without keywords"), OTHER_CATEGORY)

    def test_multi_label(self):
        cats = classify_title_multi("数据犯罪与个人信息保护研究")
        self.assertIn("刑法", cats)
        self.assertIn("数据法/网络法", cats)

    def test_empty_title_multi(self):
        self.assertEqual(classify_title_multi(""), [OTHER_CATEGORY])

    def test_build_category_tree(self):
        refs = [
            {"title": "论刑法的谦抑性原则", "document_id": 1},
            {"title": "民法典合同编研究", "document_id": 2},
            {"title": "个人信息保护法研究", "document_id": 3},
        ]
        tree = build_category_tree(refs)
        self.assertEqual(tree[0]["name"], "全部文档")
        self.assertEqual(tree[0]["count"], 3)
        names = {n["name"] for n in tree}
        self.assertIn("刑法", names)
        self.assertIn("民法", names)
        self.assertIn("数据法/网络法", names)

    def test_classify_refs(self):
        refs = [
            {"document_id": 1, "title": "刑法研究"},
            {"document_id": 2, "title": "民法研究"},
        ]
        result = classify_refs(refs)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["categories"], ["刑法"])
        self.assertEqual(result[0]["primary_category"], "刑法")
        self.assertEqual(result[1]["categories"], ["民法"])

    def test_rules_json_serializable(self):
        rules = get_rules_json()
        serialized = json.dumps(rules, ensure_ascii=False)
        self.assertIsInstance(serialized, str)
        self.assertIn("刑法", rules)
        self.assertIn("民法", rules)

    def test_all_categories_have_rules(self):
        for cat in CATEGORY_ORDER:
            self.assertIn(cat, DEFAULT_RULES,
                          f"Category '{cat}' has no rules defined")


if __name__ == "__main__":
    unittest.main()
