const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../../frontend');
const html = fs.readFileSync(path.join(root, 'client/dishes.html'), 'utf8');
const cards = fs.readFileSync(path.join(root, 'js/meal_cards.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'styles/styles.css'), 'utf8');
const common = fs.readFileSync(path.join(root, 'js/common.js'), 'utf8');

function element() {
    return {innerHTML: '', textContent: '', style: {}, dataset: {}, listeners: {},
        classList: {add(){}, remove(){}}, addEventListener(type, fn) { this.listeners[type] = fn; },
        querySelector() { return null; }, querySelectorAll() { return []; }};
}
function pageContext(fetch) {
    const b = element(), o = element(), checkout = element(), cancel = element(), swipe = element();
    const pickup = element(), orderPickup = element(), messages = [];
    const ctx = {console, fetch, URLSearchParams, dishesPageBasket:b, dishesPageOrder:o,
        dishesSwipeContent:swipe, setOrderBtn:checkout, removeOrderBtn:cancel,
        basketPickupDate:pickup, orderPickupDate:orderPickup, pickupDate:'2026-11-09',
        basketItems:[], basketLoaded:false, basketLoading:false, orderLoaded:false, orderLoading:false,
        basketCurrentPage:0, dishesLoaded:false, currentRoute:'basket', ROUTES:{BASKET:'basket'},
        showBasketLoader(){}, updating_dish_card(container, dishes) { container.rendered = dishes; },
        updateOrderTotalPrice(){}, animateCards(){}, syncBasketUi(){}, refreshPickupQRCode:async()=>{},
        show_message(message) { messages.push(message); }};
    vm.createContext(ctx);
    const updates = html.split('    async function updateBasketPage', 2)[1].split('    function renderBasketMenu', 1)[0];
    const handlers = html.split('    function typedItem', 2)[1].split("    document.addEventListener('DOMContentLoaded'", 1)[0];
    vm.runInContext('async function updateBasketPage' + updates + '\nfunction typedItem' + handlers, ctx);
    return {ctx,b,o,checkout,cancel,swipe,pickup,orderPickup,messages};
}
const response = (body, ok=true) => ({ok, json: async () => body});
async function run() {
    // An add finishing while the initial basket GET is still in flight must trigger a fresh GET.
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    let reads = 0;
    const p = pageContext(async (url, opts={}) => {
        if (url === '/api/basket/dish' && opts.method === 'GET') {
            reads++;
            if (reads === 1) { await gate; return response({dishes:[]}); }
            return response({dishes:[{item_type:'set', meal_type:'lunch', date:'2026-11-09'}]});
        }
        return response({});
    });
    const initial = p.ctx.updateBasketPage();
    const addButton = {disabled:false, closest:()=>({dataset:{itemType:'set',itemId:'1',mealType:'lunch'}, querySelector:()=>({textContent:'1'})})};
    const add = p.swipe.listeners.click({target:{closest:()=>addButton}, preventDefault(){}, stopPropagation(){}});
    await Promise.resolve(); release(); await Promise.all([initial, add]);
    assert.equal(reads, 2, 'post-add refresh must not be dropped');
    assert.equal(p.ctx.basketItems[0].meal_type, 'lunch');
    assert.match(p.pickup.textContent, /2026-11-09/);
    await p.swipe.listeners.click({target:{closest:()=>addButton}, preventDefault(){}, stopPropagation(){}});
    assert.match(p.messages.at(-1), /один комплекс/);

    // Checkout rejection must refresh the visible basket and explain reconfirmation.
    let refreshes = 0;
    const q = pageContext(async (url, opts={}) => {
        if (url === '/api/orders/order' && opts.method === 'POST') return response({detail:'Cart updated; please confirm again'}, false);
        if (url.startsWith('/api/basket/dish?') && opts.method === 'DELETE') return response({detail:'Item not found'}, false);
        if (url === '/api/basket/dish') { refreshes++; return response({dishes:[{date:'2026-11-09'}]}); }
        if (url === '/api/orders/order' && opts.method === 'DELETE') return response({detail:'Not enough time'}, false);
        return response({Orders:{ORD:[{pickup_date:'2026-11-10'}]}});
    });
    await q.checkout.listeners.click();
    assert.equal(refreshes, 1);
    assert.match(q.messages.at(-1), /Наличие изменилось/);
    await q.cancel.listeners.click();
    assert.match(q.messages.at(-1), /время|истекло/i);
    const deletedCard = {dataset:{itemType:'buffet',itemId:'8'}};
    await q.b.listeners.click({target:{closest:selector => selector === '.card_dish' ? deletedCard : {}}});
    assert.match(q.messages.at(-1), /недоступна/);
    assert.equal(refreshes, 2);
    await q.ctx.updateOrderPage();
    assert.match(q.orderPickup.textContent, /2026-11-10/);

    const empty = pageContext(async () => response({dishes:[]}));
    await empty.ctx.updateBasketPage();
    assert.match(empty.pickup.textContent, /2026-11-09/);
    let rejection = 'Only one of each set type is allowed';
    const rejected = pageContext(async () => response({detail:rejection}, false));
    await rejected.swipe.listeners.click({target:{closest:()=>addButton}, preventDefault(){}, stopPropagation(){}});
    assert.match(rejected.messages.at(-1), /один комплекс/);
    rejection = '<img src=x onerror=alert(1)>';
    await rejected.swipe.listeners.click({target:{closest:()=>addButton}, preventDefault(){}, stopPropagation(){}});
    assert.match(rejected.messages.at(-1), /попробуйте/);
    assert(!rejected.messages.at(-1).includes('<img'));

    // Real card increment updates only its own basket total, even with other panels populated.
    const cls = cards.split('class CardDishClass')[1].split('/**\n * Observer')[0];
    const totalLabel = {textContent:''}, totalSection = {style:{}};
    const basket = element(), order = element(), menu = element();
    const price = {textContent:'10'}, counter = {textContent:'2'};
    const makeCard = value => ({querySelector:()=>({textContent:String(value)})});
    basket.querySelectorAll = () => [{querySelector:()=>price}, makeCard(5)];
    order.querySelectorAll = () => [makeCard(90)];
    menu.querySelectorAll = () => [makeCard(500)];
    const document = {getElementById:id => id === 'total_order_price' ? totalLabel : totalSection,
        querySelectorAll:()=>[...basket.querySelectorAll(), ...order.querySelectorAll(), ...menu.querySelectorAll()]};
    const cardctx = {document, escapeData:s=>String(s ?? '')};
    vm.createContext(cardctx);
    const totals = common.split('function calculateOrderTotal(parent)')[1].split('/**\n * Сохраняет', 1)[0]
        .replace('export function updateOrderTotalPrice', 'function updateOrderTotalPrice');
    vm.runInContext('function calculateOrderTotal(parent)' + totals + '\nclass CardDishClass' + cls +
        '; globalThis.CardDishClass = CardDishClass;', cardctx);
    const card = new cardctx.CardDishClass({fixed_price:10}, 'dish_card_in_basket');
    card.card = {closest:()=>basket, querySelector:s=>s === '.counter_value' ? counter : price};
    card.updateTotalPrice();
    assert.equal(totalLabel.textContent, '25.00'); assert.equal(price.textContent, '20.00');
    card.card.closest = () => order;
    card.updateTotalPrice();
    assert.equal(totalLabel.textContent, '90.00');
    const set = new cardctx.CardDishClass({item_type:'set',meal_type:'lunch',dish_name:'lunch',quantity:1,fixed_price:1}, 'dish_card_in_basket');
    const markup = set.DishCardInBascet();
    assert.match(markup, /Обед/);
    assert(!/img\/(?:null|undefined)|<img/.test(markup));
    assert.match(css, /\.card_dish_details[\s\S]*?color:\s*(?:white|#fff)/i);
    assert.match(css, /\.card_dish_details[\s\S]*?(?:overflow-wrap|word-break):/i);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
