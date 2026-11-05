"""Metagame shift reconciliation. Python stdlib; boto3 only on AWS."""
import argparse
import csv
import difflib
import io
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent


def normalize(value):
    value = re.sub(r'\([^)]*\)', '', value)
    return ''.join(c for c in unicodedata.normalize('NFKD', value).casefold() if c.isalnum())


def parse_schedule(text, config):
    rows = list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
    if len(rows) < 3:
        raise ValueError('Schedule needs headers and volunteers')
    slots = {}
    day = None
    tz = ZoneInfo(config['timezone'])
    for col, header in enumerate(rows[0]):
        match = re.search(r'\((\d+)/(\d+)\)', header)
        if match:
            day = (int(match[1]), int(match[2]))
        label = rows[1][col] if col < len(rows[1]) else ''
        slot = re.fullmatch(r'\s*(\d{1,2})(?::(\d{2}))?(am|pm)\s*-\s*(\d{1,2})(?::(\d{2}))?(am|pm)\s*(?:\(\d+\))?\s*', label, re.I)
        if not slot:
            continue
        if day is None:
            raise ValueError('Slot without day')
        a, am, ap, b, bm, bp = slot.groups()
        def hour(h, p):
            h = int(h)
            if not 1 <= h <= 12:
                raise ValueError('Invalid slot hour')
            return h % 12 + (12 if p.lower() == 'pm' else 0)
        start = datetime(config['year'], *day, hour(a, ap), int(am or 0), tzinfo=tz)
        end = datetime(config['year'], *day, hour(b, bp), int(bm or 0), tzinfo=tz)
        if end <= start:
            end += timedelta(days=1)
        slots[col] = (start, end)
    if not slots:
        raise ValueError('No schedule slots found; refusing to change roles')
    volunteers = {}
    for row in rows[2:]:
        if not row or not row[0].strip() or normalize(row[0]) == 'shiftsfilled':
            continue
        name = row[0].strip()
        if name in volunteers:
            raise ValueError('Duplicate volunteer: ' + name)
        volunteers[name] = [span for col, span in slots.items() if col < len(row) and row[col].strip().lower() == 'shift']
    if not volunteers:
        raise ValueError('No volunteers found')
    return volunteers


def active_at(schedule, now, config):
    if now.tzinfo is None:
        raise ValueError('Time must include a timezone')
    before = timedelta(minutes=config.get('grace_before_minutes', 0))
    after = timedelta(minutes=config.get('grace_after_minutes', 0))
    return {name for name, spans in schedule.items() if any(start - before <= now < end + after for start, end in spans)}


def load_mapping(path=ROOT / 'data/names.csv'):
    rows = csv.reader(path.open(newline='', encoding='utf-8-sig'))
    return [(r[0].strip(), r[1].strip()) for r in rows if len(r) >= 2 and r[0].strip() not in ('', 'Names')]


def match_names(names, mapping, overrides):
    matched, issues = {}, []
    for name in sorted(names):
        target = overrides.get(name, name)
        candidates = [(n, h) for n, h in mapping if normalize(n) == normalize(target)]
        if not candidates:
            candidates = [(n, h) for n, h in mapping if difflib.SequenceMatcher(None, normalize(n), normalize(target)).ratio() >= .9]
        if len(candidates) != 1:
            issues.append({'name': name, 'reason': 'ambiguous' if candidates else 'unmatched', 'candidates': [n for n, _ in candidates]})
        elif candidates[0][1].lower() in ('', 'no discord'):
            issues.append({'name': name, 'reason': 'no Discord', 'candidates': []})
        else:
            matched[name] = candidates[0][1]
    return matched, issues


class Cache:
    """One last-good document, durable in S3 on Lambda or locally elsewhere."""
    def __init__(self):
        self.bucket = os.getenv('CACHE_BUCKET')
        self.path = Path(os.getenv('CACHE_FILE', str(ROOT / '.cache/state.json')))
        self.s3 = None
        if self.bucket:
            import boto3
            self.s3 = boto3.client('s3')
        try:
            if self.s3:
                self.data = json.loads(self.s3.get_object(Bucket=self.bucket, Key='state.json')['Body'].read())
            else:
                self.data = json.loads(self.path.read_text())
        except Exception as exc:
            if (self.s3 and getattr(exc, 'response', {}).get('Error', {}).get('Code') in ('NoSuchKey', '404')) or isinstance(exc, FileNotFoundError):
                self.data = {}
            else:
                raise

    def save(self):
        body = json.dumps(self.data)
        if self.s3:
            self.s3.put_object(Bucket=self.bucket, Key='state.json', Body=body.encode(), ContentType='application/json')
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(body)
            temporary.replace(self.path)


def fetch_schedule(config, cache):
    try:
        with urlopen(config['sheet_url'], timeout=15) as response:
            text = response.read().decode('utf-8-sig')
        schedule = parse_schedule(text, config)
    except Exception as exc:
        if 'sheet' not in cache.data:
            raise RuntimeError('Sheet unavailable and no last-good snapshot') from exc
        print(json.dumps({'warning': 'Using last-good sheet', 'saved_at': cache.data.get('sheet_saved_at'), 'error_type': type(exc).__name__}))
        return parse_schedule(cache.data['sheet'], config)
    cache.data.update(sheet=text, sheet_saved_at=datetime.now(timezone.utc).isoformat())
    cache.save()
    return schedule


class Discord:
    def __init__(self, token, guild):
        self.token, self.guild = token, guild

    def request(self, method, path, data=None, webhook=False):
        url = path if webhook else 'https://discord.com/api/v10' + path
        headers = {'User-Agent': 'MetagameShiftBot (private volunteer scheduler, 1.0)'}
        if not webhook:
            headers['Authorization'] = 'Bot ' + self.token
        if data is not None:
            headers['Content-Type'] = 'application/json'
        for attempt in range(5):
            try:
                with urlopen(Request(url, data=None if data is None else json.dumps(data).encode(), headers=headers, method=method), timeout=15) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else None
            except HTTPError as exc:
                if exc.code == 429 and attempt < 4:
                    delay = float(json.loads(exc.read()).get('retry_after', 1))
                    if delay > 10:
                        raise RuntimeError('Discord rate limit exceeds invocation window') from None
                    time.sleep(max(delay, .1))
                    continue
                # Do not expose webhook URL/token in exception output.
                raise RuntimeError(f'Discord {method} failed: HTTP {exc.code}') from None

    def members(self):
        result, after = [], '0'
        while True:
            page = self.request('GET', f'/guilds/{self.guild}/members?' + urlencode({'limit': 1000, 'after': after}))
            result.extend(page)
            if len(page) < 1000:
                return result
            after = page[-1]['user']['id']

    def resolve(self, handle):
        members = self.request('GET', f'/guilds/{self.guild}/members/search?' + urlencode({'query': handle, 'limit': 1000}))
        exact = {m['user']['id'] for m in members if handle.casefold() in {str(m['user'].get(k) or '').casefold() for k in ('username', 'global_name')} | {str(m.get('nick') or '').casefold()}}
        if len(exact) != 1:
            return None, 'ambiguous' if len(exact) > 1 else 'unmatched'
        return exact.pop(), None


def plan(desired, current):
    return sorted(desired - current), sorted(current - desired)


def reconcile(config, cache, now, dry_run, current_handles=None):
    schedule = fetch_schedule(config, cache)
    handles, issues = match_names(schedule, load_mapping(), config.get('name_overrides', {}))
    active = active_at(schedule, now, config)
    if dry_run:
        desired = {handles[n] for n in active if n in handles}
        adds, removes = plan(desired, set(current_handles or []))
        return {'time': now.astimezone(ZoneInfo(config['timezone'])).isoformat(), 'dry_run': True,
                'role_adds_handles': adds, 'role_removes_handles': removes,
                'announcement_preview': 'Now on shift: ' + ', '.join('@' + h for h in adds) if adds else None,
                'note': 'Handles only; IDs unverified. Current roles are simulated, not fetched.', 'issues': issues}
    guild, role = os.getenv('GUILD_ID', config['guild_id']), os.getenv('ROLE_ID', config['role_id'])
    token, webhook = secrets()
    if not guild.isdigit() or not role.isdigit() or not token or not webhook.startswith('https://discord.com/api/webhooks/'):
        raise ValueError('Set real guild/role IDs, bot token, and Discord webhook URL before live mode')
    discord = Discord(token, guild)
    members = discord.members()
    member_ids = {m['user']['id'] for m in members}
    current = {m['user']['id'] for m in members if role in m.get('roles', [])}
    ids = {}
    cached = cache.data.setdefault('discord_ids', {}).setdefault(guild, {})
    for name, handle in handles.items():
        uid = config.get('discord_id_overrides', {}).get(handle) or cached.get(handle)
        if uid and uid not in member_ids:
            uid = None
            cached.pop(handle, None)
        if not uid:
            uid, reason = discord.resolve(handle)
            if not uid:
                issues.append({'name': name, 'handle': handle, 'reason': 'Discord ' + reason})
                continue
            cached[handle] = uid
        ids[name] = uid
    cache.save()
    # Never remove a role from someone who might be an unresolved active volunteer.
    no_discord = {issue['name'] for issue in issues if issue['reason'] == 'no Discord'}
    if any(name not in ids and name not in no_discord for name in active):
        return {'blocked': 'Active volunteers unresolved; no role mutations', 'issues': issues}
    adds, removes = plan({ids[n] for n in active if n in ids}, current)
    for uid in removes:
        discord.request('DELETE', f'/guilds/{guild}/members/{uid}/roles/{role}')
    added = []
    try:
        for uid in adds:
            discord.request('PUT', f'/guilds/{guild}/members/{uid}/roles/{role}')
            added.append(uid)
    finally:
        if added:
            discord.request('POST', webhook + '?wait=true', {'content': 'Now on shift: ' + ', '.join('<@' + uid + '>' for uid in added), 'allowed_mentions': {'parse': [], 'users': added}}, webhook=True)
    return {'role_adds': adds, 'role_removes': removes, 'issues': issues}


def secrets():
    if os.getenv('SECRET_ARN'):
        import boto3
        value = json.loads(boto3.client('secretsmanager').get_secret_value(SecretId=os.environ['SECRET_ARN'])['SecretString'])
        return value['bot_token'], value['webhook_url']
    return os.getenv('BOT_TOKEN', ''), os.getenv('WEBHOOK_URL', '')


def configuration():
    config = json.loads((ROOT / 'config.json').read_text())
    local = ROOT / 'config.local.json'
    if local.exists():
        config.update(json.loads(local.read_text()))
    return config


def lambda_handler(event, context):
    config = configuration()
    dry = os.getenv('DRY_RUN', str(config.get('dry_run', True))).lower() == 'true'
    result = reconcile(config, Cache(), datetime.now(timezone.utc), dry)
    print(json.dumps(result))
    if result.get('blocked'):
        raise RuntimeError(result['blocked'])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--at', help='ISO 8601 time with UTC offset; defaults to now')
    parser.add_argument('--live', action='store_true', help='Actually mutate Discord; default is dry-run')
    parser.add_argument('--current-handles', default='', help='Comma-separated simulated role holders (dry-run only)')
    args = parser.parse_args()
    if args.live and (args.at or args.current_handles):
        parser.error('Simulated time/current holders are dry-run only')
    now = datetime.fromisoformat(args.at) if args.at else datetime.now(timezone.utc)
    result = reconcile(configuration(), Cache(), now, not args.live, [h for h in args.current_handles.split(',') if h])
    print(json.dumps(result, indent=2))
    return 1 if args.live and result.get('blocked') else 0


if __name__ == '__main__':
    raise SystemExit(main())
