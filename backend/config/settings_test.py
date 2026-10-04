from .settings import *  # noqa

# 本地/CI 跑测试用：文件型 SQLite（内存库多线程写会报 table locked，
# 无法真实验证并发撞码场景）。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        "TEST": {"NAME": "/tmp/sailcloth_test_db.sqlite3"},
        "OPTIONS": {"timeout": 20},
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
