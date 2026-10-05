import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
import os

# ========== НАСТРОЙКИ ==========
TOKEN = os.getenv("BOT_TOKEN", "СЮДА_ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER")
# ===============================

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

BASE_API = "https://stavka.tv/api/v2"


async def fetch_json(url: str, params: dict = None) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


async def get_matches(sport: str, limit: int = 20) -> list:
    """sport: 'dota2' или 'csgo'"""
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


def format_percent_bar(percent: int, width: int = 10) -> str:
    """Простой текстовый прогресс-бар"""
    filled = round(percent / 100 * width)
    return "█" * filled + "░" * (width - filled)


def format_user_opinion(aggregated: dict | None, popular: dict | None, match_name: str) -> str:
    """Форматирует пользовательское мнение как на скрине stavka.tv"""
    lines = [f"<b>📊 Пользовательское мнение</b>\n<b>{match_name}</b>\n"]

    if not aggregated and not popular:
        return lines[0] + "\nПока нет прогнозов от пользователей."

    # === Используем aggregated (как на скрине) ===
    if aggregated and "data" in aggregated:
        all_groups = aggregated["data"].get("all") or aggregated["data"].get("capper") or []

        for group in all_groups:
            group_name = group.get("group")
            bets_count = group.get("betsCount", 0)
            if bets_count == 0:
                continue

            if group_name == "one_two":
                lines.append(f"<b>Победитель матча</b> · {bets_count} прогнозов")
                uni = group.get("univariate") or []
                total = sum(item.get("count", 0) for item in uni) or 1
                for item in uni:
                    outcome = item.get("outcome")
                    count = item.get("count", 0)
                    pct = round(count / total * 100) if total else 0
                    name = "П1" if outcome == "w1" else "П2"
                    bar = format_percent_bar(pct)
                    lines.append(f"  {name}  {bar}  <b>{pct}%</b> ({count})")
                lines.append("")

            elif group_name == "total":
                lines.append(f"<b>Тотал</b> · {bets_count} прогнозов")
                bivariate = group.get("bivariate") or []
                for pair in bivariate:
                    for item in pair:
                        t = item.get("type", "")
                        out = str(item.get("outcome", "")).replace("_", ".")
                        count = item.get("count", 0)
                        pct = round(count / bets_count * 100) if bets_count else 0
                        name = "ТМ" if "under" in t else "ТБ"
                        bar = format_percent_bar(pct)
                        lines.append(f"  {name} ({out})  {bar}  <b>{pct}%</b> ({count})")
                lines.append("")

            elif group_name == "handicap":
                lines.append(f"<b>Форы</b> · {bets_count} прогнозов")
                bivariate = group.get("bivariate") or []
                for pair in bivariate:
                    for item in pair:
                        t = item.get("type", "")
                        out = str(item.get("outcome", "")).replace("_", ".")
                        count = item.get("count", 0)
                        pct = round(count / bets_count * 100) if bets_count else 0
                        name = "Ф1" if "handicap1" in t else "Ф2"
                        bar = format_percent_bar(pct)
                        lines.append(f"  {name} ({out})  {bar}  <b>{pct}%</b> ({count})")
                lines.append("")

            elif group_name == "correct_score":
                lines.append(f"<b>Точный счёт</b> · {bets_count} прогнозов")
                uni = group.get("univariate") or []
                total = sum(item.get("count", 0) for item in uni) or 1
                # Берём топ-4
                sorted_uni = sorted(uni, key=lambda x: x.get("count", 0), reverse=True)[:4]
                for item in sorted_uni:
                    out = item.get("outcome", "")
                    count = item.get("count", 0)
                    pct = round(count / total * 100) if total else 0
                    bar = format_percent_bar(pct)
                    lines.append(f"  {out}  {bar}  <b>{pct}%</b> ({count})")
                lines.append("")

    # Если aggregated пустой — fallback на popular
    if len(lines) <= 2 and popular and "data" in popular:
        lines.append("<b>Популярные исходы</b>")
        for item in popular.get("data", [])[:8]:
            t = item.get("type", "")
            out = str(item.get("outcome", "")).replace("_", ".")
            pct = item.get("percent", 0)
            count = item.get("count", 0)
            name = {
                "one_two": "П1" if out == "w1" else "П2",
                "total_under": f"ТМ ({out})",
                "total_over": f"ТБ ({out})",
                "handicap1": f"Ф1 ({out})",
                "handicap2": f"Ф2 ({out})",
                "correct_score": f"Счёт {out}",
            }.get(t, f"{t} {out}")
            bar = format_percent_bar(int(pct))
            lines.append(f"  {name}  {bar}  <b>{pct}%</b> ({count})")

    if len(lines) <= 2:
        return lines[0] + "\nПока мало прогнозов от пользователей."

    return "\n".join(lines)


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
        "Я показываю <b>пользовательское мнение</b> по матчам Dota 2 и Counter-Strike 2 "
        "в реальном времени — что люди выбирают чаще всего (в процентах).\n\n"
        "Данные берутся со stavka.tv\n\n"
        "Выбери дисциплину:",
        reply_markup=kb
    )


@dp.message(Command("help"))
@dp.callback_query(F.data == "help")
async def cmd_help(event: types.Message | CallbackQuery):
    text = (
        "<b>Как работает бот</b>\n\n"
        "1. Выбираешь Dota 2 или CS2\n"
        "2. Видишь список ближайших матчей\n"
        "3. Нажимаешь на матч — получаешь проценты по:\n"
        "   • Победителю матча (П1/П2)\n"
        "   • Тоталу (ТМ/ТБ)\n"
        "   • Форам\n"
        "   • Точному счёту\n\n"
        "Проценты считаются по реальным прогнозам пользователей stavka.tv.\n"
        "Чем больше прогнозов — тем точнее картинка."
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back_start")]
        ]))
        await event.answer()
    else:
        await event.answer(text)


@dp.callback_query(F.data.startswith("sport_"))
async def on_sport_chosen(callback: CallbackQuery):
    sport = callback.data.split("_", 1)[1]  # dota2 / csgo
    sport_name = "Dota 2" if sport == "dota2" else "CS2"

    await callback.message.edit_text(f"⏳ Загружаю матчи {sport_name}...")

    matches = await get_matches(sport)

    if not matches:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back_start")]
        ])
        await callback.message.edit_text(
            f"Сейчас нет ближайших матчей по {sport_name}.\nПопробуй позже.",
            reply_markup=kb
        )
        await callback.answer()
        return

    buttons = []
    for m in matches:
        home = m["teams"]["home"].get("shortName") or m["teams"]["home"]["name"]
        away = m["teams"]["away"].get("shortName") or m["teams"]["away"]["name"]
        # Время в МСК примерно
        match_date = m.get("matchDate", "")
        time_str = match_date[11:16] if len(match_date) > 16 else "?"
        slug = m["slug"]
        text_btn = f"{home} – {away}  ·  {time_str}"
        buttons.append([InlineKeyboardButton(text=text_btn, callback_data=f"m_{slug}")])

    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"sport_{sport}")])
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="back_start")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"<b>{sport_name}</b> — ближайшие матчи:\n"
        f"<i>Нажми на матч, чтобы увидеть пользовательское мнение</i>",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("m_"))
async def on_match_chosen(callback: CallbackQuery):
    slug = callback.data[2:]  # убираем "m_"

    await callback.message.edit_text("⏳ Загружаю пользовательское мнение...")

    aggregated, popular = await asyncio.gather(
        get_aggregated_bets(slug),
        get_popular_bets(slug)
    )

    # Достаём названия команд из popular или делаем заглушку
    match_name = slug.replace("-", " ").title()
    # Попробуем красивее
    if aggregated or popular:
        # slug обычно: 05-10-2026-team1-team2
        parts = slug.split("-")
        if len(parts) >= 5:
            match_name = " – ".join(parts[3:]).replace("-", " ").title()

    text = format_user_opinion(aggregated, popular, match_name)
    text += f"\n\n🔗 <a href='https://stavka.tv/matches/{slug}'>Открыть матч на stavka.tv</a>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"m_{slug}")],
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
