"""Read-only checks of the Git index before publishing; never print secret values."""
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    paths = [p for p in git('ls-files', '-z').decode().split('\0') if p]
    patterns = {
        'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'google-key': rb'AIza[0-9A-Za-z_-]{35}',
        'openai-key': rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}',
        'github-token': rb'gh[pousr]_[A-Za-z0-9]{30,}',
        'aws-access-id': rb'AKIA[0-9A-Z]{16}',
        'jwt-literal': rb'eyJ[A-Za-z0-9_-]{16,}\.eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}',
    }
    local_secrets = []
    for env_path in [ROOT / '.env', ROOT / 'backend/.env', ROOT / 'frontend/.env.local']:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding='utf-8').splitlines():
            key, sep, value = line.partition('=')
            value = value.strip().strip('\"\'')
            if sep and re.search('KEY|SECRET|TOKEN|PASSWORD', key) and len(value) >= 20:
                local_secrets.append(value.encode())
    findings = []
    total = 0
    for path in paths:
        blob = git('show', ':' + path)
        total += len(blob)
        if len(blob) > 10 * 1024 * 1024:
            findings.append((path, 'file-over-10MiB'))
        if Path(path).name.startswith('.env') and Path(path).name != '.env.example':
            findings.append((path, 'environment-file'))
        if path.endswith(('.dump', '.db', '.pem', '.key')):
            findings.append((path, 'private-artifact'))
        for label, pattern in patterns.items():
            if re.search(pattern, blob):
                findings.append((path, label))
        if any(value in blob for value in local_secrets):
            findings.append((path, 'exact-local-secret'))
    for name in ['README.md', 'docs/ENGINEERING.md', 'docs/PUBLICATION.md', 'phase7-evidence/README.md']:
        data = git('show', ':' + name).decode()
        for ref in re.findall(r'\]\(([^)]+)\)', data):
            if '://' in ref or ref.startswith('#'):
                continue
            target = (ROOT / name).parent / ref.split('#')[0]
            relative = target.resolve().relative_to(ROOT).as_posix()
            if relative not in paths:
                findings.append((name, 'unpublished-link:' + relative))
    original_hash = hashlib.sha256((ROOT / 'audit.md').read_bytes()).hexdigest()
    if original_hash != 'f52705af7e850c00103a39d29d11c28d91803916fdb22d2cfdf946f23793940c':
        findings.append(('audit.md', 'historical-file-changed'))
    for path, label in findings:
        print(path + ': ' + label)
    print(f'Index files={len(paths)} bytes={total} findings={len(findings)}; limited signature/exact-secret scan, not exhaustive certification')
    raise SystemExit(bool(findings))


if __name__ == '__main__':
    main()
