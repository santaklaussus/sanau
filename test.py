from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from dotenv import load_dotenv
import os
import json
import re
import threading
import schedule
import time
import io
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from pypdf import PdfReader 
import asyncio
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from datetime import datetime
import os
import time
import requests
import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
# Загрузка переменных окружения
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_API")
prodavec_bin = os.getenv("prodavec_bin")
# Пути к данным
DATA_PATH = "data"
USERS_FILE = "users.json"
ADMIN_ID = "1830637104"  # заменишь на свой ID

# Состояния FSM
(
    STATE_KEY,
    STATE_REGISTER_PHONE, STATE_REGISTER_PASSWORD,
    STATE_REGISTER_NAME, STATE_REGISTER_SURNAME,
    STATE_LOGIN_PHONE, STATE_LOGIN_PASSWORD
) = (
    "state",
    "register_phone", "register_password",
    "register_name", "register_surname",
    "login_phone", "login_password"
)
# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Утилиты
KASPI_API_TOKEN = os.getenv("KASPI_API")
MERCHANT_ID = os.getenv("MERCHANT_ID")
POLL_INTERVAL = 300





def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def reset_subscription_if_expired(user):
    end = user.get("subscription_end_date")
    if end and datetime.fromisoformat(end) <= datetime.now():
        user["paid_current_month"] = False
        user["subscription_end_date"] = None

def check_end_date():
    users = load_users()
    for user in users:
        end_date_str = user.get("subscription_end_date")  # формат типа "2025-08-22 16:00"
        end_date = datetime.fromisoformat(end_date_str)

        now = datetime.now()

        if now >= end_date:
            print("Срок истёк!")
            user["paid_current_month"] = False
            user["class"] = None
            save_users(users)
        else:
            print("Ещё не истёк, осталось:", end_date - now)
    

# Главное меню





def main_menu(update,context):
    phone = context.user_data.get("phone_number")
    users = load_users()
    user = next(u for u in users if u["phone_number"] == phone)
    if user.get("is_admin"):
        kb = [
                [InlineKeyboardButton("👥 Список учеников", callback_data="admin_students")],
                [InlineKeyboardButton("Изменить курс", callback_data="change_course")],
                [InlineKeyboardButton("👤 Мой профиль", callback_data="admin_profile")],
                [InlineKeyboardButton("Вопросы от учеников",callback_data="student_questions")],
                [InlineKeyboardButton("🚪 Выйти", callback_data="logout")]
            ]
        
        return InlineKeyboardMarkup(kb)
    else:
        kb = []
        if user.get("paid_current_month"):
            kb.append([
                    InlineKeyboardButton("📖 Мои курсы", callback_data="my_courses"),
                    InlineKeyboardButton("📚 Все курсы", callback_data="courses")
                ])
        else:
            kb.append([InlineKeyboardButton("📚 Все курсы", callback_data="courses")])
        kb.append([
                InlineKeyboardButton("👤 Профиль", callback_data="profile"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ])
        kb.append([InlineKeyboardButton("🚪 Выход", callback_data="logout")])
        kb.append([InlineKeyboardButton("Связаться с учителем", callback_data="contact_teacher")])
        if "answer" in user:
            kb.append([InlineKeyboardButton("Посмотреть ответ на вопрос",callback_data="see_answer_to_question")])
        return InlineKeyboardMarkup(kb)
    



# Добавить кнопку "Главное меню" внизу
def with_back_to_menu(markup):
    buttons = markup.inline_keyboard
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)

# Хэндлеры

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_user_flags(context)
    context.user_data["registering_phone_number"] = True

    # Кнопка для запроса номера телефона
    contact_button = KeyboardButton("📱 Отправить номер телефона", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "👋 Добро пожаловать в *MathUp*! Чтобы зарегистрироваться, отправьте номер телефона.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
     
async def start_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_user_flags(context)
    
    context.user_data["login_phone_number"] = True

    # Кнопка для запроса номера телефона
    contact_button = KeyboardButton("📱 Отправить номер телефона", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "🔐 Отправьте номер телефона для входа:",
        reply_markup=reply_markup
    )

async def contact_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = context.user_data.get(STATE_KEY)
    if context.user_data.get("registering_phone_number") == True:
        context.user_data["registering_phone_number"] = False
        return await handle_contact(update, context)
    if context.user_data.get("login_phone_number") == True:
        context.user_data["login_phone_number"] = False
        return await handle_login_contact(update, context)


async def handle_change_title(update:Update,context:ContextTypes.DEFAULT_TYPE):
    grade = context.user_data.get("edit").get("grade")
    lesson_number = context.user_data.get("edit").get("lesson_number")
    path = f"./data/grade_{grade}/lesson{lesson_number}/metadata.json"
    with open(path, "r", encoding='utf8') as f:
        data = json.load(f)
    data["lesson_title"] = update.message.text.strip()
    kb = [[InlineKeyboardButton(f"Обратно на урок {lesson_number}, класс {grade}", callback_data=f"change_lesson_{lesson_number}_{grade}")],
          [InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
    markup = InlineKeyboardMarkup(kb)
    with open(path, 'w', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    await update.message.reply_text(f"Новый заголовок поставлен на урок {lesson_number} класса {grade}",reply_markup=markup)
    

async def handle_change_intro(update:Update,context:ContextTypes.DEFAULT_TYPE):
    grade = context.user_data.get("edit").get("grade")
    lesson_number = context.user_data.get("edit").get("lesson_number")
    path = f"./data/grade_{grade}/lesson{lesson_number}/metadata.json"
    with open(path, "r", encoding='utf8') as f:
        data = json.load(f)
    data["intro"] = update.message.text.strip()
    with open(path, 'w', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    kb = [[InlineKeyboardButton(f"Обратно на урок {lesson_number} класс {grade}", callback_data=f"change_lesson_{lesson_number}_{grade}")],
          [InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
    markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text(f"Новое интро поставлено на урок {lesson_number} класса {grade}", reply_markup=markup)

async def handle_contact_teacher(update:Update, context:ContextTypes.DEFAULT_TYPE):
    message = update.message.text 
    users = load_users()
    phone = context.user_data.get("phone_number")
    for user in users:
        if user.get("phone_number") == phone:
            user["question"] = message 
            break 
    save_users(users)
    kb = [[InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
    await update.message.reply_text("Успешно записан вопрос, с вами свяжется учитель или админ")

async def handle_reply_to_student(update:Update, context:ContextTypes.DEFAULT_TYPE):
    phone = context.user_data["phone_to_reply"] 
    with open("users.json","r", encoding='utf8') as file:
        users = json.load(file)
    for user in users:
        if user["phone_number"] == phone:
            chat_id = user["user_id"]
    await context.bot.send_message(chat_id=chat_id, text=f"Сообщение от учителя:{update.message.text}")
    return

async def handle_change_course_title(update:Update, context:ContextTypes.DEFAULT_TYPE):
    edit_course = context.user_data.get("edit_course")
    grade = edit_course.get("grade")
    with open(f"./data/grade_{grade}/metadata.json",'r', encoding='utf8') as file:
        data = json.load(file)
    data["title"] = update.message.text 
    with open(f"./data/grade_{grade}/metadata.json",'w',encoding='utf8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        kb = [[InlineKeyboardButton(f"Обратно к изменению класса {grade}",callback_data=f"info_change_course_{grade}")],
            [InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
        markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text(f"Успешно изменен заголовок класса {grade}",reply_markup=markup)


async def handle_change_course_description(update:Update,context:ContextTypes.DEFAULT_TYPE):
    edit_course = context.user_data.get("edit_course")
    grade = edit_course.get("grade")
    with open(f"./data/grade_{grade}/metadata.json",'r',encoding='utf8') as file:
        data = json.load(file)
    data["description"] = update.message.text 
    with open(f"./data/grade_{grade}/metadata.json",'w', encoding='utf8') as file:
        json.dump(data,file, ensure_ascii=False, indent=2)
    user = context.user_data.get("user")
    kb = [[InlineKeyboardButton(f"Обратно к изменению класса {grade}",callback_data=f"info_change_course_{grade}")],
          [InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
    markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text(f"Успешно записано описание класса {grade}", reply_markup=markup)



async def handle_change_course_price(update:Update, context:ContextTypes.DEFAULT_TYPE):
    edit_course = context.user_data.get("edit_course")
    grade = edit_course.get("grade")
    with open(f"./data/grade_{grade}/metadata.json",'r',encoding='utf8') as file:
        data = json.load(file)
    data["price"] = update.message.text 
    with open(f"./data/grade_{grade}/metadata.json",'w', encoding='utf8') as file:
        json.dump(data,file,ensure_ascii=False, indent=2)
    
    kb = [[InlineKeyboardButton(f"Обратно к изменению класса {grade}",callback_data=f"info_change_course_{grade}")],
          [InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
    markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text(f"Записана новая цена для класса {grade}",reply_markup=markup)



async def handle_answer_for_student(update:Update,context:ContextTypes.DEFAULT_TYPE):
    phone_number = context.user_data.get("student_phone_number")
    users = load_users()
    for user in users:
        if user["phone_number"] == phone_number:
            user["answer"] = f"Предыдущий вопрос:{user["question"]}, Ответ на него:{update.message.text}" 
            del user["question"]

            break
    
    save_users(users)
    await update.message.reply_text("Ответ успешно сохранен!")



async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    st = context.user_data.get(STATE_KEY)
    
    if context.user_data.get("registering_password") == True:
        # clear_user_flags(context)
        context.user_data["registering_password"] = False
        return await handle_register_password(update, context)
    if context.user_data.get("registering_name") == True:
        # clear_user_flags(context)
        context.user_data["registering_name"] = False
        return await handle_register_name(update, context)
    if context.user_data.get("registering_surname") == True:
        # clear_user_flags(context)
        context.user_data["registering_surname"] = False 
        return await handle_register_surname(update, context)
    if context.user_data.get("login_password") == True:
        # clear_user_flags(context)
        context.user_data["login_password"] = False
        return await handle_login_password(update, context)
    if context.user_data.get("edit", {}).get("ongoing") == True and context.user_data.get("edit", {}).get("action") == "title":
        # clear_user_flags(context)
        context.user_data["edit"]["ongoing"] = False
        return await handle_change_title(update,context)
    if context.user_data.get("edit",{}).get("ongoing") == True and context.user_data.get("edit",{}).get("action") == "intro":
        # clear_user_flags(context)
        context.user_data["edit"]["ongoing"] = False
        return await handle_change_intro(update,context)
    # if context.user_data.get("edit",{}).get("ongoing") == True and context.user_data.get("edit",{}).get("action") == "video":
    #     # clear_user_flags(context)
    #     context.user_data["edit"]["ongoing"] = False
    #     return await handle_new_video(update,context)
    if context.user_data.get("waiting_for_contact_teacher") == True:
        clear_user_flags(context)
        return await handle_contact_teacher(update,context)
    if context.user_data.get("waiting_for_reply_to_student"):
        clear_user_flags(context)
        return await handle_reply_to_student(update,context)
    
    if context.user_data.get("edit_course",{}).get("ongoing") == True and context.user_data.get("edit_course",{}).get("action") == "title":
        # clear_user_flags(context)
        context.user_data["edit_course"]["ongoing"] = False
        return await handle_change_course_title(update,context)
    
    if context.user_data.get("edit_course",{}).get("ongoing") == True and context.user_data.get("edit_course").get("action") == "description":
        # clear_user_flags(context)
        context.user_data["edit_course"]["ongoing"] = False
        return await handle_change_course_description(update,context)
    
    if context.user_data.get("edit_course",{}).get("ongoing") == True and context.user_data.get("edit_course",{}).get("action") == "price":
        # clear_user_flags(context)
        context.user_data["edit_course"]["ongoing"] = False
        return await handle_change_course_price(update,context)
    if context.user_data.get("waiting_for_answer_for_student") == True:
        # clear_user_flags(context)
        context.user_data["waiting_for_answer_for_student"] = False
        return await handle_answer_for_student(update,context)


    


# Регистрация
def clear_user_flags(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Удаляет из context.user_data все ключи, кроме 'phone_number' и 'is_logged'.
    """
    keys_to_keep = {"phone_number", "is_logged"}
    for key in list(context.user_data.keys()):
        if key not in keys_to_keep:
            context.user_data.pop(key, None)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact.phone_number
    with open("users.json",'r', encoding='utf8') as file:
        users = json.load(file)

    for user in users:
        if user["phone_number"] == contact:
            await update.message.reply_text("Данный номер уже зарегистрирован!Залогиньтесь /login")
            return
    context.user_data["phone_number"] = contact
    context.user_data["registering_password"] = True
    await update.message.reply_text("✅ Телефон сохранён! Введите пароль.")

async def handle_register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["password"] = update.message.text.strip()
    context.user_data["registering_name"] = True
    await update.message.reply_text("✅ Пароль сохранён! Введите имя.")

async def handle_register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["first_name"] = update.message.text.strip()
    context.user_data["registering_surname"] = True
    await update.message.reply_text("✅ Имя сохранено! Введите фамилию.")

async def handle_register_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update._effective_user.id
    users = load_users()
    users.append({
        "phone_number": context.user_data["phone_number"],
        "password": context.user_data["password"],
        "first_name": context.user_data["first_name"],
        "last_name": update.message.text.strip(),
        "class": None,
        "paid_current_month": False,
        "subscription_end_date": None,
        "progress": [],
        "finished_courses": []

    })
    save_users(users)
    context.user_data[STATE_KEY] = None
    # Вот здесь убери main_menu
    await update.message.reply_text(
        "🎉 Регистрация завершена! Используйте /login для входа."
    )


# Вход

async def handle_login_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.contact.phone_number
    context.user_data["phone_number"] = phone
    users = load_users()
    for u in users:
        if u["phone_number"] == phone:
            context.user_data["login_password"] = True
            await update.message.reply_text("✅ Номер найден! Введите пароль.")
            return
    # Пользователь не найден
    await update.message.reply_text("❌ Пользователь не найден. Залогиньтесь заново /login")
    return

async def handle_login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip()
    phone = context.user_data.get("phone_number")
    with open("users.json",'r', encoding='utf8') as file:
        users = json.load(file)
        context.user_data["is_logged"] = False
    for user in users:
        if user["phone_number"] == phone and user["password"].strip() == text:
            context.user_data["is_logged"] = True
            kb = [[InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
            context.user_data["user"] = user
            await update.message.reply_text("✅ Вы вошли!", reply_markup=main_menu(update,context))
    if context.user_data.get("is_logged") == False:
        await update.message.reply_text("Неправильный пароль!Залогиньтесь заново /login")
        

    
    

# Обработка кнопок

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()
    data = query.data
    phone = context.user_data.get("phone_number")
    users = load_users()
    user = context.user_data.get("user")
    
    print("DEBUG callback_data =", data, "phone from context =", context.user_data.get("phone_number"))
    curr_user = next((u for u in users if u["phone_number"] == phone), None)

    # Админ-панель: профиль
    if data == "main_menu":
        # query = update.callback_query
        await query.edit_message_text(
            text="Главное меню:",
            reply_markup=main_menu(update, context)
        )
        return



    if data == "see_answer_to_question":
        phone = context.user_data.get("phone_number")
        users = load_users()
        user = next(u for u in users if u["phone_number"] == phone)
        answer = user["answer"]
        kb = [[InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
        markup = InlineKeyboardMarkup(kb)
        await query.edit_message_text(f"Вот ответ:{answer}", reply_markup=markup)


    if data == "student_questions":
        users = load_users()
        kb = []
        for user in users:
            if "question" in user:
                kb.append([InlineKeyboardButton(f"{user["first_name"]} {user["last_name"]}",callback_data=f"see_questions_{user["phone_number"]}")] )
        kb.append([InlineKeyboardButton("Главное меню",callback_data="main_menu")])
        markup = InlineKeyboardMarkup(kb)

        await query.edit_message_text(".", reply_markup=markup)


                

    if data.startswith("see_questions_"):
        phone_number = data.split("_")[-1]
        users = load_users()
        for user in users:
            if user["phone_number"] == phone_number:
                question = user["question"]
        kb = [[InlineKeyboardButton("Ответить",callback_data=f"answer_question_{phone_number}")]]
        kb.append([InlineKeyboardButton("Главное меню",callback_data="main_menu")])
        markup = InlineKeyboardMarkup(kb)
        await query.edit_message_text(f"Вопрос от ученика:{question}",reply_markup=markup)


    
    if data.startswith("answer_question_"):
        context.user_data["student_phone_number"] = data.split("_")[-1]
        context.user_data["waiting_for_answer_for_student"] = True
        await query.message.reply_text("Напишите ответ")
        



    if data == "change_course":
        kb = [

            [InlineKeyboardButton(f"{grade} класс" , callback_data=f"change_course_{grade}")]
            for grade in range(5,12)

            ]
        kb.append([InlineKeyboardButton("Главное меню",callback_data="main_menu")])
        markup = InlineKeyboardMarkup(kb)
        await query.edit_message_text("Выберите класс для изменения", reply_markup = markup)
        return  




    if data.startswith("change_course_"):
        grade = data.split("_")[-1]
        path = f"./data/grade_{grade}"
        os.makedirs(path, exist_ok=True)
        folders = len([d for d in os.listdir(path) if os.path.isdir(os.path.join(path,d))])
        kb = [
            [InlineKeyboardButton(f"Урок {lesson_number + 1}", callback_data=f"change_lesson_{lesson_number+1}_{grade}") ] for lesson_number in range(folders)
            
              ]
        kb.append([InlineKeyboardButton("Добавить урок",callback_data=f"add_next_lesson_{grade}")])
        kb.append([InlineKeyboardButton("Изменить описание самого курса",callback_data=f"info_change_course_{grade}")])
        kb.append([InlineKeyboardButton("Главное меню",callback_data="main_menu")])
        markup = InlineKeyboardMarkup(kb)
        await query.edit_message_text("Существующие уроки", reply_markup=markup)
        return  

    if data.startswith("change_lesson_"):
        # await query.message.reply_text(data)
        lesson_number = int(data.split("_")[-2])
        grade = data.split("_")[-1]
        path = f"./data/grade_{grade}/lesson{lesson_number}"
        path_to_metadata = f"./data/grade_{grade}/lesson{lesson_number}/metadata.json"
        # await query.message.reply_text(path)
        with open(path_to_metadata, "r", encoding='utf8') as f:
            data1 = json.load(f)
        title = data1.get("lesson_title","Нет")
        intro = data1.get("intro","Нет")
        video = data1.get("video_url","Нет")
        kb = [
            
                [InlineKeyboardButton(f"Изменить Заголовок", callback_data=f"change_title_{lesson_number}_{grade}"),],

                # [InlineKeyboardButton(f"Посмотреть заголовок", callback_data=f"view_title_{lesson_number}_{grade}")],

                [InlineKeyboardButton(f"Изменить Интро:", callback_data=f"change_intro_{lesson_number}_{grade}")],

                # [InlineKeyboardButton(f"Посмотреть Интро:", callback_data=f"view_intro_{lesson_number}_{grade}")],


                [InlineKeyboardButton(f"Скачать домашку", callback_data=f"download_hw_{lesson_number}_{grade}")],
                [InlineKeyboardButton(f"Изменить домашку", callback_data=f"change_hw_{lesson_number}_{grade}")],
                [InlineKeyboardButton(f"Посмотреть видео", callback_data=f"see_video_{lesson_number}_{grade}")],
                [InlineKeyboardButton(f"Изменить видео", callback_data=f"change_video_{lesson_number}_{grade}")],
                [InlineKeyboardButton("Главное меню",callback_data="main_menu")]


        ]
        markup = InlineKeyboardMarkup(kb)
        
        await query.edit_message_text(f"Инфа о классе {grade} урок {lesson_number}:\nЗаголовок:{title}\nИнтро:{intro}\n", reply_markup=markup)
        return  

    if data.startswith("change_video_"):
        seq = data.split("_")[-2]
        grade = data.split("_")[-1]
        context.user_data["edit"] = {
            "ongoing":True,
            "action":"video",
            "grade":grade,
            "lesson_number":seq
        }
        await update.callback_query.edit_message_text("Отправьте новое видео")
        return  




    if data.startswith("info_change_course_"):
        grade = data.split("_")[-1]
        path = f"./data/grade_{grade}"
        file_path = os.path.join(path,"metadata.json")
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf8') as file:
                json.dump({}, file)
        
        with open(f"./data/grade_{grade}/metadata.json",'r',encoding='utf8') as file:
            data1 = json.load(file)
        kb = [
            [InlineKeyboardButton("Изменить заголовок",callback_data=f"title_change_course_{grade}")],
            [InlineKeyboardButton("Изменить описание",callback_data=f"description_change_course_{grade}")],
            [InlineKeyboardButton("Изменить цену",callback_data=f"price_change_course_{grade}")],
            [InlineKeyboardButton("Главное меню",callback_data="main_menu")]
            
        ]
        title = data1.get("title","Нет")
        description = data1.get("description","Нет")
        price = data1.get("price","Нет")
        
        markup = InlineKeyboardMarkup(kb)
        await query.edit_message_text(f"Данные класса {grade}:\nЗаголовок:{title}\nОписание:{description}\nЦена:{price}", reply_markup=markup)
        return  

    if data.startswith("add_next_lesson_"):
        grade = data.split("_")[-1]
        grade_path = f"./data/grade_{grade}"
        lessons = [
            name for name in os.listdir(grade_path) if os.path.isdir(os.path.join(grade_path,name)) and name.startswith("lesson")
        ]
        lesson_numbers = [int(name.replace("lesson","")) for name in lessons if name.replace("lesson","").isdigit()]
        last_lesson = max(lesson_numbers, default=0)
        next_lesson = last_lesson + 1
        # await query.message.reply_text(f"Последний урок:{last_lesson}")

        nested_folder = f"./data/grade_{grade}/lesson{next_lesson}"
        kb = [[InlineKeyboardButton(f"Изменить урок {next_lesson} класса {grade}",callback_data=f"change_lesson_{next_lesson}_{grade}")],
            [InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
        markup = InlineKeyboardMarkup(kb)
        os.makedirs(nested_folder, exist_ok=True)
        metadata_path = os.path.join(nested_folder, "metadata.json")

        lesson_metadata = {
            "sequence": next_lesson,
            "lesson_title": "Нет",
            "intro": "Нет",
            "video_url": "Нет",
            "homework_file": "homework.pdf"
        }

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(lesson_metadata, f, ensure_ascii=False, indent=4)
        await query.edit_message_text("Урок создан!",reply_markup=markup)
        return  

    if data.startswith("reply_to_"):
        context.user_data["phone_to_reply"] = data.split("_")[-1]
        context.user_data["waiting_for_reply_to_student"] = True
        await query.edit_message_text("Напишите ответ ученику")
        return  
    




    if data.startswith("price_change_course"):
        grade = data.split("_")[-1]
        context.user_data["edit_course"] = {
            "ongoing":True,
            "action":"price",
            "grade":grade
        }
        await query.edit_message_text("Напишите новую цену")


    


    


    if data.startswith("description_change_course_"):
        grade = data.split("_")[-1]
        context.user_data["edit_course"] = {
            "ongoing":True, 
            "action":"description",
            "grade":grade
        }
        await query.edit_message_text("Напишите новое описание")

    if data.startswith("title_change_course_"):
        grade = data.split("_")[-1]
        context.user_data["edit_course"] = {
            "ongoing":True,
            "action":"title",
            "grade":grade

        }
        await query.edit_message_text("Напишите новый заголовок")
        return  



    if data.startswith("see_video"):
        seq = data.split("_")[-2]
        grade = data.split("_")[-1]
        kb = [[InlineKeyboardButton(f"Обратно на урок {seq} класс {grade}", callback_data=f"change_lesson_{seq}_{grade}")],
              [InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
        markup = InlineKeyboardMarkup(kb)
        path = f"./data/grade_{grade}/lesson{seq}/video.mp4"
        if os.path.exists(path):
            with open(path, "rb") as video_file:
                    await update.callback_query.message.delete()
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=video_file
                    )
            await update.callback_query.message.reply_text(".",reply_markup=markup)
            return  
        else:
            await update.callback_query.edit_message_text("Видео нет", reply_markup=markup)



    if data.startswith("change_hw_"):
        lesson_number = data.split("_")[-2]
        grade = data.split("_")[-1]
        context.user_data["edit"] = {
            "ongoing":True,
            "action":"homework",
            "grade":grade,
            "lesson_number":lesson_number
        }
        await update.callback_query.edit_message_text("Скиньте новую домашку")
        return  


    if data.startswith("download_hw_"):
        lesson_number = data.split("_")[-2]
        grade = data.split("_")[-1]
        path = f"./data/grade_{grade}/lesson{lesson_number}/homework.pdf"
        kb = [[InlineKeyboardButton(f"Обратно на урок {lesson_number} класс {grade}", callback_data=f"change_lesson_{lesson_number}_{grade}")],
                  [InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
        markup = InlineKeyboardMarkup(kb)
        if os.path.isfile(path):
            await update.callback_query.message.delete()
            await update.callback_query.message.reply_document(document=open(path, 'rb'))
            await update.callback_query.message.reply_text(".", reply_markup=markup)
        else:
            await update.callback_query.edit_message_text("Домашки нет",reply_markup=markup)
            return



    if data.startswith("view_intro_"):
        lesson_number = data.split("_")[-2]
        grade = data.split("_")[-1]
        path = f"./data/grade_{grade}/lesson{lesson_number}/metadata.json"
        with open(path, "r", encoding='utf8') as f:
            data1 = json.load(f)
        kb = [[InlineKeyboardButton(f"Обратно на урок {lesson_number} класс {grade}", callback_data=f"change_lesson_{lesson_number}_{grade}")]]
        markup = InlineKeyboardMarkup(kb)
        await update.callback_query.message.reply_text(f"Вот интро класса {grade} урока {lesson_number}:{data1["intro"]}", reply_markup=markup)

    if data.startswith("change_intro_"):
        lesson_number = data.split("_")[-2]
        grade = data.split("_")[-1]
        context.user_data["edit"] = {
            "ongoing":True,
            "action":"intro",
            "grade":grade,
            "lesson_number":lesson_number
        }
        await update.callback_query.edit_message_text("Напишите новое интро")
        return  


    if data.startswith("view_title_"):
        lesson_number = int(data.split("_")[-2])
        grade = data.split("_")[-1]
        path = f"./data/grade_{grade}/lesson{lesson_number}/metadata.json"
        with open(path,'r', encoding='utf8') as f:
            data1 = json.load(f)
        kb = [[InlineKeyboardButton(f"Обратно на урок {lesson_number} класс {grade}", callback_data=f"change_lesson_{lesson_number}_{grade}")]]
        markup = InlineKeyboardMarkup(kb)
        await update.callback_query.message.reply_text(f"Текущий заголовок класса {grade} урока {lesson_number}:{data1["lesson_title"]}", reply_markup=markup)
        return  
    if data.startswith("change_title_"):
        grade = data.split("_")[-1]
        lesson_number = data.split("_")[-2]
        context.user_data["edit"] = {
            "ongoing":True,
            "action":"title",
            "grade":grade,
            "lesson_number":lesson_number
        }
        await update.callback_query.edit_message_text("Напишие новый заголовок")
        return  


    




    if data == "admin_profile" and curr_user and curr_user.get("is_admin"):
        lines = [
            "👑 *АДМИН-ПАНЕЛЬ*",
            f"Имя: {curr_user['first_name']} {curr_user['last_name']}",
            f"Телефон: {curr_user['phone_number']}",
            "",
            "Возможности:",
            "- Просмотр и фильтрация учеников",
            "- Открытие любых уроков любому ученику",
            "- Просмотр прогресса и оплат учеников"
        ]
        kb = [[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]]
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return
        # Кнопка "Список учеников"
    if data == "admin_students":
        students = [u for u in users if not u.get("is_admin")]
        kb = []
        for u in students:
            kb.append([InlineKeyboardButton(f"{u['first_name']} {u['last_name']}", callback_data=f"admin_student_{u['phone_number']}")])
        kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        await query.edit_message_text("Список учеников:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # Кнопка студента - профиль
    if data.startswith("admin_student_"):
        phone = data[len("admin_student_"):]
        u = next(u for u in users if u["phone_number"] == phone)
        lines = [
            f"👤 Профиль: {u['first_name']} {u['last_name']}",
            f"Тел: {u['phone_number']}",
            f"Класс: {u.get('class','-')}",
            f"Оплачен: {'✔️' if u.get('paid_current_month') else '❌'}",
            f"Действует до: {u.get('subscription_end_date') or '—'}",
            f"Курс завершён: {'✅' if u.get('is_completed') == 'yes' else '⏳'}",
            f"Законченные курсы:{u.get("finished_courses") if u.get("finished_courses") else "Нет"}"
            "",
            "📊 Прогресс по урокам:",
        ]
        for p in u.get("progress", []):
            stat = ["🎥" if p.get("watched_video") else "❌видео", "📄" if p.get("homework_done") else "❌ДЗ"]
            lines.append(f"  Урок {p['sequence']}: {', '.join(stat)}")
        lines.append("")
        lines.append("💵 История платежей:")
        for p in u.get("payment_history", []):
            lines.append(f"{p['date'][:10]} — {p['amount']} тг")
        kb = [
            [InlineKeyboardButton("🟢 Открыть доступ к уроку", callback_data=f"admin_openlessongrade_{phone}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_students")]
        ]
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return

    # Кнопка открыть урок — выбираем класс
    if data.startswith("admin_openlessongrade_"):
        phone = data[len("admin_openlessongrade_"):]
        grade_dirs = [d for d in os.listdir("data") if d.startswith("grade_")]
        kb = []
        for g in grade_dirs:
            grade_num = g.split("_")[1]
            kb.append([InlineKeyboardButton(f"Класс {grade_num}", callback_data=f"admin_openlesson_{phone}_{grade_num}")])
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data=f"admin_student_{phone}")])
        await query.edit_message_text("Выберите класс:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # Кнопка выбрать урок
    if data.startswith("admin_openlesson_"):
        arr = data.split("_")
        phone = arr[2]
        grade = int(arr[3])

        target = next((u for u in users if u["phone_number"] == phone), None)
        if not target:
            await query.edit_message_text("Нет такого ученика")
            return
        

        # 2. Обновляем его подписку
        target["class"] = grade
        target["paid_current_month"] = True
        target["subscription_end_date"] = (
            datetime.now() + relativedelta(months=1)
        ).isoformat()
        save_users(users)
        await query.edit_message_text(
        f"✅ Уроки класса {grade} успешно открыты для {target['first_name']} {target['last_name']}!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data=f"admin_students")]
        ])
    )
        return




    # Кнопка дать доступ к уроку
    if data.startswith("admin_giveaccess_"):
        _, phone, grade, seq = data.split("_")[2:]
        # открываем урок пользователю
        u = next(u for u in users if u["phone_number"] == phone)
        prog = u.setdefault("progress", [])
        entry = next((p for p in prog if p["grade"] == int(grade) and p["sequence"] == int(seq)), None)
        if not entry:
            entry = {"grade": int(grade), "sequence": int(seq), "watched_video": True, "homework_done": True, "is_current": False}
            prog.append(entry)
        else:
            entry.update({"watched_video": True, "homework_done": True})
        save_users(users)
        await query.edit_message_text(f"Доступ к уроку {seq} класса {grade} открыт!", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад к ученику", callback_data=f"admin_student_{phone}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]))
        return




    if data == "main_menu":
        
        user = next(u for u in users if u["phone_number"] == phone)
        await query.edit_message_text("Главное меню:", reply_markup=main_menu(update,context))
        return

    if data == "logout":
        context.user_data.clear()
        await query.edit_message_text("🚪 Вы вышли из аккаунта.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]))
        return

    if data == "profile":
        user = next(u for u in users if u["phone_number"] == phone)
        reset_subscription_if_expired(user)
        save_users(users)
        lines = [
            f"👤 Профиль:",
            f"Имя: {user['first_name']} {user['last_name']}",
            f"Телефон: {user['phone_number']}",
            f"Текущий курс, класс: {user.get('class') or '—'}",
            f"Оплачен: {'✔️' if user.get('paid_current_month') else '❌'}",
            f"Действует до: {user.get('subscription_end_date') or '—'}",
            f"Завершенные курсы:{user.get("finished_courses")}"
            "",
            "📊 Прогресс по урокам:"
        ]
        prog = user.get("progress", [])
        if not prog:
            lines.append("  пока нет данных, начните курс")
        else:
            for e in prog:
                stat = ["🎥" if e.get("watched_video") else "❌ видео", "📄" if e.get("homework_done") else "❌ ДЗ"]
                cur = " (текущий)" if e.get("is_current") else ""
                lines.append(f"  Урок {e['sequence']}: {', '.join(stat)}{cur}")
        # История платежей
        lines.append("")
        lines.append("💵 История платежей:")
        payments = user.get("payment_history", [])
        if not payments:
            lines.append("  пока нет оплат")
        else:
            for p in payments[-5:]:  # последние 5 платежей
                lines.append(f"  {p['date'][:10]} — {p['amount']} тг")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]])
        await query.edit_message_text("\n".join(lines), reply_markup=kb)
        return


    if data == "help":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]])
        await query.edit_message_text("❓ Напишите ваш вопрос.", reply_markup=kb)
        return

    # Мои курсы
    if data == "my_courses":
        user = next(u for u in users if u["phone_number"] == phone)
        grade = user.get("class")
        if not grade:
            await query.edit_message_text("У вас нет курса.", reply_markup=main_menu(update,context))
            return
        prog = user.get("progress", [])
        curr = next((e for e in prog if e.get("is_current")), None)
        seq = curr["sequence"] if curr else (max([e["sequence"] for e in prog if e.get("homework_done")], default=0) + 1)
        meta_path = os.path.join(DATA_PATH, f"grade_{grade}", f"lesson{seq}", "metadata.json")
        if not os.path.exists(meta_path):
            await query.edit_message_text("Все уроки пройдены!", reply_markup=main_menu(update,context))
            return
        with open(meta_path, "r", encoding="utf8") as f:
            meta = json.load(f)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"▶ Урок {seq}", callback_data=f"start_lesson_{grade}_{seq}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        await query.edit_message_text(f"Класс : {grade}\nУрок {seq}: {meta['lesson_title']}", reply_markup=kb)
        return

    # Все курсы
    if data == "courses":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{g} класс", callback_data=f"{g}_grade_summary")] for g in range(5, 12)
        ] + [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]] )
        await query.edit_message_text("Выберите курс:", reply_markup=kb)
        return

    # Сводка и оплата
    if data.endswith("_grade_summary"):
        grade = int(data.split("_")[0])
        # for u in users:
        #     if u["phone_number"] == phone:
        #         u["class"] = grade
        # save_users(users)
        with open(os.path.join(DATA_PATH, f"grade_{grade}", "metadata.json"), "r", encoding="utf8") as f:
            meta = json.load(f)
        txt = f"*{meta['title']}*\n{meta['description']}\n💰 {meta['price']} тг/мес"
        context.user_data["price"] = meta['price']
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Оплатить курс",	callback_data=f"pay_grade_{grade}" )],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)
        return

    





    if data.startswith("pay_grade_"):
        grade = int(data.split("_")[-1])
        user = next(u for u in users if u["phone_number"] == phone)
        if user.get("paid_current_month") and user.get("class") == grade:
            await query.edit_message_text("Уже оплачен!", reply_markup=main_menu(update,context))
            return
        if user.get("class") is not None and user.get("paid_current_month") == True:
            await query.edit_message_text("Сначала закончите текущий курс!", reply_markup=main_menu(update,context))
            return
        
        user_id = query.from_user.id 
        phone = context.user_data.get("phone_number")
        link = "https://pay.kaspi.kz/pay/cxu5sykr"
        kb = [[InlineKeyboardButton("Перейти к оплате",url=link)]]
        markup = InlineKeyboardMarkup(kb)   
        context.user_data["waiting_for_check"] =  True
        context.user_data["grade"] = grade
        await query.edit_message_text("Вот ссылка на оплату. ВАЖНО - ПОСЛЕ ОПЛАТЫ СКИНЬТЕ ЧЕК ДЛЯ ПРОВЕРКИ",reply_markup=markup)
        # user["paid_current_month"] = True
        # user["subscription_end_date"] = (datetime.now() + timedelta(days=30)).isoformat()
        # user["class"] = grade
        # # добавляем историю платежей
        # if "payment_history" not in user:
        #     user["payment_history"] = []
        # with open(os.path.join(DATA_PATH, f"grade_{grade}", "metadata.json"), "r", encoding="utf8") as f:
        #     meta = json.load(f)
        # amount = meta.get("price", 0)
        # user["payment_history"].append({
        #     "date": datetime.now().isoformat(),
        #     "amount": amount
        # })
        # save_users(users)
        # kb = InlineKeyboardMarkup([
        #     [InlineKeyboardButton("▶ Начать курс", callback_data=f"start_lesson_{grade}_1")],
        #     [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        # ])
        # await query.edit_message_text("✅ Оплачено!", reply_markup=kb)
        return


    # Запуск урока
    if data.startswith("start_lesson_"):
        phone = context.user_data.get("phone_number")
        users = load_users()
        user = next((u for u in users if u["phone_number"] == phone), None)
        if user["paid_current_month"]:
        
            _, _, grade, seq = data.split("_")
            grade, seq = int(grade), int(seq)
            for u in users:
                if u["phone_number"] == phone:
                    for p in u.get("progress", []): p["is_current"] = False
                    prog = u.setdefault("progress", [])
                    ent = next((p for p in prog if p["grade"] == grade and p["sequence"] == seq), None)
                    if not ent:
                        ent = {"grade": grade, "sequence": seq, "watched_video": False, "homework_done": False, "is_current": True}
                        prog.append(ent)
                    else:
                        ent.update({"watched_video": False, "homework_done": False, "is_current": True})
                    break
            save_users(users)
            meta_path = os.path.join(DATA_PATH, f"grade_{grade}", f"lesson{seq}", "metadata.json")
            with open(meta_path, "r", encoding="utf8") as f:
                meta = json.load(f)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Просмотрел видео", callback_data=f"watched_{grade}_{seq}" )],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])
            # 1. Сначала отправь видео+описание
            with open(f"./data/grade_{grade}/lesson{seq}/video.mp4", "rb") as video_file:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video_file,
                    caption=(
                        f"▶ Урок {seq}: {meta['lesson_title']}\n"
                        f"{meta['intro']}"
                    ),
                    protect_content=True
                )
            await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Когда посмотрите видео, нажмите на кнопку ниже:",
            reply_markup=kb
        )
                
            return

            
        else:
            await query.message.reply_text("У вас не оплачено")

    # Отметка просмотра видео
    if data.startswith("watched_"):
        _, grade, seq = data.split("_")
        grade, seq = int(grade), int(seq)
        for u in users:
            if u["phone_number"] == phone:
                for p in u.get("progress", []):
                    if p["grade"] == grade and p["sequence"] == seq and p.get("is_current"):
                        p["watched_video"] = True
        save_users(users)
        meta_hw = os.path.join(DATA_PATH, f"grade_{grade}", f"lesson{seq}", "metadata.json")
        with open(meta_hw, "r", encoding="utf8") as f:
            hw = json.load(f)["homework_file"]
        path = os.path.join(DATA_PATH, f"grade_{grade}", f"lesson{seq}", hw)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Выполнил", callback_data=f"done_{grade}_{seq}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        # 1. Сначала просто отправь файл (без кнопок)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ Видео просмотрено! Вот домашнее задание:"
        )
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(path, "rb"))
        # 2. Потом новым сообщением — кнопки
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Когда выполните ДЗ, нажмите на кнопку ниже:",
            reply_markup=kb
        )
        return


    if data == "contact_teacher":
        context.user_data["waiting_for_contact_teacher"] = True
        await query.edit_message_text("Напишите ваш запрос администратору")
        return  

    # Завершение домашки
    if data.startswith("done_"):
        _, grade, seq = data.split("_")
        grade, seq = int(grade), int(seq)
        for u in users:
            if u["phone_number"] == phone:
                for p in u.get("progress", []):
                    if p["grade"]==grade and p["sequence"]==seq and p.get("is_current"):
                        p.update({"homework_done": True, "is_current": False})
        save_users(users)
        nxt = seq + 1
        nxt_meta = os.path.join(DATA_PATH, f"grade_{grade}", f"lesson{nxt}", "metadata.json")
        if os.path.exists(nxt_meta):
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶ Следующий урок", callback_data=f"start_lesson_{grade}_{nxt}" )],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])
            await query.edit_message_text(f"🎉 Урок {seq} завершён!", reply_markup=kb)
        else:
            # Помечаем курс как завершённый
            for u in users:
                if u["phone_number"] == phone and u.get("class") == grade:
                    u["progress"] = []
                    u["subscription_end_date"] = None 
                    u["paid_current_month"] = False 
                    u["class"] = None 
                    u["finished_courses"].append(grade)

                     # или True, если тебе так удобнее
            save_users(users)
            kb = [[InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
            markup = InlineKeyboardMarkup(kb)
            await query.edit_message_text("🎓 Курс пройден! Поздравляем! 🎉", reply_markup=markup)
        return

# async def admin_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     users = load_users()
#     user = next((u for u in users if u["phone_number"] == context.user_data.get("phone_number")), None)
#     if not user or not user.get("is_admin"):
#         await update.message.reply_text("⛔️ Нет доступа")
#         return
#     msg = ["Список учеников:"]
#     for u in users:
#         msg.append(f"{u['first_name']} {u['last_name']} ({u['phone_number']}) — класс: {u.get('class','-')}, оплата: {'✔️' if u.get('paid_current_month') else '❌'}")
#     await update.message.reply_text("\n".join(msg[:50]))

async def admin_student_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user = next((u for u in users if u.get("phone_number") == str(update.effective_chat.get('username', None)) or u.get("phone_number") == context.user_data.get('phone_number')), None)
    if not user or not user.get("is_admin"):
        await update.message.reply_text("⛔️ Нет доступа")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Используй: /student_profile <номер_телефона>")
        return
    phone = args[0]
    users = load_users()
    user = next((u for u in users if u["phone_number"] == phone), None)
    if not user:
        await update.message.reply_text("Ученик не найден.")
        return
    lines = [
        f"Профиль: {user['first_name']} {user['last_name']}",
        f"Тел: {user['phone_number']}",
        f"Класс: {user.get('class','-')}",
        f"Оплачен: {'✔️' if user.get('paid_current_month') else '❌'}",
        f"До: {user.get('subscription_end_date') or '—'}",
        f"Курс завершён: {'✅' if user.get('is_completed') == 'yes' else '⏳'}",
        "",
        "Прогресс:"
    ]
    for e in user.get("progress", []):
        stat = ["🎥" if e.get("watched_video") else "❌видео", "📄" if e.get("homework_done") else "❌ДЗ"]
        lines.append(f"Урок {e['sequence']}: {', '.join(stat)}")
    # История платежей
    lines.append("Платежи:")
    for p in user.get("payment_history", []):
        lines.append(f"{p['date'][:10]} — {p['amount']} тг")
    await update.message.reply_text("\n".join(lines))


async def handle_new_homework(update:Update, context:ContextTypes.DEFAULT_TYPE):
    edit = context.user_data.get("edit")
    if not edit or edit.get("ongoing") != True or edit.get("action") != "homework":
        return
    
    doc = update.message.document
    file = await doc.get_file()

    grade = edit["grade"]
    lesson_number = edit["lesson_number"]
    path = f"./data/grade_{grade}/lesson{lesson_number}/homework.pdf"
    await file.download_to_drive(path)  
    context.user_data["edit"]["ongoing"] = False
    kb = [[InlineKeyboardButton(f"Обратно на урок {lesson_number} класс {grade}", callback_data=f"change_lesson_{lesson_number}_{grade}")]]
    markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text(f"Домашка добавлена на урок {lesson_number} класса {grade}!",reply_markup=markup)

async def admin_open_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user = next((u for u in users if u.get("phone_number") == str(update.effective_chat.get('username', None)) or u.get("phone_number") == context.user_data.get('phone_number')), None)
    if not user or not user.get("is_admin"):
        await update.message.reply_text("⛔️ Нет доступа")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Используй: /open_lesson <номер_тел> <класс> <урок>")
        return
    phone, grade, seq = context.args[0], int(context.args[1]), int(context.args[2])
    users = load_users()
    user = next((u for u in users if u["phone_number"] == phone), None)
    if not user:
        await update.message.reply_text("Ученик не найден.")
        return
    prog = user.setdefault("progress", [])
    entry = next((p for p in prog if p["grade"] == grade and p["sequence"] == seq), None)
    if not entry:
        entry = {"grade": grade, "sequence": seq, "watched_video": True, "homework_done": True, "is_current": False}
        prog.append(entry)
    else:
        entry.update({"watched_video": True, "homework_done": True})
    save_users(users)
    await update.message.reply_text("Урок отмечен как пройденный для ученика.")


async def handle_new_video(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("edit",{}).get("ongoing") == True and context.user_data.get("edit",{}).get("action") == "video":
        edit = context.user_data.get("edit")
        

        grade = edit["grade"]
        lesson = edit["lesson_number"]
        path  = f"./data/grade_{grade}/lesson{lesson}"
        video = update.message.video
        file_id = video.file_id
        file = await context.bot.get_file(file_id)
        kb = [[InlineKeyboardButton(f"Обратно на урок {lesson} класс {grade}", callback_data=f"change_lesson_{lesson}_{grade}")]]
        markup = InlineKeyboardMarkup(kb)
        # сохраняем как video.mp4
        await file.download_to_drive(f"{path}/video.mp4")

        await update.message.reply_text("Видео сохранено ✅",reply_markup=markup)
         
    else:
        return


def read_pdf_text(pdf_bytes: bytes) -> str:
    """Извлекает текст из PDF файла."""
    try:
        with io.BytesIO(pdf_bytes) as f:
            reader = PdfReader(f)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
    except Exception as e:
        logger.error(f"Ошибка чтения PDF: {e}")
        return ""
    
async def handle_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_check"):
        try:
            # Получаем файл
            file = await update.message.document.get_file()
            
            # Скачиваем файл в память
            pdf_bytes = await file.download_as_bytearray()
            kb = [[InlineKeyboardButton("Главное меню",callback_data="main_menu")]]
            markup = InlineKeyboardMarkup(kb)
            # Извлекаем текст из PDF
            pdf_text = read_pdf_text(pdf_bytes)
            # await update.message.reply_text(pdf_text)
            check_number = pdf_text.splitlines()[4].split()[-1]
            amount = pdf_text.splitlines()[3].split()[0]
            bin = pdf_text.splitlines()[5].split()[-1]
            # await update.message.reply_text(f"check:{check_number}\nbin:{bin}\namount:{amount}")
            with open("checks.json",'r', encoding='utf8') as file:
                checks = json.load(file)
            liar = False
            for check in checks:
                if check["number"] == check_number or prodavec_bin != bin or int(amount) < int(context.user_data.get('price')) :
                    await update.message.reply_text("Обманщик", reply_markup=markup)
                    liar = True
                    return
            if not liar:
                # await update.message.reply_text("Успешная оплата",reply_markup=markup)
                with open("checks.json",'r', encoding='utf8') as file:
                    checks = json.load(file)
                checks.append({"number":check_number})
                with open("checks.json",'w', encoding='utf8') as file:
                    json.dump(checks, file, ensure_ascii=False, indent=2)
                users = load_users()
                phone = context.user_data.get("phone_number")
                user = next(u for u in users if u["phone_number"] == phone)

                grade = context.user_data.get("grade")
                user["paid_current_month"] = True
                user["subscription_end_date"] = (datetime.now() + timedelta(days=30)).isoformat()
                user["class"] = grade
                # добавляем историю платежей
                if "payment_history" not in user:
                    user["payment_history"] = []
                with open(os.path.join(DATA_PATH, f"grade_{grade}", "metadata.json"), "r", encoding="utf8") as f:
                    meta = json.load(f)
                amount = meta.get("price", 0)
                user["payment_history"].append({
                    "date": datetime.now().isoformat(),
                    "amount": amount
                })
                save_users(users)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶ Начать курс", callback_data=f"start_lesson_{grade}_1")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ])
                await update.message.reply_text("✅ Оплачено!", reply_markup=kb)
                context.user_data["waiting_for_check"] = False
                return


                    


        except Exception as e:
            await update.message.reply_text("Ошибка чтения PDF.")
            return

async def document_router(update:Update, context:ContextTypes.DEFAULT_TYPE):
    edit = context.user_data.get("edit")
    if context.user_data.get("waiting_for_check") == True:
        await handle_check(update,context)
        return
    elif edit.get("ongoing") == True and edit.get("action") == "homework":
        await handle_new_homework(update,context)
        return

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

schedule.every(24).hours.do(check_end_date)

# запуск планировщика в отдельном потоке
threading.Thread(target=run_schedule, daemon=True).start()
# Запуск бота
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("login", start_login))
app.add_handler(MessageHandler(filters.CONTACT, contact_router))
app.add_handler(MessageHandler(filters.Document.ALL, document_router))
# app.add_handler(MessageHandler(filters.Document.ALL, handle_new_homework))
app.add_handler(MessageHandler(filters.VIDEO, handle_new_video))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
app.add_handler(CallbackQueryHandler(handle_button))
# app.add_handler(CommandHandler("students", admin_students))
app.add_handler(CommandHandler("student_profile", admin_student_profile))
app.add_handler(CommandHandler("open_lesson", admin_open_lesson))
# app.add_handler(CommandHandler("menu",main_menu))
# asyncio.get_event_loop().create_task(periodic_reset())
# app.add_handler(MessageHandler(filters.Document.ALL, handle_check))

print("Бот запущен...")
app.run_polling()



#change_lesson убрать, не нужнное