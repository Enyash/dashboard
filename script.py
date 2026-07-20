# report_dashboard.py
from flask import Flask, render_template_string, jsonify, request
import os
import csv
from datetime import datetime, timedelta
import threading
import webbrowser
import time
import re
from collections import defaultdict
import json
import calendar

app = Flask(__name__)

CSV_FOLDER = r"\\WH-MSK-CO-1C0\Public\Эняш"
DATA_FOLDER = r"C:\1C_Data3"

MONTHS_NOM = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
]

MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]

QUARTERS = {
    1: "1 квартал",
    2: "2 квартал",
    3: "3 квартал",
    4: "4 квартал"
}

HOLIDAYS = [
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
    (2, 23),
    (3, 8),
    (5, 1),
    (5, 9),
    (6, 12),
    (11, 4),
]


def is_weekend(date_obj):
    return date_obj.weekday() >= 5


def is_holiday(date_obj):
    return (date_obj.month, date_obj.day) in HOLIDAYS


def get_next_workday(date_obj):
    next_day = date_obj + timedelta(days=1)
    while is_weekend(next_day) or is_holiday(next_day):
        next_day += timedelta(days=1)
    return next_day


def adjust_deadline_for_weekend(deadline_date):
    if is_weekend(deadline_date) or is_holiday(deadline_date):
        return get_next_workday(deadline_date)
    return deadline_date


def format_date_ru(date_obj):
    if date_obj is None:
        return "—"
    weekdays_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return f"{date_obj.day} {MONTHS_RU[date_obj.month - 1]} {date_obj.year} г. {weekdays_ru[date_obj.weekday()]}"


def parse_date_value(date_val):
    if date_val is None:
        return None
    if isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, str):
        date_val = date_val.strip().strip('"\'')
        for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y %H:%M:%S"]:
            try:
                return datetime.strptime(date_val, fmt)
            except:
                continue
    return None


def parse_report_from_ref(ref_str):
    if not ref_str:
        return "Неизвестный отчет", "", ""

    ref_str = ref_str.strip()
    report_name = ref_str
    org_name = ""
    period_info = ""

    if "Организация:" in ref_str:
        try:
            org_part = ref_str.split("Организация:")[1].strip()
            if ")" in org_part:
                org_name = org_part.split(")")[0].strip()
            else:
                org_name = org_part.strip()
        except:
            pass

    period_match = re.search(r'за\s+([^()]+?)\s*(?:\(|$)', ref_str)
    if period_match:
        period_info = period_match.group(1).strip()

    if " за " in ref_str:
        report_name = ref_str.split(" за ")[0].strip()
    elif " (Вид:" in ref_str:
        report_name = ref_str.split(" (Вид:")[0].strip()
    elif " (" in ref_str:
        report_name = ref_str.split(" (")[0].strip()

    report_name = report_name.replace('"', '').strip()
    if not report_name or len(report_name) < 2:
        report_name = "Неизвестный отчет"

    return report_name, org_name, period_info


def parse_csv_reports(filepath):
    """
    Функция парсит csv файл и возвращает массив объектов
    """
    reports = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            sample = f.read(2048)
            f.seek(0)

            delimiter = ';' if ';' in sample else ','
            reader = csv.reader(f, delimiter=delimiter)
            headers = next(reader, None)

            if not headers:
                return []

            date_col = None
            ref_col = None

            for i, h in enumerate(headers):
                h_lower = h.lower().strip().strip('"\'')
                if 'дата' in h_lower:
                    date_col = i
                elif 'ссылка' in h_lower:
                    ref_col = i

            if date_col is None:
                date_col = 0
            if ref_col is None:
                ref_col = 1 if len(headers) > 1 else 0

            for row in reader:
                if len(row) <= max(date_col, ref_col):
                    continue

                date_str = row[date_col].strip() if date_col < len(row) else ''
                ref_str = row[ref_col].strip() if ref_col < len(row) else ''

                if not date_str or not ref_str:
                    continue

                date_obj = parse_date_value(date_str)
                report_name, org_name, period_info = parse_report_from_ref(ref_str)

                reports.append({
                    "date": date_obj,
                    "date_str": date_str,
                    "report_name": report_name,
                    "org_name": org_name,
                    "period": period_info
                })
        result = sorted(reports, key=lambda x: x['date'], reverse=True)

        return result

    except Exception as e:
        print(f"❌ Ошибка парсинга CSV {filepath}: {e}")
        return []


def load_all_reports():
    organizations = {}
    all_reports_list = []

    print("\n" + "=" * 80)
    print("📊 ЗАГРУЗКА ОТЧЕТОВ ИЗ CSV (1С)")
    print("=" * 80)

    csv_folder = CSV_FOLDER
    if not os.path.exists(csv_folder):
        print(f"⚠️ Папка не найдена: {csv_folder}")
        csv_folder = DATA_FOLDER
        if not os.path.exists(csv_folder):
            os.makedirs(csv_folder)
            print(f"📁 Создана локальная папка: {csv_folder}")
        print(f"📂 Используем локальную папку: {csv_folder}")

    print(f"📂 Папка с данными: {csv_folder}")

    csv_files = [f for f in os.listdir(csv_folder) if f.lower().endswith('.csv')]

    if not csv_files:
        print("❌ CSV-файлы не найдены!")
        return {}, []

    for filename in csv_files:
        filepath = os.path.join(csv_folder, filename)
        print(f"\n📄 {filename}")

        reports = parse_csv_reports(filepath)
        all_reports_list.extend(reports)

        for report in reports:
            org_name = report["org_name"] or "Неизвестная организация"
            if org_name not in organizations:
                organizations[org_name] = []
            organizations[org_name].append(report)

        print(f"  ✅ Загружено отчетов: {len(reports)}")

    print("\n" + "=" * 80)
    print(f"📊 Итого организаций: {len(organizations)}")
    if organizations:
        for org in organizations:
            print(f"  • {org}: {len(organizations[org])} отчетов")

    # print(f"All reports list: {all_reports_list}")
    return organizations, all_reports_list


def get_report_periodicity(report_name):
    report_lower = report_name.lower()
    quarterly_keywords = ["ндс", "рсв", "ефс", "6-ндфл", "страховым взносам", "декларация по ндс"]
    for kw in quarterly_keywords:
        if kw in report_lower:
            return "квартал"
    return "месяц"


def get_next_period(last_period_str, periodicity):
    if not last_period_str:
        return None

    month_match = re.search(
        r'(январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь)\s+(\d{4})',
        last_period_str.lower())
    if month_match:
        month_name = month_match.group(1)
        year = int(month_match.group(2))
        month_num = MONTHS_NOM.index(month_name) + 1

        if periodicity == "месяц":
            if month_num == 12:
                month_num = 1
                year += 1
            else:
                month_num += 1
            return f"{MONTHS_NOM[month_num - 1]} {year} г."
        elif periodicity == "квартал":
            q = (month_num - 1) // 3 + 1
            if q == 4:
                q = 1
                year += 1
            else:
                q += 1
            return f"{QUARTERS[q]} {year} г."

    quarter_match = re.search(r'(\d)\s+квартал\s+(\d{4})', last_period_str.lower())
    if quarter_match:
        q = int(quarter_match.group(1))
        year = int(quarter_match.group(2))
        if periodicity == "квартал":
            if q == 4:
                q = 1
                year += 1
            else:
                q += 1
            return f"{QUARTERS[q]} {year} г."

    return None


def get_deadline_for_period(period_str):
    if not period_str:
        return None

    period_lower = period_str.lower()

    month_match = re.search(
        r'(январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь)\s+(\d{4})', period_lower)
    if month_match:
        month_name = month_match.group(1)
        year = int(month_match.group(2))
        month_num = MONTHS_NOM.index(month_name) + 1
        deadline_date = datetime(year, month_num, 25)
        return adjust_deadline_for_weekend(deadline_date)

    quarter_match = re.search(r'(\d)\s+квартал\s+(\d{4})', period_lower)
    if quarter_match:
        q = int(quarter_match.group(1))
        year = int(quarter_match.group(2))
        q_months = [3, 6, 9, 12]
        month_num = q_months[q - 1]
        deadline_date = datetime(year, month_num, 25)
        return adjust_deadline_for_weekend(deadline_date)

    return None


def build_matrix(organizations, all_reports_list, sort_order="desc"):
    # Группируем отчеты по названию
    report_groups = {}
    for report in all_reports_list:
        key = f'{report["report_name"]}_{report["org_name"]}'
        if key not in report_groups:
            report_groups[key] = []
        report_groups[key].append(report)

    matrix = []
    row_num = 1
    print(f"Report groups: {report_groups}")
    for report_name, reports in report_groups.items():
        # Сортируем по дате (сначала свежие)
        reports_sorted = sorted(reports, key=lambda x: x["date"] if x["date"] else datetime.min, reverse=True)
        latest_report = reports_sorted[0]
        latest_date = latest_report["date"]
        current_period = latest_report["period"]
        org_name = latest_report["org_name"]

        periodicity = get_report_periodicity(report_name)
        next_period = get_next_period(current_period, periodicity) if current_period else None
        next_deadline = get_deadline_for_period(next_period) if next_period else None

        display_name = f"{report_name} за {current_period}" if current_period else report_name

        row = {"report": display_name, "base_name": report_name, "sort_date": latest_date}

        for org_name_data, org_reports in organizations.items():
            found = False
            for r in org_reports:
                if r["report_name"] == report_name:
                    found = True
                    row[org_name_data] = {
                        "status": "Подготовлен",
                        "status_color": "green",
                        "deadline": next_deadline,
                        "deadline_str": format_date_ru(next_deadline) if next_deadline else None,
                        "days_left": (next_deadline - datetime.now()).days if next_deadline else None,
                        "is_alert": False,
                        "date_start": r["date"],
                        "date_end": r["date"],
                        "sort_date": r["date"],
                        "date_start_str": r["date_str"],
                        "date_end_str": r["date_str"],
                        "period": r["period"],
                        "next_period": next_period,
                        "next_deadline": next_deadline
                    }
                    break

            if not found:
                row[org_name_data] = {
                    "status": "Не требуется",
                    "status_color": "lightgray",
                    "deadline": None,
                    "deadline_str": None,
                    "days_left": None,
                    "is_alert": False,
                    "date_start": None,
                    "date_end": None,
                    "sort_date": None,
                    "date_start_str": None,
                    "date_end_str": None,
                    "period": "",
                    "next_period": None,
                    "next_deadline": None
                }

        matrix.append(row)
        row_num += 1

    # Сортировка матрицы по дате
    if sort_order == "desc":
        matrix.sort(key=lambda x: x["sort_date"] if x["sort_date"] else datetime.min, reverse=True)
    else:
        matrix.sort(key=lambda x: x["sort_date"] if x["sort_date"] else datetime.min)

    return matrix


def get_upcoming_deadlines(organizations, all_reports_list, days_ahead=30):
    current_date = datetime.now()
    upcoming = []

    report_groups = {}
    for report in all_reports_list:
        key = report["report_name"]
        if key not in report_groups:
            report_groups[key] = []
        report_groups[key].append(report)

    for report_name, reports in report_groups.items():
        reports_sorted = sorted(reports, key=lambda x: x["date"] if x["date"] else datetime.min, reverse=True)
        latest_report = reports_sorted[0]
        current_period = latest_report["period"]
        org_name = latest_report["org_name"]

        periodicity = get_report_periodicity(report_name)
        next_period = get_next_period(current_period, periodicity) if current_period else None
        next_deadline = get_deadline_for_period(next_period) if next_period else None

        if next_deadline:
            days_left = (next_deadline - current_date).days
            if 0 <= days_left <= days_ahead:
                upcoming.append({
                    "report": report_name,
                    "display_name": f"{report_name} за {next_period}" if next_period else report_name,
                    "deadline": next_deadline,
                    "deadline_str": format_date_ru(next_deadline),
                    "days_left": days_left,
                    "period": next_period,
                    "organization": org_name,
                    "in_excel": False
                })

    return sorted(upcoming, key=lambda x: x["days_left"])


# ============================================================
# HTML ШАБЛОН
# ============================================================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Дашборд отчетности 1С</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; padding: 20px; }
        .container { max-width: 100%; margin: 0 auto; }

        .header { 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 16px; 
            padding: 25px 30px; 
            margin-bottom: 25px; 
            color: white;
        }
        .header h1 { font-size: 28px; }
        .header h1 span { background: #e74c3c; padding: 4px 12px; border-radius: 20px; font-size: 14px; margin-left: 10px; }
        .header .subtitle { color: #a0aec0; margin-top: 5px; font-size: 14px; }
        .header .stats-row { display: flex; gap: 30px; margin-top: 15px; flex-wrap: wrap; }
        .header .stat-item { font-size: 14px; }
        .header .stat-item .num { font-weight: bold; font-size: 18px; }
        .header .stat-item .num.green { color: #48bb78; }
        .header .stat-item .num.red { color: #fc8181; }
        .header .stat-item .num.yellow { color: #ecc94b; }
        .header .stat-item .num.blue { color: #63b3ed; }
        .header .stat-item .num.gray { color: #a0aec0; }

        .filters { 
            background: white; 
            border-radius: 16px; 
            padding: 15px 20px; 
            margin-bottom: 25px; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            align-items: center;
        }
        .filters label { font-weight: 600; color: #555; font-size: 14px; }
        .filters select { padding: 8px 12px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 14px; background: white; }
        .filters input { padding: 8px 12px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 14px; }
        .filters .legend { display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }
        .filters .legend-item { display: flex; align-items: center; gap: 5px; font-size: 12px; color: #555; }
        .filters .legend-color { width: 16px; height: 16px; border-radius: 4px; }
        .filters button { 
            background: #667eea; 
            color: white; 
            border: none; 
            padding: 8px 20px; 
            border-radius: 8px; 
            cursor: pointer; 
            font-size: 14px;
            transition: 0.3s;
        }
        .filters button:hover { background: #5a67d8; }

        .sort-buttons {
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }
        .sort-buttons .sort-btn {
            padding: 6px 16px;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            background: white;
            cursor: pointer;
            font-size: 13px;
            transition: 0.3s;
            color: #4a5568;
        }
        .sort-buttons .sort-btn:hover { border-color: #667eea; background: #f7fafc; }
        .sort-buttons .sort-btn.active { border-color: #667eea; background: #667eea; color: white; }
        .sort-buttons .sort-label { font-size: 13px; color: #4a5568; font-weight: 600; margin-right: 5px; }

        .chart-card {
            background: white;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 25px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        .chart-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
            color: #1a1a2e;
        }

        .upcoming-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        .upcoming-card {
            background: white;
            border-radius: 12px;
            padding: 15px 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            border-left: 4px solid #667eea;
            transition: 0.3s;
        }
        .upcoming-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
        .upcoming-card .report-name { font-weight: 600; font-size: 14px; color: #2d3748; }
        .upcoming-card .deadline-info { font-size: 13px; color: #4a5568; margin-top: 5px; }
        .upcoming-card .days { font-weight: 700; font-size: 16px; }
        .upcoming-card .description { font-size: 11px; color: #718096; margin-top: 5px; }
        .upcoming-card .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-green { background: #c6f6d5; color: #22543d; }
        .badge-red { background: #fed7d7; color: #9b2c2c; }
        .badge-yellow { background: #feebc8; color: #9c4221; }
        .badge-gray { background: #e2e8f0; color: #4a5568; }

        .upcoming-card.danger { border-left-color: #e53e3e; }
        .upcoming-card.danger .days { color: #e53e3e; }
        .upcoming-card.warning { border-left-color: #ecc94b; }
        .upcoming-card.warning .days { color: #d69e2e; }
        .upcoming-card.success { border-left-color: #48bb78; }
        .upcoming-card.success .days { color: #48bb78; }
        .upcoming-card.gray { border-left-color: #a0aec0; }
        .upcoming-card.gray .days { color: #a0aec0; }

        .table-container { 
            background: white; 
            border-radius: 16px; 
            padding: 20px; 
            overflow-x: auto; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            flex-wrap: wrap;
            gap: 10px;
        }
        .table-header h3 { color: #2d3748; }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            font-size: 13px;
            min-width: 800px;
        }
        th { 
            text-align: left; 
            padding: 12px 10px; 
            background: #f7fafc; 
            font-weight: 600; 
            color: #2d3748; 
            border-bottom: 2px solid #e2e8f0;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        th:first-child { min-width: 50px; text-align: center; }
        th:nth-child(2) { min-width: 300px; }
        th.org-header { text-align: center; min-width: 180px; }
        td { padding: 8px 10px; border-bottom: 1px solid #edf2f7; vertical-align: top; }
        td:first-child { text-align: center; font-weight: 600; color: #4a5568; }
        td:nth-child(2) { font-weight: 500; color: #2d3748; }
        tr:hover { background: #f7fafc; }

        .row-number {
            display: inline-block;
            width: 28px;
            height: 28px;
            background: #edf2f7;
            color: #4a5568;
            border-radius: 50%;
            text-align: center;
            line-height: 28px;
            font-size: 12px;
            font-weight: 700;
        }
        .row-number.danger { background: #fed7d7; color: #9b2c2c; }
        .row-number.warning { background: #feebc8; color: #9c4221; }
        .row-number.success { background: #c6f6d5; color: #22543d; }
        .row-number.blue { background: #bee3f8; color: #2a69ac; }
        .row-number.gray { background: #e2e8f0; color: #4a5568; }

        .cell-content {
            display: flex;
            flex-direction: column;
            gap: 2px;
            padding: 6px 10px;
            border-radius: 8px;
            font-size: 12px;
            min-height: 40px;
            justify-content: center;
        }
        .cell-content .status { font-weight: 600; font-size: 13px; }
        .cell-content .deadline { font-size: 11px; opacity: 0.8; }
        .cell-content .days { font-size: 11px; font-weight: 600; }
        .cell-content .date-range { font-size: 11px; opacity: 0.7; }
        .cell-content .next-period { font-size: 11px; color: #667eea; }

        .status-green { background: #c6f6d5; color: #22543d; border-left: 4px solid #48bb78; }
        .status-yellow { background: #feebc8; color: #9c4221; border-left: 4px solid #ecc94b; }
        .status-red { background: #fed7d7; color: #9b2c2c; border-left: 4px solid #fc8181; }
        .status-blue { background: #bee3f8; color: #2a69ac; border-left: 4px solid #63b3ed; }
        .status-gray { background: #e2e8f0; color: #4a5568; border-left: 4px solid #a0aec0; }
        .status-lightgray { background: #f7fafc; color: #a0aec0; opacity: 0.5; border-left: 4px solid #e2e8f0; }

        .warning-badge {
            display: inline-block;
            background: #e53e3e;
            color: white;
            padding: 1px 8px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: 700;
            animation: pulse 1s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .footer { text-align: center; margin-top: 20px; color: #999; font-size: 12px; }
        .footer button { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            border: none; 
            padding: 10px 24px; 
            border-radius: 25px; 
            cursor: pointer; 
            font-size: 14px; 
            transition: 0.3s; 
        }
        .footer button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); }

        @media (max-width: 768px) {
            .header .stats-row { flex-direction: column; gap: 8px; }
            .filters { flex-direction: column; align-items: stretch; }
            .upcoming-grid { grid-template-columns: 1fr; }
            .table-header { flex-direction: column; align-items: flex-start; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Дашборд отчетности 1С <span>С прогнозом</span></h1>
            <div class="subtitle">Сданные отчеты и прогноз следующих периодов</div>
            <div class="stats-row" id="statsRow">
                <div class="stat-item">✅ Подготовлено: <span class="num green" id="podgotovlenCount">0</span></div>
                <div class="stat-item">📋 Всего отчетов: <span class="num blue" id="totalCount">0</span></div>
                <div class="stat-item">📅 Ближайший дедлайн: <span id="nearestDeadline" style="color: #fc8181; font-weight: bold;">-</span></div>
                <div class="stat-item">🔄 Обновлено: <span id="updateTime" style="color: #a0aec0; font-weight: normal;">-</span></div>
            </div>
        </div>

        <div class="filters">
            <label>Организация:</label>
            <select id="orgFilter" onchange="applyFilters()">
                <option value="all">Все организации</option>
            </select>

            <label>Статус:</label>
            <select id="statusFilter" onchange="applyFilters()">
                <option value="all">Все статусы</option>
                <option value="Подготовлен">✅ Подготовлен</option>
                <option value="Не требуется">➖ Не требуется</option>
            </select>

            <label>Поиск:</label>
            <input type="text" id="searchInput" oninput="applyFilters()" placeholder="Название отчета..." style="width: 200px;">

            <div class="sort-buttons">
                <span class="sort-label">📅 Сортировка:</span>
                <button class="sort-btn active" id="sortDesc" onclick="changeSort('desc')">⬇️ Сначала свежие</button>
                <button class="sort-btn" id="sortAsc" onclick="changeSort('asc')">⬆️ Сначала старые</button>
            </div>

            <div class="legend">
                <span class="legend-item"><span class="legend-color" style="background:#c6f6d5;"></span> Подготовлен</span>
                <span class="legend-item"><span class="legend-color" style="background:#f7fafc;"></span> Не требуется</span>
            </div>

            <button onclick="refreshData()">🔄 Обновить</button>
        </div>

        <div class="chart-card">
            <div class="chart-title">📈 График дедлайнов на ближайший месяц</div>
            <div id="deadlineChart" style="height: 400px;"></div>
        </div>

        <div class="chart-card">
            <div class="chart-title">📋 Отчеты к сдаче в ближайшее время</div>
            <div id="upcomingReports" class="upcoming-grid"></div>
        </div>

        <div class="table-container">
            <div class="table-header">
                <h3>📊 Матрица статусов отчетов по организациям</h3>
                <span class="sort-label" id="sortLabel">🔄 Сортировка: сначала свежие</span>
            </div>
            <table>
                <thead>
                    <tr><th>#</th><th>📋 Отчет за период</th><th id="orgHeaders"></th></tr>
                </thead>
                <tbody id="matrixBody"></tbody>
            </table>
        </div>

        <div class="footer">
            <button onclick="refreshData()">🔄 Обновить данные</button>
            <p style="margin-top: 15px;">Данные загружены из CSV: РегламентированныеОтчеты_*.csv</p>
        </div>
    </div>

    <script>
        let matrixData = null;
        let organizations = [];
        let allReports = [];
        let upcomingData = [];
        let currentSort = 'desc';

        function getStatusClass(status) {
            const map = {
                'Подготовлен': 'status-green',
                'Не требуется': 'status-lightgray'
            };
            return map[status] || 'status-lightgray';
        }

        function getRowNumberClass(status) {
            const map = {
                'Подготовлен': 'success',
                'Не требуется': ''
            };
            return map[status] || '';
        }

        function changeSort(order) {
            currentSort = order;
            document.getElementById('sortDesc').className = 'sort-btn' + (order === 'desc' ? ' active' : '');
            document.getElementById('sortAsc').className = 'sort-btn' + (order === 'asc' ? ' active' : '');
            document.getElementById('sortLabel').textContent = order === 'desc' 
                ? '🔄 Сортировка: сначала свежие' 
                : '🔄 Сортировка: сначала старые';
            refreshData();
        }

        function renderMatrix(data) {
            const orgHeaders = document.getElementById('orgHeaders');
            const tbody = document.getElementById('matrixBody');

            matrixData = data;
            organizations = data.organizations || [];
            allReports = data.matrix || [];
            upcomingData = data.upcoming || [];

            orgHeaders.innerHTML = organizations.map(org => 
                `<th class="org-header">${org}</th>`
            ).join('');

            const orgFilter = document.getElementById('orgFilter');
            const currentOrg = orgFilter.value;
            orgFilter.innerHTML = '<option value="all">Все организации</option>' + 
                organizations.map(org => `<option value="${org}">${org}</option>`).join('');
            if (currentOrg && organizations.includes(currentOrg)) {
                orgFilter.value = currentOrg;
            }

            let html = '';
            let rowNum = 1;

            allReports.forEach(row => {
                const reportName = row.report;
                let numClass = '';
                let hasSuccess = false;
                organizations.forEach(org => {
                    const info = row[org] || {};
                    const status = info.status || 'Не требуется';
                    if (status === 'Подготовлен') hasSuccess = true;
                });
                if (hasSuccess) numClass = 'success';

                let cells = `<td><span class="row-number ${numClass}">${rowNum}</span></td>`;
                cells += `<td><strong>${reportName}</strong></td>`;

                organizations.forEach(org => {
                    const info = row[org] || {};
                    const status = info.status || 'Не требуется';
                    const dateStart = info.date_start_str;
                    const dateEnd = info.date_end_str;
                    const nextPeriod = info.next_period || '';
                    const deadlineStr = info.deadline_str || '';

                    let dateRangeText = '';
                    let nextPeriodText = '';
                    let deadlineText = '';

                    if (dateStart && dateEnd) {
                        dateRangeText = `📅 ${dateStart} - ${dateEnd}`;
                    } else if (dateStart) {
                        dateRangeText = `📅 с ${dateStart}`;
                    } else if (dateEnd) {
                        dateRangeText = `📅 по ${dateEnd}`;
                    }

                    if (nextPeriod) {
                        nextPeriodText = `⏳ Следующий: ${nextPeriod}`;
                    }

                    if (deadlineStr) {
                        deadlineText = `📅 Дедлайн: ${deadlineStr}`;
                    }

                    const statusClass = getStatusClass(status);

                    cells += `<td><div class="cell-content ${statusClass}">
                        <div class="status">${status}</div>
                        ${dateRangeText ? `<div class="date-range">${dateRangeText}</div>` : ''}
                        ${deadlineText ? `<div class="deadline">${deadlineText}</div>` : ''}
                        ${nextPeriodText ? `<div class="next-period">${nextPeriodText}</div>` : ''}
                    </div></td>`;
                });

                html += `<tr>${cells}</tr>`;
                rowNum++;
            });

            tbody.innerHTML = html;
            updateStats();
            renderUpcoming(upcomingData);
            renderChart(upcomingData);
            document.getElementById('updateTime').innerHTML = new Date().toLocaleString('ru-RU');
        }

        function updateStats() {
            let podgotovlen = 0, total = 0;
            let nearestDeadline = null;
            let nearestDays = Infinity;

            allReports.forEach(row => {
                organizations.forEach(org => {
                    const info = row[org] || {};
                    const status = info.status || 'Не требуется';
                    if (status !== 'Не требуется') total++;
                    if (status === 'Подготовлен') podgotovlen++;

                    if (info.next_deadline) {
                        const days = info.days_left;
                        if (days !== null && days >= 0 && days < nearestDays) {
                            nearestDays = days;
                            nearestDeadline = info.deadline_str;
                        }
                    }
                });
            });

            if (upcomingData.length > 0 && nearestDeadline === null) {
                nearestDeadline = upcomingData[0].deadline_str;
                nearestDays = upcomingData[0].days_left;
            }

            document.getElementById('podgotovlenCount').textContent = podgotovlen;
            document.getElementById('totalCount').textContent = total;
            document.getElementById('nearestDeadline').textContent = nearestDeadline || 'Нет дедлайнов';
        }

        function renderUpcoming(upcoming) {
            const container = document.getElementById('upcomingReports');
            if (!upcoming || upcoming.length === 0) {
                container.innerHTML = '<p style="color: #718096; text-align: center; padding: 20px;">✅ Все отчеты сданы! Ближайших дедлайнов нет.</p>';
                return;
            }

            let html = '';
            upcoming.slice(0, 15).forEach((item, index) => {
                const days = item.days_left;
                const deadlineStr = item.deadline_str || '—';
                const displayName = item.display_name || item.report;
                let cardClass = '';
                let daysText = '';
                let badge = '';

                if (days <= 1) {
                    cardClass = 'danger';
                    daysText = `🔴 ${days} дн.`;
                    badge = '<span class="badge badge-red">СРОЧНО!</span>';
                } else if (days <= 3) {
                    cardClass = 'warning';
                    daysText = `🟡 ${days} дн.`;
                    badge = '<span class="badge badge-yellow">Внимание</span>';
                } else {
                    cardClass = 'gray';
                    daysText = `⚪ ${days} дн.`;
                    badge = '<span class="badge badge-gray">Не начат</span>';
                }

                html += `<div class="upcoming-card ${cardClass}">
                    <div class="report-name">${index + 1}. ${displayName}</div>
                    <div class="deadline-info">📅 ${deadlineStr} <span class="days">${daysText}</span> ${badge}</div>
                    <div class="description">${item.organization || ''}</div>
                </div>`;
            });

            container.innerHTML = html;
        }

        function renderChart(upcoming) {
            const chartDiv = document.getElementById('deadlineChart');
            if (!upcoming || upcoming.length === 0) {
                Plotly.newPlot(chartDiv, [], { height: 400, title: 'Нет предстоящих дедлайнов' });
                return;
            }

            const dates = {};
            upcoming.forEach(item => {
                const dateKey = item.deadline_str || '—';
                if (!dates[dateKey]) dates[dateKey] = [];
                dates[dateKey].push(item);
            });

            const sortedDates = Object.keys(dates).sort();
            const counts = sortedDates.map(d => dates[d].length);
            const colors = sortedDates.map(d => {
                const items = dates[d];
                const hasCritical = items.some(i => i.days_left <= 1);
                const hasWarning = items.some(i => i.days_left <= 3);
                if (hasCritical) return '#e53e3e';
                if (hasWarning) return '#ecc94b';
                return '#a0aec0';
            });

            const trace = {
                x: sortedDates,
                y: counts,
                type: 'bar',
                marker: { color: colors },
                text: sortedDates.map(d => dates[d].map(i => i.report).join('<br>')),
                hoverinfo: 'text',
                hovertemplate: '<b>%{x}</b><br>%{text}<br>Количество: %{y}<extra></extra>'
            };

            Plotly.newPlot(chartDiv, [trace], {
                height: 400,
                title: 'Количество отчетов по датам дедлайна',
                xaxis: { title: 'Дата дедлайна', tickangle: -45 },
                yaxis: { title: 'Количество отчетов' },
                hovermode: 'closest'
            });
        }

        function applyFilters() {
            const orgFilter = document.getElementById('orgFilter').value;
            const statusFilter = document.getElementById('statusFilter').value;
            const searchText = document.getElementById('searchInput').value.toLowerCase();

            if (!matrixData) return;
            let filteredReports = allReports;

            if (searchText) {
                filteredReports = filteredReports.filter(row => 
                    row.report.toLowerCase().includes(searchText)
                );
            }

            if (orgFilter !== 'all' || statusFilter !== 'all') {
                filteredReports = filteredReports.filter(row => {
                    let match = true;
                    if (orgFilter !== 'all') {
                        const info = row[orgFilter] || {};
                        if (info.status === 'Не требуется') match = false;
                    }
                    if (statusFilter !== 'all' && match) {
                        let hasStatus = false;
                        organizations.forEach(org => {
                            const info = row[org] || {};
                            if (info.status === statusFilter) hasStatus = true;
                        });
                        if (!hasStatus) match = false;
                    }
                    return match;
                });
            }

            const orgHeaders = document.getElementById('orgHeaders');
            const tbody = document.getElementById('matrixBody');
            let displayOrgs = orgFilter !== 'all' ? [orgFilter] : organizations;
            orgHeaders.innerHTML = displayOrgs.map(org => `<th class="org-header">${org}</th>`).join('');

            let html = '';
            let rowNum = 1;
            filteredReports.forEach(row => {
                let numClass = '';
                let hasSuccess = false;
                displayOrgs.forEach(org => {
                    const info = row[org] || {};
                    const status = info.status || 'Не требуется';
                    if (status === 'Подготовлен') hasSuccess = true;
                });
                if (hasSuccess) numClass = 'success';

                let cells = `<td><span class="row-number ${numClass}">${rowNum}</span></td>`;
                cells += `<td><strong>${row.report}</strong></td>`;
                displayOrgs.forEach(org => {
                    const info = row[org] || {};
                    const status = info.status || 'Не требуется';
                    const dateStart = info.date_start_str;
                    const dateEnd = info.date_end_str;
                    const nextPeriod = info.next_period || '';
                    const deadlineStr = info.deadline_str || '';

                    let dateRangeText = '';
                    let nextPeriodText = '';
                    let deadlineText = '';

                    if (dateStart && dateEnd) {
                        dateRangeText = `📅 ${dateStart} - ${dateEnd}`;
                    } else if (dateStart) {
                        dateRangeText = `📅 с ${dateStart}`;
                    } else if (dateEnd) {
                        dateRangeText = `📅 по ${dateEnd}`;
                    }

                    if (nextPeriod) {
                        nextPeriodText = `⏳ Следующий: ${nextPeriod}`;
                    }

                    if (deadlineStr) {
                        deadlineText = `📅 Дедлайн: ${deadlineStr}`;
                    }

                    cells += `<td><div class="cell-content ${getStatusClass(status)}">
                        <div class="status">${status}</div>
                        ${dateRangeText ? `<div class="date-range">${dateRangeText}</div>` : ''}
                        ${deadlineText ? `<div class="deadline">${deadlineText}</div>` : ''}
                        ${nextPeriodText ? `<div class="next-period">${nextPeriodText}</div>` : ''}
                    </div></td>`;
                });
                html += `<tr>${cells}</tr>`;
                rowNum++;
            });
            tbody.innerHTML = html;
        }

        async function refreshData() {
            const res = await fetch('/api/reports?sort=' + currentSort);
            const data = await res.json();
            renderMatrix(data);
        }

        refreshData();
        setInterval(refreshData, 300000);
    </script>
</body>
</html>
"""


# ============================================================
# FLASK МАРШРУТЫ
# ============================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/reports')
def get_reports():
    sort_order = request.args.get('sort', 'desc')
    print(f"🔄 Сортировка: {sort_order}")

    organizations, all_reports_list = load_all_reports()
    matrix = build_matrix(organizations, all_reports_list, sort_order=sort_order)

    upcoming = get_upcoming_deadlines(organizations, all_reports_list, 30)

    return jsonify({
        'organizations': list(organizations.keys()),
        'matrix': matrix,
        'upcoming': upcoming,
        'sort_order': sort_order,
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


def open_browser():
    time.sleep(2)
    webbrowser.open("http://localhost:5000")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("📊 ДАШБОРД ОТЧЕТНОСТИ 1С (CSV)")
    print("=" * 80)
    print(f"\n📂 Папка с CSV: {CSV_FOLDER}")
    print("\n🌐 Откройте: http://localhost:5000")
    print("=" * 80 + "\n")

    if not os.path.exists(CSV_FOLDER):
        print(f"⚠️ Папка не найдена: {CSV_FOLDER}")
        if not os.path.exists(DATA_FOLDER):
            os.makedirs(DATA_FOLDER)
            print(f"📁 Создана локальная папка: {DATA_FOLDER}")

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=5000)