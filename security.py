import functools
from typing import Callable

from telegram.ext import CallbackContext
from telegram.update import Update

from db import db


def known_user(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper_func(update: Update, context: CallbackContext) -> None:
        user_id = update.effective_user.id

        found_user = db.users.find_one({'user_id': user_id})

        if not found_user:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text='А мы точно знакомы? Кажется я тебя не знаю...'
            )

        return func(found_user, update, context)

    return wrapper_func
