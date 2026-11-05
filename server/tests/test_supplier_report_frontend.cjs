const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../../frontend/food_supplier/meal_planning.html'), 'utf8');
const script = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/^\s*import .*$/m, '');
const listeners = {};
const elements = {
    selection: { value: '1', add() {}, addEventListener(event, callback) { listeners.selectionChange = callback; } },
    date_dishes: { value: '2026-11-05', addEventListener(event, callback) { listeners.dateChange = callback; } },
    container_with_data_from_api: { innerHTML: '' },
    find_dishes: { addEventListener(event, callback) { listeners[event] = callback; } },
};
const requests = [];
const messages = [];
const context = {
    document: { getElementById: id => elements[id], addEventListener() {} },
    URLSearchParams,
    fetch: url => new Promise((resolve, reject) => requests.push({ url, resolve, reject })),
    show_message: message => messages.push(message),
    authRequiredAsync: () => fn => fn,
    escapeData: String,
    creating_application_elements() {},
};
vm.runInNewContext(script, context);
const response = name => ({ ok: true, json: async () => ({ sets: [], buffet: [{ dish_name: name, quantity: 1 }] }) });

(async () => {
    const first = listeners.click();
    elements.selection.value = '2';
    const second = listeners.click();
    requests[1].resolve(response('newer'));
    await second;
    requests[0].resolve(response('older'));
    await first;
    assert.match(elements.container_with_data_from_api.innerHTML, /newer/);
    assert.doesNotMatch(elements.container_with_data_from_api.innerHTML, /older/);

    const third = listeners.click();
    elements.date_dishes.value = '2026-11-06';
    const fourth = listeners.click();
    requests[3].resolve(response('latest'));
    await fourth;
    requests[2].reject(new Error('old request failed'));
    await third;
    assert.match(elements.container_with_data_from_api.innerHTML, /latest/);
    assert.deepEqual(messages, []);

    const fifth = listeners.click();
    elements.selection.value = '3';
    listeners.selectionChange();
    requests[4].resolve(response('wrong institution'));
    await fifth;
    assert.equal(elements.container_with_data_from_api.innerHTML, '');
    process.stdout.write('Supplier report concurrency checks passed\n');
})().catch(error => { console.error(error); process.exitCode = 1; });
