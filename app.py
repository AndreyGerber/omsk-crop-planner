"""
Модель оптимального выбора культур — Омская область
Прототип на Streamlit
"""

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Оптимизация посева — Омская область", layout="wide")

# ---------------------------------------------------------------------------
# СПРАВОЧНЫЕ ДАННЫЕ (заглушки — в реальной версии заменяются на API/базу данных)
# ---------------------------------------------------------------------------

import os

# Statische Zonen-Metadaten (Bodenprofile, Frosttage) — ändern sich kaum,
# bleiben daher als Referenztabelle im Code. zone_id entspricht 1:1 den IDs
# in scripts/zones.py, damit beide Teile des Projekts zusammenpassen.
ZONE_STATIC = {
    "north_taiga": {
        "name_ru": "Север (тайга)",
        "безморозные_дни": 95,
        "вегетационный_период_дни": 105,
        "почвы_типичные": ["Подзолистая", "Серая лесная"],
    },
    "north_foreststeppe": {
        "name_ru": "Северная лесостепь",
        "безморозные_дни": 110,
        "вегетационный_период_дни": 120,
        "почвы_типичные": ["Серая лесная", "Чернозём выщелоченный"],
    },
    "south_foreststeppe": {
        "name_ru": "Южная лесостепь",
        "безморозные_дни": 120,
        "вегетационный_период_дни": 130,
        "почвы_типичные": ["Чернозём выщелоченный", "Чернозём обыкновенный"],
    },
    "steppe": {
        "name_ru": "Степь",
        "безморозные_дни": 130,
        "вегетационный_период_дни": 140,
        "почвы_типичные": ["Чернозём обыкновенный", "Чернозём южный"],
    },
}

# Fallback-Klimawerte, falls noch keine CSV-Daten vorliegen (z.B. vor dem
# allerersten Workflow-Lauf) — damit die App nie abstürzt, nur mit alten
# Platzhaltern weiterläuft.
CLIMATE_FALLBACK = {
    "north_taiga": {"осадки_мм": 320, "температура_ср": 15.5},
    "north_foreststeppe": {"осадки_мм": 300, "температура_ср": 17.0},
    "south_foreststeppe": {"осадки_мм": 280, "температура_ср": 18.5},
    "steppe": {"осадки_мм": 250, "температура_ср": 19.5},
}

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SHORT_TERM_CSV = os.path.join(REPO_ROOT, "data", "short_term", "weekly_weather.csv")
LONG_TERM_CSV = os.path.join(REPO_ROOT, "data", "long_term", "yearly_climate_trend.csv")


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
        if lt is not None:
            zone["осадки_мм"] = lt["niederschlag_mittel_pro_saison_mm_30j"]
            zone["температура_ср"] = lt["temperatur_mittel_c_30j"]
            zone["_осадки_10j"] = lt["niederschlag_mittel_pro_saison_mm_10j"]
            zone["_температура_10j"] = lt["temperatur_mittel_c_10j"]
            zone["_datenquelle"] = f"CSV (30J: {lt['zeitraum_30j_von']}–{lt['zeitraum_30j_bis']})"
        else:
            zone["осадки_мм"] = CLIMATE_FALLBACK[zone_id]["осадки_мм"]
            zone["температура_ср"] = CLIMATE_FALLBACK[zone_id]["температура_ср"]
            zone["_datenquelle"] = "Platzhalter (noch keine CSV-Daten gefunden)"

        st_data = short_term.get(zone_id)
        if st_data is not None:
            zone["_kurzfristig_temperatur"] = st_data["temperatur_mittel_c"]
            zone["_kurzfristig_niederschlag"] = st_data["niederschlag_summe_mm"]
            zone["_kurzfristig_zeitraum"] = f"{st_data['zeitraum_von']} – {st_data['zeitraum_bis']}"

        zones[zone_id] = zone
    return zones


ZONES = build_zones()

CROPS = {
    "Яровая пшеница": {
        "мин_дни_роста": 85,
        "морозостойкость": "средняя",
        "потребность_вода_мм": 250,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Чернозём южный", "Серая лесная"],
        "ph_мин": 5.5, "ph_макс": 7.0,
        "урожайность_ц_га": 22,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Ячмень": {
        "мин_дни_роста": 75,
        "морозостойкость": "высокая",
        "потребность_вода_мм": 220,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Чернозём южный", "Серая лесная", "Подзолистая"],
        "ph_мин": 5.5, "ph_макс": 7.5,
        "урожайность_ц_га": 24,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Овёс": {
        "мин_дни_роста": 80,
        "морозостойкость": "высокая",
        "потребность_вода_мм": 260,
        "подходящие_почвы": ["Подзолистая", "Серая лесная", "Чернозём выщелоченный"],
        "ph_мин": 5.0, "ph_макс": 7.0,
        "урожайность_ц_га": 20,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Горох": {
        "мин_дни_роста": 70,
        "морозостойкость": "средняя",
        "потребность_вода_мм": 230,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Серая лесная"],
        "ph_мин": 6.0, "ph_макс": 7.5,
        "урожайность_ц_га": 18,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "связывающий",
    },
    "Чечевица": {
        "мин_дни_роста": 75,
        "морозостойкость": "низкая",
        "потребность_вода_мм": 200,
        "подходящие_почвы": ["Чернозём обыкновенный", "Чернозём южный"],
        "ph_мин": 6.0, "ph_макс": 8.0,
        "урожайность_ц_га": 12,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "связывающий",
    },
    "Лён масличный": {
        "мин_дни_роста": 80,
        "морозостойкость": "средняя",
        "потребность_вода_мм": 210,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Серая лесная"],
        "ph_мин": 5.5, "ph_макс": 7.0,
        "урожайность_ц_га": 9,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "нейтральный",
    },
    "Рапс яровой": {
        "мин_дни_роста": 90,
        "морозостойкость": "низкая",
        "потребность_вода_мм": 280,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный"],
        "ph_мин": 5.8, "ph_макс": 7.2,
        "урожайность_ц_га": 14,
        "интервал_севооборота_лет": 4,
        "эффект_азот": "истощающий",
    },
    "Подсолнечник": {
        "мин_дни_роста": 110,
        "морозостойкость": "низкая",
        "потребность_вода_мм": 300,
        "подходящие_почвы": ["Чернозём обыкновенный", "Чернозём южный"],
        "ph_мин": 6.0, "ph_макс": 7.5,
        "урожайность_ц_га": 16,
        "интервал_севооборота_лет": 4,
        "эффект_азот": "истощающий",
    },
    "Гречиха": {
        "мин_дни_роста": 75,
        "морозостойкость": "низкая",
        "потребность_вода_мм": 240,
        "подходящие_почвы": ["Серая лесная", "Чернозём выщелоченный", "Подзолистая"],
        "ph_мин": 5.0, "ph_макс": 6.5,
        "урожайность_ц_га": 10,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Озимая рожь": {
        "мин_дни_роста": 90,
        "морозостойкость": "высокая",
        "потребность_вода_мм": 240,
        "подходящие_почвы": ["Подзолистая", "Серая лесная", "Чернозём выщелоченный"],
        "ph_мин": 5.0, "ph_макс": 7.0,
        "урожайность_ц_га": 20,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
}

SOIL_TYPES = ["Чернозём южный", "Чернозём обыкновенный", "Чернозём выщелоченный", "Серая лесная", "Подзолистая"]


# ---------------------------------------------------------------------------
# ЛОГИКА РАСЧЁТА
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "почва": 25,
    "ph": 20,
    "климат": 25,
    "вода": 15,
    "урожайность": 15,
}


def score_crop(crop_name, crop, zone, soil_type, ph, drainage, weights):
    """
    Возвращает итоговый балл (0-100) пригодности культуры для заданных условий.

    weights: dict с ключами "почва", "ph", "климат", "вода", "урожайность" —
    относительные приоритеты пользователя (не обязательно должны давать в сумме 100,
    функция нормирует сама).

    Каждый под-балл сначала нормируется в диапазон 0-1, затем комбинируется
    с весами пользователя. Так веса можно менять независимо от внутренней логики.
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

    # 3. Вегетационный период / безморозные дни (0-1)
    if zone["безморозные_дни"] >= crop["мин_дни_роста"]:
        запас = zone["безморозные_дни"] - crop["мин_дни_роста"]
        climate_score = min(1.0, 0.6 + запас * 0.012)
    else:
        дефицит = crop["мин_дни_роста"] - zone["безморозные_дни"]
        climate_score = max(0.0, 0.6 - дефицит * 0.06)

    # 4. Водообеспеченность (0-1)
    осадки = zone["осадки_мм"]
    потребность = crop["потребность_вода_мм"]
    if drainage == "Застойное (сырое)":
        осадки *= 1.15
    elif drainage == "Хороший дренаж":
        осадки *= 0.9
    разница = abs(осадки - потребность)
    water_score = max(0.0, 1 - разница / 225)

    # 5. Урожайный потенциал (0-1, нормировано по максимуму в таблице)
    max_yield = max(c["урожайность_ц_га"] for c in CROPS.values())
    yield_score = crop["урожайность_ц_га"] / max_yield

    sub_scores = {
        "почва": soil_score,
        "ph": ph_score,
        "климат": climate_score,
        "вода": water_score,
        "урожайность": yield_score,
    }

    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0

    score = sum(sub_scores[key] * weights[key] for key in sub_scores) / total_weight
    max_score = 1.0

    return round(score / max_score * 100, 1)


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
    st.write(f"- Безморозных дней в среднем: **{zone['безморозные_дни']}**")
    st.write(f"- Вегетационный период: **{zone['вегетационный_период_дни']} дней**")
    st.write(f"- Осадки за сезон (30-летняя норма): **{zone['осадки_мм']} мм**")
    st.write(f"- Средняя температура (30-летняя норма): **{zone['температура_ср']} °C**")
    if "_осадки_10j" in zone:
        st.write(
            f"- Для сравнения, 10-летний тренд: **{zone['_осадки_10j']} мм** осадков, "
            f"**{zone['_температура_10j']} °C**"
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

weight_cols = st.columns(5)
with weight_cols[0]:
    w_soil = st.slider("Тип почвы", 0, 100, DEFAULT_WEIGHTS["почва"], help="Насколько важно точное совпадение почвы")
with weight_cols[1]:
    w_ph = st.slider("pH почвы", 0, 100, DEFAULT_WEIGHTS["ph"], help="Насколько важен диапазон pH культуры")
with weight_cols[2]:
    w_climate = st.slider("Климат / мороз", 0, 100, DEFAULT_WEIGHTS["климат"], help="Насколько важен запас безморозных дней")
with weight_cols[3]:
    w_water = st.slider("Влагообеспеченность", 0, 100, DEFAULT_WEIGHTS["вода"], help="Насколько важно совпадение осадков с потребностью культуры")
with weight_cols[4]:
    w_yield = st.slider("Урожайность", 0, 100, DEFAULT_WEIGHTS["урожайность"], help="Насколько важен потенциальный урожай (ц/га)")

user_weights = {
    "почва": w_soil,
    "ph": w_ph,
    "климат": w_climate,
    "вода": w_water,
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
            "Мин. дней роста": crop["мин_дни_роста"],
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
        "Балл пригодности рассчитан на основе соответствия почвы, pH, климата зоны, "
        "водообеспеченности и урожайного потенциала. Это прототип — веса и справочные "
        "значения культур подлежат уточнению."
    )