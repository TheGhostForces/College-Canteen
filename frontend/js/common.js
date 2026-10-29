/**
 * Переменная, хранящая таймаут для отображения сообщений
 */
let time_out_for_show_message = null

/**
 * Асинхронная функция для отображения временных сообщений на 3 секунды
 * 
 * @param {string} message - Текст сообщения для отображения
 * @param {string} type - Тип сообщения: + успех (✅), - ошибка (❌), '' - просто сообщение
 * @returns {void}
 */
export function show_message(message, type = null, time = 3000){
    const container = document.querySelector('.error_message');

    if (!container) {
        console.error('show_message: элементы не найдены');
        return;
    }

    const textElement = container.querySelector('.error_message_text');

    if (time_out_for_show_message) {
        clearTimeout(time_out_for_show_message);
        container.style.display = 'none';
        time_out_for_show_message = null;
    }
    
    container.style.display = 'block';
    
    // вызывающий код передаёт и true/false, и '+'/'-': раньше '+'/'-' не распознавались
    let icon = '🛈';
    if (type === true || type === '+') {
        icon = '✅';
    } else if (type === false || type === '-') {
        icon = '❌';
    }

    const text = message instanceof Error ? message.message : String(message);
    textElement.textContent = `${icon} ${text}`;
    
    time_out_for_show_message = setTimeout(() => {
        textElement.textContent = '';
        container.style.display = 'none';
        time_out_for_show_message = null;
    }, time);
}

/**
 * Вычисляет общую сумму заказа на основе цен блюд в корзине
 * 
 * Функция проходит по всем карточкам блюд на странице, извлекает цены
 * из элементов с классом 'price_dish' и суммирует их
 * 
 * @returns {number} Общая сумма заказа. Возвращает 0, если блюд не найдено
 */
function calculateOrderTotal(parent) {
    let parent_element = parent ? parent : document
    const dishCards = parent_element.querySelectorAll(`.card_dish`);

    let total = 0;
    
    if (dishCards){
        dishCards.forEach(card => {
            const priceElement = card.querySelector('.price_dish');
            if (priceElement) {
                const price = parseFloat(priceElement.textContent);
                if (!isNaN(price)) {
                    total += price;
                }
            }
        });
    }
    
    return total;
}

/**
 * Обновляет отображение общей суммы заказа на странице
 * 
 * Функция вычисляет общую сумму через calculateOrderTotal() и обновляет
 * соответствующий DOM-элемент. Также управляет видимостью секции с суммой -
 * скрывает её при нулевой сумме и показывает при наличии товаров.
 * 
 * @returns {void}
 */
export function updateOrderTotalPrice(parent = null) {
    const total = calculateOrderTotal(parent);
    const totalPriceSection = document.getElementById('total_price_section');
    const totalOrderPrice = document.getElementById('total_order_price');
    
    if (totalPriceSection && totalOrderPrice) {
        totalOrderPrice.textContent = total.toFixed(2);
        totalPriceSection.style.display = total > 0 ? 'block' : 'none';
        return total
    }
}

/**
 * Сохраняет данные в хранилище с fallback механизмом
 * 
 * Функция пытается сохранить данные в localStorage как основное хранилище.
 * В случае ошибки (например, при превышении квоты или в приватном режиме)
 * происходит автоматический fallback на использование cookies.
 * 
 * @param {string} name - Ключ для сохранения данных
 * @param {*} value - Значение для сохранения (будет сериализовано в JSON)
 * @param {number} [days=365] - Срок жизни в днях
 * @returns {boolean} true - если сохранено в localStorage, false - если в cookies
 * 
 * @throws {Error} Может выбросить ошибку при проблемах с сериализацией JSON
 */
export function setStored(name, value, days = 365) {
    // days <= 0 - удалить значение
    if (days <= 0) {
        removeStored(name);
        return true;
    }
    try {
        localStorage.setItem(name, JSON.stringify(value));
        // раньше срок жизни (days) в localStorage игнорировался и данные жили вечно
        localStorage.setItem(name + '__exp', String(Date.now() + days * 24 * 60 * 60 * 1000));
        return true;
    } catch (e) {
        console.error('setStored: ошибка сохранения в localStorage', e);
        const date = new Date();
        date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
        document.cookie = name + "=" + encodeURIComponent(JSON.stringify(value)) +
            ";expires=" + date.toUTCString() + ";path=/;SameSite=Lax";
        return false;
    }
}

export function removeStored(name) {
    try {
        localStorage.removeItem(name);
        localStorage.removeItem(name + '__exp');
    } catch (e) { /* localStorage недоступен */ }
    document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/";
}

/**
 * Получает значение из localStorage (приоритет) или cookie. Значения десериализуются из JSON.
 * Не логирует значения: раньше в консоль писались токен и данные пользователя.
 */
export function getStored(name) {
    try {
        const item = localStorage.getItem(name);
        if (item) {
            const exp = Number(localStorage.getItem(name + '__exp'));
            if (exp && exp < Date.now()) {
                removeStored(name);
                return null;
            }
            return JSON.parse(item);
        }

        const nameEQ = name + "=";
        const ca = document.cookie.split(';');
        for (let i = 0; i < ca.length; i++) {
            let c = ca[i];
            while (c.charAt(0) === ' ') c = c.substring(1, c.length);
            if (c.indexOf(nameEQ) === 0) {
                const value = decodeURIComponent(c.substring(nameEQ.length, c.length));
                try {
                    return JSON.parse(value);
                } catch {
                    return value;
                }
            }
        }
        return null;
    } catch (e) {
        console.error('getStored: ошибка чтения', e);
        return null;
    }
}

export function set_font_size() {
    let font_size = getStored('font_size');
    
    if (!font_size) {
        font_size = 16;
        setStored('font_size', font_size, 365);
    }
    
    document.documentElement.style.fontSize = font_size + 'px';
}


export function changing_font_size(){
    const plus_font_size = document.getElementById('plus_font_size')
    const value_font_size = document.getElementById('value_font_size')
    const minus_font_size = document.getElementById('minus_font_size')

    let font_size
    const settings_cookie = getStored('font_size')

    if (settings_cookie) {
        font_size = parseInt(settings_cookie, 10)
    }else{
        font_size = 16
        setStored('font_size', font_size, 365)
    }

    function update_font_size(new_size){
        font_size = new_size
        setStored('font_size', font_size, 365)
        value_font_size.textContent = font_size

        document.documentElement.style.fontSize = font_size + 'px'
    }

    if (plus_font_size){
        plus_font_size.addEventListener('click', () => {
            if (font_size < 22) {
                update_font_size(font_size + 1)
            }
            else{
                show_message('Максимальный размер: 22')
            }
        })
    }
    
    if (minus_font_size){
        minus_font_size.addEventListener('click', () => {
            if (font_size > 14) {
                update_font_size(font_size - 1)
            }else{
                show_message('Минимальный размер: 14')
            }
        })
    }

    if (value_font_size){
        value_font_size.textContent = font_size
    }

}

/**
 * Функция с бработчиком клика по иконке настроек
 * 
 * Выполняет вращение иконки на 200 градусов при каждом клике и увеличивает счетчик.
 * При достижении определенных значений счетчика вызывает функцию poor_settings
 * для отображения сообщений и скрытия иконки.
 * 
 * @listens click
 * @returns {void}
 */
export function creating_application_elements(){
    

    const menu = document.createElement('div');
    menu.id = 'menu';

    
    menu.innerHTML = `
        <div>
            <p>Шрифт</p>
            <div id="container_font_size">
                <button id="plus_font_size">+</button>
                <p id="value_font_size"></p>
                <button id="minus_font_size">-</button>
            </div>
        </div>
        <a href="../index.html" id="log_out"><img src="../png/exit.png" alt=""></a>
    `
    document.body.insertAdjacentHTML('beforeend', `
    <div class="error_message">
        <p class="error_message_text"></p>
    </div>
    `);

    document.body.appendChild(menu);
    log_out_account()
    changing_font_size()

    let rotate = 0;
    const settings = document.getElementById('settings');

    settings.addEventListener('click', () => {
        rotate += 200;
        
        settings.style.transition = 'transform 0.5s ease';
        settings.style.transform = `rotate(${rotate}deg)`;
    
        poor_settings(rotate)
    });
}

/**
 * Функция для иконки настроек с фидбеком для пользователя
 * 
 * Отслеживает количество кликов и при достижении определенных порогов
 * показывает предупреждающие сообщения. После 13 кликов скрывает иконку.
 * 
 * @param {number} rotate - Текущее значение прокрутки
 * @returns {void}
 * 
 * @see show_message - Функция для отображения сообщений
 */
function poor_settings(rotate){
    const thresholds = {
        1600: 'Хватит меня крутить !',
        2000: 'Прекратите !',
        2400: 'Через пару прокрутов я отключусь !',
        2800: 'Все хватит это терпеть !'
    };

    if (rotate in thresholds) {
        show_message(thresholds[rotate]);
        
        if (rotate === 2800) {
            settings.style.display = 'none';
        }
    }
}

/**
 * Функция для экранирования потенциально опасных данных
 * Преобразует специальные символы в HTML-сущности для предотвращения XSS-атак
 * 
 * @param {string|number} data - Данные для экранирования (строка или число)
 * @returns {string} Экранированная строка
 */
export function escapeData(data) {
    if (data === null || data === undefined) {
        return '';
    }
    
    // Преобразуем в строку, если это не строка
    const stringData = String(data);
    
    // Заменяем опасные символы на HTML-сущности
    return stringData
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;')
        .replace(/\//g, '&#x2F;');
}

export async function check_internet_connection() {
    if (!navigator.onLine) {
        show_message('Нет подключения к сети', '-');
        return false;
    }

    let isConnected = false;
    const maxAttempts = 3;
    let attempts = 0;

    while (!isConnected && attempts < maxAttempts) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            
            const response = await fetch(window.location.origin + '/', {
                method: 'HEAD',
                cache: 'no-cache',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                show_message('Интернет подключен', '+');
                isConnected = true;
                return true;
            }
        } catch (error) {
            console.log('❌ Нет доступа к серверу:', error.message);
            attempts++;
            
            if (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 2000));
            }
        }
    }
    
    show_message('Нет интернет-соединения', '-');
    return false;
}


/**
* Активирует кнопку и обновляет заголовок категории блюда
* 
* @param {HTMLElement} activeButton - Кнопка, которую нужно сделать активной
* @param {HTMLElement[]} buttons - Массив всех кнопок категорий
* @param {HTMLElement} title_chapter - DOM-элемент заголовка категории
* @returns {void}
* 
*/
export function activateButton(activeButton, buttons, title_chapter) {
    buttons.forEach(button => {
        if (button === activeButton) {
            button.classList.add('btn_underline');
            title_chapter.textContent = button.textContent;
        } else {
            button.classList.remove('btn_underline');
        }
    });
}

/**
 * Функция для парсинга JWT токена (JSON Web Token) без использования сторонних библиотек
 * 
 * @param {string} token - JWT токен
 * @returns {Object|null} Декодированные данные, null в случае ошибки
 */
export function parseJwtModern(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        
        const text = new TextDecoder().decode(bytes);
        return JSON.parse(text);
    } catch (error) {
        console.error('Ошибка при парсинге JWT:', error);
        return null;
    }
}

// Группа из 2-ух декораторов, для провеки аутентификации пользователя

    // Декоратор для асинхронных функций
    export function authRequiredAsync(role) {
        return function(targetFunction) {
            return async function(...args) {

                const userRole = getStored('user_role');
                if (!userRole || userRole !== role) {
                    clear_session();
                    window.location.href = '/index.html';
                    return;
                }
                return await targetFunction.apply(this, args);
            };
        };
    }

    // Декоратор синхронной функции
    export function authRequired(role) {
        return function(targetFunction) {
            return function(...args) {
                const userRole = getStored('user_role');
                if (!userRole || userRole !== role) {
                    clear_session();
                    window.location.href = '/index.html';
                    return;
                }

                return targetFunction.apply(this, args);
            };
        };
    }

/**
 * Функция для выхода из аккаунта
 */
export function log_out_account() {
    const log_out_btn = document.getElementById('log_out')
    if (log_out_btn){
        log_out_btn.addEventListener('click', async (e) => {
            e.preventDefault()
            // раньше fetch не ожидался: response.ok всегда был undefined, а запрос обрывался переходом
            try {
                const response = await fetch(`/api/auth/logout`, {
                    method: 'POST',
                    credentials: 'include'
                });
                if (!response.ok) {throw new Error(`HTTP error: ${response.status}`);}
            } catch (error) {
                console.error(error);
            }
            clear_session();
            window.location.href = '/index.html';
        })
    }
}

/**
 * Локальная часть сессии. Сам токен лежит в HttpOnly-cookie, JS его не видит;
 * здесь только роль для маршрутизации (права всё равно проверяет сервер).
 */
export function clear_session() {
    removeStored('user_role');
    removeStored('user_token'); // наследие: раньше тут хранился JWT
}

/**
 * Функция для проверки прав пользователя и его маршрутизации на соответствующие формы
 */
export function rights_verification(user_role){
    if (user_role === 'student') {
        window.location.href = '/client/dishes.html';
    }else if (user_role === 'operator'){
        window.location.href = '/distribution_operator/order_search.html';
    }else if (user_role === 'admin'){
        window.location.href = '/admin/index.html';
    }else if (user_role === 'provider'){
        window.location.href = '/food_supplier/meal_planning.html';
    }else{
        clear_session();
        window.location.href = '/index.html';
        throw new Error('Ошибка валидации')
    }
}

export function date_verification(selected_date_value){
    const now = new Date()
    const selectedDate = new Date(selected_date_value);

    if (!selected_date_value || isNaN(selectedDate.getTime())) {
        throw new Error('Ошибка даты')
    }
    if (selectedDate.getTime() > now.getTime() + 604800000){
        throw new Error('Планирование дальше, чем 1 неделя недоступно')
    }

    return selectedDate.toISOString().split('T')[0];
}

export function create_message(){
    // innerHTML += пересоздавал весь body и убивал навешанные обработчики
    document.body.insertAdjacentHTML('beforeend', `
        <div class="error_message">
            <p class="error_message_text"></p>
        </div>
    `)
}

export function check_student_id(value){
        if (!value || value > 100000) {
            throw new Error('Ошибка ID')
        }

        return value
    }

/**
 * Если сессия истекла (401 от /api/ вне /api/auth/), сбрасываем локальную сессию и ведём на вход.
 * Подключается один раз при импорте модуля.
 */
(function installAuthGuard() {
    if (window.__authGuardInstalled) return;
    window.__authGuardInstalled = true;
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
        const response = await originalFetch(...args);
        try {
            const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
            if (response.status === 401 && url.startsWith('/api/') && !url.startsWith('/api/auth/')) {
                clear_session();
                window.location.href = '/index.html';
            }
        } catch (e) { /* не мешаем основному потоку */ }
        return response;
    };
})();
