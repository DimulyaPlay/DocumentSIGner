import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import certificate_installation as certificates


class CertificateInstallationTests(unittest.TestCase):
    def test_routes_roots_and_intermediates_and_skips_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('a.crt', 'b.CER', 'c.pem', 'ignored.txt'):
                Path(directory, name).touch()
            with patch.object(certificates.subprocess, 'run') as run:
                run.side_effect = [Mock(stdout='Root\n'), Mock(),
                                   Mock(stdout='CA\n'), Mock(), Mock(stdout='')]
                certificates.install_certificates_from_directory(directory)
            imports = [call.args[0] for call in run.call_args_list
                       if call.args[0][0] == 'certutil']
            self.assertEqual(imports, [
                ['certutil', '-user', '-addstore', 'Root', os.path.join(directory, 'a.crt')],
                ['certutil', '-user', '-addstore', 'CA', os.path.join(directory, 'b.CER')],
            ])

    def test_declined_root_does_not_block_other_certificates(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'a.crt').touch()
            Path(directory, 'b.crt').touch()
            with patch.object(certificates.subprocess, 'run') as run:
                run.side_effect = [Mock(stdout='Root'),
                                   subprocess.CalledProcessError(1, 'certutil'),
                                   Mock(stdout='CA'), Mock()]
                certificates.install_certificates_from_directory(directory)
            self.assertEqual(run.call_count, 4)

    def test_windows_parser_reads_bundled_certificates_without_installing(self):
        for path in Path('root_certificates').iterdir():
            with self.subTest(path=path):
                env = os.environ.copy()
                env['DOCUMENTSIGNER_CERTIFICATE_PATH'] = str(path.resolve())
                result = subprocess.run(
                    ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                     certificates._INSPECT_CERTIFICATE],
                    env=env, capture_output=True, text=True, check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self.assertIn(result.stdout.strip(), ('', 'CA', 'Root'))


if __name__ == '__main__':
    unittest.main()
