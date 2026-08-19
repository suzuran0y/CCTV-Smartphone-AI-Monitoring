import hashlib
from pathlib import Path

from app.version import (
    CAMFLOW_APK_PATH,
    CAMFLOW_APK_SHA256,
    CAMFLOW_SOURCE_VERSION,
    CAMFLOW_VERSION_CODE,
    RELEASE_DATE,
    SENTINEL_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_versions_match_android_build_and_readmes():
    gradle = (ROOT / "PhoneCamSender" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    readme_cn = (ROOT / "README_CN.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")

    assert 'rootProject.file("../version.properties")' in gradle
    assert "versionName = camflowVersion" in gradle
    assert "versionCode = camflowVersionCode" in gradle
    assert isinstance(CAMFLOW_VERSION_CODE, int)
    assert CAMFLOW_VERSION_CODE > 0
    apk_path = ROOT / CAMFLOW_APK_PATH
    assert apk_path.is_file()
    assert f"v{CAMFLOW_SOURCE_VERSION}" in apk_path.name
    assert hashlib.sha256(apk_path.read_bytes()).hexdigest().upper() == CAMFLOW_APK_SHA256
    for readme in (readme_cn, readme_en):
        assert f"v{SENTINEL_VERSION}" in readme
        assert f"v{CAMFLOW_SOURCE_VERSION}" in readme
        assert CAMFLOW_APK_PATH in readme
        assert CAMFLOW_APK_SHA256 in readme
        assert RELEASE_DATE in readme
