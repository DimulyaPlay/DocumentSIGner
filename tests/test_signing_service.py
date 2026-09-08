import base64
import os
import tempfile
import unittest
from unittest import mock

import signing_service


class FakeKarmaClient:
    base_url = 'http://127.0.0.1:8080/'

    def __init__(self, raw_certificate):
        self.raw_certificate = raw_certificate
        self.calls = []

    def service_info(self):
        return {'appName': 'eoscryptosvc', 'carmaVersion': '56.0.219'}

    def request(self, mode, **fields):
        self.calls.append((mode, fields))
        if mode == 38:
            return {'errorCode': 0, 'certificates': ['provider-cert-id']}
        if mode == 34:
            return {
                'errorCode': 0,
                'certInfo': {
                    'RawData': base64.b64encode(self.raw_certificate).decode('ascii'),
                    'HasPrivateKey': True,
                },
            }
        if mode == 27:
            return {
                'errorCode': 0,
                'fileData': base64.b64encode(b'cms-signature').decode('ascii'),
            }
        if mode == 29:
            info = {'VerifyResultEx': {'SignatureVerifyResult': 0}}
            return {'errorCode': 0, 'signInfo': [info]}
        raise AssertionError('unexpected mode {}'.format(mode))


class SigningServiceTests(unittest.TestCase):
    def tearDown(self):
        signing_service._active_signer = None
        signing_service._active_mode = 'auto'
        signing_service._available_signers = {}

    def test_karma_probe_matches_certificate_by_der_sha1(self):
        raw = b'test DER certificate'
        thumbprint = __import__('hashlib').sha1(raw).hexdigest().upper()
        crypto = {'Test cert': {'SHA1 Hash': thumbprint}}
        signer = signing_service.KarmaSigner.probe(FakeKarmaClient(raw), crypto)
        self.assertEqual(['Test cert'], list(signer.certificates))
        self.assertEqual('provider-cert-id', signer.certificates['Test cert']['__karma_id'])

    def test_karma_sign_writes_detached_signature_after_verification(self):
        client = FakeKarmaClient(b'certificate')
        signer = signing_service.KarmaSigner(
            client, {'Test': {'__karma_id': 'provider-cert-id'}}
        )
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'document.txt')
            with open(source, 'wb') as stream:
                stream.write(b'document')
            target = signer.sign(source, {'__karma_id': 'provider-cert-id'})
            self.assertEqual(source + '.sig', target)
            with open(target, 'rb') as stream:
                self.assertEqual(b'cms-signature', stream.read())
        self.assertEqual([27, 29], [mode for mode, _ in client.calls])

    def test_karma_sign_accepts_user_approved_signature_without_timestamp(self):
        client = FakeKarmaClient(b'certificate')
        signer = signing_service.KarmaSigner(
            client, {'Test': {'__karma_id': 'provider-cert-id'}}
        )
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'document.txt')
            with open(source, 'wb') as stream:
                stream.write(b'document')
            target = signer.sign(source, {'__karma_id': 'provider-cert-id'})
            self.assertTrue(os.path.exists(target))

    def test_karma_cancellation_codes_and_messages_are_recognised(self):
        for code in (995, 1223, 0x800703E3, 0x800704C7, 0x80004004):
            self.assertTrue(signing_service._is_karma_cancellation(code, ''))
        self.assertTrue(signing_service._is_karma_cancellation(
            1, 'Операция отменена пользователем'
        ))
        self.assertFalse(signing_service._is_karma_cancellation(16118, 'Store not found'))

    def test_karma_cancel_result_becomes_separate_exception(self):
        with self.assertRaisesRegex(signing_service.SigningCancelled, 'отменено пользователем'):
            signing_service._raise_for_karma_result({
                'errorCode': 0x800704C7,
                'errorMessage': 'The operation was canceled by the user.',
            })

    @mock.patch('signing_service.KarmaSigner.probe')
    def test_startup_chooses_karma_without_tsa_probe(self, karma_probe):
        expected = mock.Mock(provider_name='КАРМА', certificates={'K': {}})
        karma_probe.return_value = expected
        with tempfile.TemporaryDirectory() as csp_path:
            csptest = os.path.join(csp_path, 'csptest.exe')
            with open(csptest, 'wb'):
                pass
            signer = signing_service.initialize_signing(
                {'csp_path': csp_path, 'karma_tsp_url': 'http://tsa/'},
                {'Crypto cert': {'SHA1 Hash': 'AA'}},
            )
        self.assertIs(signer, expected)

    @mock.patch('signing_service.KarmaSigner.probe')
    def test_manual_cryptopro_mode_uses_cryptopro_certificates(self, karma_probe):
        karma_probe.return_value = mock.Mock(
            provider_name='КАРМА', certificates={'Karma': {}}
        )
        with tempfile.TemporaryDirectory() as csp_path:
            with open(os.path.join(csp_path, 'csptest.exe'), 'wb'):
                pass
            signer = signing_service.initialize_signing(
                {'csp_path': csp_path, 'signing_mode': 'cryptopro'},
                {'Crypto': {'SHA1 Hash': 'AA'}},
            )
        self.assertEqual('КриптоПро', signer.provider_name)
        self.assertEqual('cryptopro', signing_service.get_signing_mode())
        self.assertEqual('cryptopro', signer.certificates['Crypto']['__provider__'])

    @mock.patch('signing_service.KarmaSigner.probe')
    def test_switching_mode_keeps_both_startup_providers(self, karma_probe):
        karma_signer = mock.Mock(provider_name='КАРМА', certificates={'Karma': {}})
        karma_probe.return_value = karma_signer
        with tempfile.TemporaryDirectory() as csp_path:
            with open(os.path.join(csp_path, 'csptest.exe'), 'wb'):
                pass
            signing_service.initialize_signing(
                {'csp_path': csp_path}, {'Crypto': {'SHA1 Hash': 'AA'}}
            )
            crypto_signer = signing_service.set_signing_mode('cryptopro')
            auto_signer = signing_service.set_signing_mode('auto')
        self.assertEqual('КриптоПро', crypto_signer.provider_name)
        self.assertIs(karma_signer, auto_signer)
        self.assertEqual(
            {'auto': True, 'karma': True, 'cryptopro': True},
            signing_service.get_signing_mode_availability(),
        )

    @mock.patch('signing_service.KarmaSigner.probe')
    def test_unavailable_saved_manual_mode_falls_back_to_auto(self, karma_probe):
        karma_probe.side_effect = signing_service.SigningError('offline')
        signer = signing_service.initialize_signing(
            {'csp_path': 'missing', 'signing_mode': 'karma'}, {}
        )
        self.assertEqual('auto', signing_service.get_signing_mode())
        self.assertEqual('Подписание недоступно', signer.provider_name)

    def test_queued_certificate_keeps_its_original_provider(self):
        karma = mock.Mock()
        crypto = mock.Mock()
        signing_service._available_signers = {'karma': karma, 'cryptopro': crypto}
        signing_service._active_signer = crypto
        signing_service.sign_with_active_provider(
            'document.pdf', {'__provider__': 'karma'}, {}, {}
        )
        karma.sign.assert_called_once_with('document.pdf', {'__provider__': 'karma'})
        crypto.sign.assert_not_called()


if __name__ == '__main__':
    unittest.main()
