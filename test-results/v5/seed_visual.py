"""Build isolated visual fixtures; never touch the application's real data directory."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import GenerationJob, TokenUsage

root = Path(__file__).resolve().parents[2]
runtime = Path(__file__).resolve().parent / "runtime"
client = TestClient(create_app(Settings(data_dir=runtime)))
assert not client.get('/api/projects').json()['data'], 'Visual fixtures already exist; reuse manifest instead.'
pid = client.post('/api/projects', json={'name': '暮光衣橱 · 秋日系列', 'description': '同一个模特，三套风格。保留每一处服装细节。'}).json()['data']['id']
source = root / 'data' / 'text_picture' / '2'
for i, name in enumerate(['model.png', 'clothes_1.png', 'clothes_2.png', 'clothes_3.png']):
    path = source / name
    response = client.post(f'/api/projects/{pid}/assets/' + ('model' if i == 0 else 'clothing'),
        data={} if i == 0 else {'name': ['通勤针织套装','柔粉连衣裙','经典风衣套装'][i-1], 'slot_index': str(i-1)},
        files={'file': (name, path.read_bytes(), 'image/png')})
    assert response.status_code == 201, response.text
ids = [a['id'] for a in client.get(f'/api/projects/{pid}/assets').json()['data'] if a['asset_type']=='clothing']
job = client.post(f'/api/projects/{pid}/jobs', json={'provider':'mock','clothing_order':ids}).json()['data']['id']
draft = client.post('/api/projects', json={'name':'新系列 · 等待素材','description':'视觉验收专用项目'}).json()['data']['id']
with client.app.state.session_factory() as session:
    failed = GenerationJob(project_id=pid, provider='mock', status='failed', current_node='failed', error_message='视觉测试：生成服务暂时不可用，请稍后恢复任务。')
    session.add(failed)
    session.add(TokenUsage(job_id=job, step_key='visual-fixture', provider='mock', model='visual-fixture', input_tokens=1200, output_tokens=800, total_tokens=2000))
    session.commit()
    failed_id = failed.id
backup = client.post('/api/backups/export')
assert backup.status_code == 201
manifest = {'project':pid,'draft':draft,'job':job,'failed':failed_id}
(runtime.parent/'visual-fixtures.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest))
