import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import deployment_config
import main_functions


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def ini(self, content):
        path = self.root / 'deployment.ini'
        path.write_text(content, encoding='utf-8-sig')
        return path

    def test_all_distributed_settings_are_valid(self):
        path = Path(__file__).resolve().parents[1] / 'installer' / 'deployment.example.ini'
        values = deployment_config.read_defaults(path)
        self.assertEqual(set(values), set(deployment_config.DEFAULTS) - deployment_config.INSTALLER_TASK_SETTINGS)
        self.assertFalse(values['install_certificates'])

    def test_typed_values_and_user_environment(self):
        path = self.ini('[Defaults]\nnotify=false\ndefault_page=3\nkarma_timeout=1.5\nlast_cert=Тест\ncsp_path=%DEPLOY_TEST_ROOT%\\CSP\n')
        with patch.dict(os.environ, {'DEPLOY_TEST_ROOT': 'D:\\Tools'}):
            values = deployment_config.read_defaults(path)
        self.assertIs(values['notify'], False)
        self.assertEqual(values['default_page'], 3)
        self.assertEqual(values['karma_timeout'], 1.5)
        self.assertEqual(values['last_cert'], 'Тест')
        self.assertEqual(values['csp_path'], 'D:\\Tools\\CSP')

    def test_invalid_deployment_is_rejected(self):
        for content in ('[Defaults]\nautorun=0', '[Defaults]\ndefault_page=4',
                        '[Defaults]\nkarma_timeout=nan', '[Defaults]\nkarma_timeout=-1',
                        '[Defaults]\nkarma_operation_timeout=inf', '[Defaults]\nunknown=true',
                        '[Defaults]\nsigning_mode=wrong', '[Policy]\nautorun=true',
                        '[Defaults]\nautorun=true', '[Defaults]\ncontext_menu=false',
                        '[DEFAULT]\nautorun=true\n[Defaults]',
                        '[Defaults]\nautorun=true\nautorun=false'):
            with self.subTest(content=content):
                with self.assertRaises((ValueError, deployment_config.configparser.Error)):
                    deployment_config.read_defaults(self.ini(content))

    def test_new_profile_defaults_existing_profile_preserved_on_upgrade(self):
        user_file = self.root / 'config.json'
        with patch.object(main_functions, 'read_defaults', return_value={'normalize_to_a4': True, 'default_page': 1}):
            first = main_functions.read_create_config(str(user_file))
        self.assertTrue(first['normalize_to_a4'])
        first['default_page'] = 3
        user_file.write_text(json.dumps(first), encoding='utf-8')
        with patch.object(main_functions, 'read_defaults', return_value={'default_page': 0}):
            upgraded = main_functions.read_create_config(str(user_file))
        self.assertEqual(upgraded['default_page'], 3)
        self.assertTrue(upgraded['normalize_to_a4'])

    def test_rules_seed_does_not_replace_user_rules(self):
        user = self.root / 'user'
        user.mkdir()
        source = self.root / 'default-rules.txt'
        source.write_bytes(b'initial rules')
        with patch.object(deployment_config, 'installation_directory', return_value=self.root):
            deployment_config.seed_rules(user)
            source.write_bytes(b'updated defaults')
            deployment_config.seed_rules(user)
        self.assertEqual((user / 'rules.txt').read_bytes(), b'initial rules')

    def test_rules_accept_utf8_and_legacy_cyrillic(self):
        path = self.root / 'rules.txt'
        for encoding in ('utf-8-sig', 'cp1251'):
            with self.subTest(encoding=encoding):
                path.write_bytes('C:\\Входящие|*.pdf|C:\\Готовые|Да\r\n'.encode(encoding))
                self.assertEqual(deployment_config.read_rules_lines(path)[0], 'C:\\Входящие|*.pdf|C:\\Готовые|Да\r\n')

    def test_installed_binary_uses_parent_deployment(self):
        binary_dir = self.root / 'bin'
        binary_dir.mkdir()
        (self.root / '.documentsigner-install').write_text('marker')
        with patch.object(deployment_config.sys, 'frozen', True, create=True), \
                patch.object(deployment_config.sys, 'executable', str(binary_dir / 'documentSIGner.exe')):
            self.assertEqual(deployment_config.installation_directory(), self.root)

    def test_stamp_uses_user_folder_independent_of_working_directory(self):
        previous = os.getcwd()
        try:
            os.chdir(str(self.root))
            with patch.object(main_functions, 'config_folder', str(self.root)):
                stamp = main_functions.add_text_to_stamp('Тест', '00aabb', '01.01.2026', '01.01.2027')
            self.assertEqual(Path(stamp), self.root / 'modified_stamp.png')
            self.assertTrue(Path(stamp).is_file())
        finally:
            os.chdir(previous)

    def test_autorun_falls_back_to_direct_executable(self):
        with patch.object(main_functions, 'is_machine_install', return_value=False), \
                patch.object(main_functions, 'get_application_executable', return_value=r'C:\Apps\DocumentSIGner\bin\documentSIGner.exe'), \
                patch.object(main_functions.reg, 'CreateKeyEx') as key, \
                patch.object(main_functions.reg, 'SetValueEx') as write:
            self.assertTrue(main_functions.toggle_startup_registry(True))
        self.assertEqual(write.call_args.args[-1], '"C:\\Apps\\DocumentSIGner\\bin\\documentSIGner.exe" -autorun')

    def test_frozen_application_prefers_updater_when_present(self):
        executable = self.root / 'documentSIGner.exe'
        updater = self.root / 'Update.exe'
        with patch.object(main_functions.sys, 'frozen', True, create=True), \
                patch.object(main_functions, 'get_application_executable', return_value=str(executable)):
            self.assertEqual(main_functions.get_application_launcher(), str(executable))
            updater.touch()
            self.assertEqual(main_functions.get_application_launcher(), str(updater))
            with patch.object(main_functions, 'is_machine_install', return_value=False), \
                    patch.object(main_functions.reg, 'CreateKeyEx'), \
                    patch.object(main_functions.reg, 'SetValueEx') as write:
                self.assertTrue(main_functions.toggle_startup_registry(True))
                self.assertEqual(write.call_args.args[-1], '"{}" -autorun'.format(updater))

    def test_machine_install_does_not_write_personal_autorun(self):
        with patch.object(main_functions, 'is_machine_install', return_value=True), \
                patch.object(main_functions.reg, 'CreateKeyEx') as key:
            self.assertFalse(main_functions.toggle_startup_registry(True))
        key.assert_not_called()


if __name__ == '__main__':
    unittest.main()
