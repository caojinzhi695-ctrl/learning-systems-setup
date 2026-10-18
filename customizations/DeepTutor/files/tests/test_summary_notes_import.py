import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import pymupdf
from fastapi import FastAPI
from deeptutor.api.routers import summary_notes as api
from deeptutor.services.summary_notes.import_material import extract_material


class MaterialTests(unittest.TestCase):
    def test_pdf_text_and_limits(self):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((40, 40), 'Readable PDF')
            self.assertIn('Readable PDF', extract_material('lesson.pdf', doc.tobytes()))
        self.assertEqual(extract_material('lesson.md', '课程材料'.encode()), '课程材料')
        with self.assertRaises(ValueError): extract_material('too-long.txt', b'x' * 40001)
        with self.assertRaises(ValueError): extract_material('app.exe', b'MZ')


class MaterialApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_import_and_delete_only_selected_note(self):
        app = FastAPI(); app.include_router(api.router)
        with tempfile.TemporaryDirectory() as temp, patch.object(api, 'directory', return_value=Path(temp)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
                response = await client.post('/summary-notes/import', files={'file': ('lesson.txt', '正文'.encode())})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['text'], '正文')
                self.assertEqual((await client.post('/summary-notes/import', files={'file': ('app.exe', b'MZ')})).status_code, 415)
                session = (await client.post('/summary-notes')).json()
                session['turns'] = [{'id': 'a' * 32, 'status': 'failed'}, {'id': 'b' * 32, 'status': 'complete', 'title': '保留的笔记'}]
                path = api.session_path(session['id'])
                api.atomic_write_json(path, session)
                artifact = path.parent / ('a' * 32 + '.html'); artifact.write_text('draft')
                result = await client.delete(f"/summary-notes/{session['id']}/turns/{'a' * 32}")
                self.assertEqual(result.status_code, 200)
                self.assertEqual([item['id'] for item in result.json()['turns']], ['b' * 32])
                self.assertFalse(artifact.exists())
                self.assertEqual((await client.delete(f"/summary-notes/{session['id']}/turns/invalid")).status_code, 404)


if __name__ == '__main__': unittest.main()
