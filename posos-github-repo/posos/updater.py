import hashlib, json, os, shutil, tarfile, tempfile, urllib.request
from pathlib import Path

class UpdateError(RuntimeError): pass


def github_latest(repo: str):
    req=urllib.request.Request(f'https://api.github.com/repos/{repo}/releases/latest',headers={'Accept':'application/vnd.github+json','User-Agent':'POSOS-Updater'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def check_latest(repo: str, current: str):
    data=github_latest(repo)
    latest=data.get('tag_name','').lstrip('v')
    assets={a['name']:a['browser_download_url'] for a in data.get('assets',[])}
    return {'available': bool(latest and latest != current), 'version':latest, 'notes':data.get('body',''), 'assets':assets}


def download_and_verify(url, sha_url, destination: Path):
    destination.parent.mkdir(parents=True,exist_ok=True)
    urllib.request.urlretrieve(url,destination)
    expected=urllib.request.urlopen(sha_url,timeout=15).read().decode().strip().split()[0]
    actual=hashlib.sha256(destination.read_bytes()).hexdigest()
    if actual.lower()!=expected.lower():
        destination.unlink(missing_ok=True); raise UpdateError('Update checksum did not match')
    return actual
