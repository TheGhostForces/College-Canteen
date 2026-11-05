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
    student_view = (FRONTEND / "client/dishes.html").read_text()
    assert "text: data.pickup_token" in student_view
    assert "encodeURIComponent(String(studentId))" not in student_view
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


def test_category_menu_renders_untrusted_labels_as_text():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the frontend")
    html = (FRONTEND / "client/dishes.html").read_text()
    render = (
        "function renderMenu(items, onClick) {"
        + html.split("    function renderMenu(items, onClick) {", 1)[1].split("    function animateCards", 1)[0]
    )
    script = (
        r"""
        const assert = require('node:assert/strict');
        class Element {
            constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {}; }
            set innerHTML(value) { throw new Error('untrusted data rendered as HTML'); }
            appendChild(child) { this.children.push(child); return child; }
            append(...children) { this.children.push(...children); }
            replaceChildren(...children) { this.children = children; }
            addEventListener(name, handler) { this.listeners[name] = handler; }
            querySelectorAll(tag) {
                return this.children.flatMap(child => child.tag === tag ? [child] : child.querySelectorAll(tag));
            }
        }
        const document = {createElement: tag => new Element(tag)};
        const menuDishes = new Element('ul');
        let menuButtons = [];
    """
        + render
        + r"""
        const malicious = '\" autofocus onfocus=\"globalThis.pwned=1\"><img src=x onerror=alert(1)>';
        let clicked = -1;
        renderMenu([{id: malicious, label: malicious}], index => { clicked = index; });
        assert.equal(menuButtons.length, 1);
        assert.equal(menuButtons[0].textContent, malicious);
        assert.equal(menuButtons[0].id, malicious);
        menuButtons[0].listeners.click();
        assert.equal(clicked, 0);
    """
    )
    result = subprocess.run([node, "-"], input=script, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_reserved_category_names_group_and_render():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the frontend")
    html = (FRONTEND / "client/dishes.html").read_text()
    distribution = (
        "async function distributionDishes() {"
        + html.split("    async function distributionDishes() {", 1)[1].split("    function renderDishesMenu", 1)[0]
    )
    show = (
        "function showDishPage(pageIndex, direction = 'none') {"
        + html.split("    function showDishPage(pageIndex, direction = 'none') {", 1)[1].split(
            "    function syncBasketUi", 1
        )[0]
    )
    script = (
        r"""
        const assert = require('node:assert/strict');
        const inputs = ['constructor', 'toString', '__proto__', 'constructor']
            .map((category, index) => ({category, quantity: 1, dish_name: String(index)}));
        let totalDishes = {}, totalCategories = [], dishesLoaded = false, dishesCurrentPage = 0;
        let rendered = [];
        const document = {createElement: () => ({appendChild() {}, classList: {add() {}}})};
        const dishesSwipeContent = {innerHTML: '', appendChild() {}};
        const titleChapter = {};
        const menuButtons = [];
        const loadDishes = async () => inputs;
        const sortDishesByAvailability = dishes => dishes;
        const isDishAvailable = dish => dish.quantity > 0;
        const updating_dish_card = (_container, dishes) => rendered.push(dishes.map(d => d.dish_name));
        const animateCards = () => {};
        const show_message = () => {};
    """
        + distribution
        + show
        + r"""
        (async () => {
            await distributionDishes();
            assert.deepEqual(totalCategories, ['constructor', 'toString', '__proto__']);
            for (let i = 0; i < totalCategories.length; i++) showDishPage(i);
            assert.deepEqual(rendered, [['0', '3'], ['1'], ['2']]);
        })().catch(error => { console.error(error); process.exitCode = 1; });
    """
    )
    result = subprocess.run([node, "-"], input=script, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_student_menu_consumes_sets_and_filters_unavailable_buffet():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the frontend")
    html = (FRONTEND / "client/dishes.html").read_text()
    distribution = (
        "async function distributionDishes() {"
        + html.split("    async function distributionDishes() {", 1)[1].split("    function renderDishesMenu", 1)[0]
    )
    script = (
        r"""
        const assert = require('node:assert/strict');
        let totalDishes = {}, totalCategories = [], dishesLoaded = false;
        let pickupDate = '';
        let menu = {pickup_date: '2026-11-09', dishes: [
            {id: 7, category: 'Unknown', quantity: 2, dish_name: 'Tea'},
            {id: 8, category: 'Unknown', quantity: 0, dish_name: 'Gone'}],
            sets: [{id: 9, meal_type: 'lunch', price: 10, components: [{dish_name: 'Soup'}], energy_kcal: 42}]};
        const loadDishes = async () => menu;
        const sortDishesByAvailability = dishes => dishes;
        const isDishAvailable = dish => dish.quantity > 0;
        const show_message = () => {};
    """
        + distribution
        + r"""
        (async () => {
            await distributionDishes();
            assert.equal(pickupDate, '2026-11-09');
            assert(totalCategories.includes('Unknown'));
            assert.equal(totalDishes.Unknown.length, 1);
            const all = Object.values(totalDishes).flat();
            const meal = all.find(item => item.item_type === 'set');
            assert.equal(meal.meal_set_id, 9);
            assert.equal(meal.components[0].dish_name, 'Soup');
            assert.equal(meal.energy_kcal, 42);
            assert.equal(all.find(item => item.dish_name === 'Tea').buffet_offering_id, 7);
            menu = {pickup_date: '2026-11-09', dishes: [], sets: []};
            await distributionDishes();
            assert.deepEqual(totalCategories, []);
        })().catch(error => { console.error(error); process.exitCode = 1; });
    """
    )
    result = subprocess.run([node, "-"], input=script, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_set_cards_show_safe_contents_nutrition_and_one_per_type_controls():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the frontend")
    cards = (FRONTEND / "js/meal_cards.js").read_text()
    card_class = cards.split("class CardDishClass", 1)[1].split("/**\n * Observer", 1)[0]
    common = (FRONTEND / "js/common.js").read_text()
    escape = (
        "function escapeData" + common.split("export function escapeData", 1)[1].split("export async function", 1)[0]
    )
    script = (
        r"""
        const assert = require('node:assert/strict');
    """
        + escape
        + "class CardDishClass"
        + card_class
        + r"""
        const malicious = '<img src=x onerror=alert(1)>';
        const data = {item_type: 'set', dish_name: malicious, components: [{dish_name: malicious}],
            serving_weight_g: 200, energy_kcal: 42, protein_g: 2, fat_g: 3, carbohydrates_g: 4,
            quantity: 1, fixed_price: 10};
        const card = new CardDishClass(data, 'dishes_container_let_amount');
        const html = card.createEditableAmountHTML();
        assert(!html.includes(malicious));
        assert(html.includes('&lt;img'));
        assert(html.includes('Состав:') && html.includes('42 ккал'));
        assert(!html.includes('counter_plus') && !html.includes('counter_minus'));
        const basket = card.DishCardInBascet();
        assert(!basket.includes('counter_plus') && !basket.includes('counter_minus'));
    """
    )
    result = subprocess.run([node, "-"], input=script, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_typed_basket_identifiers_and_stock_cutoff_errors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the frontend")
    html = (FRONTEND / "client/dishes.html").read_text()
    helpers = (
        "function typedItem(card, quantity) {"
        + html.split("    function typedItem(card, quantity) {", 1)[1].split(
            "    dishesSwipeContent.addEventListener", 1
        )[0]
    )
    script = (
        "const assert = require('node:assert/strict');\n"
        + helpers
        + r"""
        assert.deepEqual(typedItem({dataset:{itemType:'set', itemId:'5'}}, 1),
            {item_type:'set', meal_set_id:5, cart_quantity:1});
        assert.deepEqual(typedItem({dataset:{itemType:'buffet', itemId:'7'}}, 2),
            {item_type:'buffet', buffet_offering_id:7, cart_quantity:2});
        assert.match(serverError({detail:'Ordering closed'}), /истекло/);
        assert.match(serverError({detail:'Cart updated due to insufficient availability'}), /Наличие изменилось/);
        assert.match(serverError({detail:'Total order amount exceeds 100'}), /стоимость/i);
    """
    )
    result = subprocess.run([node, "-"], input=script, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_pickup_views_use_server_date():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise pickup views")
    script = Path(__file__).with_name("test_pickup_views.cjs")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_student_interaction_regressions():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise student interactions")
    script = Path(__file__).with_name("test_student_interactions.cjs")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_basket_entry_uses_typed_student_view():
    basket = (FRONTEND / "client/basket.html").read_text()
    assert "location.replace('./dishes.html?view=basket')" in basket


@pytest.mark.parametrize(
    "page",
    [
        "login.html",
        "authentication.html",
        "client/basket.html",
        "client/dishes.html",
        "distribution_operator/order_search.html",
    ],
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
