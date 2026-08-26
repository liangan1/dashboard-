import requests, base64, json, os

with open('deploy_config.json', 'r') as f:
    cfg = json.load(f)
token = cfg['github_token']
repo = cfg['github_repo']

with open('index.html', 'rb') as f:
    content = f.read()

# Get current SHA
url = f"https://api.github.com/repos/{repo}/contents/index.html"
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}
r = requests.get(url, headers=headers)
sha = r.json().get('sha')
print(f"Current SHA: {sha[:10]}..." if sha else "No existing file")

# Update
data = {
    'message': 'feat(us): add sub-nav, market pulse, sector fund flow, reorder sections',
    'content': base64.b64encode(content).decode(),
    'sha': sha
}
r = requests.put(url, headers=headers, json=data)
if r.status_code in (200, 201):
    info = r.json()
    print(f"✅ Pushed! commit: {info['commit']['sha'][:7]}")
    print(f"   URL: {info['content']['html_url']}")
else:
    print(f"❌ Failed: {r.status_code}")
    print(r.text[:500])
