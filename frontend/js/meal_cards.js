import { updateOrderTotalPrice, escapeData } from './export.js'

class CardDishClass {
    /**
     * Класс для создания карточки блюда с различными типами отображения
     * @param {Object} data - Данные блюда
     * @param {string} type - Тип контейнера ('dishes_container_const_amount', 'dishes_container_let_amount' или другой)
     
     */
    constructor(data, type) {
        this.data = data;
        this.type = type;
    }

    /**
     * Инициализирует создание карточки блюда
     * @returns {HTMLElement} DOM-элемент карточки
     */
    init() {
        this.card = this.createCard();
        this.addCounterListeners(this.card);
        return this.card;
    }

    /**
     * Создает DOM-элемент карточки блюда
     * @returns {HTMLElement} DOM-элемент карточки
     */
    createCard() {
        const card = document.createElement('div');
        card.className = 'card_dish';

        card.dataset.dishId = this.data.dish_id
        
        if (this.type == 'dishes_container_const_amount') {
            card.innerHTML = this.createConstantAmountHTML()
        } else if (this.type == 'dishes_container_let_amount') {
            card.innerHTML = this.createEditableAmountHTML()
        }else if (this.type == 'dish_card_in_basket') {
            card.innerHTML = this.DishCardInBascet()
        }
        
        return card;
    }

    /**
     * Карточка, которая позволяет добавлять блюда в корзину
     * @returns {string} HTML-разметка карточки
     * @private
     */

    createEditableAmountHTML() {
        return `
        <button class="add_basket">🛒</button>
        <div class="card_dish_image">
            <img src="https://voscollege.ru/img/${escapeData(this.data.img_url)}" alt="${escapeData(this.data.dish_name)}">
        </div>
        <div class="card_dish_info">
            <h2>${escapeData(this.data.dish_name)}</h2>
            <div class="card_dish_info_text">
                <p>Колич.:<br>${escapeData(this.data.quantity)} шт.</p>
                <p>Цена:<br><span class="price_dish">${escapeData(Number(this.data.fixed_price))}</span> р.</p>
            </div>
            <div class="counter_dishes">
                <button class="counter_minus">-</button>
                <p class="counter_value">1</p>
                <button class="counter_plus">+</button>
            </div>
        </div>
        `;
    }

    /**
     * Карточка, находящаяся в корзине
     * @returns {string} HTML-разметка карточки
     * @private
     */
    DishCardInBascet() {

        const initialQuantity = this.data.quantity || 1;
        const totalPrice = (this.data.fixed_price * initialQuantity).toFixed(2);

        return `
        <button class="dell_basket">-</button>
        <div class="card_dish_image">
            <img src="https://voscollege.ru/img/${escapeData(this.data.img_url)}" alt="${escapeData(this.data.dish_name)}">
        </div>
        <div class="card_dish_info">
            <h2>${escapeData(this.data.dish_name)}</h2>
            <div class="card_dish_info_text">
                <p>Колич.:<br>${escapeData(this.data.quantity)} шт.</p>
                <p>Цена:<br><span class="price_dish">${escapeData(Number(totalPrice))}</span> р.</p>
            </div>
            <div class="counter_dishes">
                <button class="counter_minus">-</button>
                <p class="counter_value">${escapeData(initialQuantity)}</p>
                <button class="counter_plus">+</button>
            </div>
        </div>
        `;
    }

    // /**
    //  * Создает HTML для карточки с постоянным количеством для оформления заказа
    //  * @returns {string} HTML-разметка карточки
    //  * @private
    //  */
    createConstantAmountHTML() {
        const initialQuantity = this.data.quantity || 1;
        const totalPrice = (this.data.fixed_price * initialQuantity).toFixed(2);

        return `
        <div class="card_dish_image">
            <img src="https://voscollege.ru/img/${escapeData(this.data.img_url)}" alt="${escapeData(this.data.dish_name)}">
        </div>
        <div class="card_dish_info">
            <h2>${escapeData(this.data.dish_name)}</h2>
            <div class="card_dish_info_text">
                <p>Ост. :<br>${escapeData(initialQuantity)} шт.</p>
                <p>Цена:<br><span class="price_dish">${totalPrice}</span> р.</p>
            </div>
            <div class="counter_dishes constant_amount">
                <p class="counter_value">${initialQuantity}</p>
            </div>
        </div>
        `;
    }

    /**
     * Обновляет отображение общей цены для карточки блюда
     */
    updateTotalPrice() {
        if (!this.card) return;
        
        const counterValue = this.card.querySelector('.counter_value');
        const priceElement = this.card.querySelector('.price_dish');
        if (counterValue && priceElement) {
            const price = this.data.fixed_price || this.data.price;
            priceElement.textContent = (price * parseInt(counterValue.textContent)).toFixed(2);
            updateOrderTotalPrice();
        }
    }

    /**
     * Добавляет обработчики событий для элементов карточки
     * @param {HTMLElement} card - DOM-элемент карточки
     */
    addCounterListeners(card) {
        this.card = card;
        
        const minusBtn = card.querySelector('.counter_minus');
        const plusBtn = card.querySelector('.counter_plus');
        const addButon = card.querySelector('.add_basket');
        const dellBtn = card.querySelector('.dell_basket');
        const counterValue = card.querySelector('.counter_value');

        if (minusBtn) {
            minusBtn.addEventListener('click', () => {
                let value = parseInt(counterValue.textContent);

                if (value > 1) {
                    value--;
                    counterValue.textContent = value;

                    this.updateTotalPrice();
                }
            });
        }

        if (plusBtn) {
            plusBtn.addEventListener('click', () => {
                let value = parseInt(counterValue.textContent);
                value++;
                counterValue.textContent = value;
                this.updateTotalPrice();
            });
        }
    }
}

/**
 * Observer для анимированного появления карточек блюд при скролле
 * 
 * Наблюдает за появлением элементов в области видимости и добавляет анимацию
 * с задержкой для каждого элемента, создавая эффект последовательного появления.
 * 
 * @type {IntersectionObserver}
 */
const observer_one = new IntersectionObserver((entries) => {
    entries.forEach((entry, index) => {
        if (entry.isIntersecting) {
            setTimeout(() => {
                entry.target.classList.add('animate_card_dish');
            }, index * 110);
        }
    });
}, {
    threshold: 0.1,
    rootMargin: '0px 0px -20px 0px'
});

/**
 * Обновляет контейнер с карточками блюд, отрисовывая новые данные и подключая анимацию
 * 
 * Функция полностью очищает контейнер и заполняет его новыми карточками блюд на основе переданных данных.
 * После отрисовки подключает IntersectionObserver для анимированного появления карточек при скролле.
 * 
 * @param {HTMLElement} dishesContainer - DOM-элемент контейнера для карточек блюд
 * @param {Object[]} data_dish - Массив данных для карточек блюд
 * @param {string} type - Тип карточки блюда ('dishes_container_const_amount' или 'dishes_container_let_amount')
 * @returns {void}
 */
/**
 * Обновляет контейнер с карточками блюд, отрисовывая новые данные и подключая анимацию
 * 
 * Функция полностью очищает контейнер и заполняет его новыми карточками блюд на основе переданных данных.
 * После отрисовки подключает IntersectionObserver для анимированного появления карточек при скролле.
 * 
 * @param {HTMLElement} dishesContainer - DOM-элемент контейнера для карточек блюд
 * @param {Object|Array} data_dish - Данные для карточек блюд (объект с массивами или простой массив)
 * @param {string} type - Тип карточки блюда ('dishes_container_const_amount' или 'dishes_container_let_amount')
 * @returns {void}
 */
/**
 * Обновляет контейнер с карточками блюд на основе данных со сервера
 * 
 * @param {HTMLElement} dishesContainer - DOM-элемент контейнера для карточек блюд
 * @param {Object} data_dish - Объект-словарь с массивами блюд (пример: {ORD-1000004: Array(3)})
 * @param {string} type - Тип карточки блюда ('dishes_container_const_amount', 'dishes_container_let_amount' или 'dish_card_in_basket')
 * @returns {void}
 */
export function updating_dish_card(dishesContainer, data_dish, type = 'dishes_container_let_amount') {
    if (!(dishesContainer instanceof HTMLElement) || !data_dish || typeof data_dish !== 'object') {
        console.error('Ошибка в updating_dish_card: неверные параметры', dishesContainer, data_dish);
        return;
    }

    console.log(data_dish)

    dishesContainer.innerHTML = '';

    Object.values(data_dish).flat().forEach(dishData => {
        const cardDish = new CardDishClass(dishData, type);
        dishesContainer.appendChild(cardDish.init());
    });
    
    // Подключаем анимацию для всех карточек
    // dishesContainer.querySelectorAll('.card_dish').forEach(card => {
    //     observer_one.observe(card);
    // });
}
