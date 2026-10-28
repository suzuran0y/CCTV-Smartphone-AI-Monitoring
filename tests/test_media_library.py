from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import authenticate


def make_file(cfg, kind='videos', name='cam_20261029_120000.mp4', content=b'media-content'):
    path = Path(cfg.get_copy()['out_root']) / kind / '20261029' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_media_permissions_pagination_download_and_ranges(system):
    app, auth, token, cfg, _, runtime = system
    first = make_file(cfg)
    active = make_file(cfg, name='cam_20261029_130000.mp4')
    runtime.rec = SimpleNamespace(current_path=str(active))
    make_file(cfg, 'snapshots', 'snapshot_20261029_120000_123456.jpg')
    visitor = app.test_client()
    paired = auth.pair(auth.pairing_code(), 'phone')
    for path in ['/api/media', '/api/media/download?kind=videos&path=20261029/cam_20261029_120000.mp4']:
        assert visitor.get(path).status_code == 401
        assert visitor.get(path, headers={'Authorization': 'Bearer ' + paired['device_token']}).status_code == 401
    admin = authenticate(app.test_client(), auth, token)
    listed = admin.get('/api/media').json
    assert [f['name'] for f in listed['items']] == [first.name]
    assert listed['items'][0]['size_bytes'] == 13
    response = admin.get('/api/media/download', query_string={'path': '20261029/' + first.name})
    assert response.data == b'media-content'
    assert 'attachment' in response.headers['Content-Disposition']
    response.close()
    response = admin.get('/api/media/download', query_string={'path': '20261029/' + first.name}, headers={'Range': 'bytes=0-4'})
    assert response.status_code == 206
    assert response.data == b'media'
    response.close()
    assert admin.get('/api/media/download', query_string={'path': '20261029/' + active.name}).status_code == 409
    for i in range(26):
        make_file(cfg, name=f'cam_20261029_140000_{i}.mp4')
    page = admin.get('/api/media').json
    assert len(page['items']) == 25 and page['has_more']
    second = admin.get('/api/media?page=2').json
    assert len(second['items']) == 2 and not second['has_more']
    assert len(admin.get('/api/media?kind=snapshots').json['items']) == 1


@pytest.mark.parametrize('relative', ['../../app/config/auth.sqlite3', '/etc/passwd',
    '20261029/../secret.mp4', '20261029\\cam_20261029_120000.mp4',
    '20261029/cam_20261029_120000.mp4:secret', '20261029/.sentinel-recordings.sqlite3'])
def test_media_rejects_path_escape(system, relative):
    app, auth, token, *_ = system
    admin = authenticate(app.test_client(), auth, token)
    assert admin.get('/api/media/download', query_string={'path': relative}).status_code == 400


def test_media_handles_missing_files_output_change_and_links(system, tmp_path):
    app, auth, token, cfg, *_ = system
    path = make_file(cfg)
    admin = authenticate(app.test_client(), auth, token)
    path.unlink()  # A retention pass can remove a file between list and download.
    assert admin.get('/api/media/download', query_string={'path': '20261029/' + path.name}).status_code == 404
    make_file(cfg)
    cfg.set_key('out_root', str(tmp_path / 'other-output'))
    assert admin.get('/api/media').json['items'] == []
    cfg.set_key('out_root', str(path.parents[2]))
    secret = tmp_path / 'private.mp4'
    secret.write_bytes(b'private')
    link = path.with_name('cam_20261029_140000.mp4')
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip('This Windows account cannot create symlinks')
    assert all(item['name'] != link.name for item in admin.get('/api/media').json['items'])
    assert admin.get('/api/media/download', query_string={'path': '20261029/' + link.name}).status_code == 400


@pytest.mark.parametrize('query', ['kind=logs', 'page=0', 'page=401', 'page_size=999', 'page=nan'])
def test_media_rejects_invalid_query(system, query):
    app, auth, token, *_ = system
    admin = authenticate(app.test_client(), auth, token)
    assert admin.get('/api/media?' + query).status_code == 400


def test_media_rejects_reparse_point_even_without_symlink_privileges(system, monkeypatch):
    app, auth, token, cfg, *_ = system
    path = make_file(cfg)
    original_lstat = Path.lstat

    def reparse(target, *args, **kwargs):
        info = original_lstat(target, *args, **kwargs)
        if target == path:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, 'lstat', reparse)
    admin = authenticate(app.test_client(), auth, token)
    assert admin.get('/api/media').json['items'] == []
    assert admin.get('/api/media/download', query_string={'path': '20261029/' + path.name}).status_code == 400
