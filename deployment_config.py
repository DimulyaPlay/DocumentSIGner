"""Typed deployment defaults, independent of Qt and the interactive user profile."""
import configparser
import math
import os
import sys
from pathlib import Path


DEFAULTS = {
    'stamp_on_original': True,
    'csp_path': r'C:\Program Files\Crypto Pro\CSP',
    'last_cert': '',
    'widget_visible': False,
    'context_menu': False,
    'autorun': False,
    'default_page': 2,
    'stamp_place': 1,
    'default_stamp_type': 0,
    'stamp_scale_percent': 25,
    'notify': False,
    'normalize_to_a4': False,
    'karma_enabled': True,
    'karma_url': 'http://127.0.0.1:8080/',
    'karma_module': 'capi',
    'karma_timeout': 15.0,
    'karma_operation_timeout': 300.0,
    'signing_mode': 'auto',
    'install_certificates': True,
}
ENUMS = {'default_page': (0, 1, 2, 3), 'stamp_place': (0, 1),
         'default_stamp_type': (0, 1, 2), 'signing_mode': ('auto', 'karma', 'cryptopro')}
INSTALLER_TASK_SETTINGS = {'autorun', 'context_menu'}


def installation_directory():
    directory = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    # Installed binaries are isolated from installer-owned deployment files.
    if directory.name.lower() == 'bin' and (directory.parent / '.documentsigner-install').is_file():
        return directory.parent
    return directory


def read_settings(path=None):
    path = Path(path) if path is not None else installation_directory() / 'deployment.ini'
    if not path.exists():
        return {}, {}
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(path.read_text(encoding='utf-8-sig'))
    if parser.defaults() or not parser.sections() or set(parser.sections()) - {'Defaults', 'Policy'}:
        raise ValueError('deployment.ini supports only [Defaults] and [Policy]')
    return tuple(_read_section(parser, section) for section in ('Defaults', 'Policy'))


def _read_section(parser, section):
    result = {}
    for key, raw in parser.items(section) if parser.has_section(section) else []:
        if key in INSTALLER_TASK_SETTINGS:
            raise ValueError(key + ' must be configured with installer /TASKS')
        if key not in DEFAULTS:
            raise ValueError('Unknown deployment setting: ' + key)
        expected = type(DEFAULTS[key])
        if expected is bool:
            if raw.lower() not in ('true', 'false'):
                raise ValueError(key + ' must be true or false')
            value = raw.lower() == 'true'
        elif expected is int:
            value = int(raw)
        elif expected is float:
            value = float(raw)
            if not math.isfinite(value) or not 0 < value <= 86400:
                raise ValueError(key + ' must be in (0, 86400]')
        else:
            value = os.path.expandvars(raw)
        if key in ENUMS and value not in ENUMS[key]:
            raise ValueError('Invalid value for ' + key)
        if key == 'stamp_scale_percent' and not 10 <= value <= 100:
            raise ValueError('stamp_scale_percent must be in [10, 100]')
        result[key] = value
    return result


def read_defaults(path=None):
    return read_settings(path)[0]


def read_policy(path=None):
    return read_settings(path)[1]


def stamp_scale_percent(value):
    """Reject malformed personal settings, keeping the historical editor scale."""
    if isinstance(value, bool):
        return 25
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number.is_integer() and 10 <= number <= 100 else 25
    except (TypeError, ValueError, OverflowError):
        return 25


def seed_rules(user_directory):
    """Seed each user's rules once; never overwrite personal rules on upgrade."""
    source = installation_directory() / 'default-rules.txt'
    target = Path(user_directory) / 'rules.txt'
    if source.is_file() and not target.exists():
        try:
            with target.open('xb') as output:
                output.write(source.read_bytes())
        except FileExistsError:
            pass


def read_rules_lines(path):
    """Accept new UTF-8 rules and existing Russian Windows (CP1251) exports."""
    data = Path(path).read_bytes()
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('cp1251')
    return text.splitlines(keepends=True)


if __name__ == '__main__':
    read_defaults(sys.argv[1])
    print('Deployment configuration is valid.')
