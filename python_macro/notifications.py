"""Discord result notifications with reward text and Roblox client captures."""
import json
import re
import uuid
from threading import Lock
from python_macro.session_stats import WaveTotals
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
        self.results = {'victory':0, 'defeat':0}
        self.total_duration = 0
        self.reward_totals = {}
        self.stat_totals = {}
        self.wave_totals = WaveTotals()
        self.wave_lock = Lock()
        self.run_finished = False

    def observe(self, value):
        with self.wave_lock:
            if value.get('new_run'):
                self.wave_totals.start_run()
                self.run_finished = False
            if not self.run_finished:
                self.wave_totals.observe(value.get('wave'))
                if value.get('result') in ('victory','defeat'):
                    if value['result'] == 'victory':
                        self.wave_totals.finish_run()
                    self.run_finished = True

    def send(self, outcome, duration=0, reward_dir=None, error=None):
        metadata = {}
        if reward_dir is not None:
            try:
                metadata = json.loads((Path(reward_dir)/'rewards.json').read_text(encoding='utf-8'))
                if not isinstance(metadata,dict):
                    metadata = {}
            except (OSError, ValueError):
                pass
        if outcome in self.results:
            self.results[outcome] += 1
            self.total_duration += max(0, duration)
            for item in metadata.get('rewards',[]):
                match = re.fullmatch(r'(\d[\d,]*)\s*[xX]\s+(.+)', str(item).strip())
                if match and 'unread reward' not in match[2].casefold():
                    name = ' '.join(match[2].split())
                    key = name.casefold()
                    old = self.reward_totals.get(key, (name,0))
                    self.reward_totals[key] = (old[0],old[1]+int(match[1].replace(',','')))
            for name in ('Total Kills','Total Damage'):
                value = str(metadata.get('stats',{}).get(name,''))
                if re.fullmatch(r'\d[\d,]*',value):
                    self.stat_totals[name] = self.stat_totals.get(name,0)+int(value.replace(',',''))
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
        if self.settings.get('mode') == 'Raid':
            description = (f"Raid | {self.settings.get('map','')} | {self.settings.get('act','')}"
                           f"\nRun time: {seconds//60}m {seconds%60}s")
        if outcome == 'error':
            # Never include exception text that might expose URLs or tokens.
            description = 'The macro needs attention. Check Action Output.'
        embed = {'title': 'Anime Expeditions - ' + outcome.title(),
                 'description':description[:4000], 'color':0x7E1726}
        fields = []
        if outcome != 'error':
            runs = sum(self.results.values())
            fields = [{'name':name, 'value':str(value), 'inline':True} for name,value in (
                ('Runs',runs), ('Victories',self.results['victory']),
                ('Defeats',self.results['defeat']),
                ('Average Run',f'{int(self.total_duration/max(1,runs))}s'),
                ('Total Run Time',f'{int(self.total_duration)}s'))]
            with self.wave_lock:
                fields.append({'name':'Total Waves Completed','value':str(self.wave_totals.total),'inline':True})
            for name,value in self.stat_totals.items():
                fields.append({'name':name,'value':f'{value:,}','inline':True})
        if self.settings.get('show_rewards','0') == '1' and reward_dir is not None:
            rewards = '\n'.join(str(item) for item in metadata.get('rewards',[]))
            fields.append({'name':'Rewards Earned', 'value':rewards[:1024] or 'Could not read rewards.', 'inline':False})
            totals = '\n'.join(f'{count:,}x {name}' for name,count in self.reward_totals.values())
            fields.append({'name':'Total Rewards (Session)', 'value':totals[:1024] or 'No readable rewards yet.', 'inline':False})
        if fields:
            embed['fields'] = fields[:25]
        payload = {'embeds':[embed], 'allowed_mentions':{'parse':[], 'users':[mention] if mention else []}}
        if mention:
            payload['content'] = f'<@{mention}>'
        image = None
        if self.settings.get('show_rewards','0') == '1' and reward_dir is not None:
            path = Path(reward_dir) / 'roblox.png'
            try:
                if path.is_file() and path.stat().st_size <= 8*1024*1024:
                    image = path.read_bytes()
            except OSError:
                self.log('Reward image unavailable. Sending the result summary.')
            if image is not None:
                embed['image'] = {'url':'attachment://roblox.png'}
                payload['attachments'] = [{'id':0,'filename':'roblox.png'}]
        boundary = 'ScatterMacro' + uuid.uuid4().hex
        if image is not None:
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
                    'Content-Type: application/json\r\n\r\n').encode() + json.dumps(payload).encode()
            body += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; '
                     'filename="roblox.png"\r\nContent-Type: image/png\r\n\r\n').encode() + image
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
