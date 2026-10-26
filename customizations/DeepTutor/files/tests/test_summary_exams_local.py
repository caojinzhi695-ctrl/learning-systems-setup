"""Offline checks for the local note-review module, without model requests."""
import json
import unittest
from io import BytesIO
from zipfile import ZipFile

from deeptutor.services.summary_notes.exams import validate_paper, export_word


def fixture(count):
    return {'title': '笔记复习', 'scope': '已保存 AI 笔记', 'questions': [
        {'id': i, 'type': 'recall', 'prompt': f'知识点{i}是什么？', 'answer': '概念',
         'explanation': '说明', 'knowledgePoint': '知识点', 'options': [], 'correctOptions': []}
        for i in range(1, count + 1)], 'recap': ['概念', '方法', '条件']}


class ReviewExamTests(unittest.TestCase):
    def test_material_based_count(self):
        for count in (1, 16, 19, 22):
            self.assertEqual(len(validate_paper(json.dumps(fixture(count)), 'stop')['questions']), count)
        for count in (0, 23):
            with self.assertRaises(ValueError):
                validate_paper(json.dumps(fixture(count)), 'stop')

    def test_incomplete_answers_and_duplicates_are_not_completed(self):
        for key in ('answer', 'explanation'):
            data = fixture(2)
            data['questions'][0][key] = ''
            with self.assertRaises(ValueError):
                validate_paper(json.dumps(data), 'stop')
        data = fixture(2)
        data['questions'][1]['prompt'] = data['questions'][0]['prompt']
        with self.assertRaises(ValueError):
            validate_paper(json.dumps(data), 'stop')
        with self.assertRaises(ValueError):
            validate_paper(json.dumps(fixture(2)), 'length')

    def test_native_word_contains_questions_before_answers(self):
        content = export_word(fixture(22))
        with ZipFile(BytesIO(content)) as archive:
            self.assertIn('[Content_Types].xml', archive.namelist())
            xml = archive.read('word/document.xml').decode()
            self.assertIn('第22题', xml)
            self.assertLess(xml.index('第一部分'), xml.index('第二部分'))
            self.assertIn('w:type="page"', xml)


if __name__ == '__main__':
    unittest.main()
