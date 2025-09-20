"""Telegram bot that provides Nightscout nutrition summaries."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.services.nightscout import fetch_treatments_between
from app.utils.treatments import parse_meta


logger = logging.getLogger("tg_summary_bot")
logging.basicConfig(level=logging.INFO)

UTC = timezone.utc
TELEGRAM_TIMEOUT = httpx.Timeout(35.0, read=35.0, connect=10.0)
DAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _format_amount(value: float, unit: str, *, precision: int = 0) -> str:
    rounded: float
    if precision == 0:
        rounded = float(round(value))
        return f"{int(rounded)} {unit}"
    rounded = round(value, precision)
    text = f"{rounded:.{precision}f}".rstrip("0").rstrip(".")
    return f"{text} {unit}"


def _parse_date_arg(argument: str) -> date:
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(argument, pattern).date()
        except ValueError:
            continue
    raise ValueError("unsupported date format")


def _pick_number(*values: Any) -> Optional[float]:
    for raw in values:
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _parse_created_at(record: Dict[str, Any]) -> Optional[datetime]:
    raw = record.get("created_at") or record.get("createdAt")
    if not raw:
        return None
    text = str(raw).replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt_value = datetime.fromisoformat(text)
    except ValueError:
        for pattern in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                dt_value = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        else:
            logger.debug("Unable to parse created_at: %s", raw)
            return None
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=UTC)
    return dt_value


def _record_local_date(record: Dict[str, Any]) -> Optional[date]:
    created_at = _parse_created_at(record)
    if created_at is None:
        return None
    offset = record.get("utcOffset")
    if isinstance(offset, (int, float)) and offset:
        created_at = created_at + timedelta(minutes=int(offset))
    return created_at.date()


def _aggregate_treatments(treatments: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    totals = {
        "entries": 0,
        "insulin": 0.0,
        "carbs": 0.0,
        "calories": 0.0,
    }
    daily: Dict[date, Dict[str, Any]] = defaultdict(lambda: {
        "entries": 0,
        "insulin": 0.0,
        "carbs": 0.0,
        "calories": 0.0,
    })

    for record in treatments:
        totals["entries"] += 1
        meta = parse_meta(record.get("notes"))
        day = _record_local_date(record)
        if day is None:
            continue

        day_stats = daily[day]
        day_stats["entries"] += 1

        insulin = _pick_number(record.get("insulin"), meta.get("insulin_u"))
        if insulin is not None:
            totals["insulin"] += insulin
            day_stats["insulin"] += insulin

        carbs = _pick_number(record.get("carbs"), meta.get("carbs_g"))
        if carbs is not None:
            totals["carbs"] += carbs
            day_stats["carbs"] += carbs

        calories = _pick_number(record.get("calories_kcal"), meta.get("calories_kcal"))
        if calories is not None:
            totals["calories"] += calories
            day_stats["calories"] += calories

    totals["daily"] = dict(daily)
    return totals


def _day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start, end


async def build_day_summary(target_date: date) -> str:
    start, end = _day_bounds(target_date)
    treatments = await fetch_treatments_between(start, end, page_size=200)
    if not treatments:
        week_start = target_date - timedelta(days=target_date.weekday())
        fallback_start = datetime.combine(week_start, time.min, tzinfo=UTC)
        fallback_end = fallback_start + timedelta(days=7)
        fallback_records = await fetch_treatments_between(fallback_start, fallback_end, page_size=500)
        treatments = [
            record
            for record in fallback_records
            if _record_local_date(record) == target_date
        ]
    totals = _aggregate_treatments(treatments)
    day_data = totals["daily"].get(target_date)

    header = f"📅 {target_date.strftime('%d.%m.%Y')}"
    if not day_data or day_data["entries"] == 0:
        return header + "\nНет записей."

    lines = [
        header,
        f"Записей: {day_data['entries']}",
        f"Инсулин: {_format_amount(day_data['insulin'], 'ед', precision=1)}",
        f"Углеводы: {_format_amount(day_data['carbs'], 'г')}",
        f"Калории: {_format_amount(day_data['calories'], 'ккал')}",
    ]
    return "\n".join(lines)


async def build_week_summary(reference_date: Optional[date] = None) -> str:
    ref = reference_date or datetime.now(UTC).date()
    week_start = ref - timedelta(days=ref.weekday())
    week_end = week_start + timedelta(days=7)

    start_dt = datetime.combine(week_start, time.min, tzinfo=UTC)
    end_dt = datetime.combine(week_end, time.min, tzinfo=UTC)

    treatments = await fetch_treatments_between(start_dt, end_dt, page_size=1000)
    totals = _aggregate_treatments(treatments)
    daily: Dict[date, Dict[str, Any]] = totals["daily"]

    days_with_entries = sum(1 for data in daily.values() if data["entries"])
    total_days = (week_end - week_start).days

    header = "📈 Неделя " + week_start.strftime("%d.%m") + " – " + (week_end - timedelta(days=1)).strftime("%d.%m.%Y")

    if totals["entries"] == 0:
        return header + "\nНет записей на этой неделе."

    avg_divider = days_with_entries or 1

    day_lines: List[str] = []
    for offset in range(total_days):
        current_day = week_start + timedelta(days=offset)
        label = DAY_LABELS[offset % len(DAY_LABELS)]
        stats = daily.get(current_day)
        if not stats or stats["entries"] == 0:
            day_lines.append(f"• {label} {current_day.strftime('%d.%m')} — нет записей")
            continue
        line = (
            f"• {label} {current_day.strftime('%d.%m')}: {stats['entries']} запис., "
            f"инсулин {_format_amount(stats['insulin'], 'ед', precision=1)}, "
            f"углеводы {_format_amount(stats['carbs'], 'г')}, "
            f"калории {_format_amount(stats['calories'], 'ккал')}"
        )
        day_lines.append(line)

    lines = [
        header,
        *day_lines,
        "",
        f"Дней с записями: {days_with_entries} из {total_days}",
        f"Записей: {totals['entries']}",
        "Итого:",
        f"• Инсулин: {_format_amount(totals['insulin'], 'ед', precision=1)}",
        f"• Углеводы: {_format_amount(totals['carbs'], 'г')}",
        f"• Калории: {_format_amount(totals['calories'], 'ккал')}",
        "Среднее за активный день:",
        f"• Инсулин: {_format_amount(totals['insulin'] / avg_divider, 'ед', precision=1)}",
        f"• Углеводы: {_format_amount(totals['carbs'] / avg_divider, 'г')}",
        f"• Калории: {_format_amount(totals['calories'] / avg_divider, 'ккал')}",
    ]
    return "\n".join(line for line in lines if line is not None)


class SummaryBot:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.tg_token:
            raise RuntimeError("TG_TOKEN is not configured")
        self.base_url = f"https://api.telegram.org/bot{self.settings.tg_token}"
        self._offset: Optional[int] = None
        self._client = httpx.AsyncClient(timeout=TELEGRAM_TIMEOUT, trust_env=False)

    async def close(self) -> None:
        await self._client.aclose()

    async def run(self) -> None:
        logger.info("Starting Telegram summary bot")
        try:
            while True:
                try:
                    updates = await self._get_updates()
                except Exception:
                    logger.exception("Failed to fetch updates")
                    await asyncio.sleep(5)
                    continue

                for update in updates:
                    self._offset = update["update_id"] + 1
                    try:
                        await self._handle_update(update)
                    except Exception:
                        logger.exception("Error handling update: %s", update)
        finally:
            await self.close()

    async def _get_updates(self) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"timeout": 25}
        if self._offset is not None:
            params["offset"] = self._offset
        response = await self._client.get(f"{self.base_url}/getUpdates", params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            logger.error("Telegram getUpdates returned non-ok payload: %s", payload)
            return []
        return payload.get("result", [])

    async def _handle_update(self, update: Dict[str, Any]) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        text = message.get("text")
        if not text:
            return

        chat_id = message["chat"]["id"]
        user = message.get("from") or {}
        user_id = user.get("id")

        if self.settings.allowed_user_ids and user_id not in self.settings.allowed_user_ids:
            logger.info("Ignoring message from unauthorized user %s", user_id)
            return

        command, _, arguments = text.partition(" ")
        command = command.lower()
        if "@" in command:
            command = command.split("@", 1)[0]

        args_list = [arg for arg in arguments.split() if arg]

        handlers = {
            "/start": self._handle_start,
            "/help": self._handle_help,
            "/today": self._handle_today,
            "/yesterday": self._handle_yesterday,
            "/day": self._handle_day,
            "/date": self._handle_day,
            "/avgweek": self._handle_week,
            "/weekavg": self._handle_week,
            "/week": self._handle_week,
        }

        handler = handlers.get(command)
        if not handler:
            await self._send_message(chat_id, "Неизвестная команда. Используйте /help для списка команд.")
            return

        await handler(chat_id, args_list)

    async def _send_message(self, chat_id: int, text: str) -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        response = await self._client.post(f"{self.base_url}/sendMessage", json=payload)
        response.raise_for_status()

    async def _handle_start(self, chat_id: int, args: List[str]) -> None:
        await self._handle_help(chat_id, args)

    async def _handle_help(self, chat_id: int, args: List[str]) -> None:
        lines = [
            "Доступные команды:",
            "/today — сумма за сегодня",
            "/yesterday — сумма за вчера",
            "/day YYYY-MM-DD — сумма за указанную дату",
            "/avgweek — итоги и среднее за текущую неделю",
        ]
        await self._send_message(chat_id, "\n".join(lines))

    async def _handle_today(self, chat_id: int, args: List[str]) -> None:
        if args:
            await self._send_message(chat_id, "Команда /today не принимает аргументы.")
            return
        target = datetime.now(UTC).date()
        summary = await build_day_summary(target)
        await self._send_message(chat_id, summary)

    async def _handle_yesterday(self, chat_id: int, args: List[str]) -> None:
        if args:
            await self._send_message(chat_id, "Команда /yesterday не принимает аргументы.")
            return
        target = datetime.now(UTC).date() - timedelta(days=1)
        summary = await build_day_summary(target)
        await self._send_message(chat_id, summary)

    async def _handle_day(self, chat_id: int, args: List[str]) -> None:
        if not args:
            await self._send_message(chat_id, "Использование: /day YYYY-MM-DD")
            return
        try:
            target_date = _parse_date_arg(args[0])
        except ValueError:
            await self._send_message(chat_id, "Не удалось распознать дату. Форматы: YYYY-MM-DD или DD.MM.YYYY")
            return
        summary = await build_day_summary(target_date)
        await self._send_message(chat_id, summary)

    async def _handle_week(self, chat_id: int, args: List[str]) -> None:
        reference: Optional[date] = None
        if args:
            try:
                reference = _parse_date_arg(args[0])
            except ValueError:
                await self._send_message(chat_id, "Не удалось распознать дату. Форматы: YYYY-MM-DD или DD.MM.YYYY")
                return
        summary = await build_week_summary(reference)
        await self._send_message(chat_id, summary)


async def main() -> None:
    bot = SummaryBot()
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Telegram summary bot stopped by user")
