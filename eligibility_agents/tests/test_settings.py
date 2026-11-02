import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from dotenv import dotenv_values
from settings import load_server_config, migrate_example
from streamlit.testing.v1 import AppTest


class SettingsTest(unittest.TestCase):
    def test_key_migrates_without_exposing_in_example(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / '.env.example').write_text('OPENAI_API_KEY="test-secret-local"\nOPENAI_MODEL=gpt-4o-mini\nAPP_PASSWORD=local-password\n')
            config = load_server_config(root=root)
            self.assertEqual(config.api_key, 'test-secret-local')
            self.assertEqual(config.password, 'local-password')
            self.assertEqual(dotenv_values(root / '.env')['OPENAI_API_KEY'], 'test-secret-local')
            self.assertNotIn('test-secret-local', (root / '.env.example').read_text())
            self.assertNotIn('local-password', (root / '.env.example').read_text())
            migrate_example(root)
            self.assertEqual(load_server_config(root=root).api_key, config.api_key)
            self.assertNotIn('test-secret-local', repr(config))

    def test_existing_different_key_is_preserved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.example').write_text('OPENAI_API_KEY=test-secret-old\n')
            (root / '.env').write_text('OPENAI_API_KEY=test-secret-current\n')
            with self.assertRaises(ValueError) as caught:
                migrate_example(root)
            self.assertNotIn('test-secret', str(caught.exception))
            self.assertIn('test-secret-current', (root / '.env').read_text())
            self.assertIn('test-secret-old', (root / '.env.example').read_text())

    def test_failed_write_keeps_original(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.example').write_text('OPENAI_API_KEY=test-secret-old\n')
            with patch('settings.set_key', side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    migrate_example(root)
            self.assertIn('test-secret-old', (root / '.env.example').read_text())

    def test_cloud_secrets_take_priority(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / '.env').write_text('OPENAI_API_KEY=local-key\n')
            config = load_server_config({'OPENAI_API_KEY':'cloud-secret', 'DEBATE_ROUNDS':3}, root=root)
            self.assertEqual(config.api_key, 'cloud-secret')
            self.assertEqual(config.rounds, 3)

    def test_missing_key_has_no_input_widget(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            with patch('settings.ROOT', Path(directory)):
                # Explicit root to avoid the function's captured default during test.
                import settings
                original = settings.load_server_config
                with patch('settings.load_server_config', side_effect=lambda secrets: original(secrets, root=Path(directory))):
                    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
                    self.assertEqual(len(app.exception), 0)
                    self.assertFalse(any('API' in widget.label for widget in app.text_input))
                    self.assertTrue(next(b for b in app.button if b.label == '지원 적격성 분석 시작').disabled)
                    self.assertTrue(any('공고핏' in title.value for title in app.title))

    def test_configured_key_is_never_rendered(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
        app.secrets['OPENAI_API_KEY'] = 'unique-test-secret-never-show'
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn('unique-test-secret-never-show', str(app.get('text_input')))
        self.assertFalse(any('API' in widget.label for widget in app.text_input))


if __name__ == '__main__':
    unittest.main()
