import asyncio
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
import os

# ========== НАСТРОЙКИ ==========
TOKEN = os.getenv("BOT_TOKEN", "СЮДА_ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER")
MIN_PREDICTIONS = 3          # показывать только матчи, где ≥ N прогнозов
# ===============================

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

BASE_API = "https://stavka.tv/api/v2"

MONTHS_RU = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "май", 6: "июн",
    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"
}


async def fetch_json(url: str, params: dict = None) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


async def get_matches(sport: str, limit: int = 30) -> list:
    data = await fetch_json(f"{BASE_API}/matches", {
        "sport": sport,
        "status": "upcoming",
        "limit": limit
    })
    if not data:
        return []
    return data.get("data", [])


async def get_aggregated_bets(slug: str) -> dict | None:
    return await fetch_json(f"{BASE_API}/matches/{slug}/aggregated-bets")


async def get_popular_bets(slug: str) -> dict | None:
    return await fetch_json(f"{BASE_API}/matches/{slug}/popular-bets")


def format_date(iso_date: str) -> str:
    """Превращает 2026-10-05T14:00:00+00:00 → 05 окт 14:00"""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        # Переводим в МСК (UTC+3)
        dt = dt + timedelta(hours=3)
        day = dt.day
        month = MONTHS_RU.get(dt.month, str(dt.month))
        time_str = dt.strftime("%H:%M")
        return f"{day:02d} {month} {time_str}"
    except Exception:
        return iso_date[11:16] if len(iso_date) > 16 else iso_date


def progress_bar(percent: int, width: int = 12) -> str:
    """Красивый прогресс-бар"""
    filled = round(percent / 100 * width)
    return "▓" * filled + "░" * (width - filled)


def format_user_opinion(aggregated: dict | None, popular: dict | None, home: str, away: str, date_str: str) -> str:
    lines = [
        f"<b>📊 Пользовательское мнение</b>",
        f"<b>{home} — {away}</b>",
        f"📅 {date_str}",
        ""
    ]

    total_predictions = 0

    if aggregated and "data" in aggregated:
        all_groups = aggregated["data"].get("all") or aggregated["data"].get("capper") or []

        for group in all_groups:
            group_name = group.get("group")
            bets_count = group.get("betsCount", 0)
            if bets_count == 0:
                continue

            total_predictions = max(total_predictions, bets_count)

            if group_name == "one_two":
                lines.append(f"<b>🏆 Победитель матча</b> · {bets_count} прогнозов")
                uni = group.get("univariate") or []
                total = sum(item.get("count", 0) for item in uni) or 1
                for item in uni:
                    outcome = item.get("outcome")
                    count = item.get("count", 0)
                    pct = round(count / total * 100) if total else 0
                    name = "П1" if outcome == "w1" else "П2"
                    bar = progress_bar(pct)
                    lines.append(f"<code>{name}</code>  {bar}  <b>{pct}%</b> ({count})")
                lines.append("")

            elif group_name == "total":
                lines.append(f"<b>📈 Тотал</b> · {bets_count} прогнозов")
                bivariate = group.get("bivariate") or []
                for pair in bivariate:
                    for item in pair:
                        t = item.get("type", "")
                        out = str(item.get("outcome", "")).replace("_", ".")
                        count = item.get("count", 0)
                        pct = round(count / bets_count * 100) if bets_count else 0
                        name = "ТМ" if "under" in t else "ТБ"
                        bar = progress_bar(pct)
                        lines.append(f"<code>{name} ({out})</code>  {bar}  <b>{pct}%</b> ({count})")
                lines.append("")

            elif group_name == "handicap":
                lines.append(f"<b>⚖️ Форы</b> · {bets_count} прогнозов")
                bivariate = group.get("bivariate") or []
                for pair in bivariate:
                    for item in pair:
                        t = item.get("type", "")
                        out = str(item.get("outcome", "")).replace("_", ".")
                        count = item.get("count", 0)
                        pct = round(count / bets_count * 100) if bets_count else 0
                        name = "Ф1" if "handicap1" in t else "Ф2"
                        bar = progress_bar(pct)
                        lines.append(f"<code>{name} ({out})</code>  {bar}  <b>{pct}%</b> ({count})")
                lines.append("")

            elif group_name == "correct_score":
                lines.append(f"<b>🎯 Точный счёт</b> · {bets_count} прогнозов")
                uni = group.get("univariate") or []
                total = sum(item.get("count", 0) for item in uni) or 1
                sorted_uni = sorted(uni, key=lambda x: x.get("count", 0), reverse=True)[:5]
                for item in sorted_uni:
                    out = item.get("outcome", "")
                    count = item.get("count", 0)
                    pct = round(count / total * 100) if total else 0
                    bar = progress_bar(pct)
                    lines.append(f"<code>{out}</code>  {bar}  <b>{pct}%</b> ({count})")
                lines.append("")

    # Fallback на popular-bets
    if total_predictions < MIN_PREDICTIONS and popular and "data" in popular:
        meta_total = popular.get("meta", {}).get("total", 0)
        if meta_total >= MIN_PREDICTIONS:
            lines.append(f"<b>🔥 Популярные исходы</b> · {meta_total} прогнозов")
            for item in popular.get("data", [])[:8]:
                t = item.get("type", "")
                out = str(item.get("outcome", "")).replace("_", ".")
                pct = int(item.get("percent", 0))
                count = item.get("count", 0)
                name_map = {
                    "one_two": "П1" if out == "w1" else "П2",
                    "total_under": f"ТМ ({out})",
                    "total_over": f"ТБ ({out})",
                    "handicap1": f"Ф1 ({out})",
                    "handicap2": f"Ф2 ({out})",
                    "correct_score": f"Счёт {out}",
                }
                name = name_map.get(t, f"{t} {out}")
                bar = progress_bar(pct)
                lines.append(f"<code>{name}</code>  {bar}  <b>{pct}%</b> ({count})")
            total_predictions = meta_total

    if total_predictions < MIN_PREDICTIONS:
        return (
            f"<b>📊 Пользовательское мнение</b>\n"
            f"<b>{home} — {away}</b>\n"
            f"📅 {date_str}\n\n"
            f"Пока слишком мало прогнозов ({total_predictions}).\n"
            f"Попробуй позже или выбери другой матч."
        )

    return "\n".join(lines).strip()


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 Dota 2", callback_data="sport_dota2"),
            InlineKeyboardButton(text="🔫 CS2", callback_data="sport_csgo"),
        ],
        [InlineKeyboardButton(text="ℹ️ Как это работает", callback_data="help")]
    ])
    await message.answer(
        "<b>Привет!</b> 👋\n\n"
        "Я показываю <b>пользовательское мнение</b> по матчам "
        "<b>Dota 2</b> и <b>CS2</b> в реальном времени.\n\n"
        "Что выбирают люди чаще всего — в процентах.\n\n"
        "Выбери дисциплину:",
        reply_markup=kb
    )


@dp.message(Command("help"))
@dp.callback_query(F.data == "help")
async def cmd_help(event: types.Message | CallbackQuery):
    text = (
        "<b>Как работает бот</b>\n\n"
        "• Выбираешь Dota 2 или CS2\n"
        "• Видишь список ближайших матчей <b>с датой и временем</b>\n"
        "• Нажимаешь на матч → получаешь проценты по:\n"
        "   🏆 Победителю\n"
        "   📈 Тоталу\n"
        "   ⚖️ Форам\n"
        "   🎯 Точному счёту\n\n"
        f"Показываются только матчи, где уже есть ≥ {MIN_PREDICTIONS} прогнозов.\n"
        "Данные обновляются в реальном времени со stavka.tv."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="back_start")]
    ])
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("sport_"))
async def on_sport_chosen(callback: CallbackQuery):
    sport = callback.data.split("_", 1)[1]
    sport_name = "Dota 2" if sport == "dota2" else "CS2"

    await callback.message.edit_text(f"⏳ Загружаю матчи {sport_name}...")

    matches = await get_matches(sport)

    if not matches:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back_start")]
        ])
        await callback.message.edit_text(
            f"Сейчас нет ближайших матчей по {sport_name}.",
            reply_markup=kb
        )
        await callback.answer()
        return

    buttons = []
    for m in matches:
        home = m["teams"]["home"].get("shortName") or m["teams"]["home"]["name"]
        away = m["teams"]["away"].get("shortName") or m["teams"]["away"]["name"]
        date_str = format_date(m.get("matchDate", ""))
        slug = m["slug"]

        text_btn = f"{home} — {away}  ·  {date_str}"
        buttons.append([InlineKeyboardButton(
            text=text_btn,
            callback_data=f"m|{slug}|{home}|{away}|{date_str}"
        )])

    buttons.append([InlineKeyboardButton(text="🔄 Обновить список", callback_data=f"sport_{sport}")])
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="back_start")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"<b>{sport_name}</b> — ближайшие матчи\n"
        f"<i>Нажми на матч, чтобы увидеть мнение людей</i>",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("m|"))
async def on_match_chosen(callback: CallbackQuery):
    parts = callback.data.split("|")
    if len(parts) < 5:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    _, slug, home, away, date_str = parts[0], parts[1], parts[2], parts[3], parts[4]

    await callback.message.edit_text("⏳ Загружаю пользовательское мнение...")

    aggregated, popular = await asyncio.gather(
        get_aggregated_bets(slug),
        get_popular_bets(slug)
    )

    text = format_user_opinion(aggregated, popular, home, away, date_str)
    text += f"\n\n🔗 <a href='https://stavka.tv/matches/{slug}'>Открыть на stavka.tv</a>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=callback.data)],
        [InlineKeyboardButton(text="« К списку матчей", callback_data="back_start")],
    ])

    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()


@dp.callback_query(F.data == "back_start")
async def back_to_start(callback: CallbackQuery):
    await cmd_start(callback.message)
    await callback.answer()


async def main():
    print("✅ Бот запущен и готов к работе")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
