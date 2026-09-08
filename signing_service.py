import base64
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid


CURRENT_USER_MY_STORE = {
    'location': 'sscu',
    'address': '',
    'name': 'MY',
}


class SigningError(RuntimeError):
    pass


class SigningCancelled(SigningError):
    """Пользователь явно отменил операцию в интерфейсе КАРМЫ."""


class KarmaOperationError(SigningError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__('КАРМА errorCode={}: {}'.format(code, message))


def _normalise_thumbprint(value):
    return ''.join(ch for ch in str(value or '') if ch.isalnum()).upper()


def _certificate_thumbprint(certificate_data):
    return _normalise_thumbprint(
        certificate_data.get('SHA1 отпечаток', certificate_data.get('SHA1 Hash', ''))
    )


def _is_karma_cancellation(code, message):
    try:
        unsigned_code = int(code) & 0xffffffff
    except (TypeError, ValueError):
        unsigned_code = None
    # ERROR_CANCELLED, ERROR_OPERATION_ABORTED и соответствующие HRESULT,
    # а также E_ABORT. Разные модули КАРМЫ возвращают разные формы кода.
    cancellation_codes = {
        995,
        1223,
        0x800703E3,
        0x800704C7,
        0x80004004,
    }
    if unsigned_code in cancellation_codes:
        return True
    text = str(message or '').casefold()
    cancellation_markers = (
        'отмен',
        'cancel',
        'operation was cancelled',
        'operation was canceled',
        'rejected by the user',
        'отклонена пользователем',
    )
    return any(marker in text for marker in cancellation_markers)


def _raise_for_karma_result(result):
    code = result.get('errorCode')
    if code == 0:
        return
    message = result.get('errorMessage', 'без описания')
    if _is_karma_cancellation(code, message):
        raise SigningCancelled('Подписание отменено пользователем в КАРМЕ')
    raise KarmaOperationError(code, message)


class KarmaHttpClient:
    def __init__(self, base_url, module, timeout, init_params):
        self.base_url = base_url.rstrip('/') + '/'
        self.module = module.strip('/') or 'capi'
        self.timeout = timeout
        self.init_params = init_params
        self.client_id = 'DocumentSIGner-{}-{}'.format(os.getpid(), uuid.uuid4().hex)

    @property
    def operation_url(self):
        return urllib.parse.urljoin(self.base_url, self.module)

    def _open(self, request):
        parsed = urllib.parse.urlsplit(request.full_url)
        if parsed.hostname in ('127.0.0.1', 'localhost', '::1'):
            return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                request, timeout=self.timeout
            )
        return urllib.request.urlopen(request, timeout=self.timeout)

    def service_info(self):
        request = urllib.request.Request(
            self.base_url,
            headers={'Accept': 'application/json', 'Cache-Control': 'no-cache'},
            method='GET',
        )
        with self._open(request) as response:
            body = response.read(256 * 1024 + 1)
        if len(body) > 256 * 1024:
            raise SigningError('слишком большой ответ GetServiceInfo')
        return json.loads(body.decode('utf-8-sig'))

    def request(self, mode, **fields):
        payload = {
            'mode': mode,
            'currentStores': [CURRENT_USER_MY_STORE.copy()],
            'extInitParams': self.init_params,
            'clientId': self.client_id,
        }
        payload.update(fields)
        request = urllib.request.Request(
            self.operation_url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={
                'Content-Type': 'application/json; charset=UTF-8',
                'Accept': 'application/json',
                'Cache-Control': 'no-cache',
            },
            method='POST',
        )
        try:
            with self._open(request) as response:
                body = response.read(128 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as error:
            raise SigningError('HTTP {} от КАРМЫ'.format(error.code))
        if len(body) > 128 * 1024 * 1024:
            raise SigningError('ответ КАРМЫ превышает 128 МБ')
        try:
            result = json.loads(body.decode('utf-8-sig'))
        except Exception as error:
            raise SigningError('некорректный JSON КАРМЫ: {}'.format(error))
        _raise_for_karma_result(result)
        return result


class CryptoProSigner:
    provider_name = 'КриптоПро'

    def __init__(self, csp_path, certificates):
        self.csp_path = csp_path
        self.certificates = {}
        for name, certificate_data in certificates.items():
            provider_data = certificate_data.copy()
            provider_data['__provider__'] = 'cryptopro'
            self.certificates[name] = provider_data

    def sign(self, source_file, certificate_data):
        thumbprint = _certificate_thumbprint(certificate_data)
        if not thumbprint:
            raise SigningError('у сертификата отсутствует SHA-1 отпечаток')
        target = source_file + '.sig'
        command = [
            os.path.join(self.csp_path, 'csptest.exe'),
            '-sfsign', '-sign', '-in', source_file, '-out', target,
            '-my', thumbprint, '-add', '-detached',
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='cp866',
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 2148081675:
            raise SigningError('КриптоПро не удалось найти закрытый ключ')
        if not os.path.isfile(target):
            stderr = (result.stderr or result.stdout or '').strip()
            raise SigningError('КриптоПро не создал подпись: {}'.format(stderr[-1000:]))
        return target


def _signature_error(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() == 'signatureverifyresult':
                try:
                    if int(child) != 0:
                        return 'SignatureVerifyResult={}'.format(child)
                except (TypeError, ValueError):
                    return 'некорректный SignatureVerifyResult={!r}'.format(child)
            nested = _signature_error(child)
            if nested:
                return nested
    elif isinstance(value, (list, tuple)):
        for child in value:
            nested = _signature_error(child)
            if nested:
                return nested
    return ''


class KarmaSigner:
    provider_name = 'КАРМА'

    def __init__(self, client, certificates):
        self.client = client
        self.certificates = certificates

    @classmethod
    def probe(cls, client, crypto_certificates):
        service_info = client.service_info()
        if service_info.get('appName') != 'eoscryptosvc':
            raise SigningError('неожиданный appName={!r}'.format(service_info.get('appName')))
        result = client.request(38, storeAddress=CURRENT_USER_MY_STORE.copy())
        certificate_ids = result.get('certificates') or []
        by_thumbprint = {
            _certificate_thumbprint(data): (name, data)
            for name, data in crypto_certificates.items()
            if _certificate_thumbprint(data)
        }
        matched = {}
        for certificate_id in certificate_ids:
            try:
                info_result = client.request(
                    34, senderCertId=certificate_id, needExtraction=True
                )
                info = info_result.get('certInfo') or {}
                raw_data = base64.b64decode(info.get('RawData', ''), validate=True)
                thumbprint = hashlib.sha1(raw_data).hexdigest().upper()
                crypto_entry = by_thumbprint.get(thumbprint)
                if not crypto_entry or not info.get('HasPrivateKey'):
                    continue
                display_name, certificate_data = crypto_entry
                provider_data = certificate_data.copy()
                provider_data['__provider__'] = 'karma'
                provider_data['__karma_id'] = certificate_id
                provider_data['__karma_cert_info'] = info
                matched[display_name] = provider_data
            except Exception:
                continue
        if not matched:
            raise SigningError('нет пригодных сертификатов КАРМЫ с закрытым ключом')
        return cls(client, matched)

    def sign(self, source_file, certificate_data):
        certificate_id = certificate_data.get('__karma_id')
        if not certificate_id:
            raise SigningError('отсутствует внутренний идентификатор сертификата КАРМЫ')
        with open(source_file, 'rb') as source:
            content = base64.b64encode(source.read()).decode('ascii')
        signed = self.client.request(
            27,
            certInclude=2,
            isAttached=False,
            senderCertId=certificate_id,
            fileData=content,
            comment='',
            uri=os.path.basename(source_file),
        )
        encoded_signature = signed.get('fileData')
        if not encoded_signature:
            raise SigningError('КАРМА вернула пустую подпись')
        try:
            signature = base64.b64decode(encoded_signature, validate=True)
        except Exception as error:
            raise SigningError('КАРМА вернула некорректную Base64-подпись: {}'.format(error))
        verified = self.client.request(
            29,
            isAttached=False,
            sendSignData=encoded_signature,
            fileData=content,
        )
        verify_error = _signature_error(verified)
        if verify_error:
            raise SigningError('проверка подписи КАРМЫ не пройдена: {}'.format(verify_error))

        target = source_file + '.sig'
        fd, temp_path = tempfile.mkstemp(
            prefix='.' + os.path.basename(source_file) + '-',
            suffix='.karma.sig.tmp',
            dir=os.path.dirname(source_file) or '.',
        )
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(signature)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_path, target)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
        return target


class UnavailableSigner:
    provider_name = 'Подписание недоступно'
    certificates = {}

    def __init__(self, reason):
        self.reason = reason

    def sign(self, source_file, certificate_data):
        raise SigningError(self.reason)


_active_signer = None
_active_mode = 'auto'
_available_signers = {}


def _normalise_signing_mode(mode):
    value = str(mode or 'auto').strip().casefold()
    if value not in ('auto', 'karma', 'cryptopro'):
        return 'auto'
    return value


def set_signing_mode(mode):
    global _active_signer, _active_mode
    selected_mode = _normalise_signing_mode(mode)
    if selected_mode == 'auto':
        _active_signer = (
            _available_signers.get('karma')
            or _available_signers.get('cryptopro')
            or UnavailableSigner('нет доступного провайдера подписи')
        )
    else:
        signer = _available_signers.get(selected_mode)
        if signer is None:
            raise SigningError('выбранное средство подписи сейчас недоступно')
        _active_signer = signer
    _active_mode = selected_mode
    return _active_signer


def initialize_signing(config, crypto_certificates):
    global _available_signers
    csp_path = config.get('csp_path', '')
    csptest_path = os.path.join(csp_path, 'csptest.exe')
    crypto_ready = bool(crypto_certificates) and os.path.isfile(csptest_path)

    karma_url = config.get('karma_url', 'http://127.0.0.1:8080/')
    karma_module = config.get('karma_module', 'capi')
    karma_timeout = float(config.get('karma_timeout', 15.0))
    # Адрес TSA и параметры расширения настраиваются в самой КАРМЕ.
    # Приложению достаточно выбрать криптографический модуль.
    init_params = 'MODULE="{}";'.format(karma_module)
    client = KarmaHttpClient(karma_url, karma_module, karma_timeout, init_params)

    karma_signer = None
    karma_error = ''
    if config.get('karma_enabled', True):
        try:
            karma_signer = KarmaSigner.probe(client, crypto_certificates)
        except Exception as error:
            karma_error = '{}: {}'.format(type(error).__name__, error)
    else:
        karma_error = 'КАРМА отключена в настройках'
    _available_signers = {}
    if karma_signer is not None:
        _available_signers['karma'] = karma_signer
    if crypto_ready:
        _available_signers['cryptopro'] = CryptoProSigner(csp_path, crypto_certificates)

    requested_mode = _normalise_signing_mode(config.get('signing_mode', 'auto'))
    if requested_mode != 'auto' and requested_mode not in _available_signers:
        requested_mode = 'auto'
    return set_signing_mode(requested_mode)


def get_active_signer():
    return _active_signer


def get_active_certificates(default_certificates=None):
    if _active_signer is None:
        return default_certificates or {}
    return _active_signer.certificates


def get_active_provider_name():
    if _active_signer is None:
        return 'КриптоПро (инициализация не выполнена)'
    return _active_signer.provider_name


def get_signing_mode():
    return _active_mode


def get_signing_mode_availability():
    return {
        'auto': True,
        'karma': 'karma' in _available_signers,
        'cryptopro': 'cryptopro' in _available_signers,
    }


def sign_with_active_provider(source_file, certificate_data, config, default_certificates):
    global _active_signer
    if _active_signer is None:
        initialize_signing(config, default_certificates)
    certificate_provider = certificate_data.get('__provider__')
    signer = _available_signers.get(certificate_provider, _active_signer)
    return signer.sign(source_file, certificate_data)
