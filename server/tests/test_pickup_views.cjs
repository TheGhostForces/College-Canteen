const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../frontend');
function element() { return {style:{}, innerHTML:'', value:'College'}; }
async function runPage(file, start, end, action) {
    const html = fs.readFileSync(path.join(root, file), 'utf8');
    const source = 'async function ' + start + html.split('    async function ' + start, 2)[1].split('    function ' + end, 1)[0];
    const requests = [];
    const ctx = {console, URLSearchParams, selection:element(), institutions:{College:4},
        summary_title:element(), orders_title:element(), input_hint:element(),
        summary_container:element(), container_with_data_from_api:element(),
        resetView(){}, getTomorrowDate:()=> '2026-11-07', buildDishSummary(){return {}}, renderDishSummary(){}, createDropDownMenuCard(){},
        show_message(message){throw Error(message)}, setTimeout(){}, document:{querySelectorAll:()=>[]},
        fetch:async url => {requests.push(url); return {ok:true, json:async()=>url.includes('next-pickup-date') ?
            {pickup_date:'2026-11-09'} : {Orders:{}}};}};
    vm.createContext(ctx);
    vm.runInContext(source, ctx);
    await ctx[start]();
    assert.equal(requests[0], '/api/orders/next-pickup-date');
    const requested = new URL(requests[1], 'http://test');
    assert.equal(requested.pathname, action);
    assert.equal(requested.searchParams.get('target_date'), '2026-11-09');
    assert.match(ctx.summary_title.textContent, /2026-11-09/);
    assert.match(ctx.orders_title.textContent, /2026-11-09/);
    if (action.endsWith('/orders')) assert.equal(requested.searchParams.get('institution_id'), '4');
}
(async () => {
    await runPage('distribution_operator/dishes_tomorrow.html', 'loadTomorrowOrders', 'printSummaryOnly', '/api/orders/orders_date');
    await runPage('food_supplier/order_packaging.html', 'loadOrdersByInstitution', 'printSummaryOnly', '/api/orders/orders');
})().catch(error => { console.error(error); process.exitCode = 1; });
