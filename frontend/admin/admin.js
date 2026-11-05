import { log_out_account } from '/js/common.js';

const byId = id => document.getElementById(id);
const userForm = byId('user-form');
const dishForm = byId('dish-form');
const roles = { student: 'Студент', provider: 'Поставщик', operator: 'Оператор раздачи', admin: 'Администратор' };
const limit = 25;
let offset = 0;
let total = 0;
let editingId = null;
let usersLoading = false;

function message(text, error = false) {
    byId('status').textContent = text;
    byId('status').dataset.error = String(error);
}

async function api(path, options = {}) {
    let response;
    try {
        response = await fetch(`/api${path}`, {
            credentials: 'include',
            ...options,
            headers: { 'Content-Type': 'application/json', ...options.headers },
        });
    } catch {
        throw new Error('Не удалось связаться с сервером. Проверьте соединение и повторите.');
    }
    const data = await response.json().catch(() => ({}));
    if (response.ok) return data;
    if (response.status === 401) throw new Error('Сессия истекла. Войдите снова.');
    if (response.status === 403) {
        byId('panel').hidden = true;
        throw new Error('Доступ запрещён. Требуется роль администратора.');
    }
    if (response.status === 409) throw new Error('Такая запись уже существует. Проверьте email или название.');
    if (response.status === 422) throw new Error('Проверьте поля формы: email, обязательные значения, даты и допустимые числа.');
    if (response.status === 404) throw new Error('Запись не найдена. Обновите список.');
    throw new Error(typeof data.detail === 'string' ? data.detail : `Ошибка сервера (${response.status}). Повторите попытку.`);
}

function cell(row, value) {
    const td = document.createElement('td');
    td.textContent = value == null ? '—' : String(value);
    row.append(td);
    return td;
}

function action(label, handler, danger = false) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    if (danger) button.className = 'danger';
    button.addEventListener('click', () => busy(button, handler));
    return button;
}

async function busy(button, task) {
    button.disabled = true;
    try { await task(); }
    catch (error) { message(error.message, true); }
    finally { button.disabled = false; }
}

function pagination() {
    byId('previous').disabled = usersLoading || offset === 0;
    byId('next').disabled = usersLoading || offset + limit >= total;
    byId('reload-users').disabled = usersLoading;
}

async function loadUsers() {
    usersLoading = true;
    pagination();
    try {
        const data = await api(`/admin/users?limit=${limit}&offset=${offset}`);
        total = data.total;
        if (offset > 0 && offset >= total) {
            offset = Math.max(0, Math.floor((total - 1) / limit) * limit);
            return await loadUsers();
        }
        byId('users-body').replaceChildren();
        for (const user of data.users) {
            const row = document.createElement('tr');
            cell(row, user.id);
            cell(row, user.email);
            cell(row, roles[user.role] || user.role);
            const s = user.student;
            cell(row, s ? `${s.full_name} · ${s.group_name} · ${s.study_start_year} — ${s.study_end_year}` : null);
            byId('users-body').append(row);
        }
        byId('users-empty').hidden = data.users.length !== 0;
        byId('page-info').textContent = total ? `${offset + 1}–${offset + data.users.length} из ${total}` : 'Нет записей';
    } finally {
        usersLoading = false;
        pagination();
    }
}

function resetDish() {
    editingId = null;
    dishForm.reset();
    byId('dish-form-title').textContent = 'Добавить блюдо';
    byId('save-dish').textContent = 'Добавить блюдо';
    byId('cancel-edit').hidden = true;
}

function editDish(dish) {
    editingId = dish.id;
    for (const name of ['dish_name', 'category', 'fixed_price', 'img_url', 'serving_weight_g', 'energy_kcal', 'protein_g', 'fat_g', 'carbohydrates_g']) {
        dishForm.elements[name].value = dish[name] ?? '';
    }
    byId('dish-form-title').textContent = `Редактировать блюдо №${dish.id}`;
    byId('save-dish').textContent = 'Сохранить изменения';
    byId('cancel-edit').hidden = false;
    dishForm.elements.dish_name.focus();
}

async function loadDishes() {
    const data = await api('/admin/dishes');
    byId('categories').replaceChildren(...[...new Set(data.dishes.map(dish => dish.category))].map(category => {
        const option = document.createElement('option');
        option.value = category;
        return option;
    }));
    byId('dishes-body').replaceChildren();
    for (const dish of data.dishes) {
        const row = document.createElement('tr');
        for (const name of ['id', 'dish_name', 'category', 'fixed_price', 'img_url']) cell(row, dish[name]);
        const controls = cell(row, '');
        controls.append(action('Изменить', () => editDish(dish)));
        controls.append(action('Убрать из меню', async () => {
            if (!window.confirm(`Убрать «${dish.dish_name}» из меню? История заказов сохранится.`)) return;
            await api(`/dishes/dish?dish_ids=${encodeURIComponent(dish.id)}`, { method: 'DELETE' });
            if (editingId === dish.id) resetDish();
            message('Блюдо убрано из меню.');
            await Promise.all([loadDishes(), loadSets()]);
        }, true));
        byId('dishes-body').append(row);
    }
    byId('dishes-empty').hidden = data.dishes.length !== 0;
}

const setForm = byId('set-form');
let editingSetId = null;
const weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница'];
const mealTypes = { breakfast: 'Завтрак', lunch: 'Обед', afternoon_snack: 'Полдник', dinner: 'Ужин' };

function resetSet() {
    editingSetId = null;
    setForm.reset();
    byId('set-form-title').textContent = 'Добавить комплекс';
    byId('cancel-set').hidden = true;
}

async function loadSets() {
    const [data, catalog] = await Promise.all([api('/dishes/meal-sets'), api('/admin/dishes')]);
    byId('anchor-form').elements.cycle_start_monday.value = data.cycle_start_monday || '';
    const select = setForm.elements.dish_ids;
    const selected = new Set([...select.selectedOptions].map(option => option.value));
    select.replaceChildren(...catalog.dishes.map(dish => {
        const option = document.createElement('option');
        option.value = String(dish.id);
        option.textContent = dish.dish_name;
        option.selected = selected.has(option.value);
        return option;
    }));
    byId('sets-body').replaceChildren();
    for (const meal of data.sets) {
        const row = document.createElement('tr');
        for (const value of [meal.cycle_week, weekdays[meal.weekday], mealTypes[meal.meal_type], meal.components.map(d => d.dish_name).join(', '), meal.price]) cell(row, value);
        const controls = cell(row, '');
        controls.append(action('Изменить', () => {
            editingSetId = meal.id;
            for (const name of ['cycle_week', 'weekday', 'meal_type', 'price']) setForm.elements[name].value = meal[name];
            for (const option of select.options) option.selected = meal.dish_ids.includes(Number(option.value));
            byId('set-form-title').textContent = `Редактировать комплекс №${meal.id}`;
            byId('cancel-set').hidden = false;
            setForm.elements.cycle_week.focus();
        }));
        controls.append(action('Удалить', async () => {
            if (!window.confirm('Удалить комплекс?')) return;
            await api(`/dishes/meal-sets/${encodeURIComponent(meal.id)}`, { method: 'DELETE' });
            if (editingSetId === meal.id) resetSet();
            await loadSets();
            message('Комплекс удалён.');
        }, true));
        byId('sets-body').append(row);
    }
    byId('sets-empty').hidden = data.sets.length !== 0;
}

byId('anchor-form').addEventListener('submit', event => {
    event.preventDefault();
    busy(event.currentTarget.querySelector('button'), async () => {
        await api('/dishes/cycle-anchor', { method: 'PUT', body: JSON.stringify({ cycle_start_monday: byId('anchor-form').elements.cycle_start_monday.value }) });
        message('Дата начала цикла сохранена.');
    });
});
setForm.addEventListener('submit', event => {
    event.preventDefault();
    busy(setForm.querySelector('[type="submit"]'), async () => {
        const body = { cycle_week: Number(setForm.elements.cycle_week.value), weekday: Number(setForm.elements.weekday.value), meal_type: setForm.elements.meal_type.value, price: Number(setForm.elements.price.value), dish_ids: [...setForm.elements.dish_ids.selectedOptions].map(option => Number(option.value)) };
        const path = editingSetId === null ? '/dishes/meal-sets' : `/dishes/meal-sets/${encodeURIComponent(editingSetId)}`;
        await api(path, { method: editingSetId === null ? 'POST' : 'PUT', body: JSON.stringify(body) });
        resetSet();
        await loadSets();
        message('Комплекс сохранён.');
    });
});
byId('cancel-set').addEventListener('click', resetSet);
byId('reload-sets').addEventListener('click', () => busy(byId('reload-sets'), loadSets));

function toggleStudent() {
    const enabled = userForm.elements.role.value === 'student';
    byId('student-fields').hidden = !enabled;
    byId('student-fields').disabled = !enabled;
}

userForm.elements.role.addEventListener('change', toggleStudent);
userForm.addEventListener('submit', event => {
    event.preventDefault();
    busy(userForm.querySelector('[type="submit"]'), async () => {
        const values = new FormData(userForm);
        const body = { user: { email: values.get('email').trim(), role: values.get('role') } };
        if (body.user.role === 'student') {
            if (Number(values.get('study_end_year')) < Number(values.get('study_start_year'))) throw new Error('Окончание обучения не может быть раньше начала.');
            body.student = Object.fromEntries(['full_name', 'group_name', 'study_start_year', 'study_end_year'].map(name => [name, values.get(name).trim()]));
            body.student.study_start_year = Number(body.student.study_start_year);
            body.student.study_end_year = Number(body.student.study_end_year);
            if (!body.student.full_name || !body.student.group_name) throw new Error('Заполните ФИО и группу.');
        }
        await api('/admin/user', { method: 'POST', body: JSON.stringify(body) });
        userForm.reset();
        toggleStudent();
        message('Пользователь создан. Вход доступен по коду из письма.');
        // Не сбрасываем offset: возможный параллельный просмотр списка не теряет страницу.
        await loadUsers();
    });
});

dishForm.addEventListener('submit', event => {
    event.preventDefault();
    busy(byId('save-dish'), async () => {
        const values = new FormData(dishForm);
        const data = {
            dish_name: values.get('dish_name').trim(),
            category: values.get('category'),
            fixed_price: Number(values.get('fixed_price')),
        };
        for (const name of ['serving_weight_g', 'energy_kcal', 'protein_g', 'fat_g', 'carbohydrates_g']) data[name] = Number(values.get(name));
        if (!data.dish_name) throw new Error('Введите название блюда.');
        const image = values.get('img_url').trim();
        if (image) {
            if (image.startsWith('/') || image.includes('..') || !/^[\wА-Яа-яЁё\-./]+$/.test(image)) {
                throw new Error('Укажите относительный путь изображения без начального / и без «..».');
            }
            data.img_url = image;
        }
        if (editingId === null) {
            await api('/dishes/dish', { method: 'POST', body: JSON.stringify({ items: [data] }) });
        } else {
            await api(`/dishes/dish?dish_id=${encodeURIComponent(editingId)}`, { method: 'PATCH', body: JSON.stringify(data) });
        }
        resetDish();
        message('Блюдо сохранено.');
        await Promise.all([loadDishes(), loadSets()]);
    });
});

byId('cancel-edit').addEventListener('click', resetDish);
byId('reload-users').addEventListener('click', () => busy(byId('reload-users'), loadUsers));
byId('reload-dishes').addEventListener('click', () => busy(byId('reload-dishes'), loadDishes));
for (const [id, delta] of [['previous', -limit], ['next', limit]]) {
    byId(id).addEventListener('click', async () => {
        const previousOffset = offset;
        offset = Math.max(0, offset + delta);
        try { await loadUsers(); }
        catch (error) { offset = previousOffset; pagination(); message(error.message, true); }
    });
}

log_out_account();
toggleStudent();
try {
    // Серверная проверка роли, а не доверие к localStorage.
    const me = await api('/admin/me');
    byId('institution').textContent = `${me.institution.name} · ID ${me.institution.id}`;
    byId('account').textContent = `Вы вошли как ${me.email}`;
    byId('panel').hidden = false;
    const results = await Promise.allSettled([loadUsers(), loadDishes(), loadSets()]);
    const failed = results.find(result => result.status === 'rejected');
    if (failed) throw failed.reason;
    message('Данные загружены.');
} catch (error) {
    message(error.message, true);
}
