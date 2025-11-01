import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# --------------------------------------------------
# 載入環境變數（Render 或 .env 皆可用）
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# 專案基底路徑
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------
# 安全性設定
# --------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-your-secret-key')

# 預設 Debug 依環境變數切換（本地開發可在 .env 設 DEBUG=True）
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# 部署時允許的主機清單
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

# --------------------------------------------------
# 已安裝的 Django App
# --------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',  # 你的主要應用
]

# --------------------------------------------------
# 中介層（Middleware）
# --------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # 提供靜態檔案服務
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# --------------------------------------------------
# URL 與模板設定
# --------------------------------------------------
ROOT_URLCONF = 'system.urls'

LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/logout/'
LOGIN_URL = '/login/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'system.wsgi.application'

# --------------------------------------------------
# 資料庫設定（Render 自動偵測 DATABASE_URL，否則用 SQLite）
# --------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv(
            "DATABASE_URL",
            f"sqlite:///{os.path.join(BASE_DIR, 'db.sqlite3')}"
        ),
        conn_max_age=600,
        ssl_require=False
    )
}

# --------------------------------------------------
# 靜態與媒體檔案設定
# --------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# WhiteNoise 壓縮與快取設定（Render 部署必要）
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --------------------------------------------------
# 其他設定
# --------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --------------------------------------------------
# API 金鑰設定（語音轉文字或 OpenAI 模型）
# --------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# 若你之後使用 openai 套件，請在程式內部用：
#   import openai
#   openai.api_key = settings.OPENAI_API_KEY
