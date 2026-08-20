"""
Модель оптимального выбора культур — Омская область
Прототип на Streamlit
"""

import os
from datetime import date

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Оптимизация посева — Омская область", layout="wide")

# ---------------------------------------------------------------------------
# СПРАВОЧНЫЕ ДАННЫЕ (заглушки — в реальной версии заменяются на API/базу данных)
# ---------------------------------------------------------------------------

# Statische Zonen-Metadaten (Bodenprofile) — ändern sich kaum, bleiben daher
# als Referenztabelle im Code. zone_id entspricht 1:1 den IDs in
# scripts/zones.py, damit beide Teile des Projekts zusammenpassen.
ZONE_STATIC = {
    "north_taiga": {
        "name_ru": "Север (тайга)",
        "почвы_типичные": ["Подзолистая", "Серая лесная"],
    },
    "north_foreststeppe": {
        "name_ru": "Северная лесостепь",
        "почвы_типичные": ["Серая лесная", "Чернозём выщелоченный"],
    },
    "south_foreststeppe": {
        "name_ru": "Южная лесостепь",
        "почвы_типичные": ["Чернозём выщелоченный", "Чернозём обыкновенный"],
    },
    "steppe": {
        "name_ru": "Степь",
        "почвы_типичные": ["Чернозём обыкновенный", "Чернозём южный"],
    },
}

# Fallback-Klimawerte, falls noch keine CSV-Daten vorliegen (z.B. vor dem
# allerersten Workflow-Lauf) — damit die App nie abstürzt, nur mit alten
# Platzhaltern weiterläuft. Werte grob nach Nord-Süd-Gradient geschätzt.
CLIMATE_FALLBACK = {
    "north_taiga": {
        "осадки_мм": 320, "температура_ср": 15.5, "gdd": 1350,
        "trockenperiode": 12, "hitzetage": 2, "vegetationsfenster_tage": 105,
    },
    "north_foreststeppe": {
        "осадки_мм": 300, "температура_ср": 17.0, "gdd": 1500,
        "trockenperiode": 14, "hitzetage": 3, "vegetationsfenster_tage": 120,
    },
    "south_foreststeppe": {
        "осадки_мм": 280, "температура_ср": 18.5, "gdd": 1650,
        "trockenperiode": 15, "hitzetage": 6, "vegetationsfenster_tage": 130,
    },
    "steppe": {
        "осадки_мм": 250, "температура_ср": 19.5, "gdd": 1800,
        "trockenperiode": 17, "hitzetage": 10, "vegetationsfenster_tage": 140,
    },
}

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SHORT_TERM_CSV = os.path.join(REPO_ROOT, "data", "short_term", "weekly_weather.csv")
LONG_TERM_CSV = os.path.join(REPO_ROOT, "data", "long_term", "yearly_climate_trend.csv")

REFERENCE_YEAR_FOR_DOY = 2001  # Nicht-Schaltjahr, nur zur Umrechnung MM-DD -> Tag-des-Jahres


def _md_to_doy(md_str):
    """Rechnet ein 'MM-DD'-Datum (aus fetch_long_term.py) in einen Tag-des-Jahres um."""
    if not md_str or not isinstance(md_str, str) or "-" not in md_str:
        return None
    try:
        month, day = md_str.split("-")
        return date(REFERENCE_YEAR_FOR_DOY, int(month), int(day)).timetuple().tm_yday
    except (ValueError, TypeError):
        return None


@st.cache_data(ttl=3600)
def load_latest_by_zone(csv_path, date_col="abfrage_datum"):
    """Lädt eine CSV und gibt pro zone_id nur die neueste Zeile zurück (als dict)."""
    if not os.path.isfile(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    if df.empty:
        return {}
    df[date_col] = pd.to_datetime(df[date_col])
    latest = df.sort_values(date_col).groupby("zone_id").tail(1)
    return latest.set_index("zone_id").to_dict("index")


def build_zones():
    """Kombiniert statische Metadaten mit den neuesten CSV-Klimadaten (30j-Basis)."""
    long_term = load_latest_by_zone(LONG_TERM_CSV)
    short_term = load_latest_by_zone(SHORT_TERM_CSV)

    zones = {}
    for zone_id, meta in ZONE_STATIC.items():
        zone = dict(meta)
        lt = long_term.get(zone_id)
        fb = CLIMATE_FALLBACK[zone_id]

        if lt is not None and "waermesumme_gdd_mittel_30j" in lt:
            zone["осадки_мм"] = lt["niederschlag_mittel_pro_saison_mm_30j"]
            zone["температура_ср"] = lt["temperatur_mittel_c_30j"]
            zone["_gdd"] = lt["waermesumme_gdd_mittel_30j"]
            zone["_trockenperiode"] = lt["laengste_trockenperiode_tage_mittel_30j"]
            zone["_hitzetage"] = lt["hitzetage_ueber_30c_mittel_30j"]

            spring_doy = _md_to_doy(lt.get("letzter_fruehjahrsfrost_datum_approx_30j"))
            fall_doy = _md_to_doy(lt.get("erster_herbstfrost_datum_approx_30j"))
            if spring_doy is not None and fall_doy is not None:
                zone["_vegetationsfenster_tage"] = fall_doy - spring_doy
            else:
                zone["_vegetationsfenster_tage"] = fb["vegetationsfenster_tage"]
            zone["_letzter_fruehjahrsfrost"] = lt.get("letzter_fruehjahrsfrost_datum_approx_30j", "неизвестно")
            zone["_erster_herbstfrost"] = lt.get("erster_herbstfrost_datum_approx_30j", "неизвестно")

            zone["_osadki_10j"] = lt.get("niederschlag_mittel_pro_saison_mm_10j")
            zone["_temperatura_10j"] = lt.get("temperatur_mittel_c_10j")
            zone["_gdd_10j"] = lt.get("waermesumme_gdd_mittel_10j")
            zone["_datenquelle"] = f"CSV (30J: {lt['zeitraum_30j_von']}–{lt['zeitraum_30j_bis']})"
        else:
            zone["осадки_мм"] = fb["осадки_мм"]
            zone["температура_ср"] = fb["температура_ср"]
            zone["_gdd"] = fb["gdd"]
            zone["_trockenperiode"] = fb["trockenperiode"]
            zone["_hitzetage"] = fb["hitzetage"]
            zone["_vegetationsfenster_tage"] = fb["vegetationsfenster_tage"]
            zone["_letzter_fruehjahrsfrost"] = "неизвестно (заглушка)"
            zone["_erster_herbstfrost"] = "неизвестно (заглушка)"
            zone["_datenquelle"] = "Platzhalter (noch keine CSV-Daten gefunden)"

        st_data = short_term.get(zone_id)
        if st_data is not None:
            zone["_kurzfristig_temperatur"] = st_data["temperatur_mittel_c"]
            zone["_kurzfristig_niederschlag"] = st_data["niederschlag_summe_mm"]
            zone["_kurzfristig_zeitraum"] = f"{st_data['zeitraum_von']} – {st_data['zeitraum_bis']}"

        zones[zone_id] = zone
    return zones


ZONES = build_zones()

# Jede Kultur jetzt zusätzlich mit:
# - необходимая_gdd: ungefähre Wärmesumme (Basis 5°C) bis zur Reife
# - макс_дней_засухи: wie viele aufeinanderfolgende trockene Tage die Kultur toleriert
# - жаростойкость: qualitative Hitzetoleranz (низкая/средняя/высокая)
# Alles Richtwerte aus allgemeiner Agrarliteratur — für den echten Einsatz zu verfeinern.
CROPS = {
    "Яровая пшеница": {
        "мин_дни_роста": 85, "необходимая_gdd": 1500, "макс_дней_засухи": 10, "жаростойкость": "средняя",
        "потребность_вода_мм": 250,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Чернозём южный", "Серая лесная"],
        "ph_мин": 5.5, "ph_макс": 7.0,
        "урожайность_ц_га": 22,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Ячмень": {
        "мин_дни_роста": 75, "необходимая_gdd": 1300, "макс_дней_засухи": 12, "жаростойкость": "высокая",
        "потребность_вода_мм": 220,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Чернозём южный", "Серая лесная", "Подзолистая"],
        "ph_мин": 5.5, "ph_макс": 7.5,
        "урожайность_ц_га": 24,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Овёс": {
        "мин_дни_роста": 80, "необходимая_gdd": 1400, "макс_дней_засухи": 8, "жаростойкость": "низкая",
        "потребность_вода_мм": 260,
        "подходящие_почвы": ["Подзолистая", "Серая лесная", "Чернозём выщелоченный"],
        "ph_мин": 5.0, "ph_макс": 7.0,
        "урожайность_ц_га": 20,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Горох": {
        "мин_дни_роста": 70, "необходимая_gdd": 1200, "макс_дней_засухи": 8, "жаростойкость": "низкая",
        "потребность_вода_мм": 230,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Серая лесная"],
        "ph_мин": 6.0, "ph_макс": 7.5,
        "урожайность_ц_га": 18,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "связывающий",
    },
    "Чечевица": {
        "мин_дни_роста": 75, "необходимая_gdd": 1300, "макс_дней_засухи": 14, "жаростойкость": "средняя",
        "потребность_вода_мм": 200,
        "подходящие_почвы": ["Чернозём обыкновенный", "Чернозём южный"],
        "ph_мин": 6.0, "ph_макс": 8.0,
        "урожайность_ц_га": 12,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "связывающий",
    },
    "Лён масличный": {
        "мин_дни_роста": 80, "необходимая_gdd": 1350, "макс_дней_засухи": 10, "жаростойкость": "средняя",
        "потребность_вода_мм": 210,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Серая лесная"],
        "ph_мин": 5.5, "ph_макс": 7.0,
        "урожайность_ц_га": 9,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "нейтральный",
    },
    "Рапс яровой": {
        "мин_дни_роста": 90, "необходимая_gdd": 1600, "макс_дней_засухи": 8, "жаростойкость": "низкая",
        "потребность_вода_мм": 280,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный"],
        "ph_мин": 5.8, "ph_макс": 7.2,
        "урожайность_ц_га": 14,
        "интервал_севооборота_лет": 4,
        "эффект_азот": "истощающий",
    },
    "Подсолнечник": {
        "мин_дни_роста": 110, "необходимая_gdd": 2000, "макс_дней_засухи": 16, "жаростойкость": "высокая",
        "потребность_вода_мм": 300,
        "подходящие_почвы": ["Чернозём обыкновенный", "Чернозём южный"],
        "ph_мин": 6.0, "ph_макс": 7.5,
        "урожайность_ц_га": 16,
        "интервал_севооборота_лет": 4,
        "эффект_азот": "истощающий",
    },
    "Гречиха": {
        "мин_дни_роста": 75, "необходимая_gdd": 1200, "макс_дней_засухи": 7, "жаростойкость": "низкая",
        "потребность_вода_мм": 240,
        "подходящие_почвы": ["Серая лесная", "Чернозём выщелоченный", "Подзолистая"],
        "ph_мин": 5.0, "ph_макс": 6.5,
        "урожайность_ц_га": 10,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Озимая рожь": {
        "мин_дни_роста": 90, "необходимая_gdd": 1400, "макс_дней_засухи": 12, "жаростойкость": "высокая",
        "потребность_вода_мм": 240,
        "подходящие_почвы": ["Подзолистая", "Серая лесная", "Чернозём выщелоченный"],
        "ph_мин": 5.0, "ph_макс": 7.0,
        "урожайность_ц_га": 20,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
}

SOIL_TYPES = ["Чернозём южный", "Чернозём обыкновенный", "Чернозём выщелоченный", "Серая лесная", "Подзолистая"]

# Пороговые значения "комфортных" хитдней по уровню жаростойкости —
# используются для расчёта штрафа за жару.
HEAT_TOLERANCE_THRESHOLDS = {"низкая": 3, "средняя": 8, "высокая": 15}


# ---------------------------------------------------------------------------
# ЛОГИКА РАСЧЁТА
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "почва": 20,
    "ph": 15,
    "окно": 20,
    "gdd": 15,
    "вода": 15,
    "жара": 5,
    "урожайность": 10,
}


def score_crop(crop_name, crop, zone, soil_type, ph, drainage, weights):
    """
    Возвращает итоговый балл (0-100) пригодности культуры для заданных условий.

    weights: dict с ключами "почва", "ph", "окно", "gdd", "вода", "жара",
    "урожайность" — относительные приоритеты пользователя (не обязательно
    должны давать в сумме 100, функция нормирует сама).

    Каждый под-балл сначала нормируется в диапазон 0-1, затем комбинируется
    с весами пользователя.
    """

    # 1. Соответствие типа почвы (0-1)
    if soil_type in crop["подходящие_почвы"]:
        soil_score = 1.0
    elif soil_type in zone["почвы_типичные"]:
        soil_score = 0.4  # почва не идеальна, но типична для зоны
    else:
        soil_score = 0.0

    # 2. Соответствие pH (0-1)
    if crop["ph_мин"] <= ph <= crop["ph_макс"]:
        ph_score = 1.0
    else:
        distance = min(abs(ph - crop["ph_мин"]), abs(ph - crop["ph_макс"]))
        ph_score = max(0.0, 1 - distance * 0.4)

    # 3. Вегетационное окно (0-1) — из РЕАЛЬНЫХ дат последнего весеннего
    # и первого осеннего заморозка (не просто "безморозные дни" как раньше)
    окно = zone["_vegetationsfenster_tage"]
    if окно >= crop["мин_дни_роста"]:
        запас = окно - crop["мин_дни_роста"]
        window_score = min(1.0, 0.6 + запас * 0.012)
    else:
        дефицит = crop["мин_дни_роста"] - окно
        window_score = max(0.0, 0.6 - дефицит * 0.06)

    # 4. Тепловая сумма / GDD (0-1) — хватает ли зоне тепла для вызревания
    gdd_zone = zone["_gdd"]
    gdd_needed = crop["необходимая_gdd"]
    if gdd_zone >= gdd_needed:
        избыток = gdd_zone - gdd_needed
        gdd_score = min(1.0, 0.6 + избыток * 0.0005)
    else:
        дефицит_gdd = gdd_needed - gdd_zone
        gdd_score = max(0.0, 0.6 - дефицит_gdd * 0.001)

    # 5. Водообеспеченность (0-1) — сумма осадков ПЛЮС риск длинной засухи
    осадки = zone["осадки_мм"]
    потребность = crop["потребность_вода_мм"]
    if drainage == "Застойное (сырое)":
        осадки *= 1.15
    elif drainage == "Хороший дренаж":
        осадки *= 0.9
    разница = abs(осадки - потребность)
    precip_score = max(0.0, 1 - разница / 225)

    засуха_зона = zone["_trockenperiode"]
    засуха_допуск = crop["макс_дней_засухи"]
    if засуха_зона <= засуха_допуск:
        dry_spell_score = 1.0
    else:
        превышение = засуха_зона - засуха_допуск
        dry_spell_score = max(0.0, 1 - превышение * 0.1)

    water_score = (precip_score + dry_spell_score) / 2

    # 6. Тепловой стресс (0-1) — количество жарких дней (>30°C) против
    # жаростойкости культуры
    хитдни_зона = zone["_hitzetage"]
    комфортный_порог = HEAT_TOLERANCE_THRESHOLDS[crop["жаростойкость"]]
    if хитдни_зона <= комфортный_порог:
        heat_score = 1.0
    else:
        превышение_жары = хитдни_зона - комфортный_порог
        heat_score = max(0.0, 1 - превышение_жары * 0.08)

    # 7. Урожайный потенциал (0-1, нормировано по максимуму в таблице)
    max_yield = max(c["урожайность_ц_га"] for c in CROPS.values())
    yield_score = crop["урожайность_ц_га"] / max_yield

    sub_scores = {
        "почва": soil_score,
        "ph": ph_score,
        "окно": window_score,
        "gdd": gdd_score,
        "вода": water_score,
        "жара": heat_score,
        "урожайность": yield_score,
    }

    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0

    score = sum(sub_scores[key] * weights[key] for key in sub_scores) / total_weight
    return round(score * 100, 1)


def apply_rotation_filter(ranked_df, history):
    """Убирает культуры, которые нарушают минимальный интервал севооборота."""
    current_year = max(history.keys()) + 1 if history else None
    filtered = []
    for _, row in ranked_df.iterrows():
        crop_name = row["Культура"]
        gap = CROPS[crop_name]["интервал_севооборота_лет"]
        blocked = False
        for year, planted_crop in history.items():
            if planted_crop == crop_name and current_year is not None:
                if (current_year - year) < gap:
                    blocked = True
                    break
        row["Разрешено севооборотом"] = "Нет" if blocked else "Да"
        filtered.append(row)
    return pd.DataFrame(filtered)


# ---------------------------------------------------------------------------
# ИНТЕРФЕЙС
# ---------------------------------------------------------------------------

st.title("🌾 Модель оптимального выбора культур — Омская область")
st.caption("Прототип: подбор 8–10 лучших культур для конкретного поля с учётом почвы, климата зоны и истории севооборота")

if not os.path.isfile(LONG_TERM_CSV) and not os.path.isfile(SHORT_TERM_CSV):
    st.info(
        "ℹ️ Пока не найдено ни одного файла с данными в `data/`. Используются "
        "заглушки. Запустите workflow'ы в GitHub Actions и сделайте `git pull`, "
        "чтобы подтянуть реальные климатические данные."
    )

st.header("1. Параметры почвы поля")
col1, col2 = st.columns(2)
with col1:
    soil_type = st.selectbox("Тип почвы", SOIL_TYPES)
    ph = st.slider("pH почвы", min_value=4.0, max_value=8.5, value=6.5, step=0.1)
with col2:
    humus = st.number_input("Содержание гумуса (%)", min_value=0.0, max_value=15.0, value=5.0, step=0.1)
    drainage = st.selectbox("Дренаж", ["Хороший дренаж", "Средний дренаж", "Застойное (сырое)"])

st.header("2. Зона расположения поля")
zone_id = st.selectbox(
    "Агроклиматическая зона (полоса ~100 км)",
    list(ZONES.keys()),
    format_func=lambda zid: ZONES[zid]["name_ru"],
)
zone = ZONES[zone_id]
with st.expander("Климатические параметры выбранной зоны"):
    st.write(f"- Вегетационное окно (по датам заморозков): **{zone['_vegetationsfenster_tage']} дней** "
             f"(с {zone['_letzter_fruehjahrsfrost']} по {zone['_erster_herbstfrost']})")
    st.write(f"- Осадки за сезон (30-летняя норма): **{zone['осадки_мм']} мм**")
    st.write(f"- Средняя температура (30-летняя норма): **{zone['температура_ср']} °C**")
    st.write(f"- Тепловая сумма (GDD, база 5°C): **{zone['_gdd']}**")
    st.write(f"- Длиннейшая засуха в среднем: **{zone['_trockenperiode']} дней подряд**")
    st.write(f"- Жарких дней (>30°C) в среднем: **{zone['_hitzetage']}**")
    if "_osadki_10j" in zone and zone["_osadki_10j"] is not None:
        st.write(
            f"- Для сравнения, 10-летний тренд: **{zone['_osadki_10j']} мм** осадков, "
            f"**{zone['_temperatura_10j']} °C**, GDD **{zone['_gdd_10j']}**"
        )
    if "_kurzfristig_zeitraum" in zone:
        st.write(
            f"- Последняя недельная сводка ({zone['_kurzfristig_zeitraum']}): "
            f"**{zone['_kurzfristig_temperatur']} °C**, "
            f"**{zone['_kurzfristig_niederschlag']} мм** осадков"
        )
    st.caption(f"Источник данных: {zone.get('_datenquelle', 'неизвестно')}")

st.header("3. История севооборота на этом поле")
st.caption("Укажите, что сеялось в последние годы (оставьте «Не сеялось», если данных нет)")
history = {}
current_year = 2026
hist_cols = st.columns(4)
for i, offset in enumerate([4, 3, 2, 1]):
    year = current_year - offset
    with hist_cols[i]:
        crop_choice = st.selectbox(
            f"{year} год",
            ["Не сеялось"] + list(CROPS.keys()),
            key=f"hist_{year}",
        )
        if crop_choice != "Не сеялось":
            history[year] = crop_choice

st.header("4. Приоритеты при выборе культуры")
st.caption(
    "Настройте, насколько важен каждый параметр при расчёте балла пригодности. "
    "Абсолютные значения не важны — важно соотношение между ползунками."
)

weight_row1 = st.columns(4)
with weight_row1[0]:
    w_soil = st.slider("Тип почвы", 0, 100, DEFAULT_WEIGHTS["почва"], help="Насколько важно точное совпадение почвы")
with weight_row1[1]:
    w_ph = st.slider("pH почвы", 0, 100, DEFAULT_WEIGHTS["ph"], help="Насколько важен диапазон pH культуры")
with weight_row1[2]:
    w_window = st.slider("Вегетационное окно", 0, 100, DEFAULT_WEIGHTS["окно"], help="Насколько важен запас дней между заморозками")
with weight_row1[3]:
    w_gdd = st.slider("Тепловая сумма (GDD)", 0, 100, DEFAULT_WEIGHTS["gdd"], help="Насколько важно, чтобы зоне хватало тепла для вызревания")

weight_row2 = st.columns(3)
with weight_row2[0]:
    w_water = st.slider("Влагообеспеченность", 0, 100, DEFAULT_WEIGHTS["вода"], help="Осадки + риск длинной засухи")
with weight_row2[1]:
    w_heat = st.slider("Жаростойкость", 0, 100, DEFAULT_WEIGHTS["жара"], help="Насколько важна устойчивость к жарким дням")
with weight_row2[2]:
    w_yield = st.slider("Урожайность", 0, 100, DEFAULT_WEIGHTS["урожайность"], help="Насколько важен потенциальный урожай (ц/га)")

user_weights = {
    "почва": w_soil,
    "ph": w_ph,
    "окно": w_window,
    "gdd": w_gdd,
    "вода": w_water,
    "жара": w_heat,
    "урожайность": w_yield,
}

total_w = sum(user_weights.values())
if total_w == 0:
    st.warning("Все ползунки на нуле — установите хотя бы один приоритет выше 0, чтобы модель могла считать.")
else:
    st.caption(
        "Текущее соотношение: "
        + " · ".join(f"{k}: {round(v / total_w * 100)}%" for k, v in user_weights.items())
    )

st.divider()

if st.button("🚀 Начать моделирование", type="primary", disabled=(total_w == 0)):
    results = []
    for crop_name, crop in CROPS.items():
        s = score_crop(crop_name, crop, zone, soil_type, ph, drainage, user_weights)
        results.append({
            "Культура": crop_name,
            "Балл пригодности": s,
            "Урожайность (ц/га, справочно)": crop["урожайность_ц_га"],
            "Треб. GDD": crop["необходимая_gdd"],
            "Мин. дней роста": crop["мин_дни_роста"],
            "Жаростойкость": crop["жаростойкость"],
            "Эффект на азот": crop["эффект_азот"],
        })

    ranked_df = pd.DataFrame(results).sort_values("Балл пригодности", ascending=False).reset_index(drop=True)
    ranked_df = apply_rotation_filter(ranked_df, history)

    st.header("Результат моделирования")

    allowed_df = ranked_df[ranked_df["Разрешено севооборотом"] == "Да"].head(10)
    blocked_df = ranked_df[ranked_df["Разрешено севооборотом"] == "Нет"]

    st.subheader("✅ Рекомендованные культуры (с учётом севооборота)")
    st.dataframe(allowed_df.drop(columns=["Разрешено севооборотом"]), use_container_width=True, hide_index=True)

    if not blocked_df.empty:
        with st.expander("⛔ Культуры, исключённые из-за севооборота"):
            st.dataframe(blocked_df.drop(columns=["Разрешено севооборотом"]), use_container_width=True, hide_index=True)

    st.caption(
        "Балл пригодности рассчитан на основе соответствия почвы, pH, вегетационного окна "
        "(по реальным датам заморозков), тепловой суммы (GDD), водообеспеченности с учётом "
        "риска засухи, жаростойкости и урожайного потенциала. Это прототип — веса и "
        "справочные значения культур подлежат уточнению."
    )