/**
 * РџРµСЂРµРјРµРЅРЅР°СЏ, С…СЂР°РЅСЏС‰Р°СЏ С‚Р°Р№РјР°СѓС‚ РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ СЃРѕРѕР±С‰РµРЅРёР№
 */
let time_out_for_show_message = null

/**
 * РђСЃРёРЅС…СЂРѕРЅРЅР°СЏ С„СѓРЅРєС†РёСЏ РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ РІСЂРµРјРµРЅРЅС‹С… СЃРѕРѕР±С‰РµРЅРёР№ РЅР° 3 СЃРµРєСѓРЅРґС‹
 * 
 * @param {string} message - РўРµРєСЃС‚ СЃРѕРѕР±С‰РµРЅРёСЏ РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ
 * @param {string} type - РўРёРї СЃРѕРѕР±С‰РµРЅРёСЏ: + СѓСЃРїРµС… (вњ…), - РѕС€РёР±РєР° (вќЊ), '' - РїСЂРѕСЃС‚Рѕ СЃРѕРѕР±С‰РµРЅРёРµ
 * @returns {void}
 */
export function show_message(message, type = null, time = 3000){
    const container = document.querySelector('.error_message');

    if (!container) {
        console.error('show_message: СЌР»РµРјРµРЅС‚С‹ РЅРµ РЅР°Р№РґРµРЅС‹');
        return;
    }

    const textElement = container.querySelector('.error_message_text');

    if (time_out_for_show_message) {
        clearTimeout(time_out_for_show_message);
        container.style.display = 'none';
        time_out_for_show_message = null;
    }
    
    container.style.display = 'block';
    
    let icon = 'рџ›€';
    switch (type) {
        case true:
            icon = 'вњ…';
            break;
        case false:
            icon = 'вќЊ';
            break;
    }
    
    textElement.textContent = `${icon} ${message}`;
    
    time_out_for_show_message = setTimeout(() => {
        textElement.textContent = '';
        container.style.display = 'none';
        time_out_for_show_message = null;
    }, time);
}

/**
 * Р’С‹С‡РёСЃР»СЏРµС‚ РѕР±С‰СѓСЋ СЃСѓРјРјСѓ Р·Р°РєР°Р·Р° РЅР° РѕСЃРЅРѕРІРµ С†РµРЅ Р±Р»СЋРґ РІ РєРѕСЂР·РёРЅРµ
 * 
 * Р¤СѓРЅРєС†РёСЏ РїСЂРѕС…РѕРґРёС‚ РїРѕ РІСЃРµРј РєР°СЂС‚РѕС‡РєР°Рј Р±Р»СЋРґ РЅР° СЃС‚СЂР°РЅРёС†Рµ, РёР·РІР»РµРєР°РµС‚ С†РµРЅС‹
 * РёР· СЌР»РµРјРµРЅС‚РѕРІ СЃ РєР»Р°СЃСЃРѕРј 'price_dish' Рё СЃСѓРјРјРёСЂСѓРµС‚ РёС…
 * 
 * @returns {number} РћР±С‰Р°СЏ СЃСѓРјРјР° Р·Р°РєР°Р·Р°. Р’РѕР·РІСЂР°С‰Р°РµС‚ 0, РµСЃР»Рё Р±Р»СЋРґ РЅРµ РЅР°Р№РґРµРЅРѕ
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
 * РћР±РЅРѕРІР»СЏРµС‚ РѕС‚РѕР±СЂР°Р¶РµРЅРёРµ РѕР±С‰РµР№ СЃСѓРјРјС‹ Р·Р°РєР°Р·Р° РЅР° СЃС‚СЂР°РЅРёС†Рµ
 * 
 * Р¤СѓРЅРєС†РёСЏ РІС‹С‡РёСЃР»СЏРµС‚ РѕР±С‰СѓСЋ СЃСѓРјРјСѓ С‡РµСЂРµР· calculateOrderTotal() Рё РѕР±РЅРѕРІР»СЏРµС‚
 * СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓСЋС‰РёР№ DOM-СЌР»РµРјРµРЅС‚. РўР°РєР¶Рµ СѓРїСЂР°РІР»СЏРµС‚ РІРёРґРёРјРѕСЃС‚СЊСЋ СЃРµРєС†РёРё СЃ СЃСѓРјРјРѕР№ -
 * СЃРєСЂС‹РІР°РµС‚ РµС‘ РїСЂРё РЅСѓР»РµРІРѕР№ СЃСѓРјРјРµ Рё РїРѕРєР°Р·С‹РІР°РµС‚ РїСЂРё РЅР°Р»РёС‡РёРё С‚РѕРІР°СЂРѕРІ.
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
 * РЎРѕС…СЂР°РЅСЏРµС‚ РґР°РЅРЅС‹Рµ РІ С…СЂР°РЅРёР»РёС‰Рµ СЃ fallback РјРµС…Р°РЅРёР·РјРѕРј
 * 
 * Р¤СѓРЅРєС†РёСЏ РїС‹С‚Р°РµС‚СЃСЏ СЃРѕС…СЂР°РЅРёС‚СЊ РґР°РЅРЅС‹Рµ РІ localStorage РєР°Рє РѕСЃРЅРѕРІРЅРѕРµ С…СЂР°РЅРёР»РёС‰Рµ.
 * Р’ СЃР»СѓС‡Р°Рµ РѕС€РёР±РєРё (РЅР°РїСЂРёРјРµСЂ, РїСЂРё РїСЂРµРІС‹С€РµРЅРёРё РєРІРѕС‚С‹ РёР»Рё РІ РїСЂРёРІР°С‚РЅРѕРј СЂРµР¶РёРјРµ)
 * РїСЂРѕРёСЃС…РѕРґРёС‚ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРёР№ fallback РЅР° РёСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ cookies.
 * 
 * @param {string} name - РљР»СЋС‡ РґР»СЏ СЃРѕС…СЂР°РЅРµРЅРёСЏ РґР°РЅРЅС‹С…
 * @param {*} value - Р—РЅР°С‡РµРЅРёРµ РґР»СЏ СЃРѕС…СЂР°РЅРµРЅРёСЏ (Р±СѓРґРµС‚ СЃРµСЂРёР°Р»РёР·РѕРІР°РЅРѕ РІ JSON)
 * @param {number} [days=365] - РЎСЂРѕРє Р¶РёР·РЅРё РІ РґРЅСЏС…
 * @returns {boolean} true - РµСЃР»Рё СЃРѕС…СЂР°РЅРµРЅРѕ РІ localStorage, false - РµСЃР»Рё РІ cookies
 * 
 * @throws {Error} РњРѕР¶РµС‚ РІС‹Р±СЂРѕСЃРёС‚СЊ РѕС€РёР±РєСѓ РїСЂРё РїСЂРѕР±Р»РµРјР°С… СЃ СЃРµСЂРёР°Р»РёР·Р°С†РёРµР№ JSON
 */
export function setCookie(name, value, days = 365) {
    try {
        // localStorage
        console.log(`setCookie: СЃРѕС…СЂР°РЅРµРЅРёРµ РІ localStorage ${name}`, value);
        localStorage.setItem(name, JSON.stringify(value));
        return true;
    } catch (e) {
        // cookies
        console.error('setCookie: РѕС€РёР±РєР° СЃРѕС…СЂР°РЅРµРЅРёСЏ РІ localStorage', e);
        const date = new Date();
        date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
        const expires = "expires=" + date.toUTCString();
        const serializedValue = JSON.stringify(value);
        document.cookie = name + "=" + encodeURIComponent(serializedValue) + ";" + expires + ";path=/";
        return false;
    }
}

/**
 * РџРѕР»СѓС‡Р°РµС‚ Р·РЅР°С‡РµРЅРёРµ РёР· С…СЂР°РЅРёР»РёС‰Р° СЃ РїСЂРёРѕСЂРёС‚РµС‚РѕРј localStorage РЅР°Рґ cookies
 * 
 * Р¤СѓРЅРєС†РёСЏ РїС‹С‚Р°РµС‚СЃСЏ РїРѕР»СѓС‡РёС‚СЊ РґР°РЅРЅС‹Рµ СЃРЅР°С‡Р°Р»Р° РёР· localStorage РєР°Рє РѕСЃРЅРѕРІРЅРѕРіРѕ С…СЂР°РЅРёР»РёС‰Р°.
 * Р•СЃР»Рё РґР°РЅРЅС‹Рµ РЅРµ РЅР°Р№РґРµРЅС‹ РІ localStorage РёР»Рё РїСЂРѕРёР·РѕС€Р»Р° РѕС€РёР±РєР°, РѕСЃСѓС‰РµСЃС‚РІР»СЏРµС‚СЃСЏ
 * РїРѕРёСЃРє РІ cookies. Р’СЃРµ Р·РЅР°С‡РµРЅРёСЏ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РґРµСЃРµСЂРёР°Р»РёР·СѓСЋС‚СЃСЏ РёР· JSON.
 * 
 * @param {string} name - РљР»СЋС‡ РґР»СЏ РїРѕРёСЃРєР° РґР°РЅРЅС‹С…
 * @returns {*} Р—РЅР°С‡РµРЅРёРµ РґР°РЅРЅС‹С…, null РµСЃР»Рё РЅРµ РЅР°Р№РґРµРЅРѕ
 */
export function getCookie(name) {
    try {
        // localStorage
        const item = localStorage.getItem(name);
        if (item) {
            const value = JSON.parse(item);
            // console.log(`getCookie: РїРѕР»СѓС‡РµРЅРёРµ РёР· localStorage ${name}`, value);
            return value;
        }
        console.log(`getCookie: ${name} РЅРµ РЅР°Р№РґРµРЅ РІ localStorage`);
        
        // cookies
        const nameEQ = name + "=";
        const ca = document.cookie.split(';');
        for(let i = 0; i < ca.length; i++) {
            let c = ca[i];
            while (c.charAt(0) === ' ') c = c.substring(1, c.length);
            if (c.indexOf(nameEQ) === 0) {
                const value = decodeURIComponent(c.substring(nameEQ.length, c.length));
                try {
                    const parsedValue = JSON.parse(value);
                    console.log(`getCookie: РїРѕР»СѓС‡РµРЅРёРµ РёР· cookie ${name}`, parsedValue);
                    return parsedValue;
                } catch {
                    console.log(`getCookie: РїРѕР»СѓС‡РµРЅРёРµ РёР· cookie ${name} (РЅРµ JSON)`, value);
                    return value;
                }
            }
        }
        console.log(`getCookie: ${name} РЅРµ РЅР°Р№РґРµРЅ РЅРё РІ localStorage, РЅРё РІ cookies`);
        return null;
    } catch (e) {
        console.error('getCookie: РѕС€РёР±РєР° С‡С‚РµРЅРёСЏ', e);
        return null;
    }
}

export function set_font_size() {
    let font_size = getCookie('font_size');
    
    if (!font_size) {
        font_size = 16;
        setCookie('font_size', font_size, 365);
    }
    
    document.documentElement.style.fontSize = font_size + 'px';
}


export function changing_font_size(){
    const plus_font_size = document.getElementById('plus_font_size')
    const value_font_size = document.getElementById('value_font_size')
    const minus_font_size = document.getElementById('minus_font_size')

    let font_size
    const settings_cookie = getCookie('font_size')

    if (settings_cookie) {
        font_size = parseInt(settings_cookie, 10)
    }else{
        font_size = 16
        setCookie('font_size', font_size, 365)
    }

    function update_font_size(new_size){
        font_size = new_size
        setCookie('font_size', font_size, 365)
        value_font_size.textContent = font_size

        document.documentElement.style.fontSize = font_size + 'px'
    }

    if (plus_font_size){
        plus_font_size.addEventListener('click', () => {
            if (font_size < 22) {
                update_font_size(font_size + 1)
            }
            else{
                show_message('РњР°РєСЃРёРјР°Р»СЊРЅС‹Р№ СЂР°Р·РјРµСЂ: 22')
            }
        })
    }
    
    if (minus_font_size){
        minus_font_size.addEventListener('click', () => {
            if (font_size > 14) {
                update_font_size(font_size - 1)
            }else{
                show_message('РњРёРЅРёРјР°Р»СЊРЅС‹Р№ СЂР°Р·РјРµСЂ: 14')
            }
        })
    }

    if (value_font_size){
        value_font_size.textContent = font_size
    }

}

/**
 * Р¤СѓРЅРєС†РёСЏ СЃ Р±СЂР°Р±РѕС‚С‡РёРєРѕРј РєР»РёРєР° РїРѕ РёРєРѕРЅРєРµ РЅР°СЃС‚СЂРѕРµРє
 * 
 * Р’С‹РїРѕР»РЅСЏРµС‚ РІСЂР°С‰РµРЅРёРµ РёРєРѕРЅРєРё РЅР° 200 РіСЂР°РґСѓСЃРѕРІ РїСЂРё РєР°Р¶РґРѕРј РєР»РёРєРµ Рё СѓРІРµР»РёС‡РёРІР°РµС‚ СЃС‡РµС‚С‡РёРє.
 * РџСЂРё РґРѕСЃС‚РёР¶РµРЅРёРё РѕРїСЂРµРґРµР»РµРЅРЅС‹С… Р·РЅР°С‡РµРЅРёР№ СЃС‡РµС‚С‡РёРєР° РІС‹Р·С‹РІР°РµС‚ С„СѓРЅРєС†РёСЋ poor_settings
 * РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ СЃРѕРѕР±С‰РµРЅРёР№ Рё СЃРєСЂС‹С‚РёСЏ РёРєРѕРЅРєРё.
 * 
 * @listens click
 * @returns {void}
 */
export function creating_application_elements(){
    

    const menu = document.createElement('div');
    menu.id = 'menu';

    
    menu.innerHTML = `
        <div>
            <p>РЁСЂРёС„С‚</p>
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
 * Р¤СѓРЅРєС†РёСЏ РґР»СЏ РёРєРѕРЅРєРё РЅР°СЃС‚СЂРѕРµРє СЃ С„РёРґР±РµРєРѕРј РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
 * 
 * РћС‚СЃР»РµР¶РёРІР°РµС‚ РєРѕР»РёС‡РµСЃС‚РІРѕ РєР»РёРєРѕРІ Рё РїСЂРё РґРѕСЃС‚РёР¶РµРЅРёРё РѕРїСЂРµРґРµР»РµРЅРЅС‹С… РїРѕСЂРѕРіРѕРІ
 * РїРѕРєР°Р·С‹РІР°РµС‚ РїСЂРµРґСѓРїСЂРµР¶РґР°СЋС‰РёРµ СЃРѕРѕР±С‰РµРЅРёСЏ. РџРѕСЃР»Рµ 13 РєР»РёРєРѕРІ СЃРєСЂС‹РІР°РµС‚ РёРєРѕРЅРєСѓ.
 * 
 * @param {number} rotate - РўРµРєСѓС‰РµРµ Р·РЅР°С‡РµРЅРёРµ РїСЂРѕРєСЂСѓС‚РєРё
 * @returns {void}
 * 
 * @see show_message - Р¤СѓРЅРєС†РёСЏ РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ СЃРѕРѕР±С‰РµРЅРёР№
 */
function poor_settings(rotate){
    const thresholds = {
        1600: 'РҐРІР°С‚РёС‚ РјРµРЅСЏ РєСЂСѓС‚РёС‚СЊ !',
        2000: 'РџСЂРµРєСЂР°С‚РёС‚Рµ !',
        2400: 'Р§РµСЂРµР· РїР°СЂСѓ РїСЂРѕРєСЂСѓС‚РѕРІ СЏ РѕС‚РєР»СЋС‡СѓСЃСЊ !',
        2800: 'Р’СЃРµ С…РІР°С‚РёС‚ СЌС‚Рѕ С‚РµСЂРїРµС‚СЊ !'
    };

    if (rotate in thresholds) {
        show_message(thresholds[rotate]);
        
        if (rotate === 2800) {
            settings.style.display = 'none';
        }
    }
}

/**
 * Р¤СѓРЅРєС†РёСЏ РґР»СЏ СЌРєСЂР°РЅРёСЂРѕРІР°РЅРёСЏ РїРѕС‚РµРЅС†РёР°Р»СЊРЅРѕ РѕРїР°СЃРЅС‹С… РґР°РЅРЅС‹С…
 * РџСЂРµРѕР±СЂР°Р·СѓРµС‚ СЃРїРµС†РёР°Р»СЊРЅС‹Рµ СЃРёРјРІРѕР»С‹ РІ HTML-СЃСѓС‰РЅРѕСЃС‚Рё РґР»СЏ РїСЂРµРґРѕС‚РІСЂР°С‰РµРЅРёСЏ XSS-Р°С‚Р°Рє
 * 
 * @param {string|number} data - Р”Р°РЅРЅС‹Рµ РґР»СЏ СЌРєСЂР°РЅРёСЂРѕРІР°РЅРёСЏ (СЃС‚СЂРѕРєР° РёР»Рё С‡РёСЃР»Рѕ)
 * @returns {string} Р­РєСЂР°РЅРёСЂРѕРІР°РЅРЅР°СЏ СЃС‚СЂРѕРєР°
 */
export function escapeData(data) {
    if (data === null || data === undefined) {
        return '';
    }
    
    // РџСЂРµРѕР±СЂР°Р·СѓРµРј РІ СЃС‚СЂРѕРєСѓ, РµСЃР»Рё СЌС‚Рѕ РЅРµ СЃС‚СЂРѕРєР°
    const stringData = String(data);
    
    // Р—Р°РјРµРЅСЏРµРј РѕРїР°СЃРЅС‹Рµ СЃРёРјРІРѕР»С‹ РЅР° HTML-СЃСѓС‰РЅРѕСЃС‚Рё
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
        show_message('РќРµС‚ РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє СЃРµС‚Рё', '-');
        return false;
    }

    let isConnected = false;
    const maxAttempts = 3;
    let attempts = 0;

    while (!isConnected && attempts < maxAttempts) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            
            const response = await fetch(server_url, {
                method: 'HEAD',
                cache: 'no-cache',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                show_message('РРЅС‚РµСЂРЅРµС‚ РїРѕРґРєР»СЋС‡РµРЅ', '+');
                isConnected = true;
                return true;
            }
        } catch (error) {
            console.log('вќЊ РќРµС‚ РґРѕСЃС‚СѓРїР° Рє СЃРµСЂРІРµСЂСѓ:', error.message);
            attempts++;
            
            if (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 2000));
            }
        }
    }
    
    show_message('РќРµС‚ РёРЅС‚РµСЂРЅРµС‚-СЃРѕРµРґРёРЅРµРЅРёСЏ', '-');
    return false;
}


/**
* РђРєС‚РёРІРёСЂСѓРµС‚ РєРЅРѕРїРєСѓ Рё РѕР±РЅРѕРІР»СЏРµС‚ Р·Р°РіРѕР»РѕРІРѕРє РєР°С‚РµРіРѕСЂРёРё Р±Р»СЋРґР°
* 
* @param {HTMLElement} activeButton - РљРЅРѕРїРєР°, РєРѕС‚РѕСЂСѓСЋ РЅСѓР¶РЅРѕ СЃРґРµР»Р°С‚СЊ Р°РєС‚РёРІРЅРѕР№
* @param {HTMLElement[]} buttons - РњР°СЃСЃРёРІ РІСЃРµС… РєРЅРѕРїРѕРє РєР°С‚РµРіРѕСЂРёР№
* @param {HTMLElement} title_chapter - DOM-СЌР»РµРјРµРЅС‚ Р·Р°РіРѕР»РѕРІРєР° РєР°С‚РµРіРѕСЂРёРё
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
 * Р¤СѓРЅРєС†РёСЏ РґР»СЏ РїР°СЂСЃРёРЅРіР° JWT С‚РѕРєРµРЅР° (JSON Web Token) Р±РµР· РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ СЃС‚РѕСЂРѕРЅРЅРёС… Р±РёР±Р»РёРѕС‚РµРє
 * 
 * @param {string} token - JWT С‚РѕРєРµРЅ
 * @returns {Object|null} Р”РµРєРѕРґРёСЂРѕРІР°РЅРЅС‹Рµ РґР°РЅРЅС‹Рµ, null РІ СЃР»СѓС‡Р°Рµ РѕС€РёР±РєРё
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
        console.error('РћС€РёР±РєР° РїСЂРё РїР°СЂСЃРёРЅРіРµ JWT:', error);
        return null;
    }
}

// Р“СЂСѓРїРїР° РёР· 2-СѓС… РґРµРєРѕСЂР°С‚РѕСЂРѕРІ, РґР»СЏ РїСЂРѕРІРµРєРё Р°СѓС‚РµРЅС‚РёС„РёРєР°С†РёРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ

    // Р”РµРєРѕСЂР°С‚РѕСЂ РґР»СЏ Р°СЃРёРЅС…СЂРѕРЅРЅС‹С… С„СѓРЅРєС†РёР№
    export function authRequiredAsync(role) {
        return function(targetFunction) {
            return async function(...args) {

                const token = getCookie('user_token');
                if (!token) {
                    window.location.href = '../index.html';
                    return;
                }

                const user = parseJwtModern(token).role
                if (user !== role) {
                    setCookie('user_token', '', -1);
                    window.location.href = '../index.html';
                }
                return await targetFunction.apply(this, args);
            };
        };
    }

    // Р”РµРєРѕСЂР°С‚РѕСЂ СЃРёРЅС…СЂРѕРЅРЅРѕР№ С„СѓРЅРєС†РёРё
    export function authRequired(role) {
        return function(targetFunction) {
            return function(...args) {
                const token = getCookie('user_token');
                
                if (!token) {
                    window.location.href = '../index.html';
                    return;
                }

                const userRole = parseJwtModern(token).role;
                if (userRole !== role) {
                    setCookie('user_token', '', -1);
                    window.location.href = '../index.html';
                    return;
                }
                
                return targetFunction.apply(this, args);
            };
        };
    }

/**
 * Р¤СѓРЅРєС†РёСЏ РґР»СЏ РІС‹С…РѕРґР° РёР· Р°РєРєР°СѓРЅС‚Р°
 */
export function log_out_account() {
    const log_out_btn = document.getElementById('log_out')
    if (log_out_btn){
        log_out_btn.addEventListener('click', () => {
            try {
                const response = fetch(`/api/auth/logout`, {
                    method: 'POST',
                    credentials: 'include' // Р”Р»СЏ СЂР°Р±РѕС‚С‹ СЃ РєСѓРєРё РЅР° СЃС‚РѕСЂРѕРЅРµ СЃРµСЂРІРµСЂР° С‡РµСЂРµР· FastAip
                });

                if (!response.ok) {throw new Error(`HTTP error!`);}
                
            } catch (error) {
                console.error(error);
                show_message(error, '-')
            }
            setCookie('user_token', '', -1);
            window.location.href = '../index.html';
        })
    }
}

/**
 * Р¤СѓРЅРєС†РёСЏ РґР»СЏ РїСЂРѕРІРµСЂРєРё РїСЂР°РІ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Рё РµРіРѕ РјР°СЂС€СЂСѓС‚РёР·Р°С†РёРё РЅР° СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓСЋС‰РёРµ С„РѕСЂРјС‹
 */
export function rights_verification(data_access_token){
    const user_role = parseJwtModern(data_access_token).role

    if (user_role === 'student') {
        window.location.href = './client/dishes.html';
    }else if (user_role === 'operator'){
        window.location.href = './distribution_operator/order_search.html';
    }else if (user_role === 'provider'){
        window.location.href = './food_supplier/meal_planning.html';
    }else{
        window.location.href = './index.html';
        throw new error('РћС€РёР±РєР° РІР°Р»РёРґР°С†РёРё')
    }
}

export function date_verification(selected_date_value){
    const now = new Date()
    const selectedDate = new Date(selected_date_value);

    if (!date_dishes.value) {
        throw new Error('РћС€РёР±РєР° РґР°С‚С‹')
    }
    if (selectedDate.getTime() > now.getTime() + 604800000){
        throw new Error('РџР»Р°РЅРёСЂРѕРІР°РЅРёРµ РґР°Р»СЊС€Рµ, С‡РµРј 1 РЅРµРґРµР»СЏ РЅРµРґРѕСЃС‚СѓРїРЅРѕ')
    }

    return selectedDate.toISOString().split('T')[0];
}

export function create_message(){
    document.body.innerHTML += `
        <div class="error_message">
            <p class="error_message_text"></p>
        </div>
    `
}

export function check_student_id(value){
        if (!value || value > 100000) {
            throw new Error('РћС€РёР±РєР° ID')
        }

        return value
    }
