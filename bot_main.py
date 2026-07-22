# -*- coding: utf-8 -*-
import os
import sys
import json
import asyncio
import time
from datetime import datetime
from typing import Optional, Dict, Any
import io
import logging
import functools
from PIL import Image, ImageDraw, ImageFont
import disnake
from disnake.ext import commands, tasks
from disnake.ui import Modal, TextInput, View, Button
from disnake import PartialEmoji, ui, ButtonStyle, Embed

# ----------------------------
# CONFIG
# ----------------------------
CONFIG = {
    "BOT_TOKEN": os.getenv("BOT_TOKEN"),  # берём из переменной окружения
    "ALLOWED_ROLES": [1154757071330365490, 1127428607606796294, 1179045907493306550],
    "ALLOWED_ROLE_TICKET": [1459249476236607498],
    "LOG_CHANNEL_ID": 1462418981825810535,
    "LOG_CHANNEL_ID_PANEL": 1462418981825810535,
    "EMBED_IMAGE_URL": "https://media.discordapp.net/attachments/1527006158282555412/1527007499192893561/image.png?ex=6a60584e&is=6a5f06ce&hm=1b0ba12a8c8d57f41c57bc03a6998178f6cfb6b83db5837d448d1ab495c46830&=&format=webp&quality=lossless&width=1766&height=686",
    "DATA_DIR": os.path.dirname(os.path.abspath(__file__)),  # теперь корень
    "PANEL_CHANNEL_ID": 1462136361711829053,
    "TICKET_CATEGORY_ID": 1462419587835363614,
    "PAID_CATEGORY_ID": 1470779295650549885,
    "TARGET_REVIEWER_ID": 796293832751972352,
    "REVIEW_COUNT_CHANNEL": 1462074763437543435,
    "TICKET_COOLDOWN_SECONDS": 5,
    "INFO_TEMPLATE_PATH": os.path.join(os.path.dirname(os.path.abspath(__file__)), "info-o-zakaze.json"),
    "PK_FILE_PATH": os.path.join(os.path.dirname(os.path.abspath(__file__)), "pk.json"),  # если нужно, но мы вшили реквизиты
    "GUILD_ID": "1127428607606796288",
    "VOICE_CHANNEL_ID": 1464699044751478815,
    "MANAGER_ROLE_ID": 1154757071330365490,
    "PAID_NOTIFY_CHANNEL_ID": 1462418981825810535,
    # ID ролей покупателей
    "ROLE_IDS": {
        "club": 1284697274655576186,
        "bronze": 1127430321214861395,
        "silver": 1137721688683970643,
        "gold": 1184886111722545232,
        "diamond": 1195799151783461016,
        "emerald": 1208442450373513277,
        "amethyst": 1471005335111335957,
        "legendary": 1208442449425334372,
        "pka": 1208442176321626162
    },
}

# Убедимся, что корневая папка существует (она и так есть)
os.makedirs(CONFIG["DATA_DIR"], exist_ok=True)

FILES = {
    "promo": os.path.join(CONFIG["DATA_DIR"], "promo_codes.json"),
    "used_promo": os.path.join(CONFIG["DATA_DIR"], "used_promo.json"),
    "promo_txt": os.path.join(CONFIG["DATA_DIR"], "promo_codes.txt"),
    "rates": os.path.join(CONFIG["DATA_DIR"], "rates.json"),
    "last_review_id": os.path.join(CONFIG["DATA_DIR"], "last_review_id.json"),
    "review_counts": os.path.join(CONFIG["DATA_DIR"], "review_counts.json"),
}

# ----------------------------
# Logging
# ----------------------------
LOG_FILE = "bot.log"
logger = logging.getLogger("dmshop")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
fh.setFormatter(fmt)
sh = logging.StreamHandler()
sh.setFormatter(fmt)
logger.addHandler(fh)
logger.addHandler(sh)

# ----------------------------
# BOT INIT
# ----------------------------
intents = disnake.Intents.default()
intents.members = True
intents.messages = True
intents.guilds = True
bot = commands.Bot(command_prefix='/', intents=intents)

# ----------------------------
# UTILS
# ----------------------------
def load_json(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error("Ошибка загрузки JSON %s: %s", path, e)
    return default

def save_json(path: str, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Ошибка сохранения JSON %s: %s", path, e)

def write_promo_txt():
    try:
        lines = [f"{k} - {v}" for k, v in promo_codes.items()]
        with open(FILES["promo_txt"], "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        logger.exception("write_promo_txt error: %s", e)

def has_required_roles_ctx(ctx):
    author = getattr(ctx, "author", None)
    if not author or not hasattr(author, "roles"):
        return False
    return any(r.id in CONFIG["ALLOWED_ROLES"] for r in author.roles)

def clean_embed_for_discohook(embed_dict: Dict[str, Any]) -> Dict[str, Any]:
    e = dict(embed_dict)
    if "image" in e and isinstance(e["image"], dict) and "url" in e["image"]:
        e["image"] = {"url": e["image"]["url"]}
    return e

# ----------------------------
# LOAD DATA
# ----------------------------
promo_codes: Dict[str, str] = load_json(FILES["promo"], {})
used_promo: Dict[str, list] = load_json(FILES["used_promo"], {})
rates: Dict[str, float] = load_json(FILES["rates"], {"KZT": 0.14, "UAH": 1.8, "RUB": 1.0, "ROBLOX_RATE": 0.65})

write_promo_txt()
save_json(FILES["rates"], rates)
save_json(FILES["promo"], promo_codes)
save_json(FILES["used_promo"], used_promo)

# ----------------------------
# ROLE SYSTEM FOR REVIEWS
# ----------------------------
def get_roles_for_count(count: int) -> list[int]:
    roles = []
    role_ids = CONFIG["ROLE_IDS"]
    if count >= 1:
        roles.append(role_ids["club"])
    if 1 <= count <= 2:
        roles.append(role_ids["bronze"])
    elif 3 <= count <= 4:
        roles.append(role_ids["silver"])
    elif 5 <= count <= 8:
        roles.append(role_ids["gold"])
    elif 9 <= count <= 12:
        roles.append(role_ids["diamond"])
    elif 13 <= count <= 17:
        roles.append(role_ids["emerald"])
    elif 18 <= count <= 23:
        roles.append(role_ids["amethyst"])
    elif 24 <= count <= 25:
        roles.append(role_ids["legendary"])
    elif count >= 26:
        roles.append(role_ids["pka"])
    return roles

async def update_user_roles(member: disnake.Member, count: int):
    role_ids = CONFIG["ROLE_IDS"]
    all_buyer_roles = list(role_ids.values())
    target_role_ids = get_roles_for_count(count)
    current_role_ids = [r.id for r in member.roles]
    to_remove = [rid for rid in all_buyer_roles if rid in current_role_ids and rid not in target_role_ids]
    to_add = [rid for rid in target_role_ids if rid not in current_role_ids]
    guild = member.guild
    for rid in to_remove:
        role = guild.get_role(rid)
        if role:
            await member.remove_roles(role)
            logger.info(f"Снята роль {role.name} у {member} (отзывов: {count})")
    for rid in to_add:
        role = guild.get_role(rid)
        if role:
            await member.add_roles(role)
            logger.info(f"Выдана роль {role.name} пользователю {member} (отзывов: {count})")
    if to_remove or to_add:
        target_names = []
        for rid in target_role_ids:
            r = guild.get_role(rid)
            if r:
                target_names.append(r.name)
        await log_discord(
            title="🔄 Обновлены роли покупателя",
            description=(
                f"**Пользователь:** {member.mention}\n"
                f"**Отзывов:** {count}\n"
                f"**Роли после обновления:** {', '.join(target_names) if target_names else 'нет'}"
            ),
            color=0x00aaff
        )

# ----------------------------
# Discord logging helper
# ----------------------------
async def log_discord(title: str, description: str, color: int = 0x00ff00, panel: bool = False):
    try:
        ch_id = CONFIG["LOG_CHANNEL_ID_PANEL"] if panel else CONFIG["LOG_CHANNEL_ID"]
        guild = bot.get_guild(int(CONFIG["GUILD_ID"]))
        if not guild:
            logger.warning("log_discord: guild not found")
            return
        log_ch = guild.get_channel(ch_id)
        if not log_ch:
            logger.warning("log_discord: channel %s not found", ch_id)
            return
        embed = disnake.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        await log_ch.send(embed=embed)
    except Exception as e:
        logger.exception("Ошибка логирования в Discord: %s", e)

# ----------------------------
# TICKET MODALS AND VIEWS
# ----------------------------
class BuyTicketModal(Modal):
    def __init__(self):
        super().__init__(title="Создание тикета на покупку", components=[
            TextInput(label="Товар", placeholder="Введите название товара", custom_id="item_name", min_length=4, max_length=50),
            TextInput(label="Способ оплаты", placeholder="Т-Банк, СПБ и т.д.", custom_id="payment_method", min_length=3, max_length=50)
        ], custom_id="buy_ticket_modal")

    async def callback(self, inter: disnake.ModalInteraction):
        uid = inter.author.id
        now = time.time()
        last = getattr(bot, "_user_ticket_cooldowns", {})
        if uid in last and now - last[uid] < CONFIG["TICKET_COOLDOWN_SECONDS"]:
            remaining = int(CONFIG["TICKET_COOLDOWN_SECONDS"] - (now - last[uid]))
            return await inter.response.send_message(f"⏳ Подождите {remaining} сек.", ephemeral=True)
        last[uid] = now
        bot._user_ticket_cooldowns = last

        item = inter.text_values.get("item_name", "—")
        pay = inter.text_values.get("payment_method", "—")
        guild = inter.guild
        cat = guild.get_channel(CONFIG["TICKET_CATEGORY_ID"])
        if not cat:
            return await inter.response.send_message("❌ Категория не найдена", ephemeral=True)

        safe_item = item.lower().replace(" ", "-")[:80]
        channel_name = f"{safe_item}"
        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(view_channel=False),
            inter.author: disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        for rid in CONFIG["ALLOWED_ROLES"]:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        for rid in CONFIG["ALLOWED_ROLE_TICKET"]:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ticket_channel = await cat.create_text_channel(name=channel_name, overwrites=overwrites)
        view = TicketButtons()

        with open(CONFIG["INFO_TEMPLATE_PATH"], "r", encoding="utf-8") as f:
            data = json.load(f)
            embeds_list = [disnake.Embed.from_dict(e) for e in data.get("embeds", [])]

        embed_order_info = embeds_list[1] if len(embeds_list) > 1 else disnake.Embed(title="Информация о заказе", color=0x7c3131)
        embed_order_info.clear_fields()
        embed_order_info.add_field(name="> Позиция:", value=f"```{item}```", inline=True)
        embed_order_info.add_field(name="> Способ оплаты:", value=f"```{pay}```", inline=True)
        embed_order_info.add_field(name="> Промокод:", value="```Не введён```", inline=True)

        await ticket_channel.send(
            f"> Добрый день, {inter.author.mention}, ваш тикет создан. Ожидайте ответа от <@&1154757071330365490>\n"
            f"> Помните, по кнопке реквизиты вы можете получить счет и оплатить — не дожидаясь менеджера.",
            embeds=[embeds_list[0], embed_order_info],
            view=view
        )
        await inter.response.send_message(f"✅ Тикет создан: {ticket_channel.mention}", ephemeral=True)

        log_ch = guild.get_channel(CONFIG["LOG_CHANNEL_ID_PANEL"])
        if log_ch:
            await log_ch.send(embed=disnake.Embed(
                title="Тикет создан",
                description=f"{inter.author.mention} → {ticket_channel.mention}\nТовар: **{item}**\nОплата: **{pay}**",
                timestamp=datetime.utcnow(),
                color=0x00ff00
            ))


class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(
        label="ㅤㅤЗакрыть тикетㅤㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="ticket:close",
        emoji=PartialEmoji(name="image_20260110_001524", id=1459219228870578371)
    )
    async def close(self, button, inter: disnake.MessageInteraction):
        confirm = ConfirmCloseView(inter.channel)
        await inter.response.send_message("Подтвердите закрытие", view=confirm, ephemeral=True)

    @disnake.ui.button(
        label="ㅤㅤㅤㅤРеквизиты ㅤ ㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="ticket:requisites",
        emoji=PartialEmoji(name="image_20260110_001406", id=1459219370495709374),
    )
    async def requisites(self, button, inter: disnake.MessageInteraction):
        embeds_data = [
            {
                "type": "rich",
                "title": "Реквизиты к заказу ",
                "description": "\n> Выберите удобный вам способ оплаты → оплатите → подтвердите кнопкой \"Оплата\". После - ожидайте <@796293832751972352>. При наличии промокода - напишите его в лот заказа, его проверят, и назначат скидку.",
                "color": 6776679,
                "fields": [
                    {"name": "> Т-БАНК", "value": "```2200 7020 8029 9345```", "inline": True},
                    {"name": "> АльфаБанк", "value": "```2200 1545 6426 7465```", "inline": True},
                    {"name": "> ОзонБанк", "value": "```2204 3204 4881 5151 ``` ", "inline": True},
                    {"name": "> Система Быстрых Платежей [ СБП ] ", "value": "```+7 983 694 76 41 Получатель - Виктор А```", "inline": False},
                    {"name": "> \nПо оплате по KTZ | UAH | USD | TON | USDT", "value": "```Ожидать ответа продавца для удтверждения реквизитов```", "inline": False},
                    {"name": "Помните - всё проверяется, обмануть - не получится.", "value": ""}
                ],
                "image": {
                    "url": "https://cdn.discordapp.com/attachments/1223595469746475049/1524107748428615690/image.png?ex=6a4e8b73&is=6a4d39f3&hm=4466b2eb4cd27ac5c4c66c374c4059b35e12b3bef7b3941a73650327788f509c&"
                }
            },
            {
                "type": "rich",
                "title": "Быстрая оплата по QR-Коду на OZON-Банк.",
                "color": 6776679,
                "fields": [],
                "image": {
                    "url": "https://media.discordapp.net/attachments/1527006158282555412/1527179418726826044/image.png?ex=6a59b82b&is=6a5866ab&hm=7c18b8d4df703ae4a509c7855b9d3ead331bf16597547ca9184ef543395cfcc9&=&format=webp&quality=lossless&width=1870&height=727"
                },
                "description": "> В данном QR-Коде, заранее выставлена оплата на Ozon-Банк. Вам достаточно выбрать с какого банка перевести, и сумму перевода."
            }
        ]
        embeds = [disnake.Embed.from_dict(clean_embed_for_discohook(e)) for e in embeds_data]
        await inter.response.send_message(embeds=embeds)
        await log_discord(
            title="Просмотр содержимого `Реквизиты`",
            description=f"Пользователь {inter.author.mention} нажал кнопку реквизитов",
            color=0x00ff00
        )

    @disnake.ui.button(
        label="ㅤㅤㅤ  Оплатитьㅤㅤㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="ticket:pay",
        emoji=PartialEmoji(name="image_20260110_001406", id=1459219370495709374),
        row=1
    )
    async def pay(self, button, inter: disnake.MessageInteraction):
        if not any(r.id in CONFIG["ALLOWED_ROLES"] for r in inter.author.roles):
            return await inter.response.send_message("⛔ Нет прав", ephemeral=True)

        msg = inter.message
        if not msg.embeds or len(msg.embeds) < 2:
            return await inter.response.send_message("❌ Второй embed не найден", ephemeral=True)

        desc = msg.embeds[1].description or ""
        if "Статус - Заказ оплачен" in desc:
            return await inter.response.send_message("Заказ уже оплачен.", ephemeral=True)

        order_embed = msg.embeds[1]
        item_name = "—"
        payment_method = "—"
        promo_value = "—"
        for field in order_embed.fields:
            fn = field.name.lower()
            if "позиция" in fn:
                item_name = field.value.strip("`\n ")
            elif "оплаты" in fn:
                payment_method = field.value.strip("`\n ")
            elif "промокод" in fn:
                promo_value = field.value.strip("`\n ")

        ed = order_embed.to_dict()
        ed["color"] = 0x676767
        ed["description"] = (
            "Статус - Заказ оплачен\n"
            f"> Подтверждено: {inter.author.mention}\n"
            f"> Время: <t:{int(time.time())}:f>"
        )
        new_view = TicketButtonsPaid()

        await msg.edit(
            embeds=[msg.embeds[0], disnake.Embed.from_dict(ed)],
            view=new_view
        )

        paid_category = inter.guild.get_channel(CONFIG["PAID_CATEGORY_ID"])
        if paid_category:
            await inter.channel.edit(category=paid_category)
        else:
            logger.warning("PAID_CATEGORY_ID not found: %s", CONFIG["PAID_CATEGORY_ID"])

        manager_role = inter.guild.get_role(CONFIG["MANAGER_ROLE_ID"])
        manager_ping = manager_role.mention if manager_role else "@менеджер"
        await inter.channel.send(
            f"💚 {manager_ping} — заказ подтверждён как **оплаченный**!\n"
            f"> Подтвердил: {inter.author.mention}"
        )

        await inter.response.send_message("✅ Заказ отмечен как оплаченный.", ephemeral=True)

        await log_discord(
            title="💰 Заказ оплачен",
            description=(
                f"**Канал:** {inter.channel.mention}\n"
                f"**Товар:** {item_name}\n"
                f"**Оплата:** {payment_method}\n"
                f"**Промокод:** {promo_value}\n"
                f"**Подтвердил:** {inter.author.mention}"
            ),
            color=0x2ecc71
        )

    @disnake.ui.button(
        label="ㅤㅤㅤㅤПромокодㅤㅤㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="ticket:promo",
        emoji=PartialEmoji(name="image_20260110_001407", id=1459219251775799511),
        row=1
    )
    async def promo(self, button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(PromoCodeModal(inter.message))


class TicketButtonsPaid(View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(
        label="ㅤㅤЗакрыть тикетㅤㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="ticket_paid:close",
        emoji=PartialEmoji(name="image_20260110_001524", id=1459219228870578371)
    )
    async def close(self, button, inter: disnake.MessageInteraction):
        confirm = ConfirmCloseView(inter.channel)
        await inter.response.send_message("Подтвердите закрытие", view=confirm, ephemeral=True)

    @disnake.ui.button(
        label="ㅤㅤㅤㅤРеквизиты ㅤ ㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="ticket_paid:requisites",
        emoji=PartialEmoji(name="image_20260110_001406", id=1459219370495709374),
    )
    async def requisites(self, button, inter: disnake.MessageInteraction):
        embeds_data = [
            {
                "type": "rich",
                "title": "Реквизиты к заказу ",
                "description": "\n> Выберите удобный вам способ оплаты → оплатите → подтвердите кнопкой \"Оплата\". После - ожидайте <@796293832751972352>. При наличии промокода - напишите его в лот заказа, его проверят, и назначат скидку.",
                "color": 6776679,
                "fields": [
                    {"name": "> Т-БАНК", "value": "```2200 7020 8029 9345```", "inline": True},
                    {"name": "> АльфаБанк", "value": "```2200 1545 6426 7465```", "inline": True},
                    {"name": "> ОзонБанк", "value": "```2204 3204 4881 5151 ``` ", "inline": True},
                    {"name": "> Система Быстрых Платежей [ СБП ] ", "value": "```+7 983 694 76 41 Получатель - Виктор А```", "inline": False},
                    {"name": "> \nПо оплате по KTZ | UAH | USD | TON | USDT", "value": "```Ожидать ответа продавца для удтверждения реквизитов```", "inline": False},
                    {"name": "Помните - всё проверяется, обмануть - не получится.", "value": ""}
                ],
                "image": {
                    "url": "https://cdn.discordapp.com/attachments/1223595469746475049/1524107748428615690/image.png?ex=6a4e8b73&is=6a4d39f3&hm=4466b2eb4cd27ac5c4c66c374c4059b35e12b3bef7b3941a73650327788f509c&"
                }
            },
            {
                "type": "rich",
                "title": "Быстрая оплата по QR-Коду на OZON-Банк.",
                "color": 6776679,
                "fields": [],
                "image": {
                    "url": "https://media.discordapp.net/attachments/1527006158282555412/1527179418726826044/image.png?ex=6a59b82b&is=6a5866ab&hm=7c18b8d4df703ae4a509c7855b9d3ead331bf16597547ca9184ef543395cfcc9&=&format=webp&quality=lossless&width=1870&height=727"
                },
                "description": "> В данном QR-Коде, заранее выставлена оплата на Ozon-Банк. Вам достаточно выбрать с какого банка перевести, и сумму перевода."
            }
        ]
        embeds = [disnake.Embed.from_dict(clean_embed_for_discohook(e)) for e in embeds_data]
        await inter.response.send_message(embeds=embeds)

    @disnake.ui.button(
        label="ㅤㅤㅤ  Оплатитьㅤㅤㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="ticket_paid:paid_done",
        emoji=PartialEmoji(name="image_20260110_001406", id=1459219370495709374),
        row=1,
        disabled=True
    )
    async def paid_done(self, button, inter: disnake.MessageInteraction):
        await inter.response.send_message("Заказ уже оплачен.", ephemeral=True)

    @disnake.ui.button(
        label="ㅤㅤㅤㅤПромокодㅤㅤㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="ticket:promo",
        emoji=PartialEmoji(name="image_20260110_001407", id=1459219251775799511),
        row=1
    )
    async def promo(self, button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(PromoCodeModal(inter.message))


class ConfirmCloseView(View):
    def __init__(self, channel):
        super().__init__(timeout=60)
        self.channel = channel

    @disnake.ui.button(
        label="Подтвердить закрытие",
        style=disnake.ButtonStyle.gray,
        custom_id="confirm:close",
        emoji=PartialEmoji(name="image_20260110_001524", id=1459219228870578371)
    )
    async def confirm(self, button, inter: disnake.MessageInteraction):
        await inter.response.send_message("Тикет удаляется...", ephemeral=True)
        await asyncio.sleep(2)
        await self.channel.delete()
        await log_discord(
            title="Тикет закрыт",
            description=f"Пользователь {inter.author.mention} закрыл тикет",
            color=0xff6600
        )


class PromoCodeModal(Modal):
    def __init__(self, msg):
        self.msg = msg
        super().__init__(title="Активация промокода", components=[
            TextInput(label="Введите промокод", custom_id="promo_code", placeholder="Например VSEMPROMO25",
                      min_length=2, max_length=50)
        ], custom_id="promo_modal")

    async def callback(self, inter: disnake.ModalInteraction):
        code = inter.text_values.get("promo_code", "").strip().upper()
        if not code:
            return await inter.response.send_message("Пустой код", ephemeral=True)
        if code not in promo_codes:
            return await inter.response.send_message("❌ Неверный промокод", ephemeral=True)

        uid = str(inter.author.id)
        used = used_promo.get(uid, [])
        if code in used:
            return await inter.response.send_message("⚠️ Вы уже использовали этот промокод", ephemeral=True)
        used.append(code)
        used_promo[uid] = used
        save_json(FILES["used_promo"], used_promo)

        if len(self.msg.embeds) > 1:
            ed = self.msg.embeds[1].to_dict()
            for f in ed.get("fields", []):
                if "промокод" in f.get("name", "").lower():
                    f["value"] = f"```{code} — {promo_codes[code]}```"
            await self.msg.edit(embeds=[self.msg.embeds[0], disnake.Embed.from_dict(ed)])
        await inter.response.send_message(f"✅ Промокод `{code}` активирован! Скидка: **{promo_codes[code]}**", ephemeral=True)
        await log_discord(
            title="Промокод активирован",
            description=f"Пользователь {inter.author.mention} активировал: `{code}` → {promo_codes[code]}",
            color=0x00ff00
        )


class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(
        label="ㅤㅤКупитьㅤㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="panel:buy",
        emoji=PartialEmoji(name="image_20260110_0014062", id=1459219275934863402)
    )
    async def buy(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(BuyTicketModal())
        await log_discord(
            title="Создание тикета",
            description=f"Пользователь {inter.author.mention} нажал кнопку «Купить»",
            color=0x00ff00
        )

    @disnake.ui.button(
        label="ㅤПромокодыㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="panel:promo",
        emoji=PartialEmoji(name="image_20260110_001407", id=1459219251775799511)
    )
    async def promo(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        text = "🎟️ Следи за новостями в <#1462070136856117258>\n\n"
        await inter.response.send_message(text, ephemeral=True)
        await log_discord(
            title="Просмотр `Промокоды`",
            description=f"Пользователь {inter.author.mention} нажал кнопку",
            color=0x00ff00
        )

    @disnake.ui.button(
        label="ㅤОплатаㅤ",
        style=disnake.ButtonStyle.gray,
        custom_id="panel:payinfo",
        emoji=PartialEmoji(name="image_20260110_001406", id=1459219370495709374)
    )
    async def payinfo(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_message("💳 Доступна оплата валютами: RUB | KZT | UAH | USD | USDT | TON", ephemeral=True)
        await log_discord(
            title="Просмотр `Оплата`",
            description=f"Пользователь {inter.author.mention} нажал кнопку",
            color=0x00ff00
        )

# ----------------------------
# REVIEW COUNTER + BANNER
# ----------------------------
async def update_review_counter():
    try:
        text_ch = bot.get_channel(CONFIG["REVIEW_COUNT_CHANNEL"])
        if not text_ch:
            text_ch = await bot.fetch_channel(CONFIG["REVIEW_COUNT_CHANNEL"])
        if not text_ch:
            logger.warning("update_review_counter: review channel not found")
            return
        count = 1431
        async for m in text_ch.history(limit=None):
            count += 1
        logger.info("Review count: %s", count)
        await update_server_banner(count)
    except Exception as e:
        logger.exception("update_review_counter error: %s", e)
        await log_discord("Ошибка обновления счётчика отзывов", str(e), color=0xff0000)

async def update_server_banner(review_count: int):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.join(script_dir, "banner.png")
        output_path = os.path.join(script_dir, "banner_ready.png")
        font_path = os.path.join(script_dir, "ProximaNova-ExtraBold.ttf")

        if not os.path.exists(base_path):
            logger.warning("Banner file not found: %s", base_path)
            return
        if not os.path.exists(font_path):
            logger.warning("Font file not found: %s", font_path)
            return

        img = Image.open(base_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path, 400)
        text = str(review_count)
        draw.text((594, 540), text, font=font, fill=(255, 255, 255), anchor="mm")
        img.save(output_path)

        guild = bot.get_guild(int(CONFIG["GUILD_ID"]))
        if not guild:
            logger.warning("update_server_banner: guild not found")
            return
        with open(output_path, "rb") as f:
            await guild.edit(banner=f.read())
        logger.info("Banner updated with %s reviews", review_count)
        await log_discord("Баннер обновлён", f"Отзывов: **{review_count}**", color=0x00aaff)
    except Exception as e:
        logger.exception("Banner update error: %s", e)
        await log_discord("Ошибка обновления баннера", str(e), color=0xff0000)

@tasks.loop(hours=24)
async def review_counter_task():
    await bot.wait_until_ready()
    await update_review_counter()

@bot.event
async def on_message(message: disnake.Message):
    if message.author.bot:
        return
    if message.channel.id == CONFIG["REVIEW_COUNT_CHANNEL"]:
        counts = load_json(FILES["review_counts"], {})
        user_id = str(message.author.id)
        counts[user_id] = counts.get(user_id, 0) + 1
        save_json(FILES["review_counts"], counts)
        if isinstance(message.author, disnake.Member):
            await update_user_roles(message.author, counts[user_id])
        bot.loop.create_task(update_review_counter())
    await bot.process_commands(message)

async def keep_voice_alive():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            guild = bot.get_guild(int(CONFIG["GUILD_ID"]))
            if guild:
                vc = guild.voice_client
                if not vc or not vc.is_connected():
                    try:
                        voice_channel = guild.get_channel(CONFIG["VOICE_CHANNEL_ID"])
                        if not voice_channel:
                            voice_channel = await bot.fetch_channel(CONFIG["VOICE_CHANNEL_ID"])
                        if voice_channel and isinstance(voice_channel, disnake.VoiceChannel):
                            await voice_channel.connect()
                            logger.info("Подключился к голосовому каналу: %s", voice_channel.name)
                    except Exception as e:
                        logger.debug("keep_voice_alive connect failed: %s", e)
        except Exception as e:
            logger.exception("keep_voice_alive loop error: %s", e)
        await asyncio.sleep(60)

async def ensure_panel():
    await bot.wait_until_ready()
    chan = bot.get_channel(CONFIG["PANEL_CHANNEL_ID"])
    if not chan:
        chan = await bot.fetch_channel(CONFIG["PANEL_CHANNEL_ID"])
    if not chan or not isinstance(chan, disnake.TextChannel):
        logger.warning("Panel channel not found")
        return
    while not bot.is_closed():
        try:
            panel_msg = None
            async for m in chan.history(limit=50):
                if m.author == bot.user and m.components:
                    panel_msg = m
                    break
            if not panel_msg:
                embed = disnake.Embed(color=disnake.Color(0x676767))
                embed.set_image(url=CONFIG["EMBED_IMAGE_URL"])
                sent_msg = await chan.send(embed=embed, view=TicketPanelView())
                bot.add_view(TicketPanelView(), message_id=sent_msg.id)
                await log_discord("Панель отправлена", f"Сообщение {sent_msg.id} отправлено заново", color=0x00ff00)
                logger.info("Panel message sent %s", sent_msg.id)
        except Exception as e:
            logger.exception("ensure_panel error: %s", e)
        await asyncio.sleep(7200)

@bot.event
async def on_disconnect():
    logger.warning("Bot disconnected from gateway")

@bot.event
async def on_resumed():
    logger.info("Bot resumed connection to gateway")

@bot.event
async def on_error(event, *args, **kwargs):
    logger.exception("Unhandled exception in event %s", event)

# ----------------------------
# ADMIN COMMANDS
# ----------------------------
def log_command(func):
    @functools.wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        try:
            guild = ctx.guild or bot.get_guild(int(CONFIG["GUILD_ID"]))
            if guild:
                log_ch = guild.get_channel(CONFIG["LOG_CHANNEL_ID_PANEL"])
                if log_ch:
                    embed = disnake.Embed(
                        title="Лог команды",
                        description=f"Команда: `{func.__name__}`\nПользователь: {ctx.author} ({ctx.author.id})\nКанал: {getattr(ctx.channel, 'mention', 'dm')}",
                        timestamp=datetime.utcnow(),
                        color=0x2f3136
                    )
                    await log_ch.send(embed=embed)
        except Exception as e:
            logger.exception("Ошибка в log_command: %s", e)
        try:
            return await func(ctx, *args, **kwargs)
        except Exception as e:
            logger.exception("Ошибка выполнения команды %s: %s", func.__name__, e)
            try:
                await ctx.send("Произошла ошибка при выполнении команды.", ephemeral=True)
            except Exception:
                pass
    return wrapper

@bot.slash_command(
    name="set_rate",
    description="Установить курс/коэффициент (админ)",
    default_member_permissions=disnake.Permissions(administrator=True)
)
@log_command
async def set_rate(ctx, имя: str, коэффициент: float):
    имя = имя.upper()
    rates[имя] = float(коэффициент)
    save_json(FILES["rates"], rates)
    await ctx.send(f"✅ Установлено: {имя} → {коэффициент}", ephemeral=True)
    await log_discord("Изменён курс/коэффициент", f"{ctx.author.mention} установил {имя} → {коэффициент}", color=0x00ff00)

@bot.slash_command(
    name="get_rates",
    description="Показать текущие курсы",
    default_member_permissions=disnake.Permissions(administrator=True)
)
@log_command
async def get_rates(ctx):
    embed = disnake.Embed(title="Курсы / коэффициенты", description=json.dumps(rates, ensure_ascii=False, indent=2))
    await ctx.send(embed=embed, ephemeral=True)

@bot.slash_command(
    name="say",
    description="Отправить сообщение от лица бота (текст или embed)",
    default_member_permissions=disnake.Permissions(administrator=True)
)
@log_command
async def say(
    ctx,
    канал: disnake.TextChannel,
    тип_сообщения: str = commands.Param(
        name="тип_сообщения",
        description="Выберите тип сообщения",
        choices=["text", "embed"]
    ),
    текст: Optional[str] = None,
    файл: Optional[disnake.Attachment] = None
):
    if тип_сообщения == "text":
        if not текст:
            return await ctx.send("Введите текст для отправки.", ephemeral=True)
        await канал.send(текст)
        await ctx.send("✅ Сообщение отправлено", ephemeral=True)
        await log_discord("Say: текст отправлен", f"{ctx.author.mention} → {канал.mention}", color=0x00ff00)
        return

    if тип_сообщения == "embed":
        if not текст and not файл:
            return await ctx.send("Укажите JSON текст или файл с JSON для embed.", ephemeral=True)
        if текст and файл:
            return await ctx.send("Только один источник: либо текст JSON, либо файл.", ephemeral=True)
        try:
            if файл:
                raw = await файл.read()
                data = json.loads(raw.decode("utf-8"))
            else:
                data = json.loads(текст)
            if "embeds" not in data:
                return await ctx.send("Нет поля 'embeds' в JSON.", ephemeral=True)
            embeds = [disnake.Embed.from_dict(clean_embed_for_discohook(e)) for e in data["embeds"]]
            content = data.get("content", " ")
            await канал.send(content=content, embeds=embeds)
            await ctx.send("✅ Embed отправлен", ephemeral=True)
            await log_discord("Say: embed отправлен", f"{ctx.author.mention} → {канал.mention}")
        except Exception as e:
            logger.exception("say embed error: %s", e)
            await ctx.send("❌ Ошибка при отправке embed.", ephemeral=True)

@bot.slash_command(
    name="get_json",
    description="Получить JSON из сообщения по ссылке",
    default_member_permissions=disnake.Permissions(administrator=True)
)
@log_command
async def get_json(ctx, message_link: str):
    try:
        parts = message_link.strip("/").split("/")
        guild_id, channel_id, message_id = map(int, parts[-3:])
    except Exception:
        return await ctx.send("Неверная ссылка.", ephemeral=True)
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        msg = await channel.fetch_message(message_id)
    except Exception as e:
        return await ctx.send(f"Ошибка получения сообщения: {e}", ephemeral=True)
    payload = {"content": msg.content if msg.content else " ", "embeds": [clean_embed_for_discohook(e.to_dict()) for e in msg.embeds]}
    buf = io.StringIO(json.dumps(payload, ensure_ascii=False, indent=2))
    await ctx.response.send_message(file=disnake.File(fp=buf, filename="message.json"), ephemeral=True)
    await log_discord("get_json", f"{ctx.author.mention} выгрузил JSON из {channel.mention}", color=0x00ff00)

@bot.slash_command(name="promo_add", description="Добавить промокод (админ)", default_member_permissions=disnake.Permissions(administrator=True))
@log_command
async def promo_add(ctx, code: str, value: str):
    code = code.upper()
    promo_codes[code] = value
    save_json(FILES["promo"], promo_codes)
    write_promo_txt()
    await ctx.send(f"✅ Промокод `{code}` добавлен → {value}", ephemeral=True)
    await log_discord("Промокод добавлен", f"{ctx.author.mention} добавил `{code}` → {value}", color=0x00ff00)

@bot.slash_command(name="promo_remove", description="Удалить промокод (админ)", default_member_permissions=disnake.Permissions(administrator=True))
@log_command
async def promo_remove(ctx, code: str):
    code = code.upper()
    if code in promo_codes:
        promo_codes.pop(code)
        save_json(FILES["promo"], promo_codes)
        write_promo_txt()
        await ctx.send(f"✅ Промокод `{code}` удалён", ephemeral=True)
        await log_discord("Промокод удалён", f"{ctx.author.mention} удалил `{code}`", color=0x00ff00)
    else:
        await ctx.send("❌ Нет такого промокода", ephemeral=True)

@bot.slash_command(name="promo_list", description="Список промокодов", default_member_permissions=disnake.Permissions(administrator=True))
@log_command
async def promo_list(ctx):
    if not promo_codes:
        return await ctx.send("Промокодов нет.", ephemeral=True)
    text = "\n".join([f"{k} → {v}" for k, v in promo_codes.items()])
    await ctx.send(f"```\n{text}\n```", ephemeral=True)

@bot.slash_command(
    name="расчет",
    description="Рассчитать итоговую цену со скидкой",
    default_member_permissions=disnake.Permissions(administrator=True)
)
async def расчет(ctx, цена: float, скидка: float):
    await ctx.response.defer(ephemeral=True)
    try:
        if скидка < 0 or скидка > 100:
            return await ctx.edit_original_response(content="❌ Скидка должна быть от 0 до 100%")
        итог = цена - (цена * (скидка / 100))
        экономия = цена - итог
        embed = disnake.Embed(title="💰 Расчёт скидки", color=0x2ecc71)
        embed.add_field(name="Исходная цена", value=f"`{цена:.2f} ₽`", inline=True)
        embed.add_field(name="Скидка", value=f"`{скидка}%`", inline=True)
        embed.add_field(name="Экономия", value=f"`{экономия:.2f} ₽`", inline=True)
        embed.add_field(name="✅ Итого к оплате", value=f"**`{итог:.2f} ₽`**", inline=False)
        await ctx.edit_original_response(embed=embed)
    except Exception as e:
        await ctx.edit_original_response(content=f"Ошибка: {e}")

@bot.slash_command(
    name="обновить_баннер",
    description="Принудительно обновить баннер сервера (счётчик отзывов)",
    default_member_permissions=disnake.Permissions(administrator=True)
)
async def обновить_баннер(ctx):
    await ctx.response.defer(ephemeral=True)
    await update_review_counter()
    await ctx.edit_original_response(content="✅ Баннер обновлён!")

@bot.slash_command(
    name="пересчитать_отзывы",
    description="Пересчитать все сообщения в канале отзывов и обновить роли (админ)",
    default_member_permissions=disnake.Permissions(administrator=True)
)
async def пересчитать_отзывы(ctx: disnake.ApplicationCommandInteraction):
    await ctx.response.defer(ephemeral=True)
    channel_id = CONFIG["REVIEW_COUNT_CHANNEL"]
    channel = bot.get_channel(channel_id)
    if not channel:
        channel = await bot.fetch_channel(channel_id)
    if not channel or not isinstance(channel, disnake.TextChannel):
        return await ctx.edit_original_response(content="❌ Канал отзывов не найден.")
    counts = {}
    try:
        async for message in channel.history(limit=None):
            if message.author.bot:
                continue
            uid = str(message.author.id)
            counts[uid] = counts.get(uid, 0) + 1
    except Exception as e:
        logger.exception("Ошибка при чтении истории канала: %s", e)
        return await ctx.edit_original_response(content=f"❌ Ошибка при чтении истории: {e}")
    if not counts:
        return await ctx.edit_original_response(content="ℹ️ В канале отзывов нет сообщений от пользователей.")
    save_json(FILES["review_counts"], counts)
    guild = ctx.guild or bot.get_guild(int(CONFIG["GUILD_ID"]))
    if not guild:
        return await ctx.edit_original_response(content="❌ Сервер не найден.")
    updated = 0
    for uid_str, count in counts.items():
        uid = int(uid_str)
        member = guild.get_member(uid)
        if member:
            await update_user_roles(member, count)
            updated += 1
        else:
            logger.warning(f"Пользователь {uid} не найден на сервере при пересчёте.")
    await update_review_counter()
    await ctx.edit_original_response(
        content=f"✅ Пересчёт завершён!\n"
                f"Всего пользователей с отзывами: {len(counts)}\n"
                f"Обновлено ролей у пользователей на сервере: {updated}"
    )
    await log_discord(
        title="📊 Пересчёт отзывов",
        description=f"Админ {ctx.author.mention} запустил пересчёт.\n"
                    f"Всего записей: {len(counts)}, обновлено ролей: {updated}",
        color=0x00aaff
    )

# ----------------------------
# CONSUMER COMMANDS
# ----------------------------
@bot.slash_command(name="robux", description="Рассчитать цену робуксов")
async def robux(ctx, кол_во: int):
    await ctx.response.defer()
    try:
        if кол_во < 200:
            return await ctx.edit_original_response(content="Минимум 200 робуксов.")
        ROBLOX_RATE = float(rates.get("ROBLOX_RATE", 0.65))
        purchase_price = кол_во * ROBLOX_RATE
        place_amount = кол_во / 0.7
        place_amount_int = int(place_amount + 0.5)
        await ctx.edit_original_response(
            content=f"- Цена: {purchase_price:.2f} ₽\n- Нужно поставить: {place_amount_int} робуксов"
        )
        await log_discord("robux", f"{ctx.author.mention} запросил {кол_во} робуксов → {purchase_price:.2f} ₽")
    except Exception as e:
        logger.exception("robux error: %s", e)
        await ctx.edit_original_response(content=f"Ошибка расчёта: {e}")

@bot.slash_command(name="steam", description="Рассчитать цену Steam-пополнения")
async def steam(
    ctx,
    сумма_пополнения: int = commands.Param(description="Сумма пополнения"),
    валюта: str = commands.Param(description="Выберите валюту", choices=["RUB", "USD", "UAH", "KZT"])
):
    await ctx.response.defer()
    try:
        валюта = валюта.upper()
        if валюта not in rates:
            return await ctx.edit_original_response(content=f"❌ Неизвестная валюта {валюта}")
        rub_price = сумма_пополнения * float(rates[валюта])
        await ctx.edit_original_response(
            content=f"{сумма_пополнения} {валюта} = **{rub_price:.2f} ₽** (курс {rates[валюта]})"
        )
        await log_discord("steam", f"{ctx.author.mention} запросил {сумма_пополнения} {валюта} → {rub_price:.2f} ₽")
    except Exception as e:
        logger.exception("steam error: %s", e)
        await ctx.edit_original_response(content=f"Ошибка расчёта: {e}")

# ---------------------------- MENU PANEL ----------------------------
MENU_CHANNEL_ID = 1462140026073776280
MENU_OPTIONS = [
    {"label": "・BuyAll", "description": "Покупка всего ・Всё в одном месте",
     "emoji": "<:buyall:1489833017047253032> ", "json_path": "catalog/menu_buyall.json"},
    {"label": "・Discord", "description": "Покупка Nitro и Boosts ・Статус и величие",
     "emoji": "<:Discord:1464831837300854936>", "json_path": "catalog/menu_discord.json"},
    {"label": "・Steam", "description": "Пополнение и очки ・Свобода к играм",
     "emoji": "<:Steam:1464833200416100402>", "json_path": "catalog/menu_steam.json"},
    {"label": "・Telegram", "description": "Звезды и Подарки ・Индивидуальность и защита",
     "emoji": "<:Telegram:1465720888677896314>", "json_path": "catalog/menu_telegram.json"},
    {"label": "・Украшение Discord", "description": "Украшения и Бейджики ・Изысканность и красота",
     "emoji": "<:Decoration:1465729329290936403>", "json_path": "catalog/menu_decoration.json"},
    {"label": "・Roblox", "description": "Донат и Помощь ・Красота и играбельность",
     "emoji": "<:Roblox:1465752155251150911>", "json_path": "catalog/menu_roblox.json"},
    {"label": "・Epic Games", "description": "Фортнайт и Аккаунт ・ Заработок и донат",
     "emoji": "<:EpicGames:1465765441887797248>", "json_path": "catalog/menu_epic.json"},
    {"label": "・Supercell", "description": "Brawl Stars и Clash Royale ・Динамика и богатство",
     "emoji": "<:SuperCell:1465768886484996260>", "json_path": "catalog/menu_supersell.json"},
    {"label": "・Spotify", "description": "Подписка на музыку ・Громкость и красочность",
     "emoji": "<:Spotify:1465770796411785330>", "json_path": "catalog/menu_spotify.json"},
    {"label": "・Дизайн", "description": "Отличный дизайн ・Выбор для лучших",
     "emoji": "<:Design:1465771436580012106>", "json_path": "catalog/menu_design.json"},
    {"label": "・Бот для Дискорда", "description": "Рабочий и легкий ・Плавность и скорость",
     "emoji": "<:Bot:1465771816080380109>", "json_path": "catalog/menu_bot.json"},
]
class MenuSelect(disnake.ui.StringSelect):
    def __init__(self):
        options = [
            disnake.SelectOption(
                label=item["label"],
                description=item["description"],
                emoji=item["emoji"],
                value=item["json_path"]
            ) for item in MENU_OPTIONS
        ]
        super().__init__(
            placeholder="Выберите категорию...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="menu_select"
        )

    async def callback(self, inter: disnake.MessageInteraction):
        json_path = self.values[0]
        try:
            if not os.path.exists(json_path):
                return await inter.response.send_message("Файл с embed не найден.", ephemeral=True)
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            embeds = [disnake.Embed.from_dict(clean_embed_for_discohook(e)) for e in data.get("embeds", [])]
            view = disnake.ui.View(timeout=None)
            view.add_item(disnake.ui.Button(
                label="Перейти в канал покупки",
                style=disnake.ButtonStyle.link,
                url="https://discord.com/channels/1127428607606796288/1462136361711829053"
            ))
            await inter.response.send_message(embeds=embeds, view=view, ephemeral=True)
        except Exception as e:
            logger.exception("MenuSelect callback error: %s", e)

class MenuView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuSelect())

@bot.event
async def on_interaction(inter):
    if isinstance(inter, disnake.MessageInteraction):
        if inter.data.get("custom_id") == "menu:buy_ticket":
            await inter.response.send_modal(BuyTicketModal())

async def send_menu_panel():
    await bot.wait_until_ready()
    channel = bot.get_channel(MENU_CHANNEL_ID)
    if not channel:
        channel = await bot.fetch_channel(MENU_CHANNEL_ID)
    if not channel:
        logger.warning("Menu panel channel not found")
        return
    existing_msg = None
    async for m in channel.history(limit=50):
        if m.author == bot.user and m.components:
            existing_msg = m
            break
    if existing_msg:
        return
    embed_path = "catalog/menu_embed.json"
    embed = disnake.Embed(title="Меню выбора", description="Выберите категорию", color=0x0499D2)
    if os.path.exists(embed_path):
        with open(embed_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            embed = disnake.Embed.from_dict(data["embeds"][0])
    msg = await channel.send(embed=embed, view=MenuView())
    bot.add_view(MenuView())

# ----------------------------
# on_ready
# ----------------------------
@bot.event
async def on_ready():
    try:
        await bot.change_presence(activity=disnake.Game(name="Diamond Shop"))
        bot.add_view(TicketPanelView())
        bot.add_view(TicketButtons())
        bot.add_view(TicketButtonsPaid())
        bot.add_view(MenuView())
        bot.loop.create_task(send_menu_panel())
        bot.loop.create_task(ensure_panel())
        bot.loop.create_task(keep_voice_alive())
        if not review_counter_task.is_running():
            review_counter_task.start()
        await update_review_counter()
        # Обновление ролей для всех при запуске
        try:
            guild = bot.get_guild(int(CONFIG["GUILD_ID"]))
            if guild:
                counts = load_json(FILES["review_counts"], {})
                for user_id_str, count in counts.items():
                    user_id = int(user_id_str)
                    member = guild.get_member(user_id)
                    if member:
                        await update_user_roles(member, count)
                    else:
                        logger.warning(f"Пользователь {user_id} не найден на сервере при запуске")
        except Exception as e:
            logger.exception("Ошибка обновления ролей при старте: %s", e)
        logger.info("%s is ready", bot.user)
        await log_discord("✅ Бот запустился", f"{bot.user} готов и онлайн", color=0x00ff00)
    except Exception as e:
        logger.exception("on_ready error: %s", e)

# ----------------------------
# Run the bot
# ----------------------------
if __name__ == "__main__":
    if not CONFIG["BOT_TOKEN"]:
        logger.error("BOT_TOKEN не установлен в переменных окружения")
        print("❌ Ошибка: не найден BOT_TOKEN. Установите переменную BOT_TOKEN.")
        sys.exit(1)
    try:
        bot.run(CONFIG["BOT_TOKEN"])
    except Exception as e:
        logger.exception("Failed to run bot: %s", e)
        raise
