"""Central runtime version metadata loaded from the repository properties file."""

from pathlib import Path


VERSION_FILE = Path(__file__).resolve().parents[1] / "version.properties"


def _load_properties() -> dict:
    properties = {}
    for raw_line in VERSION_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            properties[key.strip()] = value.strip()
    return properties


_PROPERTIES = _load_properties()
SENTINEL_VERSION = _PROPERTIES["sentinel.version"]
CAMFLOW_SOURCE_VERSION = _PROPERTIES["camflow.version"]
CAMFLOW_VERSION_CODE = int(_PROPERTIES["camflow.versionCode"])
CAMFLOW_APK_PATH = _PROPERTIES["camflow.apkPath"]
CAMFLOW_APK_SHA256 = _PROPERTIES["camflow.apkSha256"]
RELEASE_DATE = _PROPERTIES["release.date"]


def version_info() -> dict:
    return {
        "sentinel": SENTINEL_VERSION,
        "camflow_source": CAMFLOW_SOURCE_VERSION,
        "camflow_version_code": CAMFLOW_VERSION_CODE,
        "camflow_apk_path": CAMFLOW_APK_PATH,
        "camflow_apk_sha256": CAMFLOW_APK_SHA256,
        "release_date": RELEASE_DATE,
    }
