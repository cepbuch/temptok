
import os
from datetime import timedelta

from telegram.ext import (CallbackContext, CallbackQueryHandler,
                          CommandHandler, Filters, MessageHandler, Updater)
from telegram.update import Update

from db import (STRICT_MODE_START_FROM, db, get_last_not_answered_tiktok,
                get_overall_tiktok_stats, save_sent_tiktok,
                save_tiktok_reply_if_applicable)

updater = Updater(token=os.environ['BOT_TOKEN'])

dispatcher = updater.dispatcher

COMMANDS = [
    ('start', 'посмотреть инструкцию'),
    ('stats', 'посмотреть статистику по тиктокам'),
    ('watch', 'получить самый ранний неотвеченный тикток'),
    ('fails', 'статистика фейлов / задокументировать фейл'),
]

success = updater.bot.set_my_commands(COMMANDS)

if not success:
    raise ValueError('Error settings commands')


def tiktok_handler(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    known_user = db.users.find_one({'user_id': user_id})

    if not known_user:
        context.bot.send_message(
            chat_id=chat_id,
            text='А мы знакомы? Почему ты кидаешь мне тиктоки, я тебя не знаю...'
        )

    save_sent_tiktok(user_id, message.message_id, message.date, message.text)

    not_answered_tiktok = get_last_not_answered_tiktok(user_id, offset_from_now=timedelta(hours=1))

    if not_answered_tiktok:
        context.bot.send_message(
            chat_id=chat_id,
            reply_to_message_id=message.message_id,
            text=(
                f"{known_user['name']}, kind reminder о том, что у тебя есть неотвеченные тиктоки, но "
                'ты присылаешь новые. Ведь те тиктоки ценнее, чем в ленте: за тебя их уже отобрали '
                'и возможно очень сильно ждут твоей реакции.\n\n'
                'Вот самый ранний неотвеченный, пожалуйста, начни с него и просмотри внимательно все что поле:'
            )
        )
        context.bot.forward_message(
            chat_id=chat_id,
            from_chat_id=chat_id,
            message_id=not_answered_tiktok[0]['message_id']
        )

    # TODO: check milestones — every 10th tiktok in a day, every 100th tiktok overall


def reply_handler(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    user_id = update.effective_user.id

    save_tiktok_reply_if_applicable(
        user_id, message.reply_to_message.message_id,
        message.message_id, message.date, message.text
    )


def start(update: Update, context: CallbackContext) -> None:
    commands_info = '\n\n'.join(
        [f'/{command} — {description}' for command, description in COMMANDS]
    )

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            'Привет!\n\n'
            "Я буду помогать соблюдать некоторые правила #temptok'ского клуба. "
            'Какие конкретно правила — станет ясно в момент их нарушения.\n\n'
            'Единственное, чтобы я лишний раз на тебя не наговаривал, отвечайте, пожалуйста, на '
            'все тиктоки через реплаи, а не просто сообщением.\n\n'
            f'Что еще:\n\n{commands_info}'
        )
    )


def stats(update: Update, context: CallbackContext) -> None:
    # args "/stats Сережа"  — самые частые ответы сережи

    # ! Overall stats
    get_overall_tiktok_stats(STRICT_MODE_START_FROM)

    # ! Person stats
    # 1. Received tiktoks vs. answered tiktoks
    # 2. Whose tiktoks answer as in 1
    # 3. Top most popular reactions

    ...


def fails(update: Update, context: CallbackContext) -> None:
    # статистика по фейлам, fails_count + добавить фейл (а там "Кто зафейлился?")
    ...


def watch(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id,

    known_user = db.users.find_one({'user_id': user_id})

    if not known_user:
        context.bot.send_message(chat_id=chat_id, text='А мы точно знакомы? Кажется я тебя не знаю...')

    not_answered_tiktok = get_last_not_answered_tiktok(user_id)

    if not_answered_tiktok:
        context.bot.send_message(
            chat_id=chat_id,
            text='Here you go!',
            from_chat_id=chat_id,
            reply_to_message_id=not_answered_tiktok[0]['message_id']
        )
    else:
        context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"Ты молодец, ты все просмотрел{'a' if known_user['gen'] == 'f' else ''}! "
                'Можно с чистой совестью идти смотреть новые тиктоки и скидывать друзьям 😊'
            )
        )


def callback_handler(update: Update, context: CallbackContext) -> None:
    ...


tiktoks_handler = MessageHandler(
    Filters.text & Filters.regex('.*vm.tiktok.com.*'),
    tiktok_handler
)

replies_handler = MessageHandler(
    Filters.reply, reply_handler
)

dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('stats', stats))
dispatcher.add_handler(CommandHandler('watch', watch))
dispatcher.add_handler(CommandHandler('fails', watch))
dispatcher.add_handler(tiktoks_handler)
dispatcher.add_handler(replies_handler)
dispatcher.add_handler(CallbackQueryHandler(callback_handler))
# TODO: add error handler -> tg
# TODO: add decorator "Это все конечно интересно, но бот работает только в одной группе"
updater.start_polling()
