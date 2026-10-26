import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_setup  # noqa: E402

FILLED = {
    "FIREBASE_API_KEY": "AIza-test",
    "FIREBASE_PROJECT_ID": "nmamit-assistant",
    "GROQ_API_KEY": "gsk_x",
    "ADMIN_EMAILS": "nnm23is186@nmamit.in",
}


def project(tmp_path: Path, env: str | None = None) -> Path:
    shutil.copy(ROOT / ".env.example", tmp_path / ".env.example")
    if env is not None:
        (tmp_path / ".env").write_text(env, encoding="utf-8")
    return tmp_path


def test_creates_env_and_lists_missing_settings(tmp_path):
    root = project(tmp_path)
    problems = check_setup.check(root)
    assert (root / ".env").exists()
    assert len(problems) == 4
    assert all(any(name in p for p in problems) for name in check_setup.REQUIRED)


def test_fills_weak_secret_key_and_keeps_the_rest(tmp_path):
    env = "".join(f"{k}={v}\n" for k, v in FILLED.items()) + "# keep me\nSECRET_KEY=secret\n"
    root = project(tmp_path, env)
    assert check_setup.check(root) == []
    values = dotenv_values(root / ".env")
    assert len(values["SECRET_KEY"]) >= check_setup.MIN_SECRET_LENGTH
    assert values["GROQ_API_KEY"] == "gsk_x"
    assert "# keep me" in (root / ".env").read_text(encoding="utf-8")


def test_strong_secret_key_is_left_alone(tmp_path):
    key = "k" * 40
    root = project(tmp_path, "".join(f"{k}={v}\n" for k, v in FILLED.items()) + f"SECRET_KEY={key}\n")
    check_setup.check(root)
    assert dotenv_values(root / ".env")["SECRET_KEY"] == key


def test_admin_email_outside_college_domain_is_reported(tmp_path):
    env = {**FILLED, "ADMIN_EMAILS": "someone@gmail.com"}
    root = project(tmp_path, "".join(f"{k}={v}\n" for k, v in env.items()))
    problems = check_setup.check(root)
    assert len(problems) == 1 and "someone@gmail.com" in problems[0]
