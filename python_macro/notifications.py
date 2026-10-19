"""Discord result notifications with optional reward-area attachments."""
import json
import re
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler


def webhook_url(value):
    url = urlsplit(value.strip())
    if (url.scheme != 'https' or url.hostname not in {'discord.com','discordapp.com',
            'ptb.discord.com','canary.discord.com'} or url.username or url.password
            or url.port not in (None,443)
            or not re.fullmatch(r'/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9_-]+',url.path)):
        raise ValueError('Enter a valid Discord webhook URL.')
    query = dict(parse_qsl(url.query))
    query['wait'] = 'true'
    return urlunsplit(('https',url.netloc,url.path,urlencode(query),''))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Notifier:
    def __init__(self, settings, stop, log, opener=None):
        self.settings, self.stop, self.log = dict(settings), stop, log
        self.opener = opener or build_opener(NoRedirect())

    def send(self, outcome, duration=0, reward_dir=None, error=None):
        key = 'ping_error' if outcome == 'error' else 'ping_' + outcome
        if not self.settings.get('webhook','').strip() or self.settings.get(key,'0') != '1':
            return False
        if self.stop.is_set():
            return False
        try:
            url = webhook_url(self.settings['webhook'])
        except ValueError:
            self.log('Discord notification not sent: check the webhook URL.')
            return False
        user = self.settings.get('discord_id','').strip()
        mention = user if re.fullmatch(r'\d{15,22}',user) else None
        seconds = max(0,int(duration))
        description = (f"{self.settings.get('map','Story')} | {self.settings.get('act','')} | "
                       f"{self.settings.get('difficulty','')}\nRun time: {seconds//60}m {seconds%60}s")
        if outcome == 'error':
            # Never include exception text that might expose URLs or tokens.
            description = 'The macro needs attention. Check Action Output.'
        embed = {'title': 'Anime Expeditions - ' + outcome.title(),
                 'description':description[:4000], 'color':0x7E1726}
        payload = {'embeds':[embed], 'allowed_mentions':{'parse':[], 'users':[mention] if mention else []}}
        if mention:
            payload['content'] = f'<@{mention}>'
        image = None
        if self.settings.get('show_rewards','0') == '1' and reward_dir is not None:
            path = Path(reward_dir) / 'reward-strip.png'
            try:
                if path.is_file() and path.stat().st_size <= 8*1024*1024:
                    image = path.read_bytes()
            except OSError:
                self.log('Reward image unavailable. Sending the result summary.')
            if image is not None:
                embed['image'] = {'url':'attachment://rewards.png'}
                payload['attachments'] = [{'id':0,'filename':'rewards.png'}]
        boundary = 'ScatterMacro' + uuid.uuid4().hex
        if image is not None:
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
                    'Content-Type: application/json\r\n\r\n').encode() + json.dumps(payload).encode()
            body += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; '
                     'filename="rewards.png"\r\nContent-Type: image/png\r\n\r\n').encode() + image
            body += f'\r\n--{boundary}--\r\n'.encode()
            content_type = 'multipart/form-data; boundary=' + boundary
        else:
            body, content_type = json.dumps(payload).encode(), 'application/json'
        request = Request(url, data=body, headers={'Content-Type':content_type,
                          'User-Agent':'ScatterMacro/1.0'}, method='POST')
        for attempt in range(2):
            if self.stop.is_set():
                return False
            try:
                with self.opener.open(request, timeout=8) as response:
                    if response.status not in (200,204):
                        raise OSError('Discord did not confirm delivery')
                self.log('Discord notification sent.')
                return True
            except HTTPError as exc:
                if exc.code == 429 and attempt == 0:
                    try:
                        delay = min(10,max(.5,float(json.loads(exc.read()).get('retry_after',1))))
                    except (ValueError,TypeError):
                        delay = 1
                    if not self.stop.wait(delay):
                        continue
                break
            except (OSError, URLError):
                # Don't retry ambiguous transport failures and duplicate messages.
                break
        self.log('Discord notification failed. Continuing the macro.')
        return False
