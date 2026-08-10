from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'qualification' / 'source_function_comments_0_6_73.json'


def test_source_function_comment_manifest_scope():
    data = json.loads(MANIFEST.read_text())
    assert data['schema'] == 'xstar-tools-source-function-comment-overlay-v1'
    assert data['productization_version'] == '0.6.73'
    assert data['base_productization_version'] == '0.6.72'
    assert data['science_revision'] == '0.6.48.12.3.45.3.3.8'
    assert data['summary'] == {
        'annotated_files': 102,
        'cpp_files': 27,
        'cpp_function_comments': 1177,
        'python_files': 75,
        'python_function_comments': 1490,
    }


def test_source_function_comment_checker_accepts():
    proc = subprocess.run(
        [sys.executable, 'tools/qualification/check_source_function_comments.py'],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'SOURCE_FUNCTION_COMMENTS_RESULT=ACCEPT' in proc.stdout
    assert 'SOURCE_FUNCTION_COMMENTS_NONCOMMENT_CHANGED=0' in proc.stdout


def test_function_comment_guide_is_in_developer_docs():
    text = (ROOT / 'docs/developer/function_commenting.md').read_text()
    assert 'XSTAR-FUNCTION-COMMENT-BEGIN' in text
    assert 'data type' in text.lower() and 'rate type' in text.lower()
    index = (ROOT / 'docs/developer/index.md').read_text()
    assert 'function_commenting' in index
