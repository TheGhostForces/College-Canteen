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
            cell(row, s ? `${s.full_name} · ${s.group_name} · ${s.date_start} — ${s.date_end}` : null);
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
    for (const name of ['dish_name', 'category', 'fixed_price', 'img_url']) {
        dishForm.elements[name].value = dish[name] ?? '';
    }
    byId('dish-form-title').textContent = `Редактировать блюдо №${dish.id}`;
    byId('save-dish').textContent = 'Сохранить изменения';
    byId('cancel-edit').hidden = false;
    dishForm.elements.dish_name.focus();
}

async function loadDishes() {
    const data = await api('/admin/dishes');
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
            await loadDishes();
        }, true));
        byId('dishes-body').append(row);
    }
    byId('dishes-empty').hidden = data.dishes.length !== 0;
}

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
            if (values.get('date_end') < values.get('date_start')) throw new Error('Окончание обучения не может быть раньше начала.');
            body.student = Object.fromEntries(['full_name', 'group_name', 'date_start', 'date_end'].map(name => [name, values.get(name).trim()]));
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
        await loadDishes();
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
    const results = await Promise.allSettled([loadUsers(), loadDishes()]);
    const failed = results.find(result => result.status === 'rejected');
    if (failed) throw failed.reason;
    message('Данные загружены.');
} catch (error) {
    message(error.message, true);
}
