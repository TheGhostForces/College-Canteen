import { escapeData } from './common.js'

class DropDownMenuCardClass{
    constructor(key, value) {
        this.key = key;
        this.value = value;
    }
    
    init() {
        this.card = this.createCard();
        return this.card;
    }

    createCard() {
        if (!this.value || !Array.isArray(this.value) || this.value.length === 0) {
            return `
            <div class="student_order">
                <div class="title_student_order">
                    <p>${escapeData(this.key)}</p>
                    <button class="btn_for_records">↓</button>
                </div>
                <div class="dishes_of_student_order">
                    <div><p>Нет данных</p></div>
                </div>
            </div>
            `
        }

        return `
        <div class="student_order">
            <div class="title_student_order">
                <p>${escapeData(this.key)}</p>
                <button class="btn_for_records">↓</button>
            </div>
            <div class="dishes_of_student_order" style="display: none;">
                ${
                    this.value.map(item => {
                        if (!item || !item.dish_name) {
                            return null;
                        }
                        return `<div><p>${escapeData(item.dish_name)}</p><p>${item.quantity || 0}</p><p>${item.fixed_price || 0} руб.</p></div>`
                    }).filter(item => item !== null).join('')
                }
            </div>
        </div>
        `
    }
}

export function createDropDownMenuCard(data, dishesContainer) {
    dishesContainer.innerHTML = ``

    Object.entries(data).forEach(([key, value]) => {
        const cards = new DropDownMenuCardClass(key, value);
        dishesContainer.innerHTML += cards.init()
    })

    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn_for_records')) {
            const dish_info = e.target.parentElement.nextElementSibling
            if (dish_info.style.display == 'block') {
                e.target.parentElement.firstElementChild.style.color = 'red'
                dish_info.style.display = 'none'
                return
            }
            dish_info.style.display = 'block'
        }
    })
}