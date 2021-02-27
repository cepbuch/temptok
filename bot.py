
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pymorphy2
import telegram
from telegram.ext import (CallbackContext, CommandHandler, Defaults, Filters,
                          MessageHandler, Updater)
from telegram.update import Update

from db import (db, get_income_replies_stats, get_last_not_answered_tiktok,
                get_outcome_replies_tiktoks_stats, get_sent_tiktoks_stats,
                get_today_sent_tiktoks_count, get_top_most_popular_reactions,
                save_sent_tiktok, save_tiktok_reply_if_applicable)
from security import known_user
from tiktok_utils import milliseconds_to_string_duration

morph = pymorphy2.MorphAnalyzer()

defaults = Defaults(parse_mode=telegram.ParseMode.HTML)
updater = Updater(token=os.environ['BOT_TOKEN'], defaults=defaults)

dispatcher = updater.dispatcher

COMMANDS = [
    ('start', 'посмотреть инструкцию'),
    ('stats', 'посмотреть статистику по тиктокам (есть аргументы <code>"Имя" "DD.MM.YYYY"</code>)'),
    ('watch', 'получить самый ранний неотвеченный тикток'),
]

success = updater.bot.set_my_commands(COMMANDS)

if not success:
    raise ValueError('Error settings commands')


@known_user
def tiktok_handler(user: dict, update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    chat_id = update.effective_chat.id

    save_sent_tiktok(user['user_id'], message.message_id, message.date, message.text)

    not_answered_tiktok = get_last_not_answered_tiktok(user['user_id'], offset_from_now=timedelta(hours=1))

    if not_answered_tiktok:
        context.bot.send_message(
            chat_id=chat_id,
            reply_to_message_id=message.message_id,
            text=(
                f"{user['name']}, kind reminder о том, что у тебя есть неотвеченные тиктоки, но "
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

    tiktok_morph = morph.parse('тикток')[0]
    user_sent_tiktoks_count = get_sent_tiktoks_stats().get(user['id'], {}).get('sent_count', -1)
    today_sent_tiktoks_count = get_today_sent_tiktoks_count(user['id'])

    if user_sent_tiktoks_count % 100 == 0:
        tiktoks_word = tiktok_morph.make_agree_with_number(user_sent_tiktoks_count).word
        context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🥂 {user['name']}, а у тебя юбилей! За все время ты отправил{'a' if user['gen'] == 'f' else ''} "
                f"уже {user_sent_tiktoks_count} {tiktoks_word}, продолжай в том же духе!"
            )
        )

    if today_sent_tiktoks_count % 15 == 0:
        tiktoks_word = tiktok_morph.make_agree_with_number(today_sent_tiktoks_count).word
        context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"👍 Вау, вот это контент! За сегодня {user['name']} послал{'a' if user['gen'] == 'f' else ''} уже "
                f"{today_sent_tiktoks_count} {tiktoks_word}. Предлагаю не останавливаться!"
            )
        )


@known_user
def reply_handler(user: dict, update: Update, context: CallbackContext) -> None:
    message = update.effective_message

    save_tiktok_reply_if_applicable(
        user, message.reply_to_message.message_id,
        message.message_id, message.date, message.text
    )


@known_user
def start(user: dict, update: Update, context: CallbackContext) -> None:
    commands_info = '\n\n'.join(
        [f'/{command} — {description}' for command, description in COMMANDS]
    )

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            'Привет!\n\n'
            "Я буду помогать соблюдать некоторые правила temptok'ского клуба. "
            'Какие конкретно правила — станет ясно в момент их нарушения.\n\n'
            'Единственное, чтобы я лишний раз на тебя не наговаривал, отвечай, пожалуйста, на '
            'все тиктоки через реплаи, а не просто сообщением.\n\n'
            f'Что еще:\n\n{commands_info}'
        )
    )


@known_user
def stats(user: dict, update: Update, context: CallbackContext) -> None:
    all_users = list(db.users.find({}).sort('name', 1))

    for_user_id = None
    start_date = None

    if args := context.args:
        for arg in args[:2]:
            # Try parse user
            found_user = None

            try:
                found_user = next(u for u in all_users if u['name'] == arg)
                for_user_id = found_user['user_id']
                continue
            except StopIteration:
                pass

            # Or try parse date
            try:
                start_date = datetime.strptime(arg, "%d.%m.%Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

    if for_user_id:
        text = form_stats_for_person(for_user_id, all_users, start_date)
    else:
        text = form_stats_summary(all_users, start_date)

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text
    )


def form_stats_summary(users: list, start_date: Optional[datetime]) -> str:
    tiktok_morph = morph.parse('тикток')[0]

    sent_stats = get_sent_tiktoks_stats(start_date)
    outcome_replies_stats = get_outcome_replies_tiktoks_stats(start_date)
    income_replies_stats = get_income_replies_stats(start_date)

    text = ''

    for user in users:
        user_sent_stats = sent_stats.get(user['user_id'])
        user_outcome_replies_stats = outcome_replies_stats.get(user['user_id'])
        user_income_replies_stats = income_replies_stats.get(user['user_id'])

        text += f"<b>{user['name']}</b>\n"

        if user_sent_stats and user_sent_stats['sent_count']:
            tiktoks_word = tiktok_morph.make_agree_with_number(user_sent_stats['sent_count']).word
            got_answers_percent = round(user_sent_stats['got_replies_count'] / user_sent_stats['sent_count'] * 100)

            text += (
                f"Отправил{'a' if user['gen'] == 'f' else ''} "
                f"<code>{user_sent_stats['sent_count']}</code> {tiktoks_word} "
                f"и получил{'a' if user['gen'] == 'f' else ''} ответ на "
                f"<code>{user_sent_stats['got_replies_count']}</code> из них ({got_answers_percent}%). "
            )

            if user_income_replies_stats:
                text += (
                    f"AVG получает ответ за "
                    f"{milliseconds_to_string_duration(user_income_replies_stats['avg_income_reply_time'])}, "
                    f"AVG длина получаемого ахаха — "
                    f"{round(user_income_replies_stats['avg_income_laugh_indicator'], 1)}"
                )

        else:
            text += f"Не отправлял{'a' if user['gen'] == 'f' else ''} тиктоков за период :("

        text += '\n\n'

        others_sent_count = sum([v['sent_count'] for k, v in sent_stats.items() if k != user['user_id']])

        if others_sent_count:
            replied_count = 0

            if user_outcome_replies_stats:
                replied_count = user_outcome_replies_stats['replied_count']

            text += (
                f"Ответил{'a' if user['gen'] == 'f' else ''} "
                f"на <code>{replied_count}</code> "
                f"из <code>{others_sent_count}</code> тиктоков, которые "
                f"получил{'a' if user['gen'] == 'f' else ''}. "
            )

            if user_outcome_replies_stats:
                text += (
                    f"AVG отвечает за "
                    f"{milliseconds_to_string_duration(user_outcome_replies_stats['avg_outcome_reply_time'])}, "
                    f"AVG длина ахаха в ответе — "
                    f"{round(user_outcome_replies_stats['avg_outcome_laugh_indicator'], 1)}"
                )
        else:
            text += f"А отвечать {'ей' if user['gen'] == 'f' else 'ему'} некому — нет тиктоков"

        text += '\n\n'

    return text


def form_stats_for_person(user_id: int, users: list, start_date: Optional[datetime]) -> str:
    text = (
        'Тут будет статистика чтобы понять кто кому как отвечает, но потом...\n\n'
    )

    # get_personal_income_stats(user_id, start_date)
    # get_personal_outcome_stats(user_id, start_date)

    reactions = get_top_most_popular_reactions(user_id, start_date)

    text += 'Самые частые реакции:\n'
    if reactions:
        for i, reaction in enumerate(reactions, start=1):
            text += f"{i}. {reaction['_id']} ({reaction['frequency']})\n"
    else:
        text += 'Нет реакция за период'

    return text


@known_user
def watch(user: dict, update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    not_answered_tiktok = get_last_not_answered_tiktok(user['user_id'])

    if not_answered_tiktok:
        context.bot.send_message(
            chat_id=chat_id,
            text='Here you go!',
            reply_to_message_id=not_answered_tiktok['message_id']
        )
    else:
        context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"Ты молодец, ты все просмотрел{'a' if user['gen'] == 'f' else ''}! "
                'Можно с чистой совестью идти смотреть новые тиктоки и скидывать друзьям 😊'
            )
        )


def error_handler(update: Update, context: CallbackContext) -> None:
    try:
        raise context.error
    except Exception as e:
        try:
            context.bot.send_message(
                chat_id=26187519,
                text=repr(e)[:4000]
            )

            if not update.callback_query:
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text='💫 Что-то упало... Сережа, почини'
                )

        except Exception:
            pass


tiktoks_handler = MessageHandler(
    Filters.text & Filters.regex('.*vm.tiktok.com.*') & ~Filters.update.edited_message,
    tiktok_handler
)

replies_handler = MessageHandler(
    Filters.reply & ~Filters.update.edited_message,
    reply_handler
)

dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('stats', stats))
dispatcher.add_handler(CommandHandler('watch', watch))
dispatcher.add_handler(tiktoks_handler)
dispatcher.add_handler(replies_handler)
dispatcher.add_error_handler(error_handler)
updater.start_polling()
