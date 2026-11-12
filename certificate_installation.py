"""Install bundled CA certificates into the current user's Windows stores."""

import os
import subprocess


# X509Certificate2 uses Windows' certificate parser, including GOST certificates.
# Pass the path through the environment so quotes in paths cannot become code.
_INSPECT_CERTIFICATE = r"""
$ErrorActionPreference = 'Stop'
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2
try {
    $cert.Import($env:DOCUMENTSIGNER_CERTIFICATE_PATH)
    $storeName = 'CA'
    if ([Convert]::ToBase64String($cert.SubjectName.RawData) -eq
        [Convert]::ToBase64String($cert.IssuerName.RawData)) {
        $storeName = 'Root'
    }
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, 'CurrentUser')
    try {
        $store.Open('ReadOnly')
        $installed = $store.Certificates.Find('FindByThumbprint', $cert.Thumbprint, $false)
        if ($installed.Count -eq 0) { Write-Output $storeName }
    } finally { $store.Close() }
} finally { $cert.Reset() }
"""


def install_certificates_from_directory(cert_dir):
    """Keep self-issued roots in Root and intermediate certificates in CA.

    certutil runs without -silent/-f so Windows can request trust confirmation.
    Already installed certificates are skipped, including on subsequent starts.
    """
    if not os.path.isdir(cert_dir):
        return
    for filename in sorted(os.listdir(cert_dir)):
        cert_path = os.path.abspath(os.path.join(cert_dir, filename))
        if not filename.lower().endswith(('.cer', '.crt', '.pem')) or not os.path.isfile(cert_path):
            continue
        try:
            env = os.environ.copy()
            env['DOCUMENTSIGNER_CERTIFICATE_PATH'] = cert_path
            result = subprocess.run(
                ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                 '-Command', _INSPECT_CERTIFICATE],
                env=env, check=True, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            store = result.stdout.strip()
            if not store:
                continue
            if store not in ('Root', 'CA'):
                raise ValueError('Unexpected certificate store: {!r}'.format(store))
            subprocess.run(
                ['certutil', '-user', '-addstore', store, cert_path],
                check=True, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            print('Сертификат установлен в {}: {}'.format(store, cert_path))
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            print('Не удалось установить сертификат {}: {}'.format(cert_path, error))
