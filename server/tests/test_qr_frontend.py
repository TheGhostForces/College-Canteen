"""Exercise the bundled QR encoder and scanner parser without network or a browser."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.security import create_pickup_token

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def test_pickup_qr_encoder_capacity_and_scanner_extraction():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the bundled frontend QR encoder")

    basket = (FRONTEND / "client/basket.html").read_text()
    operator = (FRONTEND / "distribution_operator/order_search.html").read_text()
    token, _ = create_pickup_token(9223372036854775807, 9223372036854775806, 9223372036854775805)
    level = re.search(r"correctLevel: QRCode.CorrectLevel\.(\w+)", basket).group(1)
    assert "text: data.pickup_token" in basket
    assert "student_id=" not in operator
    assert "check_student_id" not in operator
    parser = operator.split("    function extractPickupToken(raw) {", 1)[1].split("    function focusInput()", 1)[0]
    parser = "function extractPickupToken(raw) {" + parser
    library = FRONTEND / "js/vendor/qrcode.min.js"
    script = f"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');
        const context = {{navigator: {{userAgent: ''}}, document: {{documentElement: {{tagName: 'html'}}}}}};
        vm.createContext(context);
        vm.runInContext(fs.readFileSync({json.dumps(str(library))}, 'utf8'), context);
        const token = {json.dumps(token)};
        const element = {{innerHTML: '', childNodes: [{{offsetWidth: 300, offsetHeight: 300, style: {{}}}}]}};
        const qr = new context.QRCode(element, {{
            text: token, width: 300, height: 300,
            correctLevel: context.QRCode.CorrectLevel.{level}
        }});
        assert.equal(qr._oQRCode.dataList[0].data, token);
        assert(qr._oQRCode.getModuleCount() > 21);
        assert(qr._oQRCode.getModuleCount() <= 100);
        {parser}
        assert.equal(extractPickupToken(token), token);
        assert.equal(extractPickupToken('  ' + token + '  '), token);
        assert.equal(extractPickupToken('https://example.test/qr?pickup_token=' + token), token);
        assert.equal(extractPickupToken('https://example.test/qr#pickup_token=' + token), token);
        for (const invalid of ['1', '100000', '', 'https://example.test/123',
             'https://example.test/qr?student_id=123', 'broken', 'a.b.c' + 'x'.repeat(2048)]) {{
            assert.throws(() => extractPickupToken(invalid));
        }}
    """
    result = subprocess.run([node, "-"], input=script, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "page", ["login.html", "authentication.html", "client/basket.html", "distribution_operator/order_search.html"]
)
def test_updated_frontend_module_syntax(page):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to validate frontend module syntax")
    html = (FRONTEND / page).read_text()
    script = re.search(r'<script type="module">(.*?)</script>', html, re.DOTALL).group(1)
    result = subprocess.run(
        [node, "--check", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
