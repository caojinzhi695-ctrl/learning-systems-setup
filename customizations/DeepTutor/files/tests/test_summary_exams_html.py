import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from fastapi import FastAPI
import httpx
from deeptutor.api.routers import summary_exams as api
from deeptutor.services.summary_notes.exams import export_html

PAPER = {'title':'中文 <script>alert(1)</script>', 'scope':'离线测试', 'questions':[{'id':1,'type':'single','prompt':'请选择 <img src=x onerror=alert(1)>','options':[{'key':'A','text':'甲 & 乙'}], 'correctOptions':['A'],'answer':'甲','explanation':'解释','knowledgePoint':'知识点'}], 'recap':['复习一下']}

class HtmlExamTests(unittest.IsolatedAsyncioTestCase):
    def test_interactive_template_escapes_and_has_no_external_dependencies(self):
        from deeptutor.services.summary_notes.exams import interactive_note
        html=export_html(PAPER)
        soup=BeautifulSoup(html,'html.parser')
        self.assertEqual(soup.html['lang'],'zh-CN')
        self.assertEqual(len(soup.find_all('script')),1)
        self.assertIsNone(soup.find('script',src=True))
        self.assertIsNone(soup.find('img'))
        self.assertIsNone(soup.find('link'))
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertNotIn('__DEEPTUTOR_EXAM_DATA__',html)
        self.assertIn("default-src 'none'",soup.find('meta',{'http-equiv':'Content-Security-Policy'})['content'])
        note=interactive_note(PAPER)
        self.assertEqual(note['questions'][0]['correct'],[0])
        self.assertEqual(note['id'],interactive_note(PAPER)['id'])
        self.assertEqual(interactive_note(PAPER,'fixed-id')['id'],'fixed-id')
    async def test_download_saved_paper_and_reject_incomplete(self):
        app=FastAPI();app.include_router(api.router)
        turn={'exams':[{'id':'exam','status':'complete','paper':PAPER}]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local') as client:
            with patch.object(api,'turn_for',return_value=({},turn)):
                result=await client.get('/session/turns/turn/exams/exam/html')
                self.assertEqual(result.status_code,200)
                self.assertIn('attachment;',result.headers['content-disposition'])
                self.assertIn('.html',result.headers['content-disposition'])
                self.assertTrue(result.headers['content-type'].startswith('text/html'))
                turn['exams'][0]['status']='generating'
                self.assertEqual((await client.get('/session/turns/turn/exams/exam/html')).status_code,404)
                self.assertEqual((await client.get('/session/turns/turn/exams/missing/html')).status_code,404)
