"""Online, device-bound licensing. Credentials are protected with Windows DPAPI."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import functools
import urllib.error
import urllib.request

ORIGIN = 'https://scatter-macro.shopscatter.workers.dev'
KEY_WEBSITE = ORIGIN + '/dashboard'
DISCORD_URL = 'https://discord.gg/VXAqRXvkKa'


class LicenseError(Exception):
    pass


@dataclass(frozen=True)
class VerifiedLicense:
    session: str
    expires_at: int = 0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LicenseError('Unexpected licensing redirect. Please try again later.')


def _path():
    return Path(os.environ['LOCALAPPDATA']) / 'ScatterMacro' / 'access.dat'


def _serialized(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        import msvcrt
        path = _path().with_suffix('.lock')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a+b') as lock:
            if lock.tell() == 0:
                lock.write(b'0')
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            except OSError:
                raise LicenseError('Another activation is in progress. Please try again shortly.') from None
            try:
                return function(*args, **kwargs)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    return wrapped


def _protect(data, decrypt=False):
    if os.name != 'nt':
        raise LicenseError('Device activation requires Windows.')
    class Blob(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, output = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise LicenseError('Windows could not access this device activation. Contact support before resetting it.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(output.data, output.length)
    finally:
        kernel.LocalFree(output.data)


def _load():
    try:
        path = _path()
        if not path.exists():
            return None
        if path.stat().st_size > 32768:
            raise ValueError()
        data = json.loads(_protect(path.read_bytes(), decrypt=True))
        if not isinstance(data, dict) or not re.fullmatch('[a-f0-9]{64}', data.get('device', '')):
            raise ValueError()
        return data
    except LicenseError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise LicenseError('Saved activation cannot be read. Contact support before resetting it.') from None


def _save(data):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = _protect(json.dumps(data).encode())
    fd, name = tempfile.mkstemp(prefix='access-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(encrypted)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _request(route, payload, credentials=None):
    headers = {'Content-Type': 'application/json', 'User-Agent': 'ScatterMacro-License/1'}
    if credentials:
        headers.update({'Authorization': 'Bearer ' + credentials['session'], 'X-Scatter-Device': credentials['device']})
    request = urllib.request.Request(ORIGIN + route, data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(16385)
        if len(raw) > 16384:
            raise ValueError()
        data = json.loads(raw)
        if data.get('ok') is not True or not isinstance(data.get('session'), str) or not data['session'] or not isinstance(data.get('expiresAt'), int):
            raise ValueError()
        return data
    except urllib.error.HTTPError as error:
        messages = {401: 'Activation expired. Please activate your key again.',
                    403: 'Your key is invalid, expired, revoked, or assigned to another device.',
                    409: 'This key is linked to another device. Use Discord support to request a reset.',
                    429: 'Too many attempts. Please wait a minute and try again.'}
        raise LicenseError(messages.get(error.code, 'Licensing is temporarily unavailable. Please try again.')) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise LicenseError('Unable to verify access. Check your internet connection and try again.') from None


@_serialized
def verify_key(key):
    if not isinstance(key, str) or not re.fullmatch('[A-Z0-9]{12}', re.sub('[^A-Z0-9]', '', key.upper())):
        raise LicenseError('Please enter the complete key from your dashboard.')
    credentials = _load() or {'device': secrets.token_hex(32)}
    # Persist the device before activating so an interrupted request cannot lose its binding.
    _save(credentials)
    result = _request('/v2/activate', {'key': key, 'deviceId': credentials['device']})
    credentials.update(key=key, session=result['session'], expiresAt=result['expiresAt'])
    _save(credentials)
    return VerifiedLicense(result['session'], result['expiresAt'])


def restore_access():
    credentials = _load()
    if not credentials or not credentials.get('key'):
        raise LicenseError('Activate your key in the launcher first.')
    # Revalidate the saved key against current server state, including expiry and revocation.
    return verify_key(credentials['key'])


@_serialized
def check_session():
    credentials = _load()
    if not credentials or not credentials.get('session'):
        raise LicenseError('Activate your key in the launcher first.')
    result = _request('/v2/session', {}, credentials)
    credentials.update(session=result['session'], expiresAt=result['expiresAt'])
    _save(credentials)
    return VerifiedLicense(result['session'], result['expiresAt'])


def package_request(url):
    if not url.startswith(ORIGIN + '/download/packages/anime-expeditions/'):
        raise LicenseError('Invalid protected package address.')
    check_session()
    credentials = _load()
    return urllib.request.Request(url, headers={'Authorization': 'Bearer ' + credentials['session'],
        'X-Scatter-Device': credentials['device'], 'User-Agent': 'ScatterMacro-License/1'})
