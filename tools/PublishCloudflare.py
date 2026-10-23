"""Publish immutable artifacts from GitHub Actions using short-lived OIDC."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

ORIGIN = 'https://scatter-macro.shopscatter.workers.dev'


def identity():
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    url += ('&' if '?' in url else '?') + 'audience=scatter-macro-publish'
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)['value']


def api(route, data):
    request = urllib.request.Request(ORIGIN + route, data=json.dumps(data).encode(),
        headers={'Authorization': 'Bearer ' + identity(), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def verify_upload(route, checksum):
    request = urllib.request.Request(ORIGIN + route, headers={'Authorization': 'Bearer ' + identity()})
    with urllib.request.urlopen(request, timeout=180) as response:
        actual = hashlib.file_digest(response, 'sha256').hexdigest()
    if actual != checksum:
        raise RuntimeError('Downloaded Cloudflare artifact checksum mismatch')


def upload(channel, version, path):
    path = Path(path)
    with path.open('rb') as source:
        checksum = hashlib.file_digest(source, 'sha256').hexdigest()
    route = f'/v2/publish/artifact/{channel}/{version}/{path.name}'
    if path.stat().st_size > 64 * 1024 * 1024:
        started = api(route + '?action=start', {'sha256': checksum, 'size': path.stat().st_size})
        if not started.get('existing'):
            upload_id = urllib.parse.quote(started['uploadId'], safe='')
            parts = []
            with path.open('rb') as source:
                while block := source.read(64 * 1024 * 1024):
                    request = urllib.request.Request(ORIGIN + route + f'?uploadId={upload_id}&partNumber={len(parts) + 1}',
                        data=block, method='PUT', headers={'Authorization': 'Bearer ' + identity(), 'Content-Type': 'application/octet-stream'})
                    with urllib.request.urlopen(request, timeout=180) as response:
                        parts.append(json.load(response))
            api(route + f'?action=complete&uploadId={upload_id}', {'parts': parts})
        verify_upload(route, checksum)
        return checksum
    connection = http.client.HTTPSConnection(urllib.parse.urlsplit(ORIGIN).hostname, timeout=180)
    try:
        connection.putrequest('PUT', route)
        connection.putheader('Authorization', 'Bearer ' + identity())
        connection.putheader('Content-Type', 'application/octet-stream')
        connection.putheader('Content-Length', str(path.stat().st_size))
        connection.putheader('X-Content-Sha256', checksum)
        connection.endheaders()
        with path.open('rb') as source:
            while block := source.read(1024 * 1024):
                connection.send(block)
        response = connection.getresponse()
        data = json.loads(response.read(65536))
        if response.status != 200 or data.get('sha256') != checksum or data.get('size') != path.stat().st_size:
            raise RuntimeError(f'Cloudflare artifact verification failed: HTTP {response.status}')
    finally:
        connection.close()
    verify_upload(route, checksum)
    return checksum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('channel', choices=['launcher', 'anime-expeditions'])
    parser.add_argument('version')
    args = parser.parse_args()
    prefix = 'ScatterLauncher' if args.channel == 'launcher' else 'AnimeExpeditions'
    package = Path('dist') / f'{prefix}-{args.version}-windows.zip'
    data = {'version': args.version, 'sha256': upload(args.channel, args.version, package)}
    if args.channel == 'launcher':
        data['installer_sha256'] = upload(args.channel, args.version, Path('dist/ScatterMacro.exe'))
    request = urllib.request.Request(ORIGIN + '/v2/publish/manifest/' + args.channel,
        data=json.dumps(data).encode(), headers={'Authorization': 'Bearer ' + identity(), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get('ok') is not True or result.get('version') != args.version:
        raise RuntimeError('Release manifest was not published')
    print(f'Cloudflare verified and published {args.channel} {args.version}')


if __name__ == '__main__':
    main()
