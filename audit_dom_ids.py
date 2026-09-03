import re

with open('vercel_deploy/public/app.js', 'r', encoding='utf-8') as f:
    app_js = f.read()
with open('vercel_deploy/public/index.html', 'r', encoding='utf-8') as f:
    index_html = f.read()

elem_ids = set(re.findall(r'document\.getElementById\(["\']([^"\']+)["\']\)', app_js))
html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', index_html))

missing_ids = elem_ids - html_ids
print('Element IDs in app.js:', len(elem_ids), sorted(list(elem_ids)))
print('Element IDs in index.html:', len(html_ids))
print('Missing IDs in index.html:', missing_ids)
