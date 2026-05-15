# backend/config/config.py
import os

CSV_DIR = os.environ.get("CSV_DIR", "./data")
CSV_ENCODING = os.environ.get("CSV_ENCODING", "utf-8")
IDENTITIES_FILE = os.path.join(CSV_DIR, "identities.csv")
IDENTITY_PK_COLUMN = os.environ.get("IDENTITY_PK_COLUMN", "usr_id")
ENTITLEMENTS_FILE = os.path.join(CSV_DIR, "entitlements.csv")
ASSIGNMENTS_FILE = os.path.join(CSV_DIR, "assignments.csv")
ASSIGNMENT_USER_COLUMN = os.environ.get("ASSIGNMENT_USER_COLUMN", "usr_id")

MAX_POPULATION = int(os.environ.get("MAX_POPULATION", 10000))
MAX_CONCURRENT_SESSIONS = int(os.environ.get("MAX_CONCURRENT_SESSIONS", 5))
MAX_ACTIVE_SESSIONS = int(os.environ.get("MAX_ACTIVE_SESSIONS", 5))
MAX_TOTAL_SESSIONS = int(os.environ.get("MAX_TOTAL_SESSIONS", 1000))
ALGORITHM_VERSION = os.environ.get("ALGORITHM_VERSION", "2026-05-15-001")

DEFAULT_UNIVERSAL_THRESHOLD = float(os.environ.get("DEFAULT_UNIVERSAL_THRESHOLD", 0.90))
DEFAULT_COVERAGE_THRESHOLD = float(os.environ.get("DEFAULT_COVERAGE_THRESHOLD", 0.80))
DEFAULT_SOFT_THRESHOLD = float(os.environ.get("DEFAULT_SOFT_THRESHOLD", 0.50))
DEFAULT_SIMILARITY_THRESHOLD = float(os.environ.get("DEFAULT_SIMILARITY_THRESHOLD", 0.30))
DEFAULT_MIN_GROUP_SIZE = int(os.environ.get("DEFAULT_MIN_GROUP_SIZE", 30))
DEFAULT_MAX_ROLES = int(os.environ.get("DEFAULT_MAX_ROLES", 25))
DEFAULT_OUTLIER_THRESHOLD = float(os.environ.get("DEFAULT_OUTLIER_THRESHOLD", 0.30))
DEFAULT_BIRTHRIGHT_COOCCURRENCE_THRESHOLD = float(
    os.environ.get("DEFAULT_BIRTHRIGHT_COOCCURRENCE_THRESHOLD", 0.95)
)

PORT = int(os.environ.get("PORT", 8000))
