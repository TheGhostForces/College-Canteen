// Файл meal_mini_cards.js служит для отрисовки мелких карточек блюд на странице.

class SmallCardDishClass {
    constructor(data, type, dishesContainer) {
        this.data = data;
        this.type = type
        this.dishesContainer = dishesContainer

        console.log(this.data)
    }

    init() {
        if(this.type === 'mini_card_with_let_amount'){
            this.element = this.createCardWithLetQuantity()
        }
        else if(this.type === 'default_const_amount_from_server'){
            this.element = this.createCardWithConstQuantity()
        }
        this.element.dataset.dishId = this.data.dish_id
        return this.element
    }

    
    createCardWithLetQuantity() {
        const div = document.createElement('div');
        div.className = 'mini_card';
        div.innerHTML = `
            <p>${this.data.dish_name}</p>
            <input type="number" value="${this.data.quantity || 0}">
        `;
        return div;
    }

    createCardWithConstQuantity(){
        const div = document.createElement('div');
        div.className = 'mini_card';
        div.innerHTML = `
            <p>${this.data.dish_name}</p>
            <p>${this.data.quantity}</p>

        `;
        return div;
    }
}


export function createSmallCards(dishesContainer, data, type) {
    if (!data || !dishesContainer) {
        console.error('Ошибка в передаче данных для функции createSmallCards')
        return
    }

    dishesContainer.innerHTML = ``;

    data.forEach(element => {
        const cardGenerator = new SmallCardDishClass(element, type, dishesContainer);
        const cardElement = cardGenerator.init();
        dishesContainer.appendChild(cardElement);
    })
}

// Добавьте эти стили в ваш CSS файл или вставьте через тег <style>
const styles = `
<style>
.mini_card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 8px 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
    margin-bottom: 8px;
}

.mini_card p {
    flex: 1;
    margin: 0;
    padding: 0;
    width: 50%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.mini_card p:first-child {
    text-align: left;
}

.mini_card p:last-child {
    text-align: right;
}

.mini_card input {
    width: 50%;
    padding: 4px 8px;
    box-sizing: border-box;
}
</style>
`;

// Если нужно автоматически добавить стили при импорте модуля
if (typeof document !== 'undefined') {
    const styleElement = document.createElement('style');
    styleElement.textContent = styles.replace('<style>', '').replace('</style>', '');
    document.head.appendChild(styleElement);
}